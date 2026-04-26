"""Tier A+B+C composite scoring for the ambient capture engine.

Section 3 of the artifact. Pure functions — no IO. All caller state
(phrase embeddings, board profile data) is passed in; this module has
no side-effects and no external dependencies beyond the standard library.

The scoring formula:
    final_score = (
        0.20 * board_name_similarity
        + 0.15 * board_description_similarity
        + 0.25 * card_neighbourhood_similarity
        + 0.15 * list_fit_score
        + 0.10 * memory_history_match
        + 0.10 * recency_boost
        + 0.05 * active_thread_bonus
    )

Each component is bounded [0, 1]. The recency safeguard prevents recency
alone from pushing a board into the EXECUTE lane.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Optional


# ── Low-level vector maths ────────────────────────────────────────────────────

def cosine_similarity(a: list[float], b: list[float]) -> float:
	"""Cosine similarity between two equal-length embedding vectors."""
	if not a or not b or len(a) != len(b):
		return 0.0
	dot = sum(x * y for x, y in zip(a, b))
	mag_a = math.sqrt(sum(x * x for x in a))
	mag_b = math.sqrt(sum(y * y for y in b))
	if mag_a == 0.0 or mag_b == 0.0:
		return 0.0
	return max(-1.0, min(1.0, dot / (mag_a * mag_b)))


# ── Component scorers ─────────────────────────────────────────────────────────

def card_neighbourhood_similarity(
	phrase_emb: list[float],
	card_embs: list[list[float]],
	top_k: int = 5,
) -> float:
	"""Mean cosine similarity of phrase against top-k nearest card embeddings.

	Tier B signal. If fewer than top_k cards are available, uses all of them.
	"""
	if not card_embs or not phrase_emb:
		return 0.0
	sims = sorted(
		(cosine_similarity(phrase_emb, c) for c in card_embs if c),
		reverse=True,
	)
	top = sims[:top_k]
	return sum(top) / len(top) if top else 0.0


def list_fit_score(
	phrase_emb: list[float],
	lists: list[dict],
) -> float:
	"""Max cosine similarity of phrase against list name embeddings.

	Tier A signal. Each `list` dict should have a `name_embedding` key.
	"""
	if not lists or not phrase_emb:
		return 0.0
	sims = [
		cosine_similarity(phrase_emb, lst.get("name_embedding") or [])
		for lst in lists
		if lst.get("name_embedding")
	]
	return max(sims) if sims else 0.0


def recency_boost(last_activity_iso: Optional[str]) -> float:
	"""Section 3 recency decay function.

	Returns a small additive boost representing how recently the board was
	active. Values: 0.15 (< 24h) -> 0.10 (< 72h) -> 0.05 (< 7d) -> 0.02 (< 14d) -> 0.0
	"""
	if not last_activity_iso:
		return 0.0
	try:
		ts = datetime.fromisoformat(last_activity_iso.rstrip("Z"))
		if ts.tzinfo is None:
			ts = ts.replace(tzinfo=timezone.utc)
		delta_hours = (datetime.now(timezone.utc) - ts).total_seconds() / 3600
		if delta_hours < 24:
			return 0.15
		if delta_hours < 72:
			return 0.10
		if delta_hours < 168:
			return 0.05
		if delta_hours < 336:
			return 0.02
		return 0.0
	except Exception:
		return 0.0


def active_thread_bonus(
	board_id: str,
	session_recent_boards: Optional[set[str]] = None,
	board_in_today_briefing: bool = False,
	any_card_modified_in_24h: bool = False,
) -> float:
	"""Section 3 active thread bonus, hard-capped at 0.05."""
	raw = (
		(0.03 if any_card_modified_in_24h else 0)
		+ (0.02 if board_in_today_briefing else 0)
		+ (0.05 if session_recent_boards and board_id in session_recent_boards else 0)
	)
	return min(0.05, raw)


# ── Top-level composite ───────────────────────────────────────────────────────

def composite_score(
	phrase_emb: list[float],
	board_name_emb: list[float],
	board_desc_emb: list[float],
	card_embs: list[list[float]],
	list_structs: list[dict],
	memory_history_match: float = 0.0,
	last_activity_iso: Optional[str] = None,
	board_id: str = "",
	session_recent_boards: Optional[set[str]] = None,
	board_in_briefing: bool = False,
	card_modified_24h: bool = False,
) -> float:
	"""Section 3 composite scoring formula, result bounded [0, 1]."""
	board_name_sim = cosine_similarity(phrase_emb, board_name_emb)
	board_desc_sim = cosine_similarity(phrase_emb, board_desc_emb)
	card_nb_sim = card_neighbourhood_similarity(phrase_emb, card_embs)
	l_fit = list_fit_score(phrase_emb, list_structs)
	recency = recency_boost(last_activity_iso)
	thread_b = active_thread_bonus(
		board_id,
		session_recent_boards=session_recent_boards,
		board_in_today_briefing=board_in_briefing,
		any_card_modified_in_24h=card_modified_24h,
	)
	score = (
		0.20 * board_name_sim
		+ 0.15 * board_desc_sim
		+ 0.25 * card_nb_sim
		+ 0.15 * l_fit
		+ 0.10 * max(0.0, min(1.0, memory_history_match))
		+ 0.10 * recency
		+ 0.05 * thread_b
	)
	return max(0.0, min(1.0, score))


def apply_recency_safeguard(
	score_with: float,
	score_without: float,
	silent_floor: float,
) -> float:
	"""Prevent recency alone from pushing a board into the EXECUTE lane.

	If recency is what pushed the score from ASK to EXECUTE range, clamp back
	to just below silent_floor so the engine asks instead of executing silently.
	"""
	if score_with >= silent_floor and score_without < silent_floor:
		return silent_floor - 0.001
	return score_with


# ── Anti-poisoning: lesson-derived score boost (Section 10, C2) ───────────────

#: Per-artifact Section 10: total lesson-derived adjustment is capped so
#: lessons inform, never override, structural signals.
LESSON_BOOST_CEILING = 0.20


def apply_lesson_boost(base_score: float, lessons: list[dict]) -> float:
	"""Apply routing-lesson adjustments to a composite score, respecting the ceiling.

	Each lesson dict must have:
	  - ``similarity``: float in [0, 1], cosine sim of stored embedding to the phrase
	  - ``signal_weight``: float, already computed from user_action (Section 10)

	The combined adjustment is clamped to ``+/- LESSON_BOOST_CEILING`` before
	being added to ``base_score``. The final score is bounded to [0, 1].

	Anti-poisoning guarantee (C2): regardless of how many near-identical lessons
	an adversary writes, the total influence on the score is bounded by this cap.
	"""
	if not lessons:
		return max(0.0, min(1.0, base_score))
	adjustment = sum(
		max(0.0, min(1.0, float(l.get("similarity", 0))))
		* float(l.get("signal_weight", 0))
		for l in lessons
	)
	# Clamp to ceiling in both directions
	adjustment = max(-LESSON_BOOST_CEILING, min(LESSON_BOOST_CEILING, adjustment))
	return max(0.0, min(1.0, base_score + adjustment))


def stage_lesson_for_storage(phrase: str) -> str:
	"""Return a sanitised copy of *phrase* suitable for embedding before storage.

	Engine action tags are stripped (C2 / H4) and control chars removed so
	the stored embedding represents the genuine semantic content of the phrase,
	not an attacker-controlled injection payload.
	"""
	from app.services.ambient_capture.sanitiser import (
		clamp_phrase,
		strip_engine_action_tags,
	)
	return strip_engine_action_tags(clamp_phrase(phrase))
