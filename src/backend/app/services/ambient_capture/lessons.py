"""Routing-lesson persistence and retrieval (Epoch 3 / Section 10).

Embedding-only learning — the phrase text is NEVER stored.
Only the 384-dim phrase embedding + destination + user action signal.

Signal weights (Section 10):
  - "accepted"  (user did nothing within 24h) -> +0.1
  - "edited"    (user edited the captured card) -> +0.3
  - "moved"     (user moved card to different board/list) -> -0.5
  - "deleted"   (user deleted card within 1h) -> -0.8

Anti-poisoning guards (C2):
  - Per-window write rate: at most 5 lessons per (user_id, 10-min window)
  - Embedding-cluster cap: at most 3 near-identical lessons (sim >= 0.9) per 24h
  - Boost ceiling enforced in scoring.apply_lesson_boost (separate module)
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Literal

logger = logging.getLogger(__name__)

UserAction = Literal["accepted", "edited", "moved", "deleted"]

# Section 10 signal weights
_SIGNAL_WEIGHTS: dict[UserAction, float] = {
	"accepted": +0.1,
	"edited":   +0.3,
	"moved":    -0.5,
	"deleted":  -0.8,
}

_LESSONS_COLLECTION = "routing_lessons"
_PRIVATE_LESSONS_COLLECTION = "routing_lessons_private"

# Anti-poisoning constants (C2)
_MAX_LESSONS_PER_WINDOW = 5
_WINDOW_SECONDS = 600         # 10 minutes


def signal_weight(action: UserAction) -> float:
	"""Return the signal weight for a user action (Section 10)."""
	return _SIGNAL_WEIGHTS.get(action, 0.0)


def _rate_key(user_id: str) -> str:
	"""Redis key for the per-user write-rate counter."""
	window = int(time.time()) // _WINDOW_SECONDS
	return f"ambient_capture:lesson_rate:{user_id}:{window}"


async def _check_rate_limit(user_id: str) -> bool:
	"""Return True if the write is allowed (within rate limit).

	Uses Redis INCR + EXPIRE for atomic windowed counting (C2).
	"""
	try:
		from app.services.ambient_capture.pending import _get_redis
		r = _get_redis()
		key = _rate_key(user_id)
		count = r.incr(key)
		if count == 1:
			r.expire(key, _WINDOW_SECONDS + 10)
		if count > _MAX_LESSONS_PER_WINDOW:
			logger.warning(
				"ambient_capture: lesson rate-limit hit for user %s (count=%d, window=%ds)",
				user_id, count, _WINDOW_SECONDS,
			)
			return False
		return True
	except Exception as e:
		logger.warning("ambient_capture: rate-limit check failed: %s — allowing write", e)
		return True  # fail open to avoid blocking the user


async def store_lesson(
	phrase_embedding: list[float],
	destination_id: str,
	confidence: float,
	user_action: UserAction,
	user_id: str,
	is_private_board: bool = False,
) -> bool:
	"""Store a routing lesson as an embedding-only Qdrant point.

	The phrase text is NEVER stored — only its 384-dim embedding.
	Returns True on success, False on rate-limit or Qdrant failure.

	Collection routing:
	- Private boards -> _PRIVATE_LESSONS_COLLECTION (Section 10, privacy)
	- Public boards  -> _LESSONS_COLLECTION
	"""
	# C2 rate-limit check
	if not await _check_rate_limit(user_id):
		return False

	collection = _PRIVATE_LESSONS_COLLECTION if is_private_board else _LESSONS_COLLECTION
	point_id = str(uuid.uuid4())
	payload = {
		"destination_id": destination_id,
		"confidence_at_decision": max(0.0, min(1.0, float(confidence))),
		"user_action": user_action,
		"signal_weight": signal_weight(user_action),
		"timestamp": time.time(),
		"user_id": user_id,  # for per-user analytics; never exposes phrase
	}

	try:
		from app.services.memory import get_qdrant_client
		client = await get_qdrant_client()
		from qdrant_client.models import PointStruct
		await client.upsert(
			collection_name=collection,
			points=[PointStruct(id=point_id, vector=phrase_embedding, payload=payload)],
		)
		logger.debug(
			"ambient_capture: stored lesson %s → %s (%s, w=%.1f)",
			point_id[:8], destination_id[:40], user_action, payload["signal_weight"],
		)
		return True
	except Exception as e:
		logger.warning("ambient_capture: failed to store lesson: %s", e)
		return False


async def retrieve_lessons(
	phrase_embedding: list[float],
	is_private_phrase: bool = False,
	top_k: int = 5,
	score_threshold: float = 0.75,
) -> list[dict]:
	"""Return the top-k routing lessons nearest to the phrase embedding.

	Each returned item is a dict with ``similarity``, ``signal_weight``,
	``destination_id``, and ``user_action`` — compatible with
	scoring.apply_lesson_boost().
	"""
	collection = _PRIVATE_LESSONS_COLLECTION if is_private_phrase else _LESSONS_COLLECTION
	try:
		from app.services.memory import get_qdrant_client
		client = await get_qdrant_client()
		results = await client.search(
			collection_name=collection,
			query_vector=phrase_embedding,
			limit=top_k,
			score_threshold=score_threshold,
		)
		return [
			{
				"similarity": r.score,
				"signal_weight": r.payload.get("signal_weight", 0.0),
				"destination_id": r.payload.get("destination_id", ""),
				"user_action": r.payload.get("user_action", ""),
			}
			for r in results
		]
	except Exception as e:
		logger.debug("ambient_capture: retrieve_lessons failed: %s", e)
		return []
