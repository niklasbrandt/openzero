"""Global per-request response budget and local-LLM circuit breaker.

ResponseBudget is injected at the start of route_message_stream and
propagated via a ContextVar so every downstream coroutine can:
  - Check how much time remains
  - Skip optional steps when budget is low

Circuit breaker state is stored in Redis (key: `circuit:llm_local:open`).
After 3 consecutive local-LLM timeouts in 5 minutes, the local model is
marked unavailable for CIRCUIT_OPEN_TTL_S seconds. All calls route to cloud.
"""
from __future__ import annotations

import logging
import time
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# Hard ceiling for any response (seconds). After this the user gets a cancel message.
RESPONSE_CEILING_S: float = 20.0

# When remaining budget drops below this, skip ALL optional enrichments.
BUDGET_SKIP_OPTIONAL_S: float = 1.5

# Circuit breaker: open after N consecutive local-LLM timeouts within WINDOW seconds.
CB_FAILURE_THRESHOLD: int = 3
CB_WINDOW_S: int = 300		# 5 min
CIRCUIT_OPEN_TTL_S: int = 600	# 10 min


@dataclass
class ResponseBudget:
	"""Tracks elapsed + remaining time for a single response cycle."""
	ceiling: float = RESPONSE_CEILING_S
	_start: float = field(default_factory=time.monotonic, init=False, repr=False)

	def elapsed(self) -> float:
		return time.monotonic() - self._start

	def remaining(self) -> float:
		return max(0.0, self.ceiling - self.elapsed())

	def skip_optional(self) -> bool:
		"""True when < BUDGET_SKIP_OPTIONAL_S remain — skip enrichments."""
		return self.remaining() < BUDGET_SKIP_OPTIONAL_S

	def timeout_for(self, requested: float) -> float:
		"""Return min(requested, remaining), floor 0.1s."""
		return max(0.1, min(requested, self.remaining()))


# ContextVar — set at the top of route_message_stream, read inside any coroutine.
budget_ctx: ContextVar[Optional[ResponseBudget]] = ContextVar("response_budget", default=None)


def get_budget() -> Optional[ResponseBudget]:
	return budget_ctx.get()


# ─── Circuit Breaker ──────────────────────────────────────────────────────────

async def is_local_llm_open() -> bool:
	"""Return True when circuit is open (local LLM should be skipped)."""
	try:
		from app.config import settings
		import redis.asyncio as aioredis
		r = aioredis.from_url(
			f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}",
			password=settings.REDIS_PASSWORD or None,
			decode_responses=True,
		)
		async with r:
			val = await r.get("circuit:llm_local:open")
			return val == "1"
	except Exception as _e:
		logger.debug("Circuit breaker Redis check failed: %s — defaulting closed", _e)
		return False


async def record_local_llm_timeout() -> None:
	"""Record a local-LLM timeout. Opens the circuit after CB_FAILURE_THRESHOLD within CB_WINDOW_S."""
	try:
		from app.config import settings
		import redis.asyncio as aioredis
		r = aioredis.from_url(
			f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}",
			password=settings.REDIS_PASSWORD or None,
			decode_responses=True,
		)
		async with r:
			pipe = r.pipeline()
			key = "circuit:llm_local:failures"
			pipe.incr(key)
			pipe.expire(key, CB_WINDOW_S)
			results = await pipe.execute()
			count = results[0]
			if count >= CB_FAILURE_THRESHOLD:
				await r.set("circuit:llm_local:open", "1", ex=CIRCUIT_OPEN_TTL_S)
				logger.warning(
					"Circuit breaker OPENED for local LLM after %d timeouts in %ds window. "
					"All traffic routed to cloud for %ds.",
					count, CB_WINDOW_S, CIRCUIT_OPEN_TTL_S,
				)
	except Exception as _e:
		logger.debug("Circuit breaker record_timeout failed: %s", _e)


async def reset_local_llm_circuit() -> None:
	"""Reset the circuit breaker (call after a successful local LLM response)."""
	try:
		from app.config import settings
		import redis.asyncio as aioredis
		r = aioredis.from_url(
			f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}",
			password=settings.REDIS_PASSWORD or None,
			decode_responses=True,
		)
		async with r:
			await r.delete("circuit:llm_local:failures", "circuit:llm_local:open")
	except Exception as _e:
		logger.debug("Circuit breaker reset failed: %s", _e)
