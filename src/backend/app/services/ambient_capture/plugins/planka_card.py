"""PlankaCardPlugin — creates a new card in the best-matching board/list.

Section 4 of the artifact. Tier A+B+C evidence (Epoch 2). Tier D LLM
tiebreaker is Epoch 3.

Scoring pipeline:
  1. Call operator_scope.get_operator_user_id() for scope guard.
  2. Fetch all operator boards via the profile builder (cached in Redis).
  3. For each non-private board, run scoring.composite_score against
     the phrase embedding.
  4. Apply recency safeguard.
  5. Return a PluginScore for the top candidate (or None if all scores
     are below a minimum viability threshold).

The list chosen within the winning board is the list whose name embedding
is closest to the phrase, falling back to "Inbox" or the first list.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import field
from typing import Optional

from app.services.ambient_capture.plugin import (
	ActionResult,
	CaptureDecision,
	CapturePlugin,
	PluginCapabilities,
	PluginScore,
)
from app.services.ambient_capture import scoring as _scoring
from app.services.ambient_capture.sanitiser import _sanitize_for_log

logger = logging.getLogger(__name__)

# Minimum composite score for a board to be a viable candidate.
# Boards below this threshold are ignored even in the ASK lane.
_MIN_VIABLE_SCORE = 0.10

# Cap on how many boards we score per request (performance guard).
_MAX_BOARDS_TO_SCORE = 30


class PlankaCardPlugin:
	"""Capture a phrase as a new Planka card in the best-matching board/list."""

	name = "planka_card"
	capabilities = PluginCapabilities(
		can_create_resources=True,
		can_modify_existing=False,
		can_delete=False,
		requires_hitl_for=frozenset(),  # EXECUTE lane runs silently; ASK lane handled by engine
		max_capture_size_chars=500,
	)

	async def score_match(
		self,
		phrase: str,
		context: dict,
	) -> Optional[PluginScore]:
		"""Tier A+B+C scoring.  Returns None if no viable board found."""
		from app.services.ambient_capture.profiles import get_profile_builder
		from app.services.ambient_capture.operator_scope import get_operator_user_id
		from app.services.memory import encode_async
		from app.config import settings

		operator_id = get_operator_user_id()
		if not operator_id:
			return None

		try:
			phrase_emb = await encode_async(phrase)
		except Exception as e:
			logger.warning("planka_card: embed failed: %s", e)
			return None

		builder = get_profile_builder()

		# Fetch all operator boards (Planka metadata list, not full profiles)
		try:
			raw_boards = await builder.fetch_all_boards()
		except Exception as e:
			logger.warning("planka_card: fetch_all_boards failed: %s", e)
			return None

		# Scope-guard: keep only operator-owned boards
		from app.services.ambient_capture.operator_scope import filter_operator_boards
		raw_boards = filter_operator_boards(raw_boards)

		silent_floor = getattr(settings, "AMBIENT_SILENT_FLOOR", 0.80)

		best_score = 0.0
		best_board_id: Optional[str] = None
		best_board_name: Optional[str] = None
		best_list_id: Optional[str] = None
		best_list_label: Optional[str] = None

		for raw_board in raw_boards[:_MAX_BOARDS_TO_SCORE]:
			board_id = raw_board.get("id", "")
			if not board_id:
				continue

			# Skip boards the user has explicitly marked private
			if await builder.is_private(board_id):
				continue

			# Get or build profile
			profile = await builder.get_cached(board_id)
			if profile is None:
				try:
					profile = await builder.build_for_board(board_id)
				except Exception as e:
					logger.debug("planka_card: skipping board %s (build failed): %s",
					             _sanitize_for_log(board_id), e)
					continue

			if not profile:
				continue

			# Tier C: memory history match (basic cosine against phrase emb)
			memory_match = await _memory_history_match(phrase_emb)

			score_with = _scoring.composite_score(
				phrase_emb=phrase_emb,
				board_name_emb=profile.name_embedding,
				board_desc_emb=profile.description_embedding,
				card_embs=profile.card_title_embeddings,
				list_structs=profile.lists,
				memory_history_match=memory_match,
				last_activity_iso=profile.last_activity_at,
				board_id=board_id,
				session_recent_boards=context.get("session_recent_boards"),
				board_in_briefing=context.get("board_in_briefing", False),
				card_modified_24h=context.get("card_modified_24h", False),
			)

			# Recency safeguard
			score_without = _scoring.composite_score(
				phrase_emb=phrase_emb,
				board_name_emb=profile.name_embedding,
				board_desc_emb=profile.description_embedding,
				card_embs=profile.card_title_embeddings,
				list_structs=profile.lists,
				memory_history_match=memory_match,
				last_activity_iso=None,  # strip recency
				board_id=board_id,
			)
			score = _scoring.apply_recency_safeguard(score_with, score_without, silent_floor)

			if score > best_score:
				best_score = score
				best_board_id = board_id
				best_board_name = profile.board_name
				best_list_id, best_list_label = _pick_best_list(phrase_emb, profile.lists)

		if best_score < _MIN_VIABLE_SCORE or not best_board_id:
			return None

		destination_id = best_board_id if not best_list_id else f"{best_board_id}/{best_list_id}"
		destination_label = (
			f"{best_board_name} — {best_list_label}"
			if best_list_label
			else (best_board_name or best_board_id)
		)
		return PluginScore(
			score=best_score,
			destination_id=destination_id,
			destination_label=destination_label,
			reasoning={"board_id": best_board_id, "list_id": best_list_id},
		)

	async def execute_capture(self, decision: CaptureDecision) -> ActionResult:
		"""Create the Planka card."""
		from app.services.planka import create_task as planka_create_task
		from app.services.ambient_capture.sanitiser import clamp_phrase

		phrase = clamp_phrase(decision.phrase, max_chars=200)

		# destination_id format: "board_id/list_id" or just "board_id"
		parts = decision.destination_id.split("/", 1)
		board_id = parts[0]
		list_name = decision.destination_label.split(" — ")[-1] if " — " in decision.destination_label else "Inbox"

		# Resolve board name from destination_label
		board_name = decision.destination_label.split(" — ")[0] if " — " in decision.destination_label else decision.destination_label

		try:
			path = await planka_create_task(
				board_name=board_name,
				list_name=list_name,
				title=phrase,
				description="",
			)
			if path:
				return ActionResult(
					success=True,
					message=f"Created card in {path}",
					resource_id=board_id,
				)
			return ActionResult(success=False, message="Card creation returned no path")
		except Exception as e:
			logger.warning("planka_card: execute_capture failed: %s", e)
			return ActionResult(success=False, message=str(e)[:200])

	async def explain_routing(self, decision: CaptureDecision, lang: str) -> str:
		"""One-sentence i18n explanation for the dashboard reasoning trace."""
		from app.services.translations import get_translation
		tmpl = get_translation("ambient_captured_silent", lang,
		                       fallback="Saved '{phrase}' to {board}.")
		dest = decision.destination_label
		parts = dest.split(" — ")
		board_part = parts[0] if parts else dest
		list_part = parts[1] if len(parts) > 1 else ""
		return tmpl.format(phrase=decision.phrase, board=board_part, list=list_part)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pick_best_list(
	phrase_emb: list[float],
	lists: list[dict],
) -> tuple[Optional[str], Optional[str]]:
	"""Return (list_id, list_name) of the list whose name embedding is
	closest to the phrase. Falls back to the first list named 'Inbox' or
	just the first list in the board."""
	if not lists:
		return None, None
	best_sim = -1.0
	best_id: Optional[str] = None
	best_name: Optional[str] = None
	for lst in lists:
		emb = lst.get("name_embedding") or []
		if not emb:
			continue
		sim = _scoring.cosine_similarity(phrase_emb, emb)
		if sim > best_sim:
			best_sim = sim
			best_id = lst.get("id")
			best_name = lst.get("name")
	if best_id is None:
		# No embeddings — fall back to Inbox or first list
		for lst in lists:
			if (lst.get("name") or "").lower() == "inbox":
				return lst.get("id"), lst.get("name")
		first = lists[0]
		return first.get("id"), first.get("name")
	return best_id, best_name


async def _memory_history_match(phrase_emb: list[float]) -> float:
	"""Tier C: query routing_lessons collection for similar past phrases.

	Returns a value in [0, 1] representing how consistently past similar
	captures ended in target boards that have positive outcomes.
	In Epoch 2 this is a basic similarity scan; Epoch 3 adds lesson weights.
	"""
	try:
		from qdrant_client import QdrantClient, models
		from app.config import settings
		import asyncio

		client = QdrantClient(
			host=settings.QDRANT_HOST,
			port=settings.QDRANT_PORT,
			api_key=settings.QDRANT_API_KEY,
			https=False,
			timeout=5.0,
		)
		# Check collection exists first
		def _search():
			try:
				cols = [c.name for c in client.get_collections().collections]
				if "routing_lessons" not in cols:
					return []
				return client.search(
					collection_name="routing_lessons",
					query_vector=phrase_emb,
					limit=5,
					score_threshold=0.75,
				)
			except Exception:
				return []

		loop = asyncio.get_event_loop()
		results = await loop.run_in_executor(None, _search)
		if not results:
			return 0.0
		# Simple mean score (Epoch 3 adds per-action weighting)
		return min(1.0, sum(r.score for r in results) / len(results))
	except Exception:
		return 0.0
