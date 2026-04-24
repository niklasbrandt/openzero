"""Deterministic pre-LLM intent router for Planka structural mutations.

Executes high-confidence verb intents (move/archive/mark-done) directly against
Planka without involving the chat LLM. Falls through to the existing tag-based
pipeline if no intent matches.

Language-agnostic in design: uses a small multilingual verb lexicon. Phase 1
ships EN + DE patterns; other languages return None so the existing LLM path
runs as before.

Public API:
	classify_structural_intent(text, lang) -> StructuralIntent | None
	dispatch_structural_intent(intent, lang) -> str

A StructuralIntent has:
	verb        — one of MOVE_BOARD, MOVE_CARD, ARCHIVE_CARD, MARK_DONE
	entities    — dict with verb-specific keys (board, target_project, card, list, ...)
	raw_text    — original user text (truncated for logging safety)
	confidence  — 1.0 exact match, 0.9 substring, lower for entity-only fallbacks

Confidence threshold for dispatch is decided by the caller (router.py).
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# Cap input length before running regex to prevent ReDoS (CWE-1333)
_MAX_INPUT = 500

# In-process cache for Planka project/board snapshot
_CACHE_TTL_SECONDS = 30.0
_cache: dict[str, object] = {"ts": 0.0, "projects": []}


@dataclass
class StructuralIntent:
	verb: str
	entities: dict = field(default_factory=dict)
	raw_text: str = ""
	confidence: float = 0.0


# ─── Verb detection patterns ─────────────────────────────────────────────────
# Bounded quantifiers throughout to avoid catastrophic backtracking.

# MOVE_BOARD — "move <name> board to <project>" / German variants
_MOVE_BOARD_PATTERNS = [
	re.compile(r'\bmove\s+(?:the\s+)?(.{1,80}?)\s+board\s+(?:to|into|under)\s+(.{1,80})', re.IGNORECASE),
	re.compile(r'\bmove\s+(?:the\s+)?board\s+(.{1,80}?)\s+(?:to|into|under)\s+(.{1,80})', re.IGNORECASE),
	re.compile(r'\bverschieb[e]?\s+(?:das\s+)?(.{1,80}?)[-\s]board\s+(?:zu|in|nach|unter)\s+(.{1,80})', re.IGNORECASE),
	re.compile(r'\bverschieb[e]?\s+(?:das\s+)?board\s+(.{1,80}?)\s+(?:zu|in|nach|unter)\s+(.{1,80})', re.IGNORECASE),
]

# MOVE_CARD — "move <card> to <list>" / German variants
# Conservative: requires the word "card"/"karte" or a direct list keyword (today/done/etc.)
_MOVE_CARD_PATTERNS = [
	re.compile(r'\bmove\s+(?:the\s+)?card\s+(.{1,80}?)\s+(?:to|into)\s+(.{1,80})', re.IGNORECASE),
	re.compile(r'\bverschieb[e]?\s+(?:die\s+)?karte\s+(.{1,80}?)\s+(?:zu|in|nach)\s+(.{1,80})', re.IGNORECASE),
]

# ARCHIVE_CARD — "archive (the card) <name>" / German variants
_ARCHIVE_CARD_PATTERNS = [
	re.compile(r'\barchive\s+(?:the\s+)?(?:card\s+)?(.{1,120})', re.IGNORECASE),
	re.compile(r'\barchivier[e]?\s+(?:die\s+)?(?:karte\s+)?(.{1,120})', re.IGNORECASE),
]

# MARK_DONE — "mark <card> (as) done" / "<card> is done" / German variants
_MARK_DONE_PATTERNS = [
	re.compile(r'\bmark\s+(?:the\s+)?(?:card\s+)?(.{1,80}?)\s+(?:as\s+)?done\b', re.IGNORECASE),
	re.compile(r'\b(?:set|move)\s+(?:the\s+)?(?:card\s+)?(.{1,80}?)\s+to\s+done\b', re.IGNORECASE),
	re.compile(r'\bmarkier[e]?\s+(?:die\s+)?(?:karte\s+)?(.{1,80}?)\s+(?:als\s+)?(?:erledigt|fertig)\b', re.IGNORECASE),
]

# Conversational hedges that should suppress a match even if the verb hits.
# These cover "I was thinking about moving the X board sometime", "what does it
# mean to move a board", "should I move", "consider moving", etc.
_HEDGE_PATTERNS = [
	re.compile(r'\b(?:thinking\s+about|considering|maybe|might|should\s+i|could\s+i|how\s+(?:do|to|can)\s+i|what\s+(?:does|is|happens)|why\s+(?:would|should))\b', re.IGNORECASE),
	re.compile(r"\b(?:was|were)\s+(?:thinking|planning|considering)\b", re.IGNORECASE),
	re.compile(r'\b(?:explain|tell\s+me\s+about|describe)\b', re.IGNORECASE),
]

# Supported languages. Returning None for other languages preserves existing
# LLM behaviour for users on unsupported locales.
_SUPPORTED_LANGS = {"en", "de"}


def _is_hedged(text: str) -> bool:
	return any(p.search(text) for p in _HEDGE_PATTERNS)


def _strip_filler(s: str) -> str:
	"""Trim quotes, trailing punctuation, leading articles and trailing
	politeness/filler words (please, bitte, thanks, danke) from an entity."""
	s = s.strip().strip('"\'\u201c\u201d\u2018\u2019')
	s = s.rstrip('.,;!?')
	# Strip leading articles
	s = re.sub(r'^(?:the|my|a|an|der|die|das|ein|eine|einen)\s+', '', s, flags=re.IGNORECASE)
	# Strip trailing politeness / filler so "my projects bitte" -> "my projects"
	s = re.sub(r'\s+(?:please|bitte|thanks|thank\s+you|danke|asap|now|today)\s*$', '', s, flags=re.IGNORECASE)
	return s.strip()


async def _get_planka_snapshot(force: bool = False) -> list[dict]:
	"""Return the cached list of Planka projects (with their boards).

	Each entry: {"id", "name", "boards": [{"id", "name"}]}.
	Cached in-process for _CACHE_TTL_SECONDS.
	"""
	now = time.monotonic()
	if not force and (now - float(_cache["ts"])) < _CACHE_TTL_SECONDS and _cache["projects"]:
		return _cache["projects"]  # type: ignore[return-value]
	try:
		from app.config import settings
		from app.services.planka_common import get_planka_auth_token
		import httpx
		token = await get_planka_auth_token()
		async with httpx.AsyncClient(base_url=settings.PLANKA_BASE_URL, timeout=3.0, headers={"Authorization": f"Bearer {token}"}) as client:
			pr = await client.get("/api/projects")
			pr.raise_for_status()
			projects_raw = pr.json().get("items", [])
			# Parallelise per-project detail fetches (was N+1 sequential).
			detail_tasks = [client.get(f"/api/projects/{p['id']}") for p in projects_raw]
			details = await asyncio.gather(*detail_tasks, return_exceptions=True)
			snapshot: list[dict] = []
			for p, det in zip(projects_raw, details):
				if isinstance(det, BaseException):
					logger.warning("intent_router: project %s detail fetch failed: %s", p.get("id"), det)
					continue
				try:
					det.raise_for_status()
					det_json = det.json()
				except Exception as _pe:
					logger.warning("intent_router: project %s detail parse failed: %s", p.get("id"), _pe)
					continue
				boards = det_json.get("included", {}).get("boards", []) or det_json.get("boards", [])
				snapshot.append({
					"id": p["id"],
					"name": p["name"],
					"boards": [{"id": b["id"], "name": b.get("name", "")} for b in boards],
				})
			_cache["projects"] = snapshot
			_cache["ts"] = now
			return snapshot
	except Exception as e:
		logger.warning("intent_router: planka snapshot failed: %s", e)
		return []


def _match_name(query: str, candidates: list[dict]) -> tuple[Optional[dict], float]:
	"""Return (best_match, confidence) using exact then forward-substring match."""
	if not query or not candidates:
		return None, 0.0
	q = query.lower()
	# Exact
	for c in candidates:
		if (c.get("name") or "").lower() == q:
			return c, 1.0
	# Forward substring (query inside name) — same direction guard as agent_actions
	subs = [c for c in candidates if q in (c.get("name") or "").lower()]
	if subs:
		best = min(subs, key=lambda c: abs(len(c.get("name") or "") - len(query)))
		return best, 0.9
	return None, 0.0


async def classify_structural_intent(text: str, lang: str) -> Optional[StructuralIntent]:
	"""Detect a high-confidence Planka mutation intent in the user message.

	Returns None when:
	  - language is unsupported by Phase 1
	  - no verb pattern matches
	  - the message is hedged ("thinking about", "should I", etc.)
	  - the entity could not be resolved against live Planka state
	"""
	if not text:
		return None
	if lang not in _SUPPORTED_LANGS:
		return None
	snippet = text[:_MAX_INPUT].strip()
	if _is_hedged(snippet):
		return None

	# ── MOVE_BOARD ────────────────────────────────────────────────────────
	for pat in _MOVE_BOARD_PATTERNS:
		m = pat.search(snippet)
		if m:
			board_q = _strip_filler(m.group(1))
			project_q = _strip_filler(m.group(2))
			if not board_q or not project_q:
				continue
			projects = await _get_planka_snapshot()
			if not projects:
				return None
			proj_match, proj_conf = _match_name(project_q, projects)
			if not proj_match:
				return None
			all_boards = [b for p in projects for b in p["boards"]]
			board_match, board_conf = _match_name(board_q, all_boards)
			if not board_match:
				return None
			return StructuralIntent(
				verb="MOVE_BOARD",
				entities={
					"board_id": board_match["id"],
					"board_name": board_match["name"],
					"project_id": proj_match["id"],
					"project_name": proj_match["name"],
					"raw_board_query": board_q,
					"raw_project_query": project_q,
				},
				raw_text=snippet,
				confidence=min(proj_conf, board_conf),
			)

	# ── MOVE_CARD ─────────────────────────────────────────────────────────
	for pat in _MOVE_CARD_PATTERNS:
		m = pat.search(snippet)
		if m:
			card_q = _strip_filler(m.group(1))
			list_q = _strip_filler(m.group(2))
			if not card_q or not list_q:
				continue
			# Card lookup is delegated to planka.move_card; trust the verb signal.
			return StructuralIntent(
				verb="MOVE_CARD",
				entities={"card_fragment": card_q, "destination_list": list_q, "board_name": ""},
				raw_text=snippet,
				confidence=0.9,
			)

	# ── MARK_DONE ────────────────────────────────────────────────────────
	for pat in _MARK_DONE_PATTERNS:
		m = pat.search(snippet)
		if m:
			card_q = _strip_filler(m.group(1))
			if not card_q:
				continue
			return StructuralIntent(
				verb="MARK_DONE",
				entities={"card_fragment": card_q},
				raw_text=snippet,
				confidence=0.9,
			)

	# ── ARCHIVE_CARD ──────────────────────────────────────────────────────
	for pat in _ARCHIVE_CARD_PATTERNS:
		m = pat.search(snippet)
		if m:
			card_q = _strip_filler(m.group(1))
			if not card_q:
				continue
			# Skip if the object looks like a board ("aquarium board") — leave that to the LLM
			if re.search(r'\bboard\b', card_q, re.IGNORECASE):
				return None
			return StructuralIntent(
				verb="ARCHIVE_CARD",
				entities={"card_fragment": card_q, "board_name": ""},
				raw_text=snippet,
				confidence=0.9,
			)

	return None


async def dispatch_structural_intent(intent: StructuralIntent, lang: str) -> str:
	"""Execute the intent against Planka and return a localised result string.

	Falls back to the executor's English string when no localised template is
	defined for the result type. Always appends an [AUDIT:...] tag so the
	reactive self-audit can verify the mutation.
	"""
	from app.services.translations import get_translations
	from app.services.agent_actions import (
		execute_move_board, execute_move_card, execute_archive_card, execute_mark_done,
	)
	t = get_translations(lang)

	def _localise(key: str, default: str, **kwargs: str) -> str:
		raw = t.get(key, default)
		try:
			return raw.format(**kwargs)
		except (KeyError, IndexError, ValueError):
			return default.format(**kwargs)

	verb = intent.verb
	ent = intent.entities

	if verb == "MOVE_BOARD":
		raw = await execute_move_board(ent["board_name"], ent["project_name"])
		if raw.startswith("\u26a0"):
			return raw
		msg = _localise(
			"intent_router_move_board_success",
			"Board '{board}' moved to '{project}'.",
			board=ent["board_name"], project=ent["project_name"],
		)
		audit = f"[AUDIT:move_board:{ent['board_name']}|to={ent['project_name']}]"
		# Bust the cache so a follow-up intent sees the new project assignment.
		_cache["ts"] = 0.0
		return f"{msg}\n{audit}"

	if verb == "MOVE_CARD":
		raw = await execute_move_card(ent["card_fragment"], ent["destination_list"], ent.get("board_name", ""))
		if raw.startswith("\u26a0"):
			return raw
		msg = _localise(
			"intent_router_move_card_success",
			"Card '{card}' moved to '{dest}'.",
			card=ent["card_fragment"], dest=ent["destination_list"],
		)
		audit = f"[AUDIT:move_card:{ent['card_fragment']}|to={ent['destination_list']}]"
		return f"{msg}\n{audit}"

	if verb == "MARK_DONE":
		raw = await execute_mark_done(ent["card_fragment"])
		if raw.startswith("\u26a0"):
			return raw
		msg = _localise(
			"intent_router_mark_done_success",
			"Card '{card}' marked done.",
			card=ent["card_fragment"],
		)
		audit = f"[AUDIT:mark_done:{ent['card_fragment']}]"
		return f"{msg}\n{audit}"

	if verb == "ARCHIVE_CARD":
		raw = await execute_archive_card(ent["card_fragment"], ent.get("board_name", ""))
		if raw.startswith("\u26a0"):
			return raw
		msg = _localise(
			"intent_router_archive_success",
			"Card '{card}' archived.",
			card=ent["card_fragment"],
		)
		audit = f"[AUDIT:archive_card:{ent['card_fragment']}]"
		return f"{msg}\n{audit}"

	# Unknown verb — defensive fallback, should not be reachable.
	logger.warning("intent_router: dispatch called with unknown verb %s", verb)
	return ""
