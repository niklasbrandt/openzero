"""
Self-Verification & Action Fulfillment Audit Service
─────────────────────────────────────────────────────
Three periodic checks surfaced via the existing notifier (Telegram/Dashboard).
Duplicate cards are auto-removed; all other findings are advisory only.

  1. Action fulfillment — [AUDIT:...] claim tags in Z's stored replies vs
     Planka's actual state (cards, lists, board placement).
  2. Hallucination flags — Z's factual assertions about the user cross-
     referenced against personal context loaded from /personal/*.
  3. Redundancy / coherence — duplicate card names are automatically deleted
     (oldest kept); misplaced crew lists are flagged as advisory.

Tag format used by Z in replies (see agent/agent-rules.md):
  [AUDIT:create_project:ProjectName]
  [AUDIT:create_task:TaskTitle|board=BoardName]
  [AUDIT:create_list:ListName|board=BoardName]

These tags survive the action-tag stripper (they are NOT [ACTION:...] tool
dispatch tags) and are stored in global_messages.content for later retrieval.
"""

import asyncio
import logging
import re
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# _AUDIT_LOOKBACK_DAYS is intentionally removed -- use settings.AUDIT_LOOKBACK_HOURS instead.

# Board name keywords that indicate a list/shopping/nutrition board where description is optional.
_LIST_BOARD_KEYWORDS = frozenset([
	"nutrition", "shopping", "grocery", "einkauf", "lebensmittel", "rezept", "recipe",
])

# [AUDIT:action_type:subject] or [AUDIT:action_type:subject|key=value|...]
# Linear pattern — no nested quantifiers — avoids catastrophic backtracking.
_AUDIT_TAG_RE = re.compile(
	r'\[AUDIT:(?P<action>[a-z_]{1,32}):(?P<subject>[^\|\]\n]{1,200})'
	r'(?P<attrs>(?:\|[a-z_]{1,20}=[^\|\]\n]{0,100})*)\]',
	re.IGNORECASE,
)

# Patterns that suggest Z is making factual claims about the user.
# Each alternative is a fixed-width anchor — no catastrophic backtracking.
_ASSERTION_ANCHORS = re.compile(
	r"\byou(?:'re| are) (?:a |an )?"
	r"|\byour \w+ (?:is|are|was|were) "
	r"|\byou (?:prefer|like|love|hate|dislike|want|need|use|have|don't|never) ",
	re.IGNORECASE,
)

# Negation signals to look for in personal context when checking a claim
_NEG_TEMPLATES = ("not {}", "don't {}", "never {}", "no {}", "doesn't {}", "dislike {}")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sanitize_for_log(text: Any, max_len: int = 120) -> str:
	"""Sanitize arbitrary text for safe logging (CWE-117)."""
	val = str(text)[:max_len]
	return re.escape(val)


def _parse_tag_attrs(attrs_str: str) -> dict[str, str]:
	"""Parse |key=value|key=value trailing segment from an AUDIT tag."""
	result: dict[str, str] = {}
	if not attrs_str:
		return result
	for segment in attrs_str.split("|"):
		segment = segment.strip()
		if "=" in segment:
			k, _, v = segment.partition("=")
			result[k.strip().lower()] = v.strip()
	return result


# ---------------------------------------------------------------------------
# Claim extraction
# ---------------------------------------------------------------------------

async def extract_audit_claims(hours: int | None = None) -> list[dict[str, Any]]:
	"""Return all [AUDIT:...] tags found in Z's replies in the last N hours.

	Defaults to settings.AUDIT_LOOKBACK_HOURS (48 h) when no override is supplied.
	Returns a list of dicts with keys: action, subject, attrs, at, message_id.
	"""
	from app.models.db import AsyncSessionLocal, GlobalMessage
	from sqlalchemy import select

	lookback_hours = hours if hours is not None else settings.AUDIT_LOOKBACK_HOURS
	cutoff = datetime.utcnow() - timedelta(hours=lookback_hours)
	async with AsyncSessionLocal() as session:
		result = await session.execute(
			select(GlobalMessage)
			.where(GlobalMessage.role == "z")
			.where(GlobalMessage.created_at >= cutoff)
			.order_by(GlobalMessage.created_at.asc())
		)
		messages = result.scalars().all()

	claims: list[dict[str, Any]] = []
	for msg in messages:
		for m in _AUDIT_TAG_RE.finditer(msg.content or ""):
			claims.append({
				"action": m.group("action").lower(),
				"subject": m.group("subject").strip(),
				"attrs": _parse_tag_attrs(m.group("attrs") or ""),
				"at": msg.created_at.isoformat() + "Z",
				"message_id": msg.id,
			})
	return claims


# ---------------------------------------------------------------------------
# Planka snapshot (lightweight, parallel)
# ---------------------------------------------------------------------------

async def _get_planka_snapshot() -> dict[str, Any]:
	"""Fetch a snapshot of all projects, boards, lists, and cards from Planka.

	Returns:
	  {
	    "projects": [{"id", "name"}],
	    "boards":   [{"id", "name", "project_id", "project_name"}],
	    "lists":    [{"id", "name", "board_id", "board_name"}],
	    "cards":    [{"id", "name", "list_id", "board_name"}],
	  }
	"""
	from app.services.planka_common import get_planka_auth_token

	snapshot: dict[str, Any] = {"projects": [], "boards": [], "lists": [], "cards": []}
	try:
		token = await get_planka_auth_token()
		headers = {"Authorization": f"Bearer {token}"}
		async with httpx.AsyncClient(base_url=settings.PLANKA_BASE_URL, timeout=20.0, headers=headers) as client:
			resp = await client.get("/api/projects")
			resp.raise_for_status()
			projects = resp.json().get("items", [])
			snapshot["projects"] = [{"id": p["id"], "name": p.get("name", "")} for p in projects]

			if not projects:
				return snapshot

			proj_details = await asyncio.gather(
				*[client.get(f"/api/projects/{p['id']}") for p in projects],
				return_exceptions=True,
			)

			all_boards: list[dict[str, Any]] = []
			for proj, det in zip(projects, proj_details):
				if isinstance(det, BaseException):
					logger.debug("self_audit snapshot: project %s detail failed: %s", proj["id"], det)
					continue
				for b in det.json().get("included", {}).get("boards", []):
					all_boards.append({
						"id": b["id"],
						"name": b.get("name", ""),
						"project_id": proj["id"],
						"project_name": proj.get("name", ""),
					})
			snapshot["boards"] = all_boards

			if not all_boards:
				return snapshot

			board_details = await asyncio.gather(
				*[client.get(f"/api/boards/{b['id']}", params={"included": "lists,cards"}) for b in all_boards],
				return_exceptions=True,
			)

			for b_meta, b_det in zip(all_boards, board_details):
				if isinstance(b_det, BaseException):
					continue
				b_data = b_det.json()
				for lst in b_data.get("included", {}).get("lists", []):
					snapshot["lists"].append({
						"id": lst["id"],
						"name": lst.get("name", ""),
						"board_id": b_meta["id"],
						"board_name": b_meta["name"],
					})
				# Build per-card task count from included tasks (present when Planka returns them).
				tasks_in_board = b_data.get("included", {}).get("tasks", [])
				task_count_by_card: dict[str, int] = defaultdict(int)
				for t in tasks_in_board:
					cid = t.get("cardId", "")
					if cid:
						task_count_by_card[cid] += 1

				for card in b_data.get("included", {}).get("cards", []):
					snapshot["cards"].append({
						"id": card["id"],
						"name": card.get("name", ""),
						"description": card.get("description") or "",
						"has_tasks": task_count_by_card.get(card["id"], 0) > 0,
						"list_id": card.get("listId", ""),
						"board_name": b_meta["name"],
						"created_at": card.get("createdAt", ""),
					})
	except Exception as e:
		logger.warning("self_audit: _get_planka_snapshot failed: %s", _sanitize_for_log(e))
	return snapshot


# ---------------------------------------------------------------------------
# Check 4 — Missing Descriptions
# ---------------------------------------------------------------------------

_VERB_SUFFIX_RE = re.compile(
	r'\b\w+(?:en|ern|eln|ieren)\b'  # German infinitives: waschen, kaufen, abhängen, organisieren
	r'|'
	r'\b(?:buy|get|fix|clean|order|check|call|send|book|find|write|read|do|make|take|'
	r'move|add|update|remove|delete|install|repair|return|pick|drop|pack|build|set|'
	r'create|review|prepare|schedule|organize|finish|start|test|run|go|bring)\b',  # common English verbs
	re.IGNORECASE,
)


def _title_has_verb(name: str) -> bool:
	return bool(_VERB_SUFFIX_RE.search(name))


def _check_missing_descriptions(cards: list[dict[str, Any]]) -> list[str]:
	"""Disabled: missing-description audit warnings are suppressed."""
	return []

	"""Return advisory flags for task-board cards with vague names and no description or tasks.

	Heuristic: only flag a card when ALL of the following are true:
	  - The board is a task board (board name does not match _LIST_BOARD_KEYWORDS).
	  - The card has no description.
	  - The card has no tasks/checklist items.
	  - The card name is genuinely ambiguous: 1-2 words AND contains no verb.
	    Titles with 3+ words, or any verb, are considered self-explanatory.
	"""
	flags: list[str] = []
	for card in cards:
		board_name = card.get("board_name", "")
		board_lc = board_name.lower()
		# Skip list/shopping/nutrition boards — descriptions are optional there.
		if any(kw in board_lc for kw in _LIST_BOARD_KEYWORDS):
			continue
		# Skip if a description exists.
		if (card.get("description") or "").strip():
			continue
		# Skip if the card has tasks (self-documenting via checklist).
		if card.get("has_tasks"):
			continue
		name = card.get("name", "")
		words = name.split()
		# 3+ words: descriptive enough regardless of content.
		if len(words) >= 3:
			continue
		# Contains a verb: action is clear.
		if _title_has_verb(name):
			continue
		# 1-2 word noun-only titles are genuinely ambiguous (e.g. "macbook", "TV", "PC Case").
		flags.append(
			f"Card '{name}' on board '{board_name}' has no description (ambiguous title, task board)."
		)
	return flags


async def run_missing_description_check() -> list[str]:
	"""Fetch a Planka snapshot and return advisory flags for undescribed vague-title cards."""
	snapshot = await _get_planka_snapshot()
	return _check_missing_descriptions(snapshot["cards"])


# ---------------------------------------------------------------------------
# Check 1 — Action Fulfillment
# ---------------------------------------------------------------------------

async def run_action_fulfillment_check() -> list[str]:
	"""Verify [AUDIT:...] claimed actions against Planka's actual state.

	Checks:
	- create_project: project exists; if a "My Projects" parent project exists,
	  verify the new project became a board there (not a top-level project).
	- create_task: matching card exists; optionally verify board placement.
	- create_list: list exists on the claimed board.

	Returns a list of human-readable flag strings.
	"""
	claims = await extract_audit_claims()
	if not claims:
		return []

	snapshot = await _get_planka_snapshot()
	project_names_lc = {p["name"].lower() for p in snapshot["projects"]}

	my_projects_parent = settings.AUDIT_MY_PROJECTS_PARENT.lower() if settings.AUDIT_MY_PROJECTS_PARENT else "my projects"
	flags: list[str] = []

	for claim in claims:
		action = claim["action"]
		subject = claim["subject"]
		attrs = claim["attrs"]

		if action == "create_project":
			if subject.lower() not in project_names_lc:
				flags.append(f"Project '{subject}' was claimed as created but is not found in Planka.")
				continue
			# Flag if My Projects parent exists but subject did not land as a board under it
			if my_projects_parent in project_names_lc:
				boards_under_parent = [
					b for b in snapshot["boards"]
					if b["project_name"].lower() == my_projects_parent
					and b["name"].lower() == subject.lower()
				]
				if not boards_under_parent:
					flags.append(
						f"Project '{subject}' was created as a top-level Planka project "
						f"instead of as a board under '{settings.AUDIT_MY_PROJECTS_PARENT}'. "
						f"Consider moving it there."
					)

		elif action == "create_task":
			board_hint = attrs.get("board", "")
			# Fuzzy match: subject is a substring of an existing card name
			found_cards = [c for c in snapshot["cards"] if subject.lower() in c["name"].lower()]
			if not found_cards:
				flags.append(f"Task '{subject}' was claimed as created but no matching card found in Planka.")
			elif board_hint:
				wrong_board = [c for c in found_cards if board_hint.lower() not in c["board_name"].lower()]
				if wrong_board and len(wrong_board) == len(found_cards):
					actual_boards = ", ".join({c["board_name"] for c in wrong_board})
					flags.append(
						f"Task '{subject}' was claimed to land on board '{board_hint}' "
						f"but found on: {actual_boards}."
					)

		elif action == "create_list":
			board_hint = attrs.get("board", "")
			if board_hint:
				matching = [
					lst for lst in snapshot["lists"]
					if subject.lower() in lst["name"].lower()
					and board_hint.lower() in lst["board_name"].lower()
				]
				if not matching:
					flags.append(
						f"List '{subject}' was claimed on board '{board_hint}' "
						f"but not found there. Check if it landed on a different board."
					)

	return flags


# ---------------------------------------------------------------------------
# Check 2 — Hallucination / Contradiction
# ---------------------------------------------------------------------------

async def run_hallucination_check() -> list[str]:
	"""Scan Z's recent messages for factual assertions that contradict personal context.

	Strategy:
	  1. Extract sentences from Z replies that trigger _ASSERTION_ANCHORS.
	  2. Pull a short subject phrase (next 3–4 words) from each match.
	  3. Check whether the personal context block contains a negation of that phrase.
	  4. Flag matches — heuristic only, no LLM call required.

	Returns a list of human-readable flag strings.
	"""
	from app.models.db import AsyncSessionLocal, GlobalMessage
	from app.services.personal_context import get_personal_context_for_prompt
	from sqlalchemy import select

	cutoff = datetime.utcnow() - timedelta(hours=settings.AUDIT_LOOKBACK_HOURS)
	async with AsyncSessionLocal() as session:
		result = await session.execute(
			select(GlobalMessage)
			.where(GlobalMessage.role == "z")
			.where(GlobalMessage.created_at >= cutoff)
			.order_by(GlobalMessage.created_at.asc())
		)
		z_messages = result.scalars().all()

	if not z_messages:
		return []

	personal_context = get_personal_context_for_prompt()
	if not personal_context:
		return []
	personal_lc = personal_context.lower()

	flags: list[str] = []
	seen: set[str] = set()

	for msg in z_messages:
		content = msg.content or ""
		for m in _ASSERTION_ANCHORS.finditer(content):
			# Grab 80 chars after the match start for context
			snippet = content[m.start(): m.start() + 80].strip()
			dedup_key = snippet[:50].lower()
			if dedup_key in seen:
				continue
			seen.add(dedup_key)

			# Extract a short subject phrase (3–4 words following the anchor)
			after_match = content[m.end(): m.end() + 60]
			words = after_match.split()
			subject_phrase = " ".join(words[:4]).lower().strip(".,!?;:")
			if len(subject_phrase) < 4:
				continue

			# Look for explicit negation of this phrase in personal context
			for template in _NEG_TEMPLATES:
				negated = template.format(subject_phrase)
				if negated in personal_lc:
					flags.append(
						f"Z said: '{snippet[:100]}' — but personal context contains: '{negated}'. "
						f"Verify this is accurate."
					)
					break

	return flags


# ---------------------------------------------------------------------------
# Check 3 — Redundancy & Coherence
# ---------------------------------------------------------------------------

async def _delete_planka_card(client: httpx.AsyncClient, card_id: str) -> bool:
	"""Delete a single Planka card by ID. Returns True on success, False on failure."""
	try:
		resp = await client.delete(f"/api/cards/{card_id}")
		resp.raise_for_status()
		return True
	except Exception as e:
		logger.error("self_audit: failed to delete card %s: %s", _sanitize_for_log(card_id), _sanitize_for_log(e))
		return False


async def run_redundancy_check() -> list[str]:
	"""Detect duplicate card names on the same Planka board and automatically delete extras.

	For each group of duplicates, the card with the earliest createdAt (or lowest id
	as a tie-breaker) is kept. All later duplicates are deleted via the Planka API.

	Also flags crew lists that may have landed on the wrong board (advisory only).

	Returns a list of result strings describing what was removed or could not be removed.
	"""
	from app.services.planka_common import get_planka_auth_token

	snapshot = await _get_planka_snapshot()
	flags: list[str] = []

	# 3a. Duplicate card names on the same board — auto-delete extras
	cards_by_board: dict[str, list[dict]] = defaultdict(list)
	for card in snapshot["cards"]:
		cards_by_board[card["board_name"]].append(card)

	# Collect all (board_name, card_name_lc, duplicates_to_delete) tuples first
	deletions: list[tuple[str, str, list[dict]]] = []
	for board_name, cards in cards_by_board.items():
		name_groups: dict[str, list[dict]] = defaultdict(list)
		for card in cards:
			name_groups[card["name"].lower()].append(card)
		for card_name_lc, group in name_groups.items():
			if len(group) < 2:
				continue
			# Sort: earliest createdAt first; fall back to lexicographic id sort
			def _sort_key(c: dict) -> tuple:
				ts = c.get("created_at") or ""
				return (ts, c["id"])
			group_sorted = sorted(group, key=_sort_key)
			keep = group_sorted[0]
			duplicates = group_sorted[1:]
			deletions.append((board_name, keep["name"], duplicates))

	if deletions:
		try:
			token = await get_planka_auth_token()
			headers = {"Authorization": f"Bearer {token}"}
			async with httpx.AsyncClient(base_url=settings.PLANKA_BASE_URL, timeout=20.0, headers=headers) as client:
				for board_name, canonical_name, dupes in deletions:
					removed: list[str] = []
					failed: list[str] = []
					for dupe in dupes:
						ok = await _delete_planka_card(client, dupe["id"])
						if ok:
							removed.append(dupe["id"])
						else:
							failed.append(dupe["id"])
					if removed:
						flags.append(
							f"Removed {len(removed)} duplicate card(s) '{canonical_name}' from board '{board_name}'."
						)
					if failed:
						flags.append(
							f"Could not remove {len(failed)} duplicate card(s) '{canonical_name}' "
							f"from board '{board_name}' (API error — see logs)."
						)
		except Exception as e:
			logger.error("self_audit: duplicate card cleanup failed: %s", _sanitize_for_log(e))
			for board_name, canonical_name, dupes in deletions:
				flags.append(
					f"Could not remove {len(dupes)} duplicate card(s) '{canonical_name}' "
					f"from board '{board_name}' (auth/connection error — see logs)."
				)

	# 3b. Crew board hygiene — lists that contain a crew id keyword but live on the wrong board
	try:
		from app.services.crews import crew_registry
		await crew_registry.load()
		active_crews = crew_registry.list_active()
		for crew in active_crews:
			# The canonical crew board name is the crew's display name
			crew_board_match = next(
				(
					b for b in snapshot["boards"]
					if crew.id.lower() in b["name"].lower() or crew.name.lower() in b["name"].lower()
				),
				None,
			)
			if not crew_board_match:
				continue
			# Lists on OTHER boards whose name contains the crew id — potential misplacement
			misplaced = [
				lst for lst in snapshot["lists"]
				if crew.id.lower() in lst["name"].lower()
				and lst["board_name"].lower() != crew_board_match["name"].lower()
			]
			for lst in misplaced:
				flags.append(
					f"List '{lst['name']}' looks like it belongs to crew '{crew.id}' "
					f"but is on board '{lst['board_name']}'. "
					f"Expected board: '{crew_board_match['name']}'."
				)
	except Exception as e:
		logger.debug("self_audit: crew board hygiene check skipped: %s", _sanitize_for_log(e))

	return flags


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

async def run_full_audit() -> str:
	"""Run all checks in parallel and return a formatted advisory report.

	Returns an empty string when no flags are raised (caller should skip sending).
	"""
	fulfillment_flags, hallucination_flags, redundancy_flags, description_flags = await asyncio.gather(
		run_action_fulfillment_check(),
		run_hallucination_check(),
		run_redundancy_check(),
		run_missing_description_check(),
	)

	total = len(fulfillment_flags) + len(hallucination_flags) + len(redundancy_flags) + len(description_flags)
	if total == 0:
		return ""

	from app.services.translations import get_translations, get_user_lang
	lang = await get_user_lang()
	t = get_translations(lang)

	lines: list[str] = [
		t.get("audit_report_header", "*Self-Audit Report*")
		+ f" — {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC"
	]

	if fulfillment_flags:
		lines.append("\n" + t.get("audit_section_fulfillment", "*Action Fulfillment Gaps*"))
		for f in fulfillment_flags:
			lines.append(f"• {f}")

	if hallucination_flags:
		lines.append("\n" + t.get("audit_section_contradictions", "*Possible Contradictions*"))
		for f in hallucination_flags:
			lines.append(f"• {f}")

	if redundancy_flags:
		lines.append("\n" + t.get("audit_section_redundancy", "*Redundancy / Coherence*"))
		for f in redundancy_flags:
			lines.append(f"• {f}")

	if description_flags:
		lines.append("\n" + t.get("audit_section_missing_desc", "*Missing Descriptions*"))
		for f in description_flags:
			lines.append(f"• {f}")

	lines.append(
		"\n" + t.get(
			"audit_report_footer",
			"_Action fulfillment, contradiction, and missing-description flags are advisory. "
			"Duplicate cards have been auto-removed._",
		)
	)
	lines.append(f"\n[Dashboard]({settings.BASE_URL}/dashboard)")
	return "\n".join(lines)
