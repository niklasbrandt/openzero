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

	def __init__(self, redis_client=None) -> None:
		# Lazy redis import to keep this module side-effect free at import time.
		# An explicit redis_client may be injected for testing.
		self._redis = redis_client

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

	# ── Epoch 2 implementation ───────────────────────────────────────────────

	async def fetch_all_boards(self) -> list[dict]:
		"""Return a flat list of all Planka boards across all projects.

		Each entry is a minimal dict: { "id": str, "name": str, "createdBy": str, ... }
		suitable for operator-scope filtering. Full profiles are built on demand
		via build_for_board().
		"""
		from app.services.planka_common import get_planka_auth_token
		import httpx
		from app.config import settings

		try:
			token = await get_planka_auth_token()
			headers = {"Authorization": f"Bearer {token}"}
			boards: list[dict] = []
			async with httpx.AsyncClient(
				base_url=settings.PLANKA_BASE_URL,
				headers=headers,
				timeout=15.0,
			) as client:
				resp = await client.get("/api/projects")
				resp.raise_for_status()
				projects = resp.json().get("items", [])
				# Fetch all project details in parallel
				import asyncio
				details = await asyncio.gather(
					*[client.get(f"/api/projects/{p['id']}") for p in projects],
					return_exceptions=True,
				)
				for det in details:
					if isinstance(det, Exception):
						continue
					try:
						det.raise_for_status()
						for b in det.json().get("included", {}).get("boards", []):
							boards.append(b)
					except Exception:
						pass
			return boards
		except Exception as e:
			logger.warning("ambient_capture: fetch_all_boards failed: %s", e)
			return []

	async def build_for_board(self, board_id: str) -> "Optional[BoardProfile]":
		"""Full build: Planka fetch -> sanitise -> embed -> cache.

		Steps:
		  1. Fetch board detail (name, description, updatedAt, lists, cards)
		  2. Sanitise all text with strip_control_chars + clamp_phrase
		  3. Embed name, description, each list name, each card title
		  4. Cache in Redis
		  5. Return the profile
		"""
		from app.services.planka_common import get_planka_auth_token
		from app.services.memory import encode_async
		from app.services.ambient_capture.sanitiser import strip_control_chars, clamp_phrase
		import asyncio
		import httpx
		from app.config import settings

		# Max cards to embed per board (newest first per API order, capped)
		_CARD_EMB_CAP = 50

		try:
			token = await get_planka_auth_token()
			headers = {"Authorization": f"Bearer {token}"}
			async with httpx.AsyncClient(
				base_url=settings.PLANKA_BASE_URL,
				headers=headers,
				timeout=15.0,
			) as client:
				resp = await client.get(
					f"/api/boards/{board_id}",
					params={"included": "lists,cards"},
				)
				resp.raise_for_status()
				data = resp.json()
		except Exception as e:
			logger.warning("ambient_capture: build_for_board fetch failed for %s: %s", board_id, e)
			return None

		item = data.get("item", {})
		included = data.get("included", {})

		board_name = strip_control_chars(item.get("name") or "")[:200]
		board_desc = strip_control_chars(item.get("description") or "")[:500]
		last_activity_at = item.get("updatedAt") or item.get("lastActivityAt")

		raw_lists = included.get("lists", [])
		raw_cards = included.get("cards", [])[:_CARD_EMB_CAP]

		# Build texts we need to embed
		name_text = board_name or board_id
		desc_text = board_desc or board_name

		list_names = [
			strip_control_chars(lst.get("name") or "")[:100]
			for lst in raw_lists
		]
		card_titles = [
			clamp_phrase(strip_control_chars(c.get("name") or ""), max_chars=100)
			for c in raw_cards
			if c.get("name")
		]

		# Embed everything concurrently
		texts_to_embed = [name_text, desc_text] + list_names + card_titles
		try:
			embeddings = await asyncio.gather(
				*[encode_async(t) for t in texts_to_embed],
				return_exceptions=True,
			)
		except Exception as e:
			logger.warning("ambient_capture: embedding failed for board %s: %s", board_id, e)
			return None

		def safe_emb(idx: int) -> list[float]:
			v = embeddings[idx]
			return v if isinstance(v, list) else []

		name_emb = safe_emb(0)
		desc_emb = safe_emb(1)
		base = 2

		list_structs: list[dict] = []
		for i, lst in enumerate(raw_lists):
			emb = safe_emb(base + i)
			list_structs.append({
				"id": lst.get("id", ""),
				"name": list_names[i] if i < len(list_names) else "",
				"name_embedding": emb,
			})
		base += len(raw_lists)

		card_embs: list[list[float]] = []
		for i in range(len(card_titles)):
			emb = safe_emb(base + i)
			card_embs.append(emb)

		profile = BoardProfile(
			board_id=board_id,
			board_name=board_name,
			board_description=board_desc,
			name_embedding=name_emb,
			description_embedding=desc_emb,
			lists=list_structs,
			card_title_embeddings=card_embs,
			card_count=len(raw_cards),
			last_activity_at=last_activity_at,
			privacy="auto",
			privacy_reason="",
			description_author=await self.get_authorship(board_id),
			built_at=time.time(),
		)

		await self.cache_profile(profile)
		return profile

	async def refresh_all(self) -> int:
		"""Batch-refresh all operator boards. Called by background task.

		Returns the count of successfully refreshed profiles.
		"""
		from app.services.ambient_capture.operator_scope import filter_operator_boards
		boards = await self.fetch_all_boards()
		boards = filter_operator_boards(boards)
		refreshed = 0
		for b in boards:
			board_id = b.get("id", "")
			if not board_id:
				continue
			try:
				await self.invalidate(board_id)
				p = await self.build_for_board(board_id)
				if p:
					refreshed += 1
			except Exception as e:
				logger.warning("ambient_capture: refresh_all skipped board %s: %s", board_id, e)
		logger.info("ambient_capture: refresh_all completed — %d boards refreshed", refreshed)
		return refreshed


_builder: Optional[BoardProfileBuilder] = None


def get_profile_builder() -> BoardProfileBuilder:
	global _builder
	if _builder is None:
		_builder = BoardProfileBuilder()
	return _builder


def now_epoch() -> float:
	return time.time()
