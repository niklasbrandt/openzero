"""Board profile builder + Redis cache.

Sections 3, 9, 11 of the artifact. A BoardProfile stores everything the
engine needs to score a phrase against a board:

  - name + description embeddings
  - per-list metadata
  - card-title neighbourhood embeddings
  - last-activity timestamp (for recency boost)
  - privacy classification (auto-classified per Section 9)
  - description authorship marker (for Section 11 HITL gate)

Profiles are built lazily on first need, cached in Redis with a 15-minute
batch refresh + on-mutation invalidation. Embeddings are computed via the
local all-MiniLM-L6-v2 model (no external network calls).

In Epoch 1 this module ships dark — nothing calls into it yet. Epoch 2
wires it into the scoring pipeline.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


# Cache TTLs / refresh windows (Section 3 + 9)
_PROFILE_CACHE_TTL_SECONDS = 15 * 60  # 15 min batch refresh
_PROFILE_CACHE_KEY_PREFIX = "ambient_capture:board_profile:"
_PRIVATE_BOARD_KEY_PREFIX = "ambient_capture:board_private:"
_AUTHORSHIP_KEY = "planka_authorship"  # hash: board_id -> "agent" | "user"


@dataclass
class BoardProfile:
	"""Cached, sanitised, embedded snapshot of a single Planka board."""

	board_id: str
	board_name: str
	board_description: str
	# 384-dim embeddings (lists for JSON-serialisability)
	name_embedding: list[float] = field(default_factory=list)
	description_embedding: list[float] = field(default_factory=list)
	# List metadata: each entry { id, name, name_embedding }
	lists: list[dict] = field(default_factory=list)
	# Card neighbourhood: title embeddings (capped to top N most recent)
	card_title_embeddings: list[list[float]] = field(default_factory=list)
	card_count: int = 0
	# ISO-8601 timestamp of most recent activity (used for recency_boost)
	last_activity_at: Optional[str] = None
	# Auto-classified privacy posture (Section 9)
	privacy: str = "auto"  # "public" | "private" | "auto"
	privacy_reason: str = ""
	# Authorship of the existing board description (Section 11)
	description_author: str = "user"  # "user" | "agent" | "none"
	# Profile metadata
	built_at: float = 0.0  # epoch seconds
	cache_version: int = 1


class BoardProfileBuilder:
	"""Builds and caches BoardProfile records.

	In Epoch 1 only the cache plumbing and key shapes are wired up. The
	actual build (Planka fetch + embedding compute + privacy classification)
	is implemented in Epoch 2 -- placeholder methods raise NotImplementedError
	so any accidental Epoch 1 caller fails loudly.
	"""

	def __init__(self) -> None:
		# Lazy redis import to keep this module side-effect free at import time.
		self._redis = None

	def _get_redis(self):
		if self._redis is None:
			import redis
			from app.config import settings
			self._redis = redis.Redis(
				host=settings.REDIS_HOST,
				port=settings.REDIS_PORT,
				password=settings.REDIS_PASSWORD or None,
				decode_responses=True,
				socket_timeout=2.0,
			)
		return self._redis

	def cache_key(self, board_id: str) -> str:
		return f"{_PROFILE_CACHE_KEY_PREFIX}{board_id}"

	def private_marker_key(self, board_id: str) -> str:
		return f"{_PRIVATE_BOARD_KEY_PREFIX}{board_id}"

	async def get_cached(self, board_id: str) -> Optional[BoardProfile]:
		"""Return cached profile if fresh, else None."""
		try:
			r = self._get_redis()
			raw = r.get(self.cache_key(board_id))
			if not raw:
				return None
			data = json.loads(raw)
			return BoardProfile(**data)
		except Exception as e:
			logger.debug("ambient_capture: profile cache miss for %s: %s", board_id, e)
			return None

	async def cache_profile(self, profile: BoardProfile) -> None:
		"""Persist a built profile to Redis with the standard TTL."""
		try:
			r = self._get_redis()
			r.setex(
				self.cache_key(profile.board_id),
				_PROFILE_CACHE_TTL_SECONDS,
				json.dumps(profile.__dict__),
			)
		except Exception as e:
			logger.warning("ambient_capture: failed to cache profile for %s: %s", profile.board_id, e)

	async def invalidate(self, board_id: str) -> None:
		"""Drop a profile from cache (called on board mutation)."""
		try:
			r = self._get_redis()
			r.delete(self.cache_key(board_id))
		except Exception as e:
			logger.debug("ambient_capture: failed to invalidate %s: %s", board_id, e)

	async def is_private(self, board_id: str) -> bool:
		"""Quick check used by the engine before exposing a board as a candidate."""
		try:
			r = self._get_redis()
			return r.get(self.private_marker_key(board_id)) == "1"
		except Exception:
			return False

	async def mark_private(self, board_id: str, reason: str) -> None:
		try:
			r = self._get_redis()
			r.setex(self.private_marker_key(board_id), _PROFILE_CACHE_TTL_SECONDS, "1")
			# Reason kept short for log/dashboard surfacing
			r.setex(self.private_marker_key(board_id) + ":reason", _PROFILE_CACHE_TTL_SECONDS, reason[:200])
		except Exception as e:
			logger.warning("ambient_capture: failed to mark %s private: %s", board_id, e)

	async def get_authorship(self, board_id: str) -> str:
		"""'user' (default) | 'agent' | 'none'. Checked before auto-overwriting."""
		try:
			r = self._get_redis()
			val = r.hget(_AUTHORSHIP_KEY, board_id)
			return val or "user"
		except Exception:
			return "user"

	async def set_authorship(self, board_id: str, who: str) -> None:
		try:
			r = self._get_redis()
			r.hset(_AUTHORSHIP_KEY, board_id, who)
		except Exception as e:
			logger.debug("ambient_capture: failed to set authorship %s=%s: %s", board_id, who, e)

	# ── Epoch 2 stubs ─────────────────────────────────────────────────────
	async def build_for_board(self, board_id: str) -> BoardProfile:
		"""Full build: Planka fetch -> sanitise -> embed -> classify privacy.

		Implemented in Epoch 2.
		"""
		raise NotImplementedError("BoardProfileBuilder.build_for_board lands in Epoch 2")

	async def refresh_all(self) -> int:
		"""Batch-refresh all operator boards (called by Celery every 15 min)."""
		raise NotImplementedError("BoardProfileBuilder.refresh_all lands in Epoch 2")


_builder: Optional[BoardProfileBuilder] = None


def get_profile_builder() -> BoardProfileBuilder:
	global _builder
	if _builder is None:
		_builder = BoardProfileBuilder()
	return _builder


def now_epoch() -> float:
	return time.time()
