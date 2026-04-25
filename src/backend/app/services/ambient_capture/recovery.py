"""Failure recovery, retry, and per-plugin circuit breaker.

Section 6 + Section 17.5 (M5). Hard caps:
  - 3 retries per ActionExecution
  - exponential backoff (200ms, 800ms, 3.2s)
  - 5 failures in 60s -> plugin disabled for 5 min
  - Tier D LLM is NOT re-invoked on retry (decision reused)
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Literal, Optional

logger = logging.getLogger(__name__)


MAX_RETRIES = 3
BACKOFF_SCHEDULE_SECONDS = (0.2, 0.8, 3.2)
BREAKER_FAILURE_WINDOW_SECONDS = 60.0
BREAKER_FAILURE_THRESHOLD = 5
BREAKER_OPEN_DURATION_SECONDS = 300.0


FinalStatus = Literal["success", "retry_pending", "failed_reported"]


@dataclass
class Attempt:
	attempt_number: int
	started_at: float
	finished_at: float
	error: Optional[str] = None
	resource_id: Optional[str] = None


@dataclass
class ActionExecution:
	intended_action: str
	attempts: list[Attempt] = field(default_factory=list)
	final_status: FinalStatus = "retry_pending"
	final_error_human: str = ""

	@property
	def succeeded(self) -> bool:
		return self.final_status == "success"


class CircuitBreaker:
	"""Per-plugin failure tracker. Trips after N failures in a window."""

	def __init__(self, name: str = "") -> None:
		self.name = name
		self._failures: deque[float] = deque()
		self._opened_at: Optional[float] = None

	def record_success(self) -> None:
		self._failures.clear()
		self._opened_at = None

	def record_failure(self) -> None:
		now = time.time()
		self._failures.append(now)
		# Drop entries outside the window
		cutoff = now - BREAKER_FAILURE_WINDOW_SECONDS
		while self._failures and self._failures[0] < cutoff:
			self._failures.popleft()
		if len(self._failures) >= BREAKER_FAILURE_THRESHOLD:
			if self._opened_at is None:
				self._opened_at = now
				logger.warning(
					"ambient_capture: circuit breaker opened for plugin '%s' after %d failures",
					self.name, len(self._failures),
				)

	def is_open(self) -> bool:
		"""True if the breaker is currently tripped (skip the plugin)."""
		if self._opened_at is None:
			return False
		if time.time() - self._opened_at >= BREAKER_OPEN_DURATION_SECONDS:
			# Half-open: clear and let the next call try
			self._opened_at = None
			self._failures.clear()
			logger.info("ambient_capture: circuit breaker half-open for plugin '%s'", self.name)
			return False
		return True


_breakers: dict[str, CircuitBreaker] = {}


def get_breaker(plugin_name: str) -> CircuitBreaker:
	if plugin_name not in _breakers:
		_breakers[plugin_name] = CircuitBreaker(plugin_name)
	return _breakers[plugin_name]


async def execute_with_recovery(
	intended_action: str,
	plugin_name: str,
	executor: Callable[[], Awaitable[tuple[bool, str, Optional[str]]]],
) -> ActionExecution:
	"""Run an executor with retry + breaker semantics.

	`executor` returns `(success, message, resource_id_or_None)`. On failure,
	`message` is the human-readable error for the user.

	Tier D / LLM tiebreakers MUST NOT be re-invoked here -- the decision
	passed to `executor` is already final.
	"""
	exec_record = ActionExecution(intended_action=intended_action)
	breaker = get_breaker(plugin_name)

	if breaker.is_open():
		exec_record.final_status = "failed_reported"
		exec_record.final_error_human = f"Plugin '{plugin_name}' temporarily disabled (too many recent failures)"
		return exec_record

	for attempt_idx in range(MAX_RETRIES):
		started = time.time()
		try:
			success, message, resource_id = await executor()
			finished = time.time()
			exec_record.attempts.append(
				Attempt(
					attempt_number=attempt_idx + 1,
					started_at=started,
					finished_at=finished,
					error=None if success else message,
					resource_id=resource_id,
				)
			)
			if success:
				breaker.record_success()
				exec_record.final_status = "success"
				return exec_record
			# Soft failure -> retry
		except Exception as e:
			finished = time.time()
			exec_record.attempts.append(
				Attempt(
					attempt_number=attempt_idx + 1,
					started_at=started,
					finished_at=finished,
					error=str(e),
				)
			)
		# Backoff before next retry (skip after final attempt)
		if attempt_idx < MAX_RETRIES - 1:
			delay = BACKOFF_SCHEDULE_SECONDS[attempt_idx]
			await asyncio.sleep(delay)

	# All attempts exhausted
	breaker.record_failure()
	exec_record.final_status = "failed_reported"
	last = exec_record.attempts[-1] if exec_record.attempts else None
	exec_record.final_error_human = (last.error or "unknown error") if last else "no attempts recorded"
	return exec_record
