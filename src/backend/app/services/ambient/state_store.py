"""Redis-backed circular snapshot buffer.

Key format: oz:ambient:{source_id}:snapshots  (Redis list, newest at head)
Retention:  last N snapshots per source (default 24)
Safety TTL: 2 hours

See docs/artifacts/ambient_intelligence.md §4.
"""

from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)

_KEY_PREFIX = "oz:ambient:"
_SNAPSHOTS_SUFFIX = ":snapshots"
_DEFAULT_MAX = 24
_SAFETY_TTL_S = 7200  # 2 hours


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


class StateStore:
	"""Thread-safe circular buffer backed by Redis.

	Uses LPUSH + LTRIM to keep the N most-recent snapshots per source, with
	a safety-net expiry so orphaned keys evict themselves.
	"""

	def __init__(self, max_snapshots: int = _DEFAULT_MAX) -> None:
		self.max = max_snapshots

	def push(self, source_id: str, snapshot: dict) -> None:
		key = f"{_KEY_PREFIX}{source_id}{_SNAPSHOTS_SUFFIX}"
		try:
			r = _get_redis()
			pipe = r.pipeline()
			pipe.lpush(key, json.dumps(snapshot, default=str))
			pipe.ltrim(key, 0, self.max - 1)
			pipe.expire(key, _SAFETY_TTL_S)
			pipe.execute()
		except Exception as exc:
			logger.warning("StateStore.push failed for %s: %s", source_id, exc)

	def latest(self, source_id: str, n: int = 2) -> list[dict]:
		"""Return the n most-recent snapshots (index 0 = newest)."""
		key = f"{_KEY_PREFIX}{source_id}{_SNAPSHOTS_SUFFIX}"
		try:
			r = _get_redis()
			raw = r.lrange(key, 0, n - 1)
			return [json.loads(item) for item in raw]
		except Exception as exc:
			logger.warning("StateStore.latest failed for %s: %s", source_id, exc)
			return []
