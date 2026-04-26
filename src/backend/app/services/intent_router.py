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
	verb        — one of MOVE_BOARD, MOVE_CARD, RENAME_CARD, RENAME_LIST, RENAME_CARD_TASK,
	            SET_CARD_DESC, ADD_CARD_TASK, CHECK_CARD_TASK, UNCHECK_CARD_TASK,
	            DELETE_CARD, DELETE_LIST, DELETE_CARD_TASK,
	            ARCHIVE_CARD, MARK_DONE
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
#
# Patterns are organised per language. classify_structural_intent first tries
# the user's locale, then falls back to every other language so that mixed-
# language commands (e.g. an English instruction from a Spanish UI) still
# route deterministically. The actual safety gate is the entity match against
# the live Planka snapshot — broad regex is safe because unresolved entities
# return None.
#
# For CJK / Arabic / Devanagari we avoid \b (which is unreliable for non-ASCII
# scripts) and rely on script boundaries / punctuation instead.

# Nouns that map to a Planka LIST (column) — the goal itself is the container.
# Everything else (item, todo, task, entry, aufgabe, eintrag) maps to a CARD.
_LIST_NOUNS: frozenset[str] = frozenset({
	"goal", "goals", "dream", "dreams", "wish", "wishes",
	"idea", "ideas", "resolution", "resolutions",
	"ziel", "ziele", "traum", "träume", "wunsch", "wünsche",
	"idee", "ideen", "vorsatz", "vorsätze",
})

_LANG_PATTERNS: dict[str, dict[str, list[re.Pattern]]] = {
	# ── English ───────────────────────────────────────────────────────────
	"en": {
		"sort_board": [
			# End-anchored pattern: always tried first. Handles all forms including
			# "sort lists and reorganize cards in potentially new lists in reef tank"
			# by anchoring board name at end of string — greedy .{0,300} ensures the
			# LAST 'in/on <board>' is captured, not a middle preposition.
			re.compile(
				r'\b(?:sort|reorgani[sz]e?|restructur[e]?|clean\s+up|tidy\s+up|reorder|rearrang[e]?)\b'
				r'.{0,300}'
				r'\b(?:in|on)\s+(?:the\s+)?(?:board\s+)?(?P<board>[a-z0-9][\w\s]{2,40})\s*$',
				re.IGNORECASE,
			),
			# Simple pattern: "sort/reorganize [the] [board] <name>" with no middle clause.
			# Serves as fallback when the message ends before "in <board>".
			re.compile(
				r'\b(?:sort|reorgani[sz]e?|restructur[e]?|clean\s+up|tidy\s+up|reorder|rearrang[e]?)\b'
				r'\s+(?:the\s+)?(?:board\s+)?(?P<board>[a-z0-9]\w[\w\s]{1,48}?)(?:\s*$|\s+(?:board|lists?|cards?))',
				re.IGNORECASE,
			),
		],
		"move_board": [
			re.compile(r'\bmove\s+(?:the\s+)?(.{1,200}?)\s+board\s+(?:to|into|under)\s+(.{1,200})', re.IGNORECASE),
			re.compile(r'\bmove\s+(?:the\s+)?board\s+(.{1,200}?)\s+(?:to|into|under)\s+(.{1,200})', re.IGNORECASE),
		],
		"move_card": [
			re.compile(r'\bmove\s+(?:the\s+)?card\s+(.{1,200}?)\s+(?:to|into)\s+(.{1,200})', re.IGNORECASE),
		],
		"rename_card": [
			re.compile(r'\brename\s+(?:the\s+)?(?:card\s+)?(.{1,200}?)\s+to\s+(.{1,200})', re.IGNORECASE),
			re.compile(r'\b(?:change|update)\s+(?:the\s+)?(?:card\s+)?(.{1,200}?)\s+(?:name|title)\s+to\s+(.{1,200})', re.IGNORECASE),
		],
		"rename_list": [
			re.compile(r'\brename\s+(?:the\s+)?(?:list|column)\s+(.{1,200}?)\s+to\s+(.{1,200})', re.IGNORECASE),
			re.compile(r'\b(?:change|update)\s+(?:the\s+)?(?:list|column)\s+(?:name\s+)?(.{1,200}?)\s+to\s+(.{1,200})', re.IGNORECASE),
		],
		# "new life goal home", "new goal buy house", "new dream X", "new wish X"
		# Also handles bulk: "new life goals: home, eating, garden, physique"
		# Anchored at start, high-confidence shorthand for adding items to a
		# board whose name contains the noun keyword (goal→life goals, etc.).
		"board_item_add": [
			# Bulk form: "new life goals: home, eating, garden" (colon + comma-list, newlines OK)
			re.compile(
				r'^\s*(?:new|add)\s+(?:life\s+)?'
				r'(?P<noun>goal|goals|dream|dreams|wish|wishes|idea|ideas|resolution|resolutions|item|items|todo|todos|task|tasks|entry|entries)'
				r'\s*:\s*(?P<titles>[\w\s,;\-äöüÄÖÜß]{2,2000})$',
				re.IGNORECASE | re.DOTALL,
			),
			# Single form: "new life goal home" (no colon)
			re.compile(
				r'^\s*(?:new|add)\s+(?:life\s+)?'
				r'(?P<noun>goal|goals|dream|dreams|wish|wishes|idea|ideas|resolution|resolutions|item|todo|task|entry)\s+'
				r'(?P<title>.{1,200})$',
				re.IGNORECASE,
			),
		],
		"create_card": [
			# "add/create/new card|task <title> to|on|in <list-or-board>"
			re.compile(r'\b(?:add|create|new|make)\s+(?:a\s+|the\s+)?(?:card|task|todo|to-do)\s+(?:named\s+|called\s+)?(.{1,200}?)(?:\s+(?:to|on|in|under)\s+(.{1,200}))?$', re.IGNORECASE),
			# "add <title> card|task to|on|in <list-or-board>" (postfix noun)
			re.compile(r'\b(?:add|create|new)\s+(?:a\s+|the\s+)?(.{1,200}?)\s+(?:card|task|todo|to-do)(?:\s+(?:to|on|in|under)\s+(.{1,200}))?$', re.IGNORECASE),
			# "add <title> to <list>" (no card noun, but explicit destination)
			re.compile(r'\b(?:add|put)\s+(.{1,200}?)\s+(?:to|on|onto|in|into)\s+(?:my\s+|the\s+)?(.{1,200}?)(?:\s+(?:list|board))?$', re.IGNORECASE),
		],
		"create_list": [
			re.compile(r'\b(?:add|create|new|make)\s+(?:a\s+|the\s+)?list\s+(?:called\s+|named\s+)?(.{1,200}?)(?:\s+(?:to|on|in|under)\s+(?:the\s+)?(.{1,200}))?$', re.IGNORECASE),
			re.compile(r'\b(?:add|create|new)\s+(.{1,200}?)\s+list(?:\s+(?:to|on|in|under)\s+(?:the\s+)?(.{1,200}))?$', re.IGNORECASE),
		],
		"archive_card": [
			re.compile(r'\barchive\s+(?:the\s+)?(?:card\s+)?(.{1,200})', re.IGNORECASE),
		],
		"mark_done": [
			re.compile(r'\bmark\s+(?:the\s+)?(?:card\s+)?(.{1,200}?)\s+(?:as\s+)?done\b', re.IGNORECASE),
			re.compile(r'\b(?:set|move)\s+(?:the\s+)?(?:card\s+)?(.{1,200}?)\s+to\s+done\b', re.IGNORECASE),
		],
		"set_card_desc": [
			re.compile(r'\b(?:set|update|change)\s+(?:the\s+)?desc(?:ription)?\s+(?:of\s+)?(?:the\s+)?(?:card\s+)?(.{1,200}?)\s+to\s+(.{1,200})', re.IGNORECASE),
			re.compile(r'\bdescribe\s+(?:the\s+)?(?:card\s+)?(.{1,200}?)\s+as\s+(.{1,200})', re.IGNORECASE),
		],
		"add_card_task": [
			re.compile(r'\b(?:add|create)\s+(?:a\s+)?(?:task|item|todo|checklist\s+item)\s+(.{1,200}?)\s+(?:to|on|in)\s+(?:the\s+)?card\s+(.{1,200})', re.IGNORECASE),
		],
		"rename_card_task": [
			re.compile(r'\brename\s+(?:the\s+)?(?:task|item|todo)\s+(.{1,200}?)\s+(?:in|on)\s+(?:the\s+)?(?:card\s+)?(.{1,200}?)\s+to\s+(.{1,200})', re.IGNORECASE),
		],
		"check_card_task": [
			re.compile(r'\b(?:check(?:\s+off)?|tick(?:\s+off)?|complete)\s+(?:the\s+)?(?:task|item|todo)\s+(.{1,200}?)\s+(?:in|on|of)\s+(?:the\s+)?(?:card\s+)?(.{1,200})', re.IGNORECASE),
			re.compile(r'\bmark\s+(?:the\s+)?(?:task|item|todo)\s+(.{1,200}?)\s+(?:in|on|of)\s+(?:the\s+)?(?:card\s+)?(.{1,200}?)\s+(?:as\s+)?(?!not\s)(?:done|complete|finished)\b', re.IGNORECASE),
		],
		"uncheck_card_task": [
			re.compile(r'\b(?:uncheck|untick|unmark|reopen)\s+(?:the\s+)?(?:task|item|todo)\s+(.{1,200}?)\s+(?:in|on|of)\s+(?:the\s+)?(?:card\s+)?(.{1,200})', re.IGNORECASE),
			re.compile(r'\bmark\s+(?:the\s+)?(?:task|item|todo)\s+(.{1,200}?)\s+(?:in|on|of)\s+(?:the\s+)?(?:card\s+)?(.{1,200}?)\s+(?:as\s+)?(?:not\s+done|undone|incomplete)\b', re.IGNORECASE),
		],
		"delete_card": [
			re.compile(r'\b(?:delete|remove|discard|trash)\s+(?:the\s+)?card\s+(.{1,200})', re.IGNORECASE),
		],
		"delete_list": [
			re.compile(r'\b(?:delete|remove|discard)\s+(?:the\s+)?(?:list|column)\s+(.{1,200})', re.IGNORECASE),
		],
		"delete_card_task": [
			re.compile(r'\b(?:delete|remove)\s+(?:the\s+)?(?:task|item|todo)\s+(.{1,200}?)\s+(?:from|in|on)\s+(?:the\s+)?(?:card\s+)?(.{1,200})', re.IGNORECASE),
		],
		"create_board": [
			re.compile(r'\b(?:create|add|make|new)\s+(?:a\s+)?board\s+(?:called\s+|named\s+)?(.{1,200}?)(?:\s+(?:in|to|inside|under)\s+(?:the\s+)?(?:project\s+)?(.{1,200}))?$', re.IGNORECASE),
		],
		"rename_board": [
			re.compile(r'\b(?:rename|change\s+the\s+name\s+of)\s+(?:the\s+)?board\s+(.{1,200}?)\s+to\s+(.{1,200})', re.IGNORECASE),
			re.compile(r'\bchange\s+(?:the\s+)?board\s+name\s+(.{1,200}?)\s+to\s+(.{1,200})', re.IGNORECASE),
		],
		"delete_board": [
			re.compile(r'\b(?:delete|remove|discard|trash)\s+(?:the\s+)?board\s+(.{1,200})', re.IGNORECASE),
		],
		"create_project": [
			re.compile(r'\b(?:create|add|make|new)\s+(?:a\s+)?project\s+(?:called\s+|named\s+)?(.{1,200})', re.IGNORECASE),
		],
		"rename_project": [
			re.compile(r'\b(?:rename|change\s+the\s+name\s+of)\s+(?:the\s+)?project\s+(.{1,200}?)\s+to\s+(.{1,200})', re.IGNORECASE),
			re.compile(r'\bchange\s+(?:the\s+)?project\s+name\s+(.{1,200}?)\s+to\s+(.{1,200})', re.IGNORECASE),
		],
		"delete_project": [
			re.compile(r'\b(?:delete|remove|discard|trash)\s+(?:the\s+)?project\s+(.{1,200})', re.IGNORECASE),
		],
		"hedges": [
			re.compile(r'\b(?:thinking\s+about|considering|maybe|might|should\s+i|could\s+i|how\s+(?:do|to|can)\s+i|what\s+(?:does|is|happens)|why\s+(?:would|should))\b', re.IGNORECASE),
			re.compile(r"\b(?:was|were)\s+(?:thinking|planning|considering)\b", re.IGNORECASE),
			re.compile(r'\b(?:explain|tell\s+me\s+about|describe)\b', re.IGNORECASE),
		],
	},
	# ── German ────────────────────────────────────────────────────────────
	"de": {
		"sort_board": [
			# End-anchored pattern: always tried first. Handles "sortiere Listen und Karten
			# in potenziell neuen Listen im Aquarium-Board" by anchoring at end of string.
			re.compile(
				r'\b(?:sortier[e]?|reorganisier[e]?|neu\s+sortier[e]?|aufräum[e]?n?|umstrukturieren|neu\s+anordnen)\b'
				r'.{0,300}'
				r'\b(?:in|im|auf|für)\s+(?:dem\s+|das\s+|der\s+)?(?:board\s+)?(?P<board>[a-z0-9äöüÄÖÜß][\w\s]{2,40})\s*$',
				re.IGNORECASE,
			),
			# Simple non-greedy fallback: "sortiere [das] [Board] <name>".
			re.compile(
				r'\b(?:sortier[e]?|reorganisier[e]?|neu\s+sortier[e]?|aufräum[e]?n?|umstrukturieren|neu\s+anordnen)\b'
				r'(?:\s+(?:listen?|karten?|und|in|potenziell|neue|\s)+)?'
				r'(?:in|auf|für|das\s+)?(?:board\s+)?(?P<board>[a-z0-9äöüÄÖÜß][\w\s]{2,50})',
				re.IGNORECASE,
			),
		],
		"move_board": [
			re.compile(r'\bverschieb[e]?\s+(?:das\s+)?(.{1,200}?)[-\s]board\s+(?:zu|in|nach|unter)\s+(.{1,200})', re.IGNORECASE),
			re.compile(r'\bverschieb[e]?\s+(?:das\s+)?board\s+(.{1,200}?)\s+(?:zu|in|nach|unter)\s+(.{1,200})', re.IGNORECASE),
		],
		"move_card": [
			re.compile(r'\bverschieb[e]?\s+(?:die\s+)?karte\s+(.{1,200}?)\s+(?:zu|in|nach)\s+(.{1,200})', re.IGNORECASE),
		],
		"rename_card": [
			re.compile(r'\b(?:umbenenn(?:en?|t)?)\s+(?:die\s+)?(?:karte\s+)?(.{1,200}?)\s+(?:in|zu|nach)\s+(.{1,200})', re.IGNORECASE),
			re.compile(r'\b(?:benenn[e]?)\s+(?:die\s+)?(?:karte\s+)?(.{1,200}?)\s+(?:in|zu|nach)\s+(.{1,200}?)(?:\s+um)?$', re.IGNORECASE),
		],
		"rename_list": [
			re.compile(r'\b(?:umbenenn(?:en?|t)?)\s+(?:die\s+)?(?:liste|spalte|kolumne)\s+(.{1,200}?)\s+(?:in|zu|nach)\s+(.{1,200})', re.IGNORECASE),
			re.compile(r'\b(?:benenn[e]?)\s+(?:die\s+)?(?:liste|spalte|kolumne)\s+(.{1,200}?)\s+(?:in|zu|nach)\s+(.{1,200}?)(?:\s+um)?$', re.IGNORECASE),
		],
		# "neues ziel X", "new goal X", "neuer dream X" — anchored shorthand
		# Also handles bulk: "neue ziele: home, essen, garten"
		"board_item_add": [
			# Bulk form with colon
			re.compile(
				r'^\s*(?:new|neues?|neuer?|neue?|hinzufügen)\s+(?:life\s+|lebens)?'
				r'(?P<noun>ziel|ziele|traum|träume|wunsch|wünsche|idee|ideen|vorsatz|vorsätze|goal|goals|dream|dreams|wish|wishes|item|items|todo|todos|aufgabe|aufgaben|eintrag|einträge|task|tasks|entry|entries)'
				r'\s*:\s*(?P<titles>[\w\s,;\-äöüÄÖÜß]{2,2000})$',
				re.IGNORECASE | re.DOTALL,
			),
			# Single form (no colon)
			re.compile(
				r'^\s*(?:new|neues?|neuer?|neue?|hinzufügen)\s+(?:life\s+|lebens)?'
				r'(?P<noun>ziel|ziele|traum|träume|wunsch|wünsche|idee|ideen|vorsatz|vorsätze|goal|goals|dream|dreams|wish|wishes|item|todo|aufgabe|eintrag|task|entry)\s+'
				r'(?P<title>.{1,200})$',
				re.IGNORECASE,
			),
		],
		"create_card": [
			re.compile(r'\b(?:erstell[e]?|f[üu]g[e]?\s+hinzu|leg[e]?\s+an|neu[e]?)\s+(?:eine\s+)?(?:karte|aufgabe|task|todo)\s+(?:namens?\s+|mit\s+dem\s+namen\s+)?(.{1,200}?)(?:\s+(?:zu|in|auf|unter)\s+(.{1,200}))?$', re.IGNORECASE),
			re.compile(r'\b(?:f[üu]g[e]?)\s+(.{1,200}?)\s+(?:zu|in|auf)\s+(?:meine[rn]?\s+|der\s+|die\s+|das\s+)?(.{1,200}?)(?:\s+(?:hinzu|liste|board))?$', re.IGNORECASE),
		],
		"create_list": [
			re.compile(r'\b(?:erstell[e]?|f[üu]g[e]?\s+hinzu|leg[e]?\s+an|neu[e]?)\s+(?:eine\s+)?(?:liste|spalte)\s+(?:namens?\s+|mit\s+dem\s+namen\s+)?(.{1,200}?)(?:\s+(?:zu[mr]?|in|auf|unter)\s+(?:dem\s+|das\s+|der\s+)?(?:board\s+)?(.{1,200}))?$', re.IGNORECASE),
			re.compile(r'\b(?:f[üu]g[e]?)\s+(?:eine\s+)?(?:liste|spalte)\s+(.{1,200}?)\s+(?:zu[mr]?|in|auf)\s+(?:dem\s+|das\s+|der\s+)?(.{1,200}?)(?:\s+hinzu)?$', re.IGNORECASE),
		],
		"archive_card": [
			re.compile(r'\barchivier[e]?\s+(?:die\s+)?(?:karte\s+)?(.{1,200})', re.IGNORECASE),
		],
		"mark_done": [
			re.compile(r'\bmarkier[e]?\s+(?:die\s+)?(?:karte\s+)?(.{1,200}?)\s+(?:als\s+)?(?:erledigt|fertig)\b', re.IGNORECASE),
		],
		"set_card_desc": [
			re.compile(r'\b(?:setze?|[\xc3\xa4a]ndere?|aktualisiere?)\s+(?:die\s+)?Beschreibung\s+(?:von\s+)?(?:der\s+)?(?:Karte\s+)?(.{1,200}?)\s+(?:auf|zu|in)\s+(.{1,200})', re.IGNORECASE),
			re.compile(r'\bbeschreibe?\s+(?:die\s+)?(?:Karte\s+)?(.{1,200}?)\s+als\s+(.{1,200})', re.IGNORECASE),
		],
		"add_card_task": [
			re.compile(r'\bf[\xfc u]ge?\s+(?:eine[n]?\s+)?(?:Aufgabe|Todo|Eintrag)\s+(.{1,200}?)\s+zur?\s+(?:der\s+)?Karte\s+(.{1,200})\s+hinzu', re.IGNORECASE),
		],
		"rename_card_task": [
			re.compile(r'\b(?:umbenenn(?:en?|t)?)\s+(?:die\s+)?(?:Aufgabe|Todo)\s+(.{1,200}?)\s+(?:in|bei|von)\s+(?:der\s+)?(?:Karte\s+)?(.{1,200}?)\s+(?:in|zu|nach)\s+(.{1,200})', re.IGNORECASE),
		],
		"check_card_task": [
			re.compile(r'\b(?:abhake?n?|abhak[e]?|erledige?)\s+(?:die\s+)?(?:Aufgabe|Todo)\s+(.{1,200}?)\s+(?:in|bei|auf)\s+(?:der\s+)?(?:Karte\s+)?(.{1,200})', re.IGNORECASE),
			re.compile(r'\bmarkiere?\s+(?:die\s+)?(?:Aufgabe|Todo)\s+(.{1,200}?)\s+(?:in|bei|auf)\s+(?:der\s+)?(?:Karte\s+)?(.{1,200}?)\s+als\s+(?:erledigt|fertig|abgeschlossen)\b', re.IGNORECASE),
		],
		"uncheck_card_task": [
			re.compile(r'\bmarkiere?\s+(?:die\s+)?(?:Aufgabe|Todo)\s+(.{1,200}?)\s+(?:in|bei|auf)\s+(?:der\s+)?(?:Karte\s+)?(.{1,200}?)\s+als\s+(?:nicht\s+erledigt|offen|unerledigt)\b', re.IGNORECASE),
		],
		"delete_card": [
			re.compile(r'\b(?:lösch[e]?|entfern[e]?)\s+(?:die\s+)?karte\s+(.{1,200})', re.IGNORECASE),
		],
		"delete_list": [
			re.compile(r'\b(?:lösch[e]?|entfern[e]?)\s+(?:die\s+)?(?:liste|spalte)\s+(.{1,200})', re.IGNORECASE),
		],
		"delete_card_task": [
			re.compile(r'\b(?:lösch[e]?|entfern[e]?)\s+(?:die\s+)?aufgabe\s+(.{1,200}?)\s+(?:von|aus|in|auf)\s+(?:der\s+)?(?:karte\s+)?(.{1,200})', re.IGNORECASE),
		],
		"create_board": [
			re.compile(r'\b(?:erstell[e]?|leg[e]\s+an|f\u00fcge?\s+hinzu|neue[sr]?)\s+(?:ein(?:em?)?\s+)?(?:Board|Tafel|Pinnwand)\s+(?:namens\s+|mit\s+(?:dem\s+)?Namen\s+)?(.{1,200}?)(?:\s+(?:in|bei|unter)\s+(.{1,200}))?$', re.IGNORECASE),
		],
		"rename_board": [
			re.compile(r'\b(?:benennt?\s+um|umbenenn(?:e|en)?)\s+(?:das\s+)?(?:Board|Tafel|Pinnwand)\s+(.{1,200}?)\s+(?:in|zu)\s+(.{1,200})', re.IGNORECASE),
			re.compile(r'\b\u00e4ndere?\s+(?:den\s+)?Namen\s+(?:des\s+)?(?:Boards?|Tafel)\s+(.{1,200}?)\s+(?:in|zu)\s+(.{1,200})', re.IGNORECASE),
		],
		"delete_board": [
			re.compile(r'\b(?:l\u00f6sch[e]?|entfern[e]?)\s+(?:das\s+)?(?:Board|Tafel|Pinnwand)\s+(.{1,200})', re.IGNORECASE),
		],
		"create_project": [
			re.compile(r'\b(?:erstell[e]?|leg[e]\s+an|neue[sr]?)\s+(?:ein(?:em?)?\s+)?(?:Projekt)\s+(?:namens\s+|mit\s+(?:dem\s+)?Namen\s+)?(.{1,200})', re.IGNORECASE),
		],
		"rename_project": [
			re.compile(r'\b(?:benennt?\s+um|umbenenn(?:e|en)?)\s+(?:das\s+)?Projekt\s+(.{1,200}?)\s+(?:in|zu)\s+(.{1,200})', re.IGNORECASE),
			re.compile(r'\b\u00e4ndere?\s+(?:den\s+)?Namen\s+(?:des\s+)?Projekts?\s+(.{1,200}?)\s+(?:in|zu)\s+(.{1,200})', re.IGNORECASE),
		],
		"delete_project": [
			re.compile(r'\b(?:l\u00f6sch[e]?|entfern[e]?)\s+(?:das\s+)?Projekt\s+(.{1,200})', re.IGNORECASE),
		],
		"hedges": [
			re.compile(r'\b(?:vielleicht|eventuell|sollte\s+ich|könnte\s+ich|wie\s+(?:kann|soll)\s+ich|was\s+(?:bedeutet|ist|passiert)|warum)\b', re.IGNORECASE),
			re.compile(r'\b(?:erkläre|erklär|sag\s+mir|beschreibe)\b', re.IGNORECASE),
		],
	},
	# ── Spanish ───────────────────────────────────────────────────────────
	"es": {
		"sort_board": [
			re.compile(
				r'\b(?:ordena[r]?|sortea[r]?|reorganiza[r]?|reestructura[r]?|limpia[r]?|reordena[r]?|arregla[r]?)\b'
				r'(?:\s+(?:listas?|tarjetas?|y|en|nuevas?|\s)+)?'
				r'(?:en|en\s+el|del?\s+)?(?:tablero\s+)?(?P<board>[a-z0-9][\w\s]{2,50})',
				re.IGNORECASE,
			),
		],
		"move_board": [
			re.compile(r'\b(?:mueve|mover|muevo)\s+(?:el|la)?\s*tablero\s+(.{1,200}?)\s+(?:a|hacia|hasta|en)\s+(.{1,200})', re.IGNORECASE),
			re.compile(r'\b(?:mueve|mover|muevo)\s+(?:el|la)?\s*(.{1,200}?)\s+tablero\s+(?:a|hacia|hasta|en)\s+(.{1,200})', re.IGNORECASE),
		],
		"move_card": [
			re.compile(r'\b(?:mueve|mover|muevo)\s+(?:la|el)?\s*tarjeta\s+(.{1,200}?)\s+(?:a|hacia|hasta|en)\s+(.{1,200})', re.IGNORECASE),
		],
		"rename_card": [
			re.compile(r'\b(?:renombra[r]?|cambia[r]?\s+(?:el\s+)?nombre)\s+(?:la|el)?\s*(?:tarjeta\s+)?(.{1,200}?)\s+(?:a|por|como)\s+(.{1,200})', re.IGNORECASE),
		],
		"rename_list": [
			re.compile(r'\b(?:renombra[r]?|cambia[r]?\s+(?:el\s+)?nombre)\s+(?:la|el)?\s*(?:lista|columna)\s+(.{1,200}?)\s+(?:a|por|como)\s+(.{1,200})', re.IGNORECASE),
		],
		"create_card": [
			re.compile(r'\b(?:agrega[r]?|añade[r]?|crea[r]?|nueva?)\s+(?:una?\s+)?(?:tarjeta|tarea|todo)\s+(?:llamad[ao]?\s+|con\s+nombre\s+)?(.{1,200}?)(?:\s+(?:a|en)\s+(.{1,200}))?$', re.IGNORECASE),
			re.compile(r'\b(?:agrega[r]?|añade[r]?)\s+(.{1,200}?)\s+(?:a|en)\s+(?:mi\s+|el\s+|la\s+)?(.{1,200}?)(?:\s+(?:lista|tablero))?$', re.IGNORECASE),
		],
		"create_list": [
			re.compile(r'\b(?:agrega[r]?|crea[r]?|nueva?)\s+(?:una?\s+)?(?:lista|columna)\s+(?:llamada?\s+|con\s+nombre\s+)?(.{1,200}?)(?:\s+(?:a|en|sobre)\s+(?:el\s+|la\s+)?(?:board\s+|tablero\s+)?(.{1,200}))?$', re.IGNORECASE),
		],
		"archive_card": [
			re.compile(r'\barchiv(?:a|ar|o)\s+(?:la|el)?\s*(?:tarjeta\s+)?(.{1,200})', re.IGNORECASE),
		],
		"mark_done": [
			re.compile(r'\bmarc(?:a|ar|o)\s+(?:la|el)?\s*(?:tarjeta\s+)?(.{1,200}?)\s+(?:como\s+)?(?:hech[oa]|complet(?:ad[oa]|o)|terminad[oa]|list[oa])\b', re.IGNORECASE),
		],
		"set_card_desc": [
			re.compile(r'\b(?:establece[r]?|cambia[r]?|actualiza[r]?)\s+(?:la\s+)?descripci[o\xf3]n\s+(?:de\s+)?(?:la\s+)?(?:tarjeta\s+)?(.{1,200}?)\s+(?:a|como)\s+(.{1,200})', re.IGNORECASE),
		],
		"add_card_task": [
			re.compile(r'\b(?:agrega[r]?|a[\xf1n]ade[r]?)\s+(?:una?\s+)?(?:tarea|elemento|todo)\s+(.{1,200}?)\s+(?:a|en)\s+(?:la\s+)?tarjeta\s+(.{1,200})', re.IGNORECASE),
		],
		"rename_card_task": [
			re.compile(r'\brenombra[r]?\s+(?:la\s+)?(?:tarea|elemento)\s+(.{1,200}?)\s+en\s+(?:la\s+)?(?:tarjeta\s+)?(.{1,200}?)\s+(?:a|como)\s+(.{1,200})', re.IGNORECASE),
		],
		"check_card_task": [
			re.compile(r'\b(?:marca[r]?|completa[r]?)\s+(?:la\s+)?(?:tarea|elemento)\s+(.{1,200}?)\s+(?:en|de)\s+(?:la\s+)?(?:tarjeta\s+)?(.{1,200})', re.IGNORECASE),
		],
		"uncheck_card_task": [
			re.compile(r'\b(?:desmarca[r]?|quita[r]?\s+la\s+marca)\s+(?:la\s+)?(?:tarea|elemento)\s+(.{1,200}?)\s+(?:en|de)\s+(?:la\s+)?(?:tarjeta\s+)?(.{1,200})', re.IGNORECASE),
		],
		"delete_card": [
			re.compile(r'\b(?:eliminar?|borra[r]?|quitar?)\s+(?:la\s+)?tarjeta\s+(.{1,200})', re.IGNORECASE),
		],
		"delete_list": [
			re.compile(r'\b(?:eliminar?|borra[r]?|quitar?)\s+(?:la\s+)?(?:lista|columna)\s+(.{1,200})', re.IGNORECASE),
		],
		"delete_card_task": [
			re.compile(r'\b(?:eliminar?|borra[r]?|quitar?)\s+(?:la\s+)?tarea\s+(.{1,200}?)\s+(?:de|en)\s+(?:la\s+)?(?:tarjeta\s+)?(.{1,200})', re.IGNORECASE),
		],
		"create_board": [
			re.compile(r'\b(?:crear?|a\u00f1adir?|agregar?|nuevo|nueva)\s+(?:un\s+)?(?:tablero|board)\s+(?:llamado\s+|con\s+nombre\s+)?(.{1,200}?)(?:\s+(?:en|dentro\s+de)\s+(.{1,200}))?$', re.IGNORECASE),
		],
		"rename_board": [
			re.compile(r'\b(?:renombrar?)\s+(?:el\s+)?(?:tablero|board)\s+(.{1,200}?)\s+(?:a|por)\s+(.{1,200})', re.IGNORECASE),
			re.compile(r'\bcambiar?\s+(?:el\s+)?nombre\s+(?:del?\s+)?(?:tablero|board)\s+(.{1,200}?)\s+(?:a|por)\s+(.{1,200})', re.IGNORECASE),
		],
		"delete_board": [
			re.compile(r'\b(?:eliminar?|borrar?|suprimir)\s+(?:el\s+)?(?:tablero|board)\s+(.{1,200})', re.IGNORECASE),
		],
		"create_project": [
			re.compile(r'\b(?:crear?|a\u00f1adir?|agregar?)\s+(?:un\s+)?proyecto\s+(?:llamado\s+|con\s+nombre\s+)?(.{1,200})', re.IGNORECASE),
		],
		"rename_project": [
			re.compile(r'\b(?:renombrar?)\s+(?:el\s+)?proyecto\s+(.{1,200}?)\s+(?:a|por)\s+(.{1,200})', re.IGNORECASE),
			re.compile(r'\bcambiar?\s+(?:el\s+)?nombre\s+(?:del?\s+)?proyecto\s+(.{1,200}?)\s+(?:a|por)\s+(.{1,200})', re.IGNORECASE),
		],
		"delete_project": [
			re.compile(r'\b(?:eliminar?|borrar?|suprimir)\s+(?:el\s+)?proyecto\s+(.{1,200})', re.IGNORECASE),
		],
		"hedges": [
			re.compile(r'\b(?:estaba\s+pensando|tal\s+vez|quizás|quiza|debería|deberia|cómo|como\s+se|qué\s+significa|que\s+significa|por\s+qué|por\s+que)\b', re.IGNORECASE),
			re.compile(r'\b(?:explica|explícame|explicame|describe|cuéntame|cuentame)\b', re.IGNORECASE),
		],
	},
	# ── French ────────────────────────────────────────────────────────────
	"fr": {
		"sort_board": [
			re.compile(
				r'\b(?:trie[r]?|réorganise[r]?|reorganise[r]?|restructure[r]?|range[r]?|classe[r]?|réordonne[r]?|reordonne[r]?)\b'
				r'(?:\s+(?:listes?|cartes?|et|dans|nouvelles?|\s)+)?'
				r'(?:dans\s+(?:le\s+)?|du\s+)?(?:tableau\s+)?(?P<board>[a-z0-9][\w\s]{2,50})',
				re.IGNORECASE,
			),
		],
		"move_board": [
			re.compile(r'\bdéplac(?:e|er|ez)\s+(?:le|la)?\s*tableau\s+(.{1,200}?)\s+(?:vers|à|dans|en)\s+(.{1,200})', re.IGNORECASE),
			re.compile(r'\bdeplac(?:e|er|ez)\s+(?:le|la)?\s*tableau\s+(.{1,200}?)\s+(?:vers|à|dans|en)\s+(.{1,200})', re.IGNORECASE),
		],
		"move_card": [
			re.compile(r'\bdéplac(?:e|er|ez)\s+(?:la|le)?\s*carte\s+(.{1,200}?)\s+(?:vers|à|dans)\s+(.{1,200})', re.IGNORECASE),
			re.compile(r'\bdeplac(?:e|er|ez)\s+(?:la|le)?\s*carte\s+(.{1,200}?)\s+(?:vers|à|dans)\s+(.{1,200})', re.IGNORECASE),
		],
		"rename_card": [
			re.compile(r'\brenomm(?:e|er|ez)\s+(?:la|le)?\s*(?:carte\s+)?(.{1,200}?)\s+(?:en|par)\s+(.{1,200})', re.IGNORECASE),
		],
		"rename_list": [
			re.compile(r'\brenomm(?:e|er|ez)\s+(?:la|le)?\s*(?:liste|colonne)\s+(.{1,200}?)\s+(?:en|par)\s+(.{1,200})', re.IGNORECASE),
		],
		"create_card": [
			re.compile(r'\b(?:ajoute[rz]?|créer?|crée|nouvelle?)\s+(?:une?\s+)?(?:carte|tâche|tache|todo)\s+(?:appel[eé]e?\s+|nomm[eé]e?\s+)?(.{1,200}?)(?:\s+(?:vers|à|dans|en|sur)\s+(.{1,200}))?$', re.IGNORECASE),
			re.compile(r'\b(?:ajoute[rz]?)\s+(.{1,200}?)\s+(?:à|dans|en|sur)\s+(?:ma\s+|mon\s+|la\s+|le\s+|les\s+)?(.{1,200}?)(?:\s+(?:liste|tableau))?$', re.IGNORECASE),
		],
		"create_list": [
			re.compile(r'\b(?:ajoute[rz]?|créer?|crée|nouvelle?)\s+(?:une?\s+)?(?:liste|colonne)\s+(?:appelée?\s+|nommée?\s+)?(.{1,200}?)(?:\s+(?:vers|à|dans|en|sur)\s+(?:le\s+|la\s+)?(?:tableau\s+)?(.{1,200}))?$', re.IGNORECASE),
		],
		"archive_card": [
			re.compile(r'\barchiv(?:e|er|ez)\s+(?:la|le)?\s*(?:carte\s+)?(.{1,200})', re.IGNORECASE),
		],
		"mark_done": [
			re.compile(r'\bmarqu(?:e|er|ez)\s+(?:la|le)?\s*(?:carte\s+)?(.{1,200}?)\s+(?:comme\s+)?(?:terminée?|finie?|faite?|achevée?)\b', re.IGNORECASE),
		],
		"set_card_desc": [
			re.compile(r'\b(?:d[\xe9e]fini[rst]?|change[rz]?|mets?|modif(?:ie[rz]?))\s+(?:la\s+)?description\s+(?:de\s+)?(?:la\s+)?(?:carte\s+)?(.{1,200}?)\s+(?:[\xe0a]|en)\s+(.{1,200})', re.IGNORECASE),
		],
		"add_card_task": [
			re.compile(r'\b(?:ajoute[rz]?|ajoute)\s+(?:une?\s+)?(?:t[\xe2a]che|[\xe9e]l[\xe9e]ment|todo)\s+(.{1,200}?)\s+(?:[\xe0a]|dans|sur)\s+(?:la\s+)?carte\s+(.{1,200})', re.IGNORECASE),
		],
		"rename_card_task": [
			re.compile(r'\brennomm(?:ez?|er?)\s+(?:la\s+)?(?:t[\xe2a]che|[\xe9e]l[\xe9e]ment)\s+(.{1,200}?)\s+(?:dans|sur|de)\s+(?:la\s+)?(?:carte\s+)?(.{1,200}?)\s+en\s+(.{1,200})', re.IGNORECASE),
		],
		"check_card_task": [
			re.compile(r'\b(?:coche[rz]?|compl[\xe9e]ter?|marqu[\xe9e]?e?\s+comme\s+termin[\xe9e])\s+(?:la\s+)?(?:t[\xe2a]che|[\xe9e]l[\xe9e]ment)\s+(.{1,200}?)\s+(?:dans|sur|de)\s+(?:la\s+)?(?:carte\s+)?(.{1,200})', re.IGNORECASE),
		],
		"uncheck_card_task": [
			re.compile(r'\b(?:d[\xe9e]cochez?|d[\xe9e]coche[rz]?)\s+(?:la\s+)?(?:t[\xe2a]che|[\xe9e]l[\xe9e]ment)\s+(.{1,200}?)\s+(?:dans|sur|de)\s+(?:la\s+)?(?:carte\s+)?(.{1,200})', re.IGNORECASE),
		],
		"delete_card": [
			re.compile(r'\b(?:supprimer?|supprime[rz]?|effacer?|enlever?)\s+(?:la\s+)?carte\s+(.{1,200})', re.IGNORECASE),
		],
		"delete_list": [
			re.compile(r'\b(?:supprimer?|supprime[rz]?|effacer?|enlever?)\s+(?:la\s+)?(?:liste|colonne)\s+(.{1,200})', re.IGNORECASE),
		],
		"delete_card_task": [
			re.compile(r'\b(?:supprimer?|supprime[rz]?|effacer?|enlever?)\s+(?:la\s+)?(?:t[\xe2a]che|[\xe9e]l[\xe9e]ment)\s+(.{1,200}?)\s+(?:de|dans)\s+(?:la\s+)?(?:carte\s+)?(.{1,200})', re.IGNORECASE),
		],
		"create_board": [
			re.compile(r'\b(?:cr\u00e9e[r]?|ajouter?|nouveau|nouvelle)\s+(?:un\s+)?(?:tableau|board)\s+(?:appel\u00e9\s+|nomm\u00e9\s+)?(.{1,200}?)(?:\s+(?:dans|en)\s+(.{1,200}))?$', re.IGNORECASE),
		],
		"rename_board": [
			re.compile(r'\b(?:renomme[r]?)\s+(?:le\s+)?(?:tableau|board)\s+(.{1,200}?)\s+(?:en|par)\s+(.{1,200})', re.IGNORECASE),
			re.compile(r'\bchanger?\s+(?:le\s+)?nom\s+(?:du\s+)?(?:tableau|board)\s+(.{1,200}?)\s+(?:en|par)\s+(.{1,200})', re.IGNORECASE),
		],
		"delete_board": [
			re.compile(r'\b(?:supprime[r]?|efface[r]?|enl\u00e8ve[r]?)\s+(?:le\s+)?(?:tableau|board)\s+(.{1,200})', re.IGNORECASE),
		],
		"create_project": [
			re.compile(r'\b(?:cr\u00e9er?|ajouter?)\s+(?:un\s+)?projet\s+(?:appel\u00e9\s+|nomm\u00e9\s+)?(.{1,200})', re.IGNORECASE),
		],
		"rename_project": [
			re.compile(r'\b(?:renomme[r]?)\s+(?:le\s+)?projet\s+(.{1,200}?)\s+(?:en|par)\s+(.{1,200})', re.IGNORECASE),
			re.compile(r'\bchanger?\s+(?:le\s+)?nom\s+(?:du\s+)?projet\s+(.{1,200}?)\s+(?:en|par)\s+(.{1,200})', re.IGNORECASE),
		],
		"delete_project": [
			re.compile(r'\b(?:supprime[r]?|efface[r]?|enl\u00e8ve[r]?)\s+(?:le\s+)?projet\s+(.{1,200})', re.IGNORECASE),
		],
		"hedges": [
			re.compile(r'\b(?:je\s+pensais|peut[- ]être|devrais[- ]je|pourrais[- ]je|comment\s+(?:est-ce|puis|dois)|qu(?:e|\u2019)est[- ]ce\s+que|pourquoi)\b', re.IGNORECASE),
			re.compile(r'\b(?:explique|décris|decris|raconte)\b', re.IGNORECASE),
		],
	},
	# ── Portuguese ────────────────────────────────────────────────────────
	"pt": {
		"sort_board": [
			re.compile(
				r'\b(?:ordena[r]?|reorganiza[r]?|reestrutura[r]?|arruma[r]?|classifica[r]?|reordena[r]?)\b'
				r'(?:\s+(?:listas?|cartões?|cartoes?|e|em|novas?|\s)+)?'
				r'(?:em\s+(?:o\s+)?|do\s+)?(?:quadro\s+)?(?P<board>[a-z0-9][\w\s]{2,50})',
				re.IGNORECASE,
			),
		],
		"move_board": [
			re.compile(r'\b(?:mova|mover|move)\s+(?:o|a)?\s*quadro\s+(.{1,200}?)\s+(?:para|a|em)\s+(.{1,200})', re.IGNORECASE),
		],
		"move_card": [
			re.compile(r'\b(?:mova|mover|move)\s+(?:a|o)?\s*(?:cartão|cartao|carta)\s+(.{1,200}?)\s+(?:para|a|em)\s+(.{1,200})', re.IGNORECASE),
		],
		"rename_card": [
			re.compile(r'\b(?:renomear?|renomeie)\s+(?:o|a)?\s*(?:cartão|cartao\s+)?(.{1,200}?)\s+(?:para|como)\s+(.{1,200})', re.IGNORECASE),
		],
		"rename_list": [
			re.compile(r'\b(?:renomear?|renomeie)\s+(?:o|a)?\s*(?:lista|coluna)\s+(.{1,200}?)\s+(?:para|como)\s+(.{1,200})', re.IGNORECASE),
		],
		"create_card": [
			re.compile(r'\b(?:adicionar?|adicione|criar?|crie|nova?)\s+(?:um[a]?\s+)?(?:cartão|cartao|tarefa|todo)\s+(?:chamad[ao]?\s+|com\s+nome\s+)?(.{1,200}?)(?:\s+(?:para|em|n[ao])\s+(.{1,200}))?$', re.IGNORECASE),
			re.compile(r'\b(?:adicionar?|adicione)\s+(.{1,200}?)\s+(?:para|em|n[ao])\s+(?:minha?\s+|meu\s+|a\s+|o\s+)?(.{1,200}?)(?:\s+(?:lista|quadro))?$', re.IGNORECASE),
		],
		"create_list": [
			re.compile(r'\b(?:adicionar?|adicione|criar?|crie|nova?)\s+(?:uma?\s+)?(?:lista|coluna)\s+(?:chamada?\s+|com\s+nome\s+)?(.{1,200}?)(?:\s+(?:para|em|n[ao])\s+(?:o\s+|a\s+)?(?:quadro\s+)?(.{1,200}))?$', re.IGNORECASE),
		],
		"archive_card": [
			re.compile(r'\barquiv(?:a|ar|e)\s+(?:a|o)?\s*(?:cartão|cartao|carta\s+)?(.{1,200})', re.IGNORECASE),
		],
		"mark_done": [
			re.compile(r'\bmarc(?:a|ar|e)\s+(?:o|a)?\s*(?:cartão|cartao|carta\s+)?(.{1,200}?)\s+(?:como\s+)?(?:concluíd[oa]|concluido|feit[oa]|finalizad[oa]|pront[oa])\b', re.IGNORECASE),
		],		"set_card_desc": [
			re.compile(r'\b(?:definir?|mudar?|atualizar?)\s+(?:a\s+)?descri[c\xe7][a\xe3]o\s+(?:d[oa]\s+)?(?:cart[a\xe3]o\s+)?(.{1,200}?)\s+(?:para|como)\s+(.{1,200})', re.IGNORECASE),
		],
		"add_card_task": [
			re.compile(r'\b(?:adicionar?|adicione?)\s+(?:uma?\s+)?(?:tarefa|item|todo)\s+(.{1,200}?)\s+(?:ao?|no?|em)\s+cart[a\xe3]o\s+(.{1,200})', re.IGNORECASE),
		],
		"rename_card_task": [
			re.compile(r'\brenomear?\s+(?:a\s+)?(?:tarefa|item)\s+(.{1,200}?)\s+(?:no?|em)\s+(?:cart[a\xe3]o\s+)?(.{1,200}?)\s+para\s+(.{1,200})', re.IGNORECASE),
		],
		"check_card_task": [
			re.compile(r'\b(?:marcar?|completar?)\s+(?:a\s+)?(?:tarefa|item)\s+(.{1,200}?)\s+(?:no?|em)\s+(?:cart[a\xe3]o\s+)?(.{1,200}?)\s+(?:como\s+)?(?:conclu[i\xed]d[ao]|feit[ao]|pront[ao])\b', re.IGNORECASE),
		],
		"uncheck_card_task": [
			re.compile(r'\b(?:desmarcar?|desmarque)\s+(?:a\s+)?(?:tarefa|item)\s+(.{1,200}?)\s+(?:no?|em)\s+(?:cart[a\xe3]o\s+)?(.{1,200})', re.IGNORECASE),
		],
		"delete_card": [
			re.compile(r'\b(?:excluir?|apaga[r]?|remover?)\s+(?:o\s+|a\s+)?cart[a\xe3]o\s+(.{1,200})', re.IGNORECASE),
		],
		"delete_list": [
			re.compile(r'\b(?:excluir?|apaga[r]?|remover?)\s+(?:a\s+)?(?:lista|coluna)\s+(.{1,200})', re.IGNORECASE),
		],
		"delete_card_task": [
			re.compile(r'\b(?:excluir?|apaga[r]?|remover?)\s+(?:a\s+)?tarefa\s+(.{1,200}?)\s+(?:de|do|da)\s+(?:cart[a\xe3]o\s+)?(.{1,200})', re.IGNORECASE),
		],
		"create_board": [
			re.compile(r'\b(?:cria[r]?|adiciona[r]?|novo|nova)\s+(?:um\s+)?(?:quadro|board)\s+(?:chamado\s+|com\s+(?:o\s+)?nome\s+)?(.{1,200}?)(?:\s+(?:em|no|na|dentro\s+de)\s+(.{1,200}))?$', re.IGNORECASE),
		],
		"rename_board": [
			re.compile(r'\b(?:renomear?)\s+(?:o\s+)?(?:quadro|board)\s+(.{1,200}?)\s+para\s+(.{1,200})', re.IGNORECASE),
			re.compile(r'\bmuda[r]?\s+(?:o\s+)?nome\s+(?:do\s+)?(?:quadro|board)\s+(.{1,200}?)\s+para\s+(.{1,200})', re.IGNORECASE),
		],
		"delete_board": [
			re.compile(r'\b(?:excluir?|apaga[r]?|remove[r]?|deleta[r]?)\s+(?:o\s+)?(?:quadro|board)\s+(.{1,200})', re.IGNORECASE),
		],
		"create_project": [
			re.compile(r'\b(?:criar?|adicionar?|novo)\s+(?:um\s+)?projeto\s+(?:chamado\s+|com\s+nome\s+)?(.{1,200})', re.IGNORECASE),
		],
		"rename_project": [
			re.compile(r'\b(?:renomear?)\s+(?:o\s+)?projeto\s+(.{1,200}?)\s+para\s+(.{1,200})', re.IGNORECASE),
			re.compile(r'\bmuda[r]?\s+(?:o\s+)?nome\s+(?:do\s+)?projeto\s+(.{1,200}?)\s+para\s+(.{1,200})', re.IGNORECASE),
		],
		"delete_project": [
			re.compile(r'\b(?:excluir?|apaga[r]?|remove[r]?|deleta[r]?)\s+(?:o\s+)?projeto\s+(.{1,200})', re.IGNORECASE),
		],
		"hedges": [
			re.compile(r'\b(?:estava\s+pensando|talvez|deveria|poderia|como\s+(?:eu|posso)|o\s+que\s+significa|por\s+que|por\s+quê)\b', re.IGNORECASE),
			re.compile(r'\b(?:explica|explique|descreva|conte)\b', re.IGNORECASE),
		],
	},
	# ── Russian ───────────────────────────────────────────────────────────
	"ru": {
		"sort_board": [
			re.compile(
				r'(?:отсортируй|сортируй|реорганизуй|упорядочи|разбери|реструктурируй|разложи)\s+'
				r'(?:списки\s+|карточки\s+|и\s+|в\s+|новые\s+)*'
				r'(?:на\s+)?(?:доск[еу]\s+)?(?P<board>[а-яёА-ЯЁa-z0-9][\w\s]{2,50})',
				re.IGNORECASE,
			),
		],
		"move_board": [
			re.compile(r'(?:переместить?|перенест?и|перенеси|перемести)\s+(?:доску|борд)\s+(.{1,200}?)\s+(?:в|на|к)\s+(.{1,200})', re.IGNORECASE),
		],
		"move_card": [
			re.compile(r'(?:переместить?|перенест?и|перемести)\s+(?:карточку|карту)\s+(.{1,200}?)\s+(?:в|на|к)\s+(.{1,200})', re.IGNORECASE),
		],
		"rename_card": [
			re.compile(r'(?:переименуй|переименовать)\s+(?:карточку\s+)?(.{1,200}?)\s+(?:в|на)\s+(.{1,200})', re.IGNORECASE),
		],
		"rename_list": [
			re.compile(r'(?:переименуй|переименовать)\s+(?:список|колонку|столбец)\s+(.{1,200}?)\s+(?:в|на)\s+(.{1,200})', re.IGNORECASE),
		],
		"create_card": [
			re.compile(r'(?:добавь?|создай?|создать|новую?)\s+(?:карточку?|задачу?)?\s+(?:с\s+именем\s+|под\s+названием\s+)?(.{1,200}?)(?:\s+(?:в|на|к)\s+(.{1,200}))?$', re.IGNORECASE),
			re.compile(r'(?:добавь?)\s+(.{1,200}?)\s+(?:в|на|к)\s+(?:мою?\s+)?(.{1,200}?)(?:\s+(?:список|доску))?$', re.IGNORECASE),
		],
		"create_list": [
			re.compile(r'(?:добавь?|создай?|создать|новый?|новую?)\s+(?:список|колонку|столбец)\s+(?:с\s+названием\s+)?(.{1,200}?)(?:\s+(?:в|на|к)\s+(?:доску?\s+)?(.{1,200}))?$', re.IGNORECASE),
		],
		"archive_card": [
			re.compile(r'(?:заархивируй|архивируй|архивировать)\s+(?:карточку\s+)?(.{1,200})', re.IGNORECASE),
		],
		"mark_done": [
			re.compile(r'(?:отметь?|пометь?|отметить)\s+(?:карточку\s+)?(.{1,200}?)\s+(?:как\s+)?(?:готово|выполнено|завершено|сделано|выполнена)', re.IGNORECASE),
		],
		"set_card_desc": [
			re.compile(r'(?:установить?|изменить?|обновить?)\s+описание\s+(?:карточки\s+)?(.{1,200}?)\s+(?:на|как)\s+(.{1,200})', re.IGNORECASE),
		],
		"add_card_task": [
			re.compile(r'(?:добавить|добавь)\s+(?:задачу|задание|пункт)\s+(.{1,200}?)\s+(?:к|в|на)\s+(?:карточку?\s+)?(.{1,200})', re.IGNORECASE),
		],
		"rename_card_task": [
			re.compile(r'(?:переименовать|переименуй)\s+(?:задачу|задание)\s+(.{1,200}?)\s+(?:в|на)\s+(?:карточке?\s+)?(.{1,200}?)\s+(?:в|на)\s+(.{1,200})', re.IGNORECASE),
		],
		"check_card_task": [
			re.compile(r'(?:отметить?|отметь|выполнить?|выполни)\s+(?:задачу|задание)\s+(.{1,200}?)\s+(?:в|на)\s+(?:карточке?\s+)?(.{1,200})', re.IGNORECASE),
		],
		"uncheck_card_task": [
			re.compile(r'(?:снять?\s+отметку|снять?\s+галочку)\s+(?:с\s+)?(?:задачи|задания)\s+(.{1,200}?)\s+(?:в|на)\s+(?:карточке?\s+)?(.{1,200})', re.IGNORECASE),
		],
		"delete_card": [
			re.compile(r'(?:удали[тье]?|убери|удалить)\s+(?:карточку|карточка)\s+(.{1,200})', re.IGNORECASE),
		],
		"delete_list": [
			re.compile(r'(?:удали[тье]?|убери|удалить)\s+(?:список|колонку)\s+(.{1,200})', re.IGNORECASE),
		],
		"delete_card_task": [
			re.compile(r'(?:удали[тье]?|убери|удалить)\s+(?:задачу|задание)\s+(.{1,200}?)\s+(?:из|от)\s+(?:карточк[иу]\s+)?(.{1,200})', re.IGNORECASE),
		],
		"create_board": [
			re.compile(r'\b(?:создай|создать|добавь|добавить|новую?)\s+(?:доску|борд)\s+(?:с\s+(?:именем|названием)\s+|под\s+названием\s+)?(.{1,200}?)(?:\s+(?:в|для)\s+(.{1,200}))?$', re.IGNORECASE),
		],
		"rename_board": [
			re.compile(r'\b(?:переименуй?|переименовать)\s+(?:доску|борд)\s+(.{1,200}?)\s+(?:на|в)\s+(.{1,200})', re.IGNORECASE),
			re.compile(r'\bсмени?\s+название\s+(?:доски|борда)\s+(.{1,200}?)\s+(?:на|в)\s+(.{1,200})', re.IGNORECASE),
		],
		"delete_board": [
			re.compile(r'\b(?:удали?|удалить|убери?|убрать)\s+(?:доску|борд)\s+(.{1,200})', re.IGNORECASE),
		],
		"create_project": [
			re.compile(r'\b(?:создай?|создать|добавь|добавить)\s+(?:проект)\s+(.{1,200})', re.IGNORECASE),
		],
		"rename_project": [
			re.compile(r'\b(?:переименуй?|переименовать)\s+(?:проект)\s+(.{1,200}?)\s+(?:на|в)\s+(.{1,200})', re.IGNORECASE),
			re.compile(r'\bсмени?\s+название\s+проекта\s+(.{1,200}?)\s+(?:на|в)\s+(.{1,200})', re.IGNORECASE),
		],
		"delete_project": [
			re.compile(r'\b(?:удали?|удалить|убери?|убрать)\s+(?:проект)\s+(.{1,200})', re.IGNORECASE),
		],
		"hedges": [
			re.compile(r'(?:может\s+быть|возможно|следует\s+ли|стоит\s+ли|как\s+(?:мне|можно)|что\s+значит|зачем|почему)', re.IGNORECASE),
			re.compile(r'(?:объясни|расскажи|опиши)', re.IGNORECASE),
		],
	},
	# ── Japanese ──────────────────────────────────────────────────────────
	"ja": {
		"sort_board": [
			re.compile(
				r'(?:並べ替え|整理|再整理|ソート|並び替え)(?:て|し)?'
				r'(?:リスト|カード|と|に|新しい)*'
				r'(?P<board>[\w\s・]{2,50})(?:ボード|掲示板|の)?',
			),
		],
		"move_board": [
			re.compile(r'(.{1,200}?)(?:ボード|掲示板)を(.{1,200}?)(?:に|へ)(?:移動|動か)'),
		],
		"move_card": [
			re.compile(r'(.{1,200}?)(?:カード|タスク)を(.{1,200}?)(?:に|へ)(?:移動|動か)'),
		],
		"rename_card": [
			re.compile(r'(.{1,200}?)(?:カード|タスク)?の名前を(.{1,200}?)(?:に|へ)?(?:変更|変え|名前変更)'),
			re.compile(r'(.{1,200}?)を(.{1,200}?)に(?:名前変更|リネーム)'),
		],
		"rename_list": [
			re.compile(r'(?:リスト|列)(.{1,200}?)の名前を(.{1,200}?)(?:に|へ)?(?:変更|変え)'),
			re.compile(r'(?:リスト|列)(.{1,200}?)を(.{1,200}?)に(?:名前変更|リネーム)'),
		],
		"create_card": [
			re.compile(r'(.{1,200}?)(?:カード|タスク|todo)(?:を)?(?:作成|追加)(?:して)?(?:(.{1,200})に)?'),
			re.compile(r'(.{1,200}?)を(.{1,200}?)(?:に|へ)追加'),
		],		"create_list": [
			re.compile(r'(?:リスト|列)(?:を)?(?:作成|追加)(?:して)?(.{1,200}?)(?:(?:に|へ)(.{1,200}))?'),
			re.compile(r'(.{1,200}?)(?:リスト|列)を(.{1,200}?)(?:に|へ)?(?:作成|追加)'),
		],		"archive_card": [
			re.compile(r'(.{1,200}?)(?:を)(?:アーカイブ|保管)'),
		],
		"mark_done": [
			re.compile(r'(.{1,200}?)(?:を)(?:完了|終了|済み)(?:に|として)?'),
		],
		"set_card_desc": [
			re.compile(r'(.{1,200}?)(?:カード)?の説明を(.{1,200})(?:に|へ)?(?:設定|変更|更新)'),
		],
		"add_card_task": [
			re.compile(r'(?:タスク|作業|課題)(.{1,200}?)をカード(.{1,200}?)に追加'),
		],
		"rename_card_task": [
			re.compile(r'(?:タスク|作業)(.{1,200}?)をカード(.{1,200}?)で(.{1,200}?)(?:に|へ)リネーム'),
		],
		"check_card_task": [
			re.compile(r'(?:タスク|作業|課題)(.{1,200}?)をカード(.{1,200}?)(?:で|の)?(?:完了|チェック|終了)'),
		],
		"uncheck_card_task": [
			re.compile(r'(?:タスク|作業|課題)(.{1,200}?)をカード(.{1,200}?)(?:で|の)?(?:未完了|チェック外|開く)'),
		],
		"delete_card": [
			re.compile(r'(?:カード|タスク)[\u300e]?(.{1,200}?)[\u300f]?(?:を)?削除'),
		],
		"delete_list": [
			re.compile(r'(?:リスト|列)[\u300e]?(.{1,200}?)[\u300f]?(?:を)?削除'),
		],
		"delete_card_task": [
			re.compile(r'(?:タスク|作業|課題)(.{1,200}?)をカード(.{1,200}?)(?:から)?削除'),
		],
		"create_board": [
			re.compile(r'(.{1,200}?)という?ボードを(?:作成|追加)'),
			re.compile(r'(?:ボード|掲示板)(.{1,200}?)を(?:作成|追加)'),
		],
		"rename_board": [
			re.compile(r'(?:ボード|掲示板)(.{1,200}?)の名前を(.{1,200}?)(?:に|へ)?(?:変更|変え|リネーム)'),
		],
		"delete_board": [
			re.compile(r'(?:ボード|掲示板)(.{1,200}?)(?:を)?削除'),
		],
		"create_project": [
			re.compile(r'(?:プロジェクト)(.{1,200}?)(?:を)?(?:作成|追加|新規作成)'),
		],
		"rename_project": [
			re.compile(r'(?:プロジェクト)(.{1,200}?)の名前を(.{1,200}?)(?:に|へ)?(?:変更|変え|リネーム)'),
		],
		"delete_project": [
			re.compile(r'(?:プロジェクト)(.{1,200}?)(?:を)?削除'),
		],
		"hedges": [
			re.compile(r'(?:考えていた|かもしれない|べきか|どうやって|どうすれば|どういう意味|なぜ)'),
			re.compile(r'(?:説明して|教えて)'),
		],
	},
	# ── Chinese (Simplified + common Traditional verbs) ───────────────────
	"zh": {
		"sort_board": [
			re.compile(
				r'(?:排序|整理|重组|重新排列|整顿|归类)'
				r'(?:列表|卡片|和|在|新的)*'
				r'(?:看板|面板|板)?(?P<board>[\w\s]{2,50})',
			),
		],
		"move_board": [
			re.compile(r'(?:把|将|將)(.{1,200}?)(?:看板|面板|板)(?:移动|移動|移)到(.{1,200})'),
		],
		"move_card": [
			re.compile(r'(?:把|将|將)(.{1,200}?)(?:卡片|卡)(?:移动|移動|移)到(.{1,200})'),
		],
		"rename_card": [
			re.compile(r'(?:把|将|將)?(.{1,200}?)(?:卡片|卡)?(?:重命名|改名)为(.{1,200})'),
			re.compile(r'(?:重命名|改名)(.{1,200}?)(?:为|到)(.{1,200})'),
		],
		"rename_list": [
			re.compile(r'(?:把|将|將)?(.{1,200}?)(?:列表|清单|栅)?(?:重命名|改名)为(.{1,200})'),
			re.compile(r'(?:将|把)?(?:列表|清单|栅)(.{1,200}?)(?:改名为|重命名为)(.{1,200})'),
		],
		"create_card": [
			re.compile(r'(?:添加|创建|新建|增加)(.{1,200}?)(?:卡片|任务|task)(?:到|至)?(.{1,200})?'),
			re.compile(r'(?:把|将)(.{1,200}?)(?:加入|进|添加到)(.{1,200})'),
		],
		"create_list": [
			re.compile(r'(?:添加|创建|新建|增加)(?:一个)?(?:列表|清单|栏)(.{1,200}?)(?:到|至|在)?(.{1,200})?'),
		],
		"archive_card": [
			re.compile(r'(?:把|将|將)?(.{1,200}?)(?:归档|歸檔|存档|存檔)'),
		],
		"mark_done": [
			re.compile(r'(?:把|将|將)?(.{1,200}?)(?:标记|標記|标|標)?为(?:完成|已完成|已做|done)'),
		],
		"set_card_desc": [
			re.compile(r'(?:设置|更改|更新)(?:卡片)?(.{1,200}?)的描述(?:为|到)(.{1,200})'),
		],
		"add_card_task": [
			re.compile(r'添加(?:任务|事项)(.{1,200}?)(?:到|至)(?:卡片)?(.{1,200})'),
		],
		"rename_card_task": [
			re.compile(r'将(?:任务|事项)(.{1,200}?)(?:在|于)(?:卡片)?(.{1,200}?)重命名为(.{1,200})'),
		],
		"check_card_task": [
			re.compile(r'(?:勾选|完成|标记完成)(?:任务|事项)(.{1,200}?)(?:在|于)(?:卡片)?(.{1,200})'),
		],
		"uncheck_card_task": [
			re.compile(r'(?:取消勾选|取消完成)(?:任务|事项)(.{1,200}?)(?:在|于)(?:卡片)?(.{1,200})'),
		],
		"delete_card": [
			re.compile(r'删除(?:卡片)(.{1,200})'),
		],
		"delete_list": [
			re.compile(r'删除(?:列表|清单)(.{1,200})'),
		],
		"delete_card_task": [
			re.compile(r'删除(?:任务|事项)(.{1,200}?)(?:从|自)(?:卡片)?(.{1,200})'),
		],
		"create_board": [
			re.compile(r'(?:添加|创建|新建|增加)(?:一个)?(?:看板|面板|board)(.{1,200}?)(?:到|至|在)?(.{1,200})?'),
		],
		"rename_board": [
			re.compile(r'(?:把|将|將)?(?:看板|面板|board)(.{1,200}?)(?:重命名|改名)为(.{1,200})'),
		],
		"delete_board": [
			re.compile(r'(?:删除|移除|删去)(?:看板|面板|board)(.{1,200})'),
		],
		"create_project": [
			re.compile(r'(?:新建|创建|添加)(?:项目|project)(.{1,200})'),
		],
		"rename_project": [
			re.compile(r'(?:把|将|將)?(?:项目|project)(.{1,200}?)(?:重命名|改名)为(.{1,200})'),
		],
		"delete_project": [
			re.compile(r'(?:删除|移除|删去)(?:项目|project)(.{1,200})'),
		],
		"hedges": [
			re.compile(r'(?:在想|可能|也许|也許|应该|應該|怎么|怎麼|如何|什么意思|什麼意思|为什么|為什麼)'),
			re.compile(r'(?:解释|解釋|说明|說明|告诉我|告訴我)'),
		],
	},
	# ── Korean ────────────────────────────────────────────────────────────
	"ko": {
		"sort_board": [
			re.compile(
				r'(?:정렬|재구성|재정리|정리|재배열)(?:해|하)?'
				r'(?:목록|카드|그리고|에|새로운)*'
				r'(?P<board>[\w\s]{2,50})(?:보드|판)?',
			),
		],
		"move_board": [
			re.compile(r'(.{1,200}?)\s*(?:보드|판)(?:을|를)?\s*(.{1,200}?)(?:로|으로|에)\s*(?:이동|옮)'),
		],
		"move_card": [
			re.compile(r'(.{1,200}?)\s*카드(?:을|를)?\s*(.{1,200}?)(?:로|으로|에)\s*(?:이동|옮)'),
		],		"rename_card": [
			re.compile(r'(.{1,200}?)\s*(?:카드)?\s*이름(?:을|를)?\s*(.{1,200}?)(?:으로|로)\s*(?:변경|바꿰|바교)'),
		],
		"rename_list": [
			re.compile(r'(.{1,200}?)\s*(?:리스트|목록|열)?\s*이름(?:을|를)?\s*(.{1,200}?)(?:으로|로)\s*(?:변경|바꿰|바교)'),
		],		"create_card": [
			re.compile(r'(?:카드|태스크|todo)\s*(?:를|을)?\s*(.{1,200}?)(?:\s*(?:에|에게|으로)\s*(.{1,200}))?$'),
			re.compile(r'(.{1,200}?)(?:카드|태스크)\s*(?:추가|등록)'),
			re.compile(r'(.{1,200}?)\s*(?:에|으로)\s*(?:.{1,200})?\s*(?:추가하기|등록하기|넣기)'),
		],
		"create_list": [
			re.compile(r'(?:리스트|목록|열)\s*(?:를|을)?\s*(?:추가|만들|생성)(.{1,200}?)(?:\s*(?:에|에게|으로)\s*(.{1,200}))?$'),
			re.compile(r'(.{1,200}?)(?:리스트|목록|열)\s*(?:추가|생성|만들)'),
		],
		"archive_card": [
			re.compile(r'(.{1,200}?)(?:을|를)?\s*(?:보관|아카이브)'),
		],
		"mark_done": [
			re.compile(r'(.{1,200}?)(?:을|를)?\s*(?:완료|끝)'),
		],
		"set_card_desc": [
			re.compile(r'(.{1,200})카드의?\s*설명(?:을|를)?\s*(.{1,200})(?:으로|로)\s*(?:설정|변경)'),
		],
		"add_card_task": [
			re.compile(r'(?:작업|태스크|할일)\s*(.{1,200}?)(?:을|를)?\s*카드\s*(.{1,200}?)에\s*추가'),
		],
		"rename_card_task": [
			re.compile(r'(?:작업|태스크)\s*(.{1,200}?)(?:을|를)?\s*카드\s*(.{1,200}?)에서\s*(.{1,200}?)(?:으로|로)\s*이름\s*변경'),
		],
		"check_card_task": [
			re.compile(r'(?:작업|태스크)\s*(.{1,200}?)(?:을|를)?\s*카드\s*(.{1,200}?)(?:에서|에서의)?\s*(?:완료|체크)'),
		],
		"uncheck_card_task": [
			re.compile(r'(?:작업|태스크)\s*(.{1,200}?)(?:을|를)?\s*카드\s*(.{1,200}?)(?:에서)?\s*(?:미완료|체크\s*해제)'),
		],
		"delete_card": [
			re.compile(r'카드\s*(.{1,200}?)(?:을|를)?\s*(?:삭제|제거)'),
		],
		"delete_list": [
			re.compile(r'(?:리스트|목록|열)\s*(.{1,200}?)(?:을|를)?\s*(?:삭제|제거)'),
		],
		"delete_card_task": [
			re.compile(r'(?:작업|태스크)\s*(.{1,200}?)(?:을|를)?\s*카드\s*(.{1,200}?)(?:에서|에서의)?\s*(?:삭제|제거)'),
		],
		"create_board": [
			re.compile(r'(.{1,200}?)에서?의?\s*보드(?:를|을)?\s*(?:만들|추가)(?:어|여|해)'),
			re.compile(r'(.{1,200}?)\s*(?:명의|이름의)?\s*보드(?:를|을)?\s*(?:만들|추가)'),
		],
		"rename_board": [
			re.compile(r'보드(.{1,200}?)이름(?:을|를)\s*(.{1,200})(?:으로|로)\s*(?:변경|바꾸)'),
		],
		"delete_board": [
			re.compile(r'보드(.{1,200})(?:를|을)?\s*(?:삭제|제거)'),
		],
		"create_project": [
			re.compile(r'프로젝트(.{1,200}?)(?:을|를)?\s*(?:생성|만들기|추가)'),
		],
		"rename_project": [
			re.compile(r'프로젝트(.{1,200}?)이름(?:을|를)\s*(.{1,200})(?:으로|로)\s*(?:변경|바꾸)'),
		],
		"delete_project": [
			re.compile(r'프로젝트(.{1,200})(?:를|을)?\s*(?:삭제|제거)'),
		],
		"hedges": [
			re.compile(r'(?:생각하고\s+있었|혹시|할까요|어떻게|무슨\s+뜻|왜)'),
			re.compile(r'(?:설명|알려)'),
		],
	},
	# ── Hindi ─────────────────────────────────────────────────────────────
	"hi": {
		"sort_board": [
			re.compile(
				r'(?:क्रमबद्ध\s+करें|व्यवस्थित\s+करें|पुनर्गठित\s+करें|साफ\s+करें|सॉर्ट\s+करें)'
				r'(?:\s+(?:सूचियां|कार्ड|और|में|नए)*)?'
				r'(?:\s+(?:बोर्ड\s+)?(?P<board>[\w\s]{2,50}))',
			),
		],
		"move_board": [
			re.compile(r'(.{1,200}?)\s*बोर्ड\s*को\s*(.{1,200}?)\s*(?:में|पर|को)\s*(?:ले\s+जाएं|ले\s+जाओ|स्थानांतरित|मूव)'),
		],
		"move_card": [
			re.compile(r'(.{1,200}?)\s*कार्ड\s*को\s*(.{1,200}?)\s*(?:में|पर)\s*(?:ले\s+जाएं|ले\s+जाओ|मूव)'),
		],
		"rename_card": [
			re.compile(r'(.{1,200}?)\s*(?:कार्ड)?\s*का\s*नाम\s+(.{1,200}?)\s*(?:करें|बदलें|रखें)'),
			re.compile(r'(?:रीनेम|नाम\s+बदलें)\s+(?:कार्ड\s+)?(.{1,200}?)\s+(?:को|में)\s+(.{1,200})'),
		],
		"rename_list": [
			re.compile(r'(?:सूची|लिस्ट|कॉलम)\s+(.{1,200}?)\s+का\s+नाम\s+(.{1,200}?)\s*(?:करें|बदलें|रखें)'),
		],
		"create_card": [
			re.compile(r'(?:जोड़ें|जोड़ो|बनाओ|बनाएं|नया)\s+(?:कार्ड|कार्य)?\s+(.{1,200}?)(?:\s+(?:में|पर)\s+(.{1,200}))?$', re.IGNORECASE),
			re.compile(r'(.{1,200}?)\s+को\s+(?:जोड़ें|जोड़ो)\s+(.{1,200})'),
		],
		"create_list": [
			re.compile(r'(?:जोड़ें|जोड़ो|बनाओ|बनाएं|नई?)\s+(?:सूची|लिस्ट|कॉलम)\s+(.{1,200}?)(?:\s+(?:में|पर)\s+(.{1,200}))?$', re.IGNORECASE),
		],
		"archive_card": [
			re.compile(r'(.{1,200}?)\s*को\s*(?:संग्रह|आर्काइव|संग्रहित)'),
		],
		"mark_done": [
			re.compile(r'(.{1,200}?)\s*को\s*(?:पूर्ण|पूरा|पूरा\s+हो\s+गया|समाप्त)'),
		],
		"set_card_desc": [
			re.compile(r'(?:कार्ड)?\s*(.{1,200}?)\s*का\s+विवरण\s+(.{1,200})\s*(?:करें|बदलें|सेट\s+करें)'),
		],
		"add_card_task": [
			re.compile(r'(?:कार्य|टास्क|काम)\s+(.{1,200}?)\s+(?:को\s+)?(?:कार्ड)?\s*(.{1,200}?)\s+में\s+(?:जोड़ें|जोड़े)'),
		],
		"rename_card_task": [
			re.compile(r'(?:कार्य|टास्क)\s+(.{1,200}?)\s+(?:कार्ड)?\s*(.{1,200}?)\s+में\s+(.{1,200}?)\s+नाम\s+(?:करें|बदलें)'),
		],
		"check_card_task": [
			re.compile(r'(?:कार्य|टास्क)\s+(.{1,200}?)\s+(?:को\s+)?(?:कार्ड)?\s*(.{1,200}?)\s+में\s+(?:पूर्ण|चेक|समाप्त)\s*(?:करें|करो|मार्क)?'),
		],
		"uncheck_card_task": [
			re.compile(r'(?:कार्य|टास्क)\s+(.{1,200}?)\s+(?:को\s+)?(?:कार्ड)?\s*(.{1,200}?)\s+में\s+(?:अपूर्ण|अनचेक)\s*(?:करें|करो)?'),
		],
		"delete_card": [
			re.compile(r'(?:कार्ड)?\s*(.{1,200}?)\s*को\s*(?:हटाएं|हटाएँ|डिलीट\s*करें)'),
		],
		"delete_list": [
			re.compile(r'(?:सूची|लिस्ट|कॉलम)\s+(.{1,200}?)\s+को\s+(?:हटाएं|हटाएँ|डिलीट\s*करें)'),
		],
		"delete_card_task": [
			re.compile(r'(?:कार्य|टास्क)\s+(.{1,200}?)\s+(?:को\s+)?(?:कार्ड)?\s*(.{1,200}?)\s+से\s+(?:हटाएं|हटाएँ|डिलीट\s*करें)'),
		],
		"create_board": [
			re.compile(r'\b(?:बनाओ|बनाएं|जोड़ो|जोड़ें|नया|नई)\s+बोर्ड\s+(.{1,200}?)(?:\s+(?:में|पर)\s+(.{1,200}))?$', re.IGNORECASE),
		],
		"rename_board": [
			re.compile(r'\bबोर्ड\s+(.{1,200}?)\s+(?:का\s+नाम\s+बदलकर|को)\s+(.{1,200}?)\s+(?:करें|करो|रखें)', re.IGNORECASE),
		],
		"delete_board": [
			re.compile(r'\b(?:हटाओ|हटाएं|मिटाओ|मिटाएं)\s+बोर्ड\s+(.{1,200})', re.IGNORECASE),
		],
		"create_project": [
			re.compile(r'\bनया\s+प्रोजेक्ट\s+(.{1,200})\s+(?:बनाएं|बनाओ)', re.IGNORECASE),
			re.compile(r'\bप्रोजेक्ट\s+(.{1,200})\s+(?:बनाएं|बनाओ|जोड़ें)', re.IGNORECASE),
		],
		"rename_project": [
			re.compile(r'\bप्रोजेक्ट\s+(.{1,200}?)\s+का\s+नाम\s+बदलकर\s+(.{1,200})\s+(?:करें|करो|रखें)', re.IGNORECASE),
		],
		"delete_project": [
			re.compile(r'\b(?:हटाओ|हटाएं|मिटाओ|मिटाएं)\s+प्रोजेक्ट\s+(.{1,200})', re.IGNORECASE),
		],
		"hedges": [
			re.compile(r'(?:सोच\s+रहा\s+था|शायद|क्या\s+मुझे|कैसे|मतलब\s+क्या|क्यों)'),
			re.compile(r'(?:समझाओ|बताओ|वर्णन)'),
		],
	},
	# ── Arabic ────────────────────────────────────────────────────────────
	"ar": {
		"sort_board": [
			re.compile(
				r'(?:رتّب|رتب|أعد\s+ترتيب|نظّم|نظم|إعادة\s+هيكلة)\s+'
				r'(?:القوائم|البطاقات|و|في|جديدة)*\s*'
				r'(?:اللوحة\s+|لوحة\s+)?(?P<board>[\w\s]{2,50})',
				re.IGNORECASE,
			),
		],
		"move_board": [
			re.compile(r'(?:انقل|نقل|حرّك|حرك)\s+(?:اللوحة|لوحة)\s+(.{1,200}?)\s+(?:إلى|الى|في)\s+(.{1,200})'),
		],
		"move_card": [
			re.compile(r'(?:انقل|نقل|حرّك|حرك)\s+(?:البطاقة|بطاقة)\s+(.{1,200}?)\s+(?:إلى|الى|في)\s+(.{1,200})'),
		],
		"rename_card": [
			re.compile(r'(?:أعد|اعد)\s+تسمية\s+(?:البطاقة\s+)?(.{1,200}?)\s+(?:إلى|الى)\s+(.{1,200})'),
			re.compile(r'(?:غيّر|غير)\s+(?:اسم\s+)?(?:البطاقة\s+)?(.{1,200}?)\s+(?:إلى|الى)\s+(.{1,200})'),
		],
		"rename_list": [
			re.compile(r'(?:أعد|اعد)\s+تسمية\s+(?:القائمة\s+)?(.{1,200}?)\s+(?:إلى|الى)\s+(.{1,200})'),
			re.compile(r'(?:غيّر|غير)\s+(?:اسم\s+)?(?:القائمة\s+)?(.{1,200}?)\s+(?:إلى|الى)\s+(.{1,200})'),
		],
		"create_card": [
			re.compile(r'(?:أضف|اضف|أنشئ|انشئ)\s+(?:بطاقة?|مهمة?)?\s*(.{1,200}?)(?:\s+(?:إلى|الى|في)\s+(.{1,200}))?$'),
			re.compile(r'(?:أضف|اضف)\s+(.{1,200}?)\s+(?:إلى|الى|في)\s+(.{1,200})'),
		],
		"create_list": [
			re.compile(r'(?:أضف|اضف|أنشئ|انشئ)\s+(?:قائمة?|عمود?)?\s*(?:اسمها?\s+)?(.{1,200}?)(?:\s+(?:إلى|الى|في)\s+(?:لوحة\s+)?(.{1,200}))?$'),
		],
		"archive_card": [
			re.compile(r'(?:أرشف|ارشف|أرشفة|ارشفة)\s+(?:البطاقة\s+)?(.{1,200})'),
		],
		"mark_done": [
			re.compile(r'(?:علّم|علم|اعتبر|حدد)\s+(?:البطاقة\s+)?(.{1,200}?)\s+(?:كـ?|ك)?(?:منجز|مكتمل|تم|منته[ىي])'),
		],
		"set_card_desc": [
			re.compile(r'(?:عيّن|عين|غيّر|غير)\s+وصف\s+(?:البطاقة\s+)?(.{1,200}?)\s+(?:إلى|الى)\s+(.{1,200})'),
		],
		"add_card_task": [
			re.compile(r'(?:أضف|اضف)\s+(?:مهمة|عنصر)\s+(.{1,200}?)\s+(?:إلى|الى|في)\s+(?:بطاقة\s+)?(.{1,200})'),
		],
		"rename_card_task": [
			re.compile(r'(?:أعد|اعد)\s+تسمية\s+(?:مهمة|عنصر)\s+(.{1,200}?)\s+(?:في|على)\s+(?:بطاقة\s+)?(.{1,200}?)\s+(?:إلى|الى)\s+(.{1,200})'),
		],
		"check_card_task": [
			re.compile(r'(?:علّم|علم|أكمل|اكمل)\s+(?:مهمة|عنصر)\s+(.{1,200}?)\s+(?:في|على)\s+(?:بطاقة\s+)?(.{1,200})'),
		],
		"uncheck_card_task": [
			re.compile(r'(?:أزل|ازل)\s+علامة\s+(?:مهمة|عنصر)\s+(.{1,200}?)\s+(?:في|على)\s+(?:بطاقة\s+)?(.{1,200})'),
		],
		"delete_card": [
			re.compile(r'(?:احذف|حذف|أحذف)\s+(?:البطاقة\s+)?(.{1,200})'),
		],
		"delete_list": [
			re.compile(r'(?:احذف|حذف|أحذف)\s+(?:القائمة\s+)?(.{1,200})'),
		],
		"delete_card_task": [
			re.compile(r'(?:احذف|حذف|أحذف)\s+(?:مهمة|عنصر)\s+(.{1,200}?)\s+(?:من|في)\s+(?:بطاقة\s+)?(.{1,200})'),
		],
		"create_board": [
			re.compile(r'(?:أنشئ|انشئ|أضف|اضف)\s+(?:لوحة|بورد|board)\s+(?:باسم\s+|تسمى\s+)?(.{1,200}?)(?:\s+(?:في|إلى|الى)\s+(.{1,200}))?$'),
		],
		"rename_board": [
			re.compile(r'(?:أعد|اعد)\s+تسمية\s+(?:اللوحة\s+)?(.{1,200}?)\s+(?:إلى|الى)\s+(.{1,200})'),
			re.compile(r'(?:غيّر|غير)\s+(?:اسم\s+)?(?:اللوحة\s+)?(.{1,200}?)\s+(?:إلى|الى)\s+(.{1,200})'),
		],
		"delete_board": [
			re.compile(r'(?:احذف|حذف|أحذف)\s+(?:اللوحة|لوحة)\s+(.{1,200})'),
		],
		"create_project": [
			re.compile(r'(?:أنشئ|انشئ|أضف|اضف)\s+(?:مشروع)\s+(?:باسم\s+)?(.{1,200})'),
		],
		"rename_project": [
			re.compile(r'(?:أعد|اعد)\s+تسمية\s+(?:المشروع\s+)?(.{1,200}?)\s+(?:إلى|الى)\s+(.{1,200})'),
			re.compile(r'(?:غيّر|غير)\s+(?:اسم\s+)?(?:المشروع\s+)?(.{1,200}?)\s+(?:إلى|الى)\s+(.{1,200})'),
		],
		"delete_project": [
			re.compile(r'(?:احذف|حذف|أحذف)\s+(?:المشروع|(?:مشروع))\s+(.{1,200})'),
		],
		"hedges": [
			re.compile(r'(?:كنت\s+أفكر|ربما|هل\s+يجب|هل\s+ينبغي|كيف\s+(?:يمكن|أستطيع)|ماذا\s+يعني|لماذا)'),
			re.compile(r'(?:اشرح|وضّح|وضح|أخبرني|اخبرني)'),
		],
	},
}

# All language codes with at least one verb pattern. Used by classify() to
# decide which dicts to iterate. Adding a new language is just adding it here
# and providing a _LANG_PATTERNS entry above.
_SUPPORTED_LANGS = set(_LANG_PATTERNS.keys())

# Filler / article / possessive prefixes across all supported languages,
# stripped from extracted entity strings before fuzzy match.
_LEADING_FILLER_RE = re.compile(
	r'^(?:'
	# EN
	r'the|my|a|an|'
	# DE
	r'der|die|das|den|dem|des|ein|eine|einen|einem|einer|mein|meine|meinen|meinem|meiner|meines|'
	# ES
	r'el|la|los|las|un|una|unos|unas|mi|mis|tu|tus|su|sus|'
	# FR
	r'le|les|un|une|des|mon|ma|mes|ton|ta|tes|son|sa|ses|du|de\s+la|'
	# PT
	r'o|os|as|um|uma|uns|umas|meu|minha|meus|minhas|teu|tua|seu|sua|'
	# RU (basic possessives/demonstratives)
	r'мой|моя|моё|мои|этот|эта|это|эти|тот|та|то|те|'
	# HI
	r'यह|वह|मेरा|मेरी|मेरे|आपका|आपकी|आपके|'
	# KO
	r'이|그|저|내|나의|'
	# ZH
	r'这|那|我的|你的|'
	# AR (definite article handled via prefix removal below; include common possessives)
	r'هذا|هذه|تلك|ذلك'
	r')\s+',
	re.IGNORECASE,
)

# Trailing politeness / filler suffixes across all supported languages.
_TRAILING_FILLER_RE = re.compile(
	r'\s+(?:'
	# EN
	r'please|thanks|thank\s+you|asap|now|today|'
	# DE
	r'bitte|danke|jetzt|heute|'
	# ES
	r'por\s+favor|gracias|ahora|hoy|'
	# FR
	r's[\u2019\']il\s+(?:vous|te)\s+pla[iî]t|svp|stp|merci|maintenant|aujourd[\u2019\']hui|'
	# PT
	r'por\s+favor|obrigad[oa]|agora|hoje|'
	# RU
	r'пожалуйста|спасибо|сейчас|сегодня|'
	# JA (kept for safety; mostly suffix particles)
	r'お願いします|ください|お願い|'
	# ZH
	r'请|麻烦|谢谢|'
	# KO
	r'주세요|해주세요|부탁(?:합니다|해요)?|'
	# HI
	r'कृपया|धन्यवाद|'
	# AR
	r'من\s+فضلك|لو\s+سمحت|شكرا|الآن|اليوم'
	r')\s*$',
	re.IGNORECASE,
)


def _is_hedged(text: str, lang: str) -> bool:
	"""True if any hedge pattern from the user's lang OR English fires."""
	for code in (lang, "en"):
		patterns = _LANG_PATTERNS.get(code, {}).get("hedges", [])
		if any(p.search(text) for p in patterns):
			return True
	return False


def _strip_filler(s: str) -> str:
	"""Trim quotes, trailing punctuation, leading articles/possessives and
	trailing politeness/filler words across all supported languages."""
	s = s.strip().strip('"\'\u201c\u201d\u2018\u2019')
	s = s.rstrip('.,;!?،۔。、')
	# Repeat once in case both an article and a possessive stack ("my the X")
	for _ in range(2):
		new = _LEADING_FILLER_RE.sub('', s)
		if new == s:
			break
		s = new
	s = _TRAILING_FILLER_RE.sub('', s)
	# Arabic definite article "ال" prefix — strip if word starts with it and
	# the remaining stem is at least 2 chars (avoid stripping "ال" alone).
	if s.startswith('ال') and len(s) > 4:
		s_stripped = s[2:]
		# Only strip when the rest looks like Arabic word characters
		if re.match(r'^[\u0600-\u06FF]', s_stripped):
			s = s_stripped
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


def _lang_iter_order(lang: str) -> list[str]:
	"""Return iteration order: requested lang first, then EN as universal
	fallback, then every other supported lang (handles mixed-language
	commands like English instructions from a Spanish UI)."""
	first = lang if lang in _SUPPORTED_LANGS else "en"
	rest = [c for c in _LANG_PATTERNS.keys() if c not in (first, "en")]
	if first == "en":
		return [first] + rest
	return [first, "en"] + rest


def _patterns_for(verb_key: str, lang: str) -> list[re.Pattern]:
	"""Yield patterns for a verb across all languages, requested lang first."""
	out: list[re.Pattern] = []
	for code in _lang_iter_order(lang):
		out.extend(_LANG_PATTERNS.get(code, {}).get(verb_key, []))
	return out


# Recognise the word "board" across all supported scripts so that the
# ARCHIVE_CARD path can refuse to archive boards by mistake.
_BOARD_WORD_RE = re.compile(
	r'(?:\bboard\b|tablero|tableau|quadro|доск|ボード|掲示板|看板|面板|보드|बोर्ड|اللوحة|لوحة)',
	re.IGNORECASE,
)


async def classify_structural_intent(text: str, lang: str) -> Optional[StructuralIntent]:
	"""Detect a high-confidence Planka mutation intent in the user message.

	Multilingual: tries the user's locale first, then English, then every
	other supported language. The entity match against live Planka state is
	the actual safety gate — broad regex is safe because unresolved entities
	return None.

	Returns None when:
	  - no verb pattern matches in any supported language
	  - the message is hedged ("thinking about", "should I", "wie kann ich", ...)
	  - the entity could not be resolved against live Planka state
	"""
	if not text:
		return None
	snippet = text[:_MAX_INPUT].strip()
	if _is_hedged(snippet, lang):
		return None

	# ── MOVE_BOARD ────────────────────────────────────────────────────────
	for pat in _patterns_for("move_board", lang):
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
				# Fallback: user may have said "X board" meaning "the board
				# inside project X". If board_q matches a project with exactly
				# one board, use that single board.
				proj_alt, proj_alt_conf = _match_name(board_q, projects)
				if proj_alt:
					proj_boards = proj_alt.get("boards") or []
					if len(proj_boards) == 1:
						board_match = proj_boards[0]
						board_conf = min(proj_alt_conf, 0.85)
						logger.info(
							"intent_router: MOVE_BOARD fallback - '%s' matched project '%s' with single board '%s'",
							board_q, proj_alt.get("name"), board_match.get("name"),
						)
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
	for pat in _patterns_for("move_card", lang):
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

	# ── UNCHECK_CARD_TASK ─────────────────────────────────────────────────
	# Must come before CHECK_CARD_TASK: CHECK's "mark...done" pattern can
	# greedily capture "Shopping as not" in card_fragment and still match
	# "done" at the end unless UNCHECK runs first.
	for pat in _patterns_for("uncheck_card_task", lang):
		m = pat.search(snippet)
		if m:
			task_q = _strip_filler(m.group(1)) if m.lastindex and m.lastindex >= 1 else ""
			card_q = _strip_filler(m.group(2)) if m.lastindex and m.lastindex >= 2 and m.group(2) else ""
			if not task_q or not card_q:
				continue
			return StructuralIntent(
				verb="UNCHECK_CARD_TASK",
				entities={"task_fragment": task_q, "card_fragment": card_q},
				raw_text=snippet,
				confidence=0.85,
			)

	# ── CHECK_CARD_TASK ────────────────────────────────────────────────────
	# Must come before MARK_DONE: "mark task X in card Y as done" would
	# be swallowed by MARK_DONE's looser "mark X as done" pattern.
	for pat in _patterns_for("check_card_task", lang):
		m = pat.search(snippet)
		if m:
			task_q = _strip_filler(m.group(1)) if m.lastindex and m.lastindex >= 1 else ""
			card_q = _strip_filler(m.group(2)) if m.lastindex and m.lastindex >= 2 and m.group(2) else ""
			if not task_q or not card_q:
				continue
			return StructuralIntent(
				verb="CHECK_CARD_TASK",
				entities={"task_fragment": task_q, "card_fragment": card_q},
				raw_text=snippet,
				confidence=0.85,
			)

	# ── MARK_DONE ────────────────────────────────────────────────────────
	for pat in _patterns_for("mark_done", lang):
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
	for pat in _patterns_for("archive_card", lang):
		m = pat.search(snippet)
		if m:
			card_q = _strip_filler(m.group(1))
			if not card_q:
				continue
			# Skip if the object looks like a board — leave that to the LLM
			if _BOARD_WORD_RE.search(card_q):
				return None
			return StructuralIntent(
				verb="ARCHIVE_CARD",
				entities={"card_fragment": card_q, "board_name": ""},
				raw_text=snippet,
				confidence=0.9,
			)

	# ── RENAME_CARD_TASK ──────────────────────────────────────────────────
	# Must come before RENAME_LIST/RENAME_CARD: "rename task X in card Y to Z"
	# would be captured by RENAME_CARD's broad "rename X to Z" pattern.
	for pat in _patterns_for("rename_card_task", lang):
		m = pat.search(snippet)
		if m:
			task_q = _strip_filler(m.group(1)) if m.lastindex and m.lastindex >= 1 else ""
			card_q = _strip_filler(m.group(2)) if m.lastindex and m.lastindex >= 2 and m.group(2) else ""
			new_name_q = _strip_filler(m.group(3)) if m.lastindex and m.lastindex >= 3 and m.group(3) else ""
			if not task_q or not card_q or not new_name_q:
				continue
			return StructuralIntent(
				verb="RENAME_CARD_TASK",
				entities={"task_fragment": task_q, "card_fragment": card_q, "new_name": new_name_q},
				raw_text=snippet,
				confidence=0.85,
			)

	# ── RENAME_LIST ───────────────────────────────────────────────────────
	# Checked before RENAME_CARD: "rename list X to Y" is more specific.
	for pat in _patterns_for("rename_list", lang):
		m = pat.search(snippet)
		if m:
			list_q = _strip_filler(m.group(1)) if m.lastindex and m.lastindex >= 1 else ""
			new_name_q = _strip_filler(m.group(2)) if m.lastindex and m.lastindex >= 2 and m.group(2) else ""
			if not list_q or not new_name_q:
				continue
			return StructuralIntent(
				verb="RENAME_LIST",
				entities={"list_fragment": list_q, "new_name": new_name_q},
				raw_text=snippet,
				confidence=0.85,
			)

	# ── RENAME_BOARD ─────────────────────────────────────────────────────
	# Checked before RENAME_CARD and RENAME_LIST: "rename board X to Y" is more
	# specific and must be resolved first to avoid the broad rename_card pattern
	# capturing "board" as a card name.
	for pat in _patterns_for("rename_board", lang):
		m = pat.search(snippet)
		if m:
			board_q = _strip_filler(m.group(1)) if m.lastindex and m.lastindex >= 1 else ""
			new_name_q = _strip_filler(m.group(2)) if m.lastindex and m.lastindex >= 2 and m.group(2) else ""
			if not board_q or not new_name_q:
				continue
			return StructuralIntent(
				verb="RENAME_BOARD",
				entities={"board_fragment": board_q, "new_name": new_name_q},
				raw_text=snippet,
				confidence=0.85,
			)

	# ── DELETE_PROJECT ────────────────────────────────────────────────────
	for pat in _patterns_for("delete_project", lang):
		m = pat.search(snippet)
		if m:
			project_q = _strip_filler(m.group(1)) if m.lastindex and m.lastindex >= 1 else ""
			if not project_q:
				continue
			return StructuralIntent(
				verb="DELETE_PROJECT",
				entities={"project_fragment": project_q},
				raw_text=snippet,
				confidence=0.85,
			)

	# ── RENAME_PROJECT ────────────────────────────────────────────────────
	for pat in _patterns_for("rename_project", lang):
		m = pat.search(snippet)
		if m:
			project_q = _strip_filler(m.group(1)) if m.lastindex and m.lastindex >= 1 else ""
			new_name_q = _strip_filler(m.group(2)) if m.lastindex and m.lastindex >= 2 and m.group(2) else ""
			if not project_q or not new_name_q:
				continue
			return StructuralIntent(
				verb="RENAME_PROJECT",
				entities={"project_fragment": project_q, "new_name": new_name_q},
				raw_text=snippet,
				confidence=0.85,
			)

	# ── CREATE_PROJECT ────────────────────────────────────────────────────
	for pat in _patterns_for("create_project", lang):
		m = pat.search(snippet)
		if m:
			project_name_q = _strip_filler(m.group(1)) if m.lastindex and m.lastindex >= 1 else ""
			if not project_name_q:
				continue
			return StructuralIntent(
				verb="CREATE_PROJECT",
				entities={"project_name": project_name_q},
				raw_text=snippet,
				confidence=0.85,
			)

	# ── RENAME_CARD ───────────────────────────────────────────────────────
	# Checked after RENAME_LIST and RENAME_BOARD since generic "rename X to Y"
	# would shadow both.
	for pat in _patterns_for("rename_card", lang):
		m = pat.search(snippet)
		if m:
			card_q = _strip_filler(m.group(1)) if m.lastindex and m.lastindex >= 1 else ""
			new_name_q = _strip_filler(m.group(2)) if m.lastindex and m.lastindex >= 2 and m.group(2) else ""
			if not card_q or not new_name_q:
				continue
			return StructuralIntent(
				verb="RENAME_CARD",
				entities={"card_fragment": card_q, "new_name": new_name_q},
				raw_text=snippet,
				confidence=0.85,
			)

	# ── SET_CARD_DESC ─────────────────────────────────────────────────────
	for pat in _patterns_for("set_card_desc", lang):
		m = pat.search(snippet)
		if m:
			card_q = _strip_filler(m.group(1)) if m.lastindex and m.lastindex >= 1 else ""
			desc_q = m.group(2).strip() if m.lastindex and m.lastindex >= 2 and m.group(2) else ""
			if not card_q or not desc_q:
				continue
			return StructuralIntent(
				verb="SET_CARD_DESC",
				entities={"card_fragment": card_q, "description": desc_q},
				raw_text=snippet,
				confidence=0.85,
			)

	# ── CREATE_LIST ───────────────────────────────────────────────────────
	# Checked before CREATE_CARD: explicit "list" noun is more specific than
	# the broad "add X to Y" create_card pattern 3, which would otherwise
	# steal "add a new list In Progress to Garden".
	# Guard: if "card", "task", or "todo" appears as an explicit keyword
	# BEFORE "list" in the snippet (e.g. "add Emperor Angel card to review
	# list on tank board"), this is a CREATE_CARD command — skip ahead.
	_pre_list_snippet = snippet
	_list_pos = snippet.lower().find(" list")
	if _list_pos > 0:
		_pre_list_snippet = snippet[:_list_pos]
	_has_card_kw_before_list = bool(re.search(r'\b(?:card|task|todo)\b', _pre_list_snippet, re.IGNORECASE))
	if not _has_card_kw_before_list:
		for pat in _patterns_for("create_list", lang):
			m = pat.search(snippet)
			if m:
				name_q = _strip_filler(m.group(1)) if m.lastindex and m.lastindex >= 1 else ""
				board_q = _strip_filler(m.group(2)) if m.lastindex and m.lastindex >= 2 and m.group(2) else ""
				if not name_q:
					continue
				return StructuralIntent(
					verb="CREATE_LIST",
					entities={"list_name": name_q, "board_name": board_q},
					raw_text=snippet,
					confidence=0.85,
				)

	# ── ADD_CARD_TASK ─────────────────────────────────────────────────────
	# Checked before CREATE_CARD: "add task X to card Y" would otherwise
	# be captured as CREATE_CARD with dest="card Y".
	for pat in _patterns_for("add_card_task", lang):
		m = pat.search(snippet)
		if m:
			task_q = _strip_filler(m.group(1)) if m.lastindex and m.lastindex >= 1 else ""
			card_q = _strip_filler(m.group(2)) if m.lastindex and m.lastindex >= 2 and m.group(2) else ""
			if not task_q or not card_q:
				continue
			return StructuralIntent(
				verb="ADD_CARD_TASK",
				entities={"task_name": task_q, "card_fragment": card_q},
				raw_text=snippet,
				confidence=0.85,
			)

	# ── DELETE_CARD_TASK ──────────────────────────────────────────────────
	# Checked before DELETE_CARD: "remove task X from card Y" would otherwise
	# be captured by DELETE_CARD's broader pattern.
	for pat in _patterns_for("delete_card_task", lang):
		m = pat.search(snippet)
		if m:
			task_q = _strip_filler(m.group(1)) if m.lastindex and m.lastindex >= 1 else ""
			card_q = _strip_filler(m.group(2)) if m.lastindex and m.lastindex >= 2 and m.group(2) else ""
			if not task_q or not card_q:
				continue
			return StructuralIntent(
				verb="DELETE_CARD_TASK",
				entities={"task_fragment": task_q, "card_fragment": card_q},
				raw_text=snippet,
				confidence=0.85,
			)

	# ── DELETE_LIST ───────────────────────────────────────────────────────
	for pat in _patterns_for("delete_list", lang):
		m = pat.search(snippet)
		if m:
			list_q = _strip_filler(m.group(1)) if m.lastindex and m.lastindex >= 1 else ""
			if not list_q:
				continue
			return StructuralIntent(
				verb="DELETE_LIST",
				entities={"list_fragment": list_q},
				raw_text=snippet,
				confidence=0.85,
			)

	# ── DELETE_CARD ───────────────────────────────────────────────────────
	for pat in _patterns_for("delete_card", lang):
		m = pat.search(snippet)
		if m:
			card_q = _strip_filler(m.group(1)) if m.lastindex and m.lastindex >= 1 else ""
			if not card_q:
				continue
			return StructuralIntent(
				verb="DELETE_CARD",
				entities={"card_fragment": card_q},
				raw_text=snippet,
				confidence=0.85,
			)

	# ── DELETE_BOARD ─────────────────────────────────────────────────────
	for pat in _patterns_for("delete_board", lang):
		m = pat.search(snippet)
		if m:
			board_q = _strip_filler(m.group(1)) if m.lastindex and m.lastindex >= 1 else ""
			if not board_q:
				continue
			return StructuralIntent(
				verb="DELETE_BOARD",
				entities={"board_fragment": board_q},
				raw_text=snippet,
				confidence=0.85,
			)

	# ── CREATE_BOARD ──────────────────────────────────────────────────────
	for pat in _patterns_for("create_board", lang):
		m = pat.search(snippet)
		if m:
			board_name_q = _strip_filler(m.group(1)) if m.lastindex and m.lastindex >= 1 else ""
			project_q = _strip_filler(m.group(2)) if m.lastindex and m.lastindex >= 2 and m.group(2) else ""
			if not board_name_q:
				continue
			return StructuralIntent(
				verb="CREATE_BOARD",
				entities={"board_name": board_name_q, "project_fragment": project_q},
				raw_text=snippet,
				confidence=0.85,
			)

	# ── BOARD_ITEM_ADD ────────────────────────────────────────────────────
	# Must run before CREATE_CARD: "new goal X" would otherwise be captured
	# by create_card pattern 1 ("new <noun> <title>").
	for pat in _patterns_for("board_item_add", lang):
		m = pat.search(snippet)
		if m:
			noun_q = m.group("noun").lower().strip()
			# Check if this is a bulk (colon) match or single match
			try:
				titles_raw = m.group("titles")
			except IndexError:
				titles_raw = None
			if titles_raw is not None:
				# Bulk: split on comma, semicolon, or newline — clean each item
				raw_items = re.split(r'[,;\n]+', titles_raw)
				titles_list = [t.strip().strip('"\'-') for t in raw_items if t.strip().strip('"\'-')]
				if not titles_list:
					continue
				title_q = ""
			else:
				try:
					title_q = m.group("title").strip()
				except IndexError:
					continue
				titles_list = []
			if not noun_q or (not title_q and not titles_list):
				continue
			# Fuzzy-match noun against live board names (goal → "life goals", etc.)
			projects = await _get_planka_snapshot()
			matched_board = ""
			if projects:
				all_boards = [b for p in projects for b in p["boards"]]
				best_board, best_conf = _match_name(noun_q, all_boards)
				# Broad match: accept if noun appears anywhere in board name
				if not best_board:
					for b in all_boards:
						if noun_q in (b["name"] or "").lower():
							best_board = b
							break
				if best_board:
					matched_board = best_board["name"]
					logger.info(
						"intent_router: BOARD_ITEM_ADD noun='%s' → board='%s' titles=%s",
						noun_q, matched_board, titles_list or [title_q],
					)
			entities: dict = {"noun": noun_q, "board_name": matched_board}
			if titles_list:
				entities["titles"] = titles_list
			else:
				entities["title"] = title_q
			return StructuralIntent(
				verb="BOARD_ITEM_ADD",
				entities=entities,
				raw_text=snippet,
				confidence=1.0,
			)

	# ── CREATE_CARD ───────────────────────────────────────────────────────
	# SORT_BOARD check runs first to prevent "sort ... reef tank" being caught
	# by create_card's broad "add/new" patterns.
	for pat in _patterns_for("sort_board", lang):
		m = pat.search(snippet)
		if m:
			board_q = _strip_filler(m.group("board")).strip().rstrip(".,;!?")
			# Strip the generic word "board" if it is a trailing qualifier
			# (e.g. "aquarium board" → "aquarium") to improve fuzzy matching.
			import re as _bre
			board_q = _bre.sub(r'\bboard\b', '', board_q, flags=_bre.IGNORECASE).strip()
			if not board_q:
				continue
			# Sanity check: a real board name should not be more than 4 words.
			# If it's longer, the pattern captured a phrase (e.g. "reorganize cards in ..."),
			# not an actual board name — skip to the next pattern.
			if len(board_q.split()) > 4:
				continue
			# Verify board exists in Planka snapshot before committing.
			projects = await _get_planka_snapshot()
			if projects:
				all_boards = [b for p in projects for b in p["boards"]]
				best_board, _conf = _match_name(board_q, all_boards)
				if not best_board:
					for b in all_boards:
						bn = (b["name"] or "").lower()
						bq = board_q.lower()
						if bq in bn or bn in bq:
							best_board = b
							break
				# If still unresolved, return intent with empty board_id so dispatch
				# can use its full 120s budget to resolve it via the LLM.
				if best_board:
					return StructuralIntent(
						verb="SORT_BOARD",
						entities={"board_fragment": board_q, "board_name": best_board["name"], "board_id": best_board["id"]},
						raw_text=snippet,
						confidence=0.95,
					)
				else:
					# Board not found by name — return unresolved intent so dispatch can try LLM
					return StructuralIntent(
						verb="SORT_BOARD",
						entities={"board_fragment": board_q, "board_name": "", "board_id": ""},
						raw_text=snippet,
						confidence=0.92,
					)

	# ── CREATE_CARD ───────────────────────────────────────────────────────
	for pat in _patterns_for("create_card", lang):
		m = pat.search(snippet)
		if m:
			title_q = _strip_filler(m.group(1)) if m.lastindex and m.lastindex >= 1 else ""
			dest_q = _strip_filler(m.group(2)) if m.lastindex and m.lastindex >= 2 and m.group(2) else ""
			if not title_q:
				continue
			return StructuralIntent(
				verb="CREATE_CARD",
				entities={"title": title_q, "destination": dest_q},
				raw_text=snippet,
				confidence=0.85,
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
		execute_create_card, execute_create_list, execute_rename_card, execute_rename_list,
		execute_set_card_desc, execute_add_card_task,
		execute_check_card_task, execute_uncheck_card_task, execute_rename_card_task,
		execute_delete_card, execute_delete_list, execute_delete_card_task,
		execute_create_board, execute_rename_board, execute_delete_board,
		execute_create_project, execute_rename_project, execute_delete_project,
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

	if verb == "BOARD_ITEM_ADD":
		board_dest = ent.get("board_name") or ""
		noun = ent.get("noun", "").lower()
		# Support both single ("title") and bulk ("titles") forms
		titles: list[str] = ent.get("titles") or ([ent["title"]] if ent.get("title") else [])
		if not titles:
			return "\u26a0 No title(s) provided for BOARD_ITEM_ADD."
		results: list[str] = []
		audit_parts: list[str] = []
		for t_item in titles:
			if noun in _LIST_NOUNS:
				# Goal/dream/wish/idea → create a LIST (column) on the board so the
				# goal itself becomes a container for milestone cards under it.
				raw = await execute_create_list(t_item, board_dest, lang)
				if raw.startswith("\u26a0"):
					results.append(raw)
				else:
					board_label = board_dest or "Operator Board"
					results.append(
						_localise(
							"intent_router_create_list_success",
							"List '{list_name}' created on '{board}'.",
							list_name=t_item, board=board_label,
						)
					)
					audit_parts.append(f"[AUDIT:board_item_add_list:{t_item}|board={board_label}]")
			else:
				# Item/todo/task/entry → create a CARD on the Inbox list of the board.
				dest_arg = f"Inbox list on {board_dest}" if board_dest else ""
				raw = await execute_create_card(t_item, dest_arg, lang)
				if raw.startswith("\u26a0"):
					results.append(raw)
				else:
					dest_label = board_dest or "Inbox"
					results.append(
						_localise(
							"intent_router_create_card_success",
							"Card '{title}' added to '{dest}'.",
							title=t_item, dest=dest_label,
						)
					)
					audit_parts.append(f"[AUDIT:board_item_add_card:{t_item}|board={dest_label}]")
		out = "\n".join(results)
		if audit_parts:
			out += "\n" + "\n".join(audit_parts)
		return out

	if verb == "CREATE_CARD":
		raw = await execute_create_card(ent["title"], ent.get("destination", ""), lang)
		if raw.startswith("\u26a0"):
			return raw
		dest_label = ent.get("destination") or "Inbox"
		msg = _localise(
			"intent_router_create_card_success",
			"Card '{title}' added to '{dest}'.",
			title=ent["title"], dest=dest_label,
		)
		audit = f"[AUDIT:create_card:{ent['title']}|dest={dest_label}]"
		return f"{msg}\n{audit}"

	if verb == "CREATE_LIST":
		raw = await execute_create_list(ent["list_name"], ent.get("board_name", ""), lang)
		if raw.startswith("\u26a0"):
			return raw
		board_label = ent.get("board_name") or "Operator Board"
		msg = _localise(
			"intent_router_create_list_success",
			"List '{list_name}' created on '{board}'.",
			list_name=ent["list_name"], board=board_label,
		)
		audit = f"[AUDIT:create_list:{ent['list_name']}|board={board_label}]"
		return f"{msg}\n{audit}"

	if verb == "RENAME_CARD":
		raw = await execute_rename_card(ent["card_fragment"], ent["new_name"], lang)
		if raw.startswith("\u26a0"):
			return raw
		msg = _localise(
			"intent_router_rename_card_success",
			"Card '{card}' renamed to '{new_name}'.",
			card=ent["card_fragment"], new_name=ent["new_name"],
		)
		audit = f"[AUDIT:rename_card:{ent['card_fragment']}|new_name={ent['new_name']}]"
		return f"{msg}\n{audit}"

	if verb == "RENAME_LIST":
		raw = await execute_rename_list(ent["list_fragment"], ent["new_name"], lang)
		if raw.startswith("\u26a0"):
			return raw
		msg = _localise(
			"intent_router_rename_list_success",
			"List '{list}' renamed to '{new_name}'.",
			list=ent["list_fragment"], new_name=ent["new_name"],
		)
		audit = f"[AUDIT:rename_list:{ent['list_fragment']}|new_name={ent['new_name']}]"
		return f"{msg}\n{audit}"

	if verb == "SET_CARD_DESC":
		raw = await execute_set_card_desc(ent["card_fragment"], ent["description"], lang)
		if raw.startswith("\u26a0"):
			return raw
		msg = _localise(
			"intent_router_set_card_desc_success",
			"Description of '{card}' updated.",
			card=ent["card_fragment"],
		)
		audit = f"[AUDIT:set_card_desc:{ent['card_fragment']}]"
		return f"{msg}\n{audit}"

	if verb == "ADD_CARD_TASK":
		raw = await execute_add_card_task(ent["card_fragment"], ent["task_name"], lang)
		if raw.startswith("\u26a0"):
			return raw
		msg = _localise(
			"intent_router_add_card_task_success",
			"Task '{task}' added to card '{card}'.",
			task=ent["task_name"], card=ent["card_fragment"],
		)
		audit = f"[AUDIT:add_card_task:{ent['task_name']}|card={ent['card_fragment']}]"
		return f"{msg}\n{audit}"

	if verb == "CHECK_CARD_TASK":
		raw = await execute_check_card_task(ent["card_fragment"], ent["task_fragment"], lang)
		if raw.startswith("\u26a0"):
			return raw
		msg = _localise(
			"intent_router_check_card_task_success",
			"Task '{task}' in card '{card}' marked as done.",
			task=ent["task_fragment"], card=ent["card_fragment"],
		)
		audit = f"[AUDIT:check_card_task:{ent['task_fragment']}|card={ent['card_fragment']}]"
		return f"{msg}\n{audit}"

	if verb == "UNCHECK_CARD_TASK":
		raw = await execute_uncheck_card_task(ent["card_fragment"], ent["task_fragment"], lang)
		if raw.startswith("\u26a0"):
			return raw
		msg = _localise(
			"intent_router_uncheck_card_task_success",
			"Task '{task}' in card '{card}' marked as not done.",
			task=ent["task_fragment"], card=ent["card_fragment"],
		)
		audit = f"[AUDIT:uncheck_card_task:{ent['task_fragment']}|card={ent['card_fragment']}]"
		return f"{msg}\n{audit}"

	if verb == "RENAME_CARD_TASK":
		raw = await execute_rename_card_task(ent["card_fragment"], ent["task_fragment"], ent["new_name"], lang)
		if raw.startswith("\u26a0"):
			return raw
		msg = _localise(
			"intent_router_rename_card_task_success",
			"Task '{task}' in card '{card}' renamed to '{new_name}'.",
			task=ent["task_fragment"], card=ent["card_fragment"], new_name=ent["new_name"],
		)
		audit = f"[AUDIT:rename_card_task:{ent['task_fragment']}|card={ent['card_fragment']}|new_name={ent['new_name']}]"
		return f"{msg}\n{audit}"

	if verb == "DELETE_CARD":
		raw = await execute_delete_card(ent["card_fragment"], lang)
		if raw.startswith("\u26a0"):
			return raw
		msg = _localise("intent_router_delete_card_success", "Card '{card}' deleted.", card=ent["card_fragment"])
		audit = f"[AUDIT:delete_card:{ent['card_fragment']}]"
		return f"{msg}\n{audit}"

	if verb == "DELETE_LIST":
		raw = await execute_delete_list(ent["list_fragment"], lang)
		if raw.startswith("\u26a0"):
			return raw
		msg = _localise("intent_router_delete_list_success", "List '{list}' deleted.", list=ent["list_fragment"])
		audit = f"[AUDIT:delete_list:{ent['list_fragment']}]"
		return f"{msg}\n{audit}"

	if verb == "DELETE_CARD_TASK":
		raw = await execute_delete_card_task(ent["card_fragment"], ent["task_fragment"], lang)
		if raw.startswith("\u26a0"):
			return raw
		msg = _localise(
			"intent_router_delete_card_task_success",
			"Task '{task}' removed from card '{card}'.",
			task=ent["task_fragment"], card=ent["card_fragment"],
		)
		audit = f"[AUDIT:delete_card_task:{ent['task_fragment']}|card={ent['card_fragment']}]"
		return f"{msg}\n{audit}"

	if verb == "CREATE_BOARD":
		raw = await execute_create_board(ent["board_name"], ent.get("project_fragment", ""), lang)
		if raw.startswith("⚠"):
			return raw
		msg = _localise(
			"intent_router_create_board_success",
			"Board '{board}' created.",
			board=ent["board_name"],
		)
		audit = f"[AUDIT:create_board:{ent['board_name']}|project={ent.get('project_fragment', '')}]"
		return f"{msg}\n{audit}"

	if verb == "RENAME_BOARD":
		raw = await execute_rename_board(ent["board_fragment"], ent["new_name"], lang)
		if raw.startswith("⚠"):
			return raw
		msg = _localise(
			"intent_router_rename_board_success",
			"Board '{board}' renamed to '{new_name}'.",
			board=ent["board_fragment"], new_name=ent["new_name"],
		)
		audit = f"[AUDIT:rename_board:{ent['board_fragment']}|new_name={ent['new_name']}]"
		return f"{msg}\n{audit}"

	if verb == "DELETE_BOARD":
		raw = await execute_delete_board(ent["board_fragment"], lang)
		if raw.startswith("⚠"):
			return raw
		msg = _localise("intent_router_delete_board_success", "Board '{board}' deleted.", board=ent["board_fragment"])
		audit = f"[AUDIT:delete_board:{ent['board_fragment']}]"
		return f"{msg}\n{audit}"

	if verb == "CREATE_PROJECT":
		raw = await execute_create_project(ent["project_name"], lang)
		if raw.startswith("⚠duplicate:"):
			project = raw[len("⚠duplicate:"):]
			msg = _localise("intent_router_create_project_duplicate", "Project '{project}' already exists.", project=project)
			return msg
		if raw.startswith("⚠"):
			return raw
		msg = _localise("intent_router_create_project_success", "Project '{project}' created.", project=ent["project_name"])
		audit = f"[AUDIT:create_project:{ent['project_name']}]"
		return f"{msg}\n{audit}"

	if verb == "RENAME_PROJECT":
		raw = await execute_rename_project(ent["project_fragment"], ent["new_name"], lang)
		if raw.startswith("⚠notfound:"):
			msg = _localise("intent_router_rename_project_not_found", "Could not rename project '{project}' — not found.", project=ent["project_fragment"])
			return msg
		if raw.startswith("⚠"):
			return raw
		msg = _localise("intent_router_rename_project_success", "Project '{project}' renamed to '{new_name}'.", project=ent["project_fragment"], new_name=ent["new_name"])
		audit = f"[AUDIT:rename_project:{ent['project_fragment']}->{ent['new_name']}]"
		return f"{msg}\n{audit}"

	if verb == "DELETE_PROJECT":
		raw = await execute_delete_project(ent["project_fragment"], lang)
		if raw.startswith("⚠notfound:"):
			msg = _localise("intent_router_delete_project_not_found", "Could not delete project '{project}' — not found.", project=ent["project_fragment"])
			return msg
		if raw.startswith("⚠"):
			return raw
		msg = _localise("intent_router_delete_project_success", "Project '{project}' deleted.", project=ent["project_fragment"])
		audit = f"[AUDIT:delete_project:{ent['project_fragment']}]"
		return f"{msg}\n{audit}"

	if verb == "SORT_BOARD":
		board_id = ent.get("board_id", "")
		board_name = ent.get("board_name", ent.get("board_fragment", ""))
		board_frag = ent.get("board_fragment", board_name)
		# If classifier could not resolve board_id (colloquial name like "aquarium"),
		# use the fast model here — dispatch has a 120s budget vs classifier's ~3s.
		if not board_id and board_frag:
			try:
				from app.services.llm import chat as _res_chat
				_snap = await _get_planka_snapshot()
				if _snap:
					_all_b = [b for p in _snap for b in p["boards"]]
					_names = ", ".join((b.get("name") or "") for b in _all_b)
					_res_q = (
						f"Available boards: {_names}\n"
						f"Which board does the user mean by '{board_frag}'? "
						"The user may use a synonym or nickname (e.g. 'aquarium' for 'reef tank').\n"
						"Reply with ONLY the exact board name from the list, or NONE."
					)
					_res_ans = await asyncio.wait_for(_res_chat(_res_q, tier="fast"), timeout=30.0)
					_res_ans = _res_ans.strip().strip("'\".").rstrip(".,;!?")
					if _res_ans.upper() != "NONE":
						for _b in _all_b:
							if (_b.get("name") or "").lower() == _res_ans.lower():
								board_id = _b["id"]
								board_name = _b["name"]
								logger.info("SORT_BOARD dispatch: resolved '%s' → '%s'", board_frag, board_name)
								break
			except Exception as _res_err:
				logger.warning("SORT_BOARD dispatch: board resolution failed: %s", _res_err)
		if not board_id:
			_snap2 = await _get_planka_snapshot()
			if _snap2:
				_all_b2 = [b for p in _snap2 for b in p["boards"]]
				_avail = ", ".join((b.get("name") or "") for b in _all_b2)
				return f"⚠ Could not find a board matching '{board_frag}'. Available boards: {_avail}."
			return f"⚠ Could not locate board '{board_name}' in Planka."
		try:
			from app.services.planka import get_planka_auth_token
			from app.config import settings
			from app.services.llm import chat
			import httpx as _httpx
			import json as _json
			token = await get_planka_auth_token()
			headers = {"Authorization": f"Bearer {token}"}
			async with _httpx.AsyncClient(base_url=settings.PLANKA_BASE_URL, timeout=30.0, headers=headers) as client:
				resp = await client.get(f"/api/boards/{board_id}", params={"included": "lists,cards"})
				resp.raise_for_status()
				detail = resp.json()
				lists = detail.get("included", {}).get("lists", [])
				cards = detail.get("included", {}).get("cards", [])
				if not lists:
					return f"⚠ Board '{board_name}' has no lists to sort."

				# ── Step 1: Sort lists alphabetically via position patch ──────
				sorted_lists = sorted(lists, key=lambda l: l.get("name", "").lower())
				_step = 65535
				for i, lst in enumerate(sorted_lists):
					await client.patch(f"/api/lists/{lst['id']}", json={"position": _step * (i + 1)})

				# ── Step 2: Fast-model compact plan for card grouping ─────────
				# Ask the fast model for a JSON plan: which new lists to create
				# and which cards to move. Keeps output to ~80 tokens of JSON
				# so the local model can answer in seconds, not minutes.
				list_names = [l.get("name") or "?" for l in lists]
				card_entries = [{"name": c.get("name") or "?", "list": next((l.get("name") for l in lists if l["id"] == c.get("listId")), "?")} for c in cards]
				plan_prompt = (
					f"Board: {board_name}\n"
					f"Existing lists (do NOT recreate these): {list_names}\n"
					f"Cards (name → current list): {[(e['name'], e['list']) for e in card_entries]}\n"
					f"User request: {intent.raw_text}\n\n"
					"Output ONLY compact JSON — no commentary:\n"
					'{"new_lists":["name",...],"moves":{"card name":"target list"}}\n'
					"Rules:\n"
					"- NEVER suggest creating a list that already exists in the 'Existing lists' above.\n"
					"- Move ALL cards in 'Inbox' that clearly belong in another list.\n"
					"- Cards sharing the same theme (e.g. all coral/species names) belong in the same list.\n"
					"- Only create a new list if no existing list is a suitable home.\n"
					"- Empty arrays/objects only if genuinely nothing to do."
				)
				plan: dict = {}
				try:
					plan_text = await asyncio.wait_for(chat(plan_prompt, tier="fast"), timeout=25.0)
					_js = plan_text.find("{")
					_je = plan_text.rfind("}") + 1
					if _js >= 0 and _je > _js:
						plan = _json.loads(plan_text[_js:_je])
				except Exception as _pe:
					logger.warning("SORT_BOARD: plan generation failed: %s — skipping card moves", _pe)

				# ── Step 3: Execute plan deterministically ────────────────────
				all_list_index = {(l["name"] or "").lower(): l["id"] for l in lists}
				card_index = {(c["name"] or "").lower(): c for c in cards}
				results: list[str] = []

				# Create new lists from plan
				for new_name in plan.get("new_lists", []):
					if new_name.lower() in all_list_index:
						continue
					pos = _step * (len(sorted_lists) + len(all_list_index) + 1)
					cr = await client.post(f"/api/boards/{board_id}/lists", json={"name": new_name, "type": "active", "position": pos})
					if cr.status_code < 400:
						new_id = (cr.json().get("item") or {}).get("id", "")
						if new_id:
							all_list_index[new_name.lower()] = new_id
							results.append(f"Created list: {new_name}")

				# Move cards according to plan
				for card_name, target_list in plan.get("moves", {}).items():
					card = card_index.get(card_name.lower())
					target_id = all_list_index.get(target_list.lower())
					if card and target_id and card.get("listId") != target_id:
						mv = await client.patch(f"/api/cards/{card['id']}", json={"listId": target_id, "position": _step})
						if mv.status_code < 400:
							results.append(f"Moved '{card_name}' → {target_list}")

				# ── Step 4: Build summary ─────────────────────────────────────
				lines = [f"Reorganised '{board_name}':"]
				lines.append(f"Lists (alphabetical): {', '.join(l.get('name','?') for l in sorted_lists)}")
				if results:
					lines.append("")
					lines.extend(results)
				if not plan.get("new_lists") and not plan.get("moves"):
					lines.append("Cards already well-grouped — no moves needed.")
				lines.append("\nTo move a card: 'move <card> to <list>'.")
				audit = f"[AUDIT:sort_board:{board_name}|lists={len(sorted_lists)}|moves={len(plan.get('moves', {}))}]"
				_cache["ts"] = 0.0
				return "\n".join(lines) + "\n" + audit
		except Exception as _e:
			logger.error("intent_router SORT_BOARD failed: %s", _e)
			return f"⚠ Failed to reorganise board '{board_name}': {_e}"


        # Unknown verb — defensive fallback, should not be reachable.
	logger.warning("intent_router: dispatch called with unknown verb %s", verb)
	return ""
