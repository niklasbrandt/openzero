"""Unified channel-scoped pending capture queue.

Section 5 of the artifact + C3 (confirmation hijack) + H3 (cross-channel
confused deputy) mitigations.

Key shape: pending_capture:{user_id}:{channel}
TTL: configurable in AgentsWidget (default 90s)
Hijack guard: monotonic sequence + invalidation on new ambient message

The unified queue replaces the ad-hoc per-channel pending state. The existing
SENSITIVE_ACTIONS HITL queue is also funnelled through this shape in Epoch 2
so there is one Redis namespace and one dashboard surface.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


_PENDING_PREFIX = "ambient_capture:pending:"
_DEFAULT_TTL_SECONDS = 90
_SEQUENCE_KEY_PREFIX = "ambient_capture:pending_seq:"


def pending_key(user_id: str, channel: str) -> str:
	"""Channel-scoped Redis key (H3)."""
	return f"{_PENDING_PREFIX}{user_id}:{channel}"


@dataclass
class PendingCapture:
	"""A capture awaiting user confirmation."""

	pending_id: str
	user_id: str
	channel: str  # "telegram" | "whatsapp" | "dashboard"
	plugin_name: str
	phrase: str
	destination_id: str
	destination_label: str
	confidence: float
	# Monotonic sequence for hijack protection (C3)
	sequence: int = 0
	# When this entry was created (epoch seconds)
	created_at: float = field(default_factory=time.time)
	# Optional alternative candidates surfaced in the ASK prompt
	alternatives: list[dict] = field(default_factory=list)


def _get_redis():
	import redis
	from app.config import settings
	return redis.Redis(
		host=settings.REDIS_HOST,
		port=settings.REDIS_PORT,
		password=settings.REDIS_PASSWORD or None,
		decode_responses=True,
		socket_timeout=2.0,
	)


def _next_sequence(user_id: str, channel: str) -> int:
	"""Atomic monotonic counter per (user_id, channel)."""
	try:
		r = _get_redis()
		return int(r.incr(f"{_SEQUENCE_KEY_PREFIX}{user_id}:{channel}"))
	except Exception as e:
		logger.warning("ambient_capture: failed to increment pending sequence: %s", e)
		# Fall back to time-based (less safe but never blocks the user)
		return int(time.time() * 1000)


def _ttl_seconds() -> int:
	from app.config import settings
	val = getattr(settings, "AMBIENT_PENDING_TTL_SECONDS", _DEFAULT_TTL_SECONDS)
	try:
		return max(10, min(600, int(val)))
	except Exception:
		return _DEFAULT_TTL_SECONDS


async def store_pending(
	user_id: str,
	channel: str,
	plugin_name: str,
	phrase: str,
	destination_id: str,
	destination_label: str,
	confidence: float,
	alternatives: Optional[list[dict]] = None,
) -> PendingCapture:
	"""Create and store a pending capture, replacing any existing entry on the
	same (user, channel) key. Returns the created PendingCapture."""
	pending = PendingCapture(
		pending_id=str(uuid.uuid4()),
		user_id=user_id,
		channel=channel,
		plugin_name=plugin_name,
		phrase=phrase,
		destination_id=destination_id,
		destination_label=destination_label,
		confidence=confidence,
		sequence=_next_sequence(user_id, channel),
		alternatives=alternatives or [],
	)
	try:
		r = _get_redis()
		r.setex(pending_key(user_id, channel), _ttl_seconds(), json.dumps(asdict(pending)))
	except Exception as e:
		logger.warning("ambient_capture: failed to store pending capture: %s", e)
	return pending


async def consume_pending(user_id: str, channel: str) -> Optional[PendingCapture]:
	"""Atomically read + delete the pending entry for this (user, channel).

	Returns None if no entry, or if the entry has expired.
	"""
	try:
		r = _get_redis()
		key = pending_key(user_id, channel)
		# GETDEL is single-roundtrip atomic on Redis 6.2+; fall back to pipeline.
		try:
			raw = r.execute_command("GETDEL", key)
		except Exception:
			pipe = r.pipeline()
			pipe.get(key)
			pipe.delete(key)
			raw, _ = pipe.execute()
		if not raw:
			return None
		data = json.loads(raw)
		return PendingCapture(**data)
	except Exception as e:
		logger.warning("ambient_capture: failed to consume pending: %s", e)
		return None


async def peek_pending(user_id: str, channel: str) -> Optional[PendingCapture]:
	"""Read without consuming. Used by the engine to decide whether a new
	ambient message should invalidate an existing pending entry (C3)."""
	try:
		r = _get_redis()
		raw = r.get(pending_key(user_id, channel))
		if not raw:
			return None
		return PendingCapture(**json.loads(raw))
	except Exception as e:
		logger.debug("ambient_capture: peek_pending failed: %s", e)
		return None


async def invalidate_pending(user_id: str, channel: str) -> bool:
	"""Drop a pending entry without consuming it (used when a fresh ambient
	message arrives during the window — agent re-asks rather than letting
	an arbitrary later reply confirm a stale capture)."""
	try:
		r = _get_redis()
		return bool(r.delete(pending_key(user_id, channel)))
	except Exception as e:
		logger.warning("ambient_capture: failed to invalidate pending: %s", e)
		return False
