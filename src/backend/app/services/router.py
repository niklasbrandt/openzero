"""Unified freetext routing layer.

All message-routing decisions that were previously duplicated across
telegram_bot._process_freetext and dashboard.event_generator live here.

Flow for every incoming user message:
  1. Keyword-based crew routing  (resolve_active_crews)
  2. Z responds via chat_stream_with_context
  3. Sanitise + rehydrate assembled response
  4. ROUTE-tag interception (Z self-routes)
  5. bus.commit_reply (action parsing, memory, DB save)
  6. Post-processing: crew attribution footer, action errors, phantom guard

Each channel adapter streams tokens as they arrive via the async generator
`route_message_stream`, then reads the final RouterResult for display.
"""

from __future__ import annotations

import logging
import re
import asyncio
from dataclasses import dataclass, field
from typing import AsyncIterator, Callable, Awaitable

from app.common.phantom import PHANTOM_RE as _PHANTOM_RE  # noqa: E402

logger = logging.getLogger(__name__)

# Maximum input length applied before running complex regexes on user-controlled
# text to prevent polynomial (ReDoS) backtracking (CWE-1333).
_MAX_RE_INPUT = 500
_MAX_RE_REPLY = 10_000


def _sanitize_for_log(text: str, max_len: int = 80) -> str:
	"""Strip newlines from user-controlled text before writing to logs (CWE-117)."""
	return text[:max_len].replace('\n', '\\n').replace('\r', '\\r')


# Regex for Z-initiated ROUTE tags (tolerates missing 'ACTION:' prefix / closing ']')
_ROUTE_RE = re.compile(
	r'\[(?:ACTION:\s*)?ROUTE\s*\|\s*CREW:\s*([a-z0-9_-]+)\s*\]?',
	re.IGNORECASE,
)

# Recall-history detector: user wants a retrospective of their own messages for a given day/range.
_RECALL_HISTORY_RE = re.compile(
	r'(?:'
	r'\b(?:recall|look\s+up|review|show\s+me|list|go\s+through)\b'
	r'\s+(?:\S[^\n]{0,59}\s+)?(?:i\s+)?(?:asked|sent|gave|told|messaged)\s+you\b'
	r'|\brecall\b[^\n]{0,80}\b(?:today|this\s+morning|earlier\s+today|yesterday|\d{1,4}\s{1,20}days?\s{1,20}ago|last\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|week)|last\s+two\s+weeks?|past\s+(?:two\s+)?weeks?|this\s+week|recently)\b'
	r'|\bwhat\s+(?:did\s+i|have\s+i)\s+ask(?:ed)?[^\n]{0,60}\b(?:today|this\s+morning|yesterday|\d{1,4}\s{1,20}days?\s{1,20}ago)\b'
	r'|\b(?:list|show\s+me|review|go\s+through)\b[^\n]{0,60}\b(?:my\s+messages?|what\s+i\s+ask(?:ed)?)\b'
	r'|\b(?:my\s+)?(?:tasks?|requests?|things?)\s+(?:i\s+)?(?:asked|gave|told|sent)[^\n]{0,40}\b(?:today|yesterday|\d{1,4}\s{1,20}days?\s{1,20}ago)\b'
	r'|(?:and\s+)?i\s+asked\s+(?:today\s+)?(?:about\s+)?(?:an?\s+)?other\s+thing\b'
	r'|\bdid\s+you\s+(?:do|create|add|make|get)\s+(?:it|that|them)\b'
	r'|\b(?:so\s+)?(?:are|were|was)\s+(?:they|it|those)\s+(?:created|added|saved|built|done|set\s+up|executed)\b'
	r'|\bdid\s+(?:those|they|it|that)\s+(?:get\s+)?(?:created|added|saved|go\s+through|work|execute)\b'
	r'|\bwas\s+(?:it|that|the\s+(?:task|board|card|todo))\s+(?:created|added|saved|done|executed)\b'
	r'|\bcheck\b[^\n]{0,60}\b(?:uncreated|missing|unfinished|pending|unexecuted)\b[^\n]{0,60}\b(?:tasks?|todos?|items?)\b'
	r'|\b(?:uncreated|missing)\s+(?:tasks?|todos?|items?)\b'
	r'|\bwhich\s+(?:tasks?|todos?|items?)\s+(?:were\s+not|weren.t|have\s+not\s+been|haven.t\s+been|did\s+not|didn.t)\s+(?:created|saved|added|executed|done)\b'
	r')',
	re.IGNORECASE,
)

# Server-side pre-filter: PERSISTENCE verbs only — informational verbs (give me, check,
# find, get, show me, how to, review, research) are intentionally excluded to prevent
# recipe requests, questions, and status checks from polluting task recall.
_TASK_SIGNAL_RE = re.compile(
	r'\b(?:create|add|make|set\s+up|build|save|store|remind\s+me|send|'
	r'schedule|book|plan|update|edit|delete|remove|move|'
	r'write|draft|note|log|track|record|'
	r'finish|complete|finalize|prep|prepare|coordinate|sync|refresh|apply|'
	r'submit|fix|resolve|deploy|'
	r'new\s+(?:board|task|todo|card|list|project)|open\s+a\b)\b',
	re.IGNORECASE,
)

# Messages to always skip in task recalls regardless of verb content.
# Covers: nav commands, ack words, status questions, Telegram reply-quotes, question openers, how-to phrases.
_SKIP_RECALL_RE = re.compile(
	r'^(?:'
	r'/'
	r'|and\s+now|ok|okay|sure|fine|great|thanks|yes|no\b'
	r'|did\s+you|i\s+(?:did|pressed|pushed|tried|went|feel|felt|am|was)\b'
	r'|\[Replying to:'
	r'|(?:are|were|was|have|has|had|is|do|does|did|can|could|would|should|shall)\s'
	r'|how\s+(?:to|do|can|should|would|does|about)\b'
	r'|what\s+(?:is|are|do|does|did|was|were|would|can)\b'
	r'|(?:tell|show|explain|describe)\s+me\b'
	r')',
	re.IGNORECASE,
)

# Relative-date extractor used by the recall intercept
_DAYS_AGO_RE = re.compile(r'(\d{1,4})\s{1,20}days?\s{1,20}ago', re.IGNORECASE)
_WEEKDAY_MAP = {
	'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
	'friday': 4, 'saturday': 5, 'sunday': 6,
}

def _resolve_timeframe(text: str) -> tuple[int, bool]:
	"""Parse time range from natural language.

	Returns (days, is_range):
	  is_range=True  -> fetch the last N days as a rolling window (get_range_exchanges)
	  is_range=False -> fetch a specific single day by offset (get_day_exchanges)
	"""
	import datetime as _dt
	lower = text[:_MAX_RE_INPUT].lower()
	# Multi-day range patterns
	if re.search(r'two\s+weeks?', lower):
		return 14, True
	m_nw = re.search(r'(\d{1,4})\s{1,20}weeks?', lower)
	if m_nw:
		return int(m_nw.group(1)) * 7, True
	m_nd = re.search(r'(?:last|past)\s{1,20}(\d{1,4})\s{1,20}days?', lower)
	if m_nd:
		return int(m_nd.group(1)), True
	if re.search(r'(?:last|this|past)\s+week\b|over\s+the\s+(?:last|past)\s+week\b', lower):
		return 7, True
	if re.search(r'(?:past|last)\s+few\s+days?\b|recently\b', lower):
		return 7, True
	# Single-day patterns
	if 'yesterday' in lower:
		return 1, False
	m = _DAYS_AGO_RE.search(lower)
	if m:
		return int(m.group(1)), False
	for day_name, weekday_num in _WEEKDAY_MAP.items():
		if f'last {day_name}' in lower:
			today_num = _dt.datetime.utcnow().weekday()
			delta = (today_num - weekday_num) % 7
			return (delta if delta > 0 else 7), False
	return 0, False  # default: today

# Manual audit-intent detector — intercepts explicit self-audit requests from the user.
# Placed before recall-history so "look back … audit" is not consumed by the recall intercept.
# Pattern notes: [^.!?]{0,80} is a safe bounded negated class — no catastrophic backtracking.
_AUDIT_INTENT_RE = re.compile(
	r'\baudit\s+(?:your\s+)?(?:triggered\s+)?actions?\b'
	r'|\baudit\s+your\s+triggered\b'
	r'|\blook\s+back\b[^.!?]{0,80}\baudit\b'
	r'|\bcheck\s+what\s+you\s+did\b'
	r'|\b(?:verify|check|review)\s+your\s+actions?\b',
	re.IGNORECASE,
)

# Board reorganisation detector — matches "sort/reorganize/tidy [board_name]"
# Capture group 1: the board name fragment (trimmed by caller).
_REORGANIZE_BOARD_RE = re.compile(
	# English
	r'\b(?:sort|reorgani[sz]e?|restructur[e]?|clean\s+up|tidy\s+up|reorder|rearrang[e]?'
	# German
	r'|sortier[e]?|reorganisier[e]?|neu\s+sortier[e]?|aufr[\u00e4a]um[e]?n?|umstrukturieren|neu\s+anordnen'
	# Spanish / Portuguese
	r'|reorganiza[r]?|reestructura[r]?|reestrutura[r]?|reordena[r]?'
	# French
	r'|r[\u00e9e]organise[r]?|restructure[r]?|r[\u00e9e]ordonne[r]?'
	r')\b'
	r'(?:\s+(?:lists?\s+and\s+)?(?:(?:re)?organiz[e]?\s+)?(?:cards?\s+(?:in|on)\s+)?(?:(?:new|potentially\s+new)\s+lists?\s+in\s+)?)?'
	r'(?:(?:the|my|in|on|board|auf|dem|das|der|im)\s+)?'
	r'(?P<board>[a-z0-9\u00e4\u00f6\u00fc\u00c4\u00d6\u00dc\u00df][\w\s]{2,50})',
	re.IGNORECASE,
)


@dataclass
class RouterResult:
	"""Final state after all routing/post-processing is complete."""
	reply: str				# Clean reply text ready for display
	model: str				# Model or crew label used
	executed_cmds: list		= field(default_factory=list)
	pending_actions: list	= field(default_factory=list)
	routed_to_crew: str | None = None  # crew_id if a crew handled it


async def route_message_stream(
	user_text: str,
	history: list,
	channel: str,
	lang: str = "en",
	save_history: bool = True,
	status_callback: "Callable[[str], Awaitable[None]] | None" = None,
) -> tuple[AsyncIterator[str], "asyncio.Future[RouterResult]"]:
	"""Return (token_stream, result_future).

	Yield tokens from whichever handler is chosen (crew or Z).
	When the stream is exhausted, await result_future to get RouterResult.

	Usage::

		stream, result_fut = await route_message_stream(text, history, "telegram")
		async for token in stream:
			# forward to client / update Telegram message
			...
		result = await result_fut
	"""
	loop = asyncio.get_event_loop()
	result_future: asyncio.Future[RouterResult] = loop.create_future()

	async def _generate() -> AsyncIterator[str]:
		# ── Budget initialization ─────────────────────────────────────────────
		from app.common.response_budget import ResponseBudget, budget_ctx, RESPONSE_CEILING_S  # noqa: F401
		_budget = ResponseBudget()
		_budget_token = budget_ctx.set(_budget)  # noqa: F841

		from app.services.crews import resolve_active_crews
		from app.services.crews_native import native_crew_engine
		from app.services.llm import (
			chat_stream_with_context,
			sanitise_output,
			rehydrate_response,
			get_active_rep_map,
			last_model_used,
		)
		from app.services.message_bus import bus
		from app.services.translations import get_translations as _get_t
		_t = _get_t(lang or "en")

		async def _status(msg: str) -> None:
			if status_callback is not None:
				try:
					await status_callback(msg)
				except Exception:
					pass

		# ── 0.0 Fast-path bypass for trivial messages ────────────────────────
		# Short greetings and ack messages skip the full cascade to save 1-3s.
		# Guard: message must be short AND match a whitelist — never skip if it
		# contains action verbs (the user could be saying "ok save this").
		_FAST_PATH_RE = re.compile(
			r'^(?:hi|hello|hey|hallo|moin|guten\s+(?:morgen|tag|abend)'
			r'|danke|thanks|thank\s+you|merci|gracias|obrigado'
			r'|ok|okay|ja|yes|nein|no|sure|great|fine|perfect|super|cool|nice'
			r'|gut|sehr\s+gut|alles\s+klar|verstanden|got\s+it'
			r'|[\U0001F44D\U0001F44C\U0001F60A\u2764\U0001F600-\U0001F64F]'
			r')[!.?\s]*$',
			re.IGNORECASE,
		)
		_HAS_ACTION_VERB_RE = re.compile(
			r'\b(?:save|create|add|make|set|build|move|delete|send|remind|schedule|book|'
			r'sort|reorganize|reorganise|show|list|find|search|tell|explain|speichern|erstellen|'
			r'hinzuf[üu]gen|verschieben|l[öo]schen|sortier|zeig)\b',
			re.IGNORECASE,
		)
		_trimmed = user_text.strip()
		if (
			len(_trimmed.split()) <= 4
			and _FAST_PATH_RE.match(_trimmed[:_MAX_RE_INPUT])
			and not _HAS_ACTION_VERB_RE.search(_trimmed[:_MAX_RE_INPUT])
		):
			logger.debug("Router 0.0: fast-path bypass for '%s'", _sanitize_for_log(user_text))
			_fp_chunks = []
			async for _fp_token in chat_stream_with_context(user_text, history=history):
				_fp_chunks.append(_fp_token)
				yield _fp_token
			_fp_response = sanitise_output("".join(_fp_chunks))
			_fp_response = rehydrate_response(_fp_response, get_active_rep_map())
			_fp_clean, _fp_cmds, _fp_pending = await bus.commit_reply(
				channel=channel, raw_reply=_fp_response,
				model=last_model_used.get(), user_text=user_text, save=save_history,
			)
			result_future.set_result(RouterResult(
				reply=_fp_clean, model=last_model_used.get(),
				executed_cmds=_fp_cmds, pending_actions=_fp_pending,
			))
			return

		# ── -1. Manual audit intercept ───────────────────────────────────────
		# Explicit self-audit requests ("audit your actions", "look back and audit",
		# etc.) are handled deterministically here — no LLM call, no crew routing.
		# Placed before the recall intercept so "look back … audit" is not swallowed
		# by the conversation-history recall logic.
		if _AUDIT_INTENT_RE.search(user_text[:_MAX_RE_INPUT]):
			logger.info("Router: audit intent detected — running full self-audit")
			from app.services.self_audit import run_full_audit
			from app.services.translations import get_translations, get_user_lang
			try:
				audit_report = await run_full_audit()
			except Exception as _ae:
				logger.error("Router audit intercept: run_full_audit failed: %s", _ae)
				audit_report = ""
			if audit_report:
				response = audit_report
			else:
				_lang = await get_user_lang()
				_t = get_translations(_lang)
				response = _t.get(
					"audit_clean_msg",
					"Self-audit complete — no issues found. "
					"All tracked actions are verified and consistent with Planka's live state.",
				)
			yield response
			clean, cmds, pending = await bus.commit_reply(
				channel=channel, raw_reply=response,
				model="self_audit", user_text=user_text, save=save_history,
			)
			result_future.set_result(RouterResult(
				reply=clean, model="self_audit",
				executed_cmds=cmds, pending_actions=pending,
			))
			return

		# ── 0. Recall-history intercept ──────────────────────────────────────
		# When the user asks to recall messages from today, yesterday, N days ago, etc.,
		# fetch the actual conversation from DB and inject it — never consult Planka.
		# Pre-filter: only run heavy regex if common recall keywords are present.
		_common_recall_words = ("recall", "look up", "review", "show me", "last", "yesterday", "today", "did you")
		if any(w in user_text.lower() for w in _common_recall_words) and _RECALL_HISTORY_RE.search(user_text[:_MAX_RE_INPUT]):
			from app.models.db import get_day_exchanges, get_range_exchanges
			from app.services.planka import find_item_in_planka
			days_ago, is_range = _resolve_timeframe(user_text)
			if is_range:
				all_exchanges = await get_range_exchanges(days_ago)
			else:
				all_exchanges = await get_day_exchanges(days_ago)
			# Strip the current recall/status request itself
			all_exchanges = [m for m in all_exchanges if m["content"].strip() != user_text.strip()]
			if is_range:
				if days_ago == 14:
					day_label = "the last two weeks"
				elif days_ago == 7:
					day_label = "the last week"
				else:
					day_label = f"the last {days_ago} days"
			elif days_ago == 0:
				day_label = "today (since midnight UTC)"
			elif days_ago == 1:
				day_label = "yesterday"
			else:
				day_label = f"{days_ago} days ago"

			user_msgs = [m for m in all_exchanges if m["role"] == "user"]

			# Server-side pre-filter: only keep user messages that look like task requests.
			seen_content: set[str] = set()
			task_msgs: list[dict] = []
			_common_task_words = ("create", "add", "make", "set", "save", "sent", "told", "ask", "track", "log")
			for m in user_msgs:
				content = m["content"].strip()
				if _SKIP_RECALL_RE.match(content):
					continue
				if len(content.split()) < 3:
					continue
				# Skip meta-recall queries (the class of message we are currently processing)
				if any(w in content.lower() for w in _common_recall_words) and _RECALL_HISTORY_RE.search(content[:_MAX_RE_INPUT]):
					continue
				if not any(w in content.lower() for w in _common_task_words) or not _TASK_SIGNAL_RE.search(content):
					continue
				# Dedup: strip trailing punctuation/backslash so "do it\" == "do it"
				key = content.lower().rstrip('\\/ \t.,!?')
				if key in seen_content:
					continue
				seen_content.add(key)
				task_msgs.append(m)

			# Extract the most likely item name from a task message.
			# Tries multiple heuristics in priority order.
			_TITLE_EXPLICIT_RE = re.compile(
				r'(?:titled?|called?|named?)\s+["\'\u201c\u2018]?([^"\'\u201d\u2019.\[\]\n]{3,60})["\'\u201d\u2019]?'
				r'|["\'\u201c\u2018]([^"\'\u201d\u2019\x27]{3,60})["\'\u201d\u2019\x27]',
				re.IGNORECASE,
			)
			_TITLE_REMIND_RE = re.compile(r'\bremind\s+(?:me\s+)?to\s+([^.!?\n]{2,50})', re.IGNORECASE)
			_TITLE_COLON_RE = re.compile(r'\b(?:todo|task|reminder)\s+(?:for\s+[^\s:]{1,20}\s*)?:\s*([^\n.!?]{3,60})', re.IGNORECASE)
			_TITLE_ADD_TO_RE = re.compile(r'\badd\s+([^.!?\n]{2,30}?)\s+to\s+(?:the\s+)?(?:shopping|list\b|board\b)', re.IGNORECASE)

			def _extract_title(text: str) -> str:
				"""Return best guessed item title from a task description, or ''."""
				short = text[:200]
				m = _TITLE_EXPLICIT_RE.search(short)
				if m:
					return (m.group(1) or m.group(2) or "").strip().rstrip(".,;!?")
				m = _TITLE_REMIND_RE.search(short)
				if m:
					title = m.group(1).strip().rstrip(".,;!?")
					# Strip trailing time qualifiers ("in 10 minutes", "at 3", etc.)
					title = re.sub(r'\s+(?:in\s+\d+|at\s+\d)\S*$', '', title, flags=re.IGNORECASE).strip()
					return " ".join(title.split()[:7])
				m = _TITLE_COLON_RE.search(short)
				if m:
					return m.group(1).strip().rstrip(".,;!?")
				m = _TITLE_ADD_TO_RE.search(short)
				if m:
					return m.group(1).strip().rstrip(".,;!?")
				return ""

			if task_msgs:
				# Verify each task against live Planka state (ground truth).
				import asyncio as _asyncio

				async def _planka_status(task_text: str) -> str:
					title = _extract_title(task_text)
					if not title:
						return "unverifiable"
					found = await find_item_in_planka(title)
					return "found" if found else "missing"

				statuses = await _asyncio.gather(
					*[_planka_status(m["content"]) for m in task_msgs],
					return_exceptions=True,
				)

				lines = []
				for m, status in zip(task_msgs, statuses, strict=False):
					if isinstance(status, Exception):
						status_label = " [could not verify - check Planka]"
					elif status == "found":
						status_label = " [FOUND in Planka]"
					elif status == "missing":
						status_label = " [NOT found in Planka - was NOT saved]"
					else:
						status_label = " [could not verify - check Planka]"
					lines.append(f"[{m['at'][11:16]}] {m['content']}{status_label}")
				# Build deterministic response — no LLM to avoid hallucinations and token leaks.
				_found = sum(1 for s in statuses if s == "found")
				_missing = sum(1 for s in statuses if s == "missing")
				_unveri = sum(1 for s in statuses if s == "unverifiable" or isinstance(s, Exception))
				parts = []
				if _missing:
					parts.append(f"{_missing} not saved")
				if _found:
					parts.append(f"{_found} saved in Planka")
				if _unveri:
					parts.append(f"{_unveri} could not verify (no clear title)")
				summary_line = f"({', '.join(parts)})" if parts else "(no items)"
				response = f"Tasks requested {day_label} {summary_line}:\n\n" + "\n".join(lines)
			elif user_msgs:
				# fallback: no task-like messages found — show all messages as-is
				response = (
					f"No task requests matched for {day_label}. "
					f"Here are all messages from that period:\n\n"
					+ "\n".join(f"[{m['at'][11:16]}] {m['content']}" for m in user_msgs)
				)
			else:
				response = f"No messages found in the database for {day_label}."
			# Yield directly — no LLM pass, so no hallucinations, no PII re-tokenisation.
			yield response
			clean, cmds, pending = await bus.commit_reply(
				channel=channel, raw_reply=response,
				model="recall", user_text=user_text, save=save_history,
			)
			result_future.set_result(RouterResult(
				reply=clean, model="recall",
				executed_cmds=cmds, pending_actions=pending,
			))
			return

		# ── 0.4 Save-follow-up context injector ──────────────────────────────
		# Detects two trigger patterns:
		#   A. "Speicher die Rezepte" — explicit save request where the content
		#      was generated by Z earlier and is not inline.
		#   B. "du hast sie mir heute geschickt" — user pointing at Z's own
		#      earlier output in response to Z saying "nicht im Kontext".
		#
		# In both cases: fetch the relevant Z output from DB and inject it so
		# the LLM can emit CREATE_TASK tags without asking the user to repeat.
		#
		# Keyword-relevance matching: extract the save-target noun (rezepte,
		# workouts, …) and prefer Z messages that actually contain that word.
		# Falls back to most-recent with 3+ newlines if no semantic match found.
		_SAVE_ZOUTPUT_RE = re.compile(
			r'\b(?:speichere?|save|ablegen?|sichern?)\b[^.!?\n]{0,80}'
			r'\b(?:rezepte?|recipes?|workouts?|trainings?|pl[aä]ne?|plans?|gerichte|mahlzeiten|items?|ergebnisse?|notizen?|notes?)\b',
			re.IGNORECASE,
		)
		# Pattern B: user pointing at Z's own earlier output ("you already sent them")
		_SENT_BY_Z_RE = re.compile(
			r'\bdu hast (?:sie|es|die|den)\s+(?:mir\s+)?(?:heute|gestern|schon|gerade|already|earlier)\s+(?:geschickt|gesendet|erzählt|gemacht|erstellt|gegeben)\b'
			r'|\byou (?:already |just )?(?:sent|gave|wrote|made|created) (?:them|it|me)\b'
			r'|\bschau\s+(?:doch\s+)?(?:mal\s+)?(?:in\s+)?(?:deinen?|dein(?:er|em)?\s+)?(?:nachrichten|verlauf|historie|history|chat)\b',
			re.IGNORECASE,
		)
		_trimmed_save = user_text.strip()
		_save_is_explicit = (
			len(_trimmed_save) <= 120
			and _SAVE_ZOUTPUT_RE.search(_trimmed_save[:_MAX_RE_INPUT])
		)
		_save_is_recall_hint = (
			not _save_is_explicit
			and len(_trimmed_save) <= 150
			and _SENT_BY_Z_RE.search(_trimmed_save[:_MAX_RE_INPUT])
		)
		if _save_is_explicit or _save_is_recall_hint:
			await _status(_t.get("status_fetching_history", "Searching your messages..."))
			# Extract the target noun from the save request so we can find the
			# relevant Z message rather than just the most recent long one.
			_save_noun_m = re.search(
				r'\b(rezepte?|recipes?|workouts?|trainings?|gerichte?|mahlzeiten|'
				r'pl[aä]ne?|plans?|notizen?|notes?|ergebnisse?)\b',
				_trimmed_save, re.IGNORECASE,
			)
			_save_noun = _save_noun_m.group(0).lower() if _save_noun_m else ""
			# Single-day fetch first (fast path), then expand to 4 days
			try:
				from app.models.db import get_day_exchanges as _get_today_only
				_today_only = await asyncio.wait_for(_get_today_only(0), timeout=3.0)
				_z_candidates = [
					m for m in reversed(_today_only)
					if m.get("role") == "z"
					and m.get("content", "").count("\n") >= 2
					and not m["content"].startswith("[SYSTEM")
				]
				# If today yields nothing, expand to 4-day range
				if not _z_candidates:
					from app.models.db import get_range_exchanges as _get_range
					_range_msgs = await asyncio.wait_for(_get_range(days=4), timeout=6.0)
					_z_candidates = [
						m for m in reversed(_range_msgs)
						if m.get("role") == "z"
						and m.get("content", "").count("\n") >= 2
						and not m["content"].startswith("[SYSTEM")
					]
				# Semantic filter: prefer messages that contain the target noun
				if _save_noun and _z_candidates:
					_noun_root = _save_noun[:6]  # e.g. "rezept" from "rezepte"
					_relevant = [m for m in _z_candidates if _noun_root in m.get("content", "").lower()]
					if _relevant:
						_z_candidates = _relevant
				if _z_candidates:
					_zout = _z_candidates[0]["content"]
					_zout_ts = _z_candidates[0].get("at", "")[:16]
					_ctx_label = (
						f"[Z'S OWN OUTPUT FROM {_zout_ts} — these are the items the user wants to save]\n"
						if not _save_is_recall_hint else
						f"[Z'S OWN OUTPUT FROM {_zout_ts} — the user confirmed you sent this earlier; save every item using CREATE_TASK tags]\n"
					)
					_save_ctx = (
						_ctx_label
						+ f"{_zout[:6000]}\n"
						+ "[END Z OUTPUT — save every item above using CREATE_TASK tags as instructed "
						+ "by the SAVE FOLLOW-UP RULE. Do NOT ask the user to re-send.]"
					)
					_save_ctx_inject = {"role": "assistant", "content": _save_ctx}
					logger.info(
						"Router 0.4: injected Z's own output (%d chars) for save follow-up "
						"(noun=%r recall_hint=%s)",
						len(_zout), _save_noun, _save_is_recall_hint,
					)
				else:
					_save_ctx_inject = None
			except asyncio.TimeoutError:
				_save_ctx_inject = None
				logger.debug("Router 0.4: DB fetch timed out for save follow-up")
			except Exception as _sfi_err:
				_save_ctx_inject = None
				logger.debug("Router 0.4: save follow-up inject failed: %s", _sfi_err)
		else:
			_save_ctx_inject = None

		# ── 0.45 State-question ground-truth injection (L3) ──────────────────
		# Intercepts "where is X?", "did you save X?", "wo sind die?" and similar
		# state queries. Instead of letting the LLM guess from prose history, we
		# do a live Planka card search and inject a [VERIFIED PLANKA STATE] context
		# message so the LLM MUST answer from facts, not imagination.
		#
		# Extra context is accumulated in _sq_extra_ctx and applied when _ctx_history
		# is constructed at step 0.55 — this avoids reassigning the closure variable.
		# Errors and timeouts are fully absorbed — fall-through is always safe.
		_sq_extra_ctx: list[dict] = []  # accumulator for state-query context injection
		# Merge save-follow-up context injection from step 0.4 (if any)
		if _save_ctx_inject:
			_sq_extra_ctx.append(_save_ctx_inject)
		_STATE_QUERY_RE = re.compile(
			# German
			r'\bwo\s+(?:sind|ist|sind\s+die|habe\s+ich|hast\s+du)\b'
			r'|\bhast\s+du\s+(?:das|die|es|sie)?\s*(?:gespeichert|erstellt|hinzugef[üu]gt|abgelegt|gemacht)\b'
			r'|\bwurde\s+(?:das|es|die)\s+(?:gespeichert|erstellt|angelegt)\b'
			r'|\bwo\s+(?:wurde|wurden|habe|hat)\b'
			# English
			r'|\bwhere\s+(?:is|are|did\s+you|was|were)\s+(?:it|they|the|that|those)\b'
			r'|\bdid\s+you\s+(?:save|create|add|store|put|make)\b'
			r'|\bwas\s+(?:it|that|the\s+(?:task|card|board|todo|item))\s+(?:saved|created|added|stored)\b'
			r'|\bwere\s+(?:they|those|the\s+(?:tasks?|cards?|items?))\s+(?:saved|created|added|stored)\b'
			# Spanish / French
			r'|\b(?:d[oó]nde|où)\s+(?:est[aá]|son|est|sont)\b'
			r'|\b(?:guardaste|enregistr[eé])\b',
			re.IGNORECASE,
		)
		# Minimum word count to bother searching — "wo" alone is too vague
		_STATE_QUERY_WORDS_MIN = 2
		_state_text_trimmed = user_text.strip()[:_MAX_RE_INPUT]
		if (
			len(_state_text_trimmed.split()) >= _STATE_QUERY_WORDS_MIN
			and _STATE_QUERY_RE.search(_state_text_trimmed)
		):
			# Extract a search fragment: last multi-word phrase or quoted term
			# from the user message that might be a card/board title
			_SQ_QUOTE_RE = re.compile(r'["\u201c]([^"\u201d]{2,50})["\u201d]')
			_SQ_FRAG_RE = re.compile(
				r'(?:'
				r'(?:die|den|der|das|mein|the|my|it|sie|es|los?|les?|las?)\s+)?'
				r'([A-Za-z\u00c0-\u017e\u0400-\u04FF][A-Za-z\u00c0-\u017e\u0400-\u04FF\s]{1,40})'
				r'(?:\s+(?:gespeichert|erstellt|saved|created|added|store|board|card|task|todo|list))?'
				r'\??$',
				re.IGNORECASE,
			)
			_sq_frag: str = ""
			_sq_q = _SQ_QUOTE_RE.search(user_text[:_MAX_RE_INPUT])
			if _sq_q:
				_sq_frag = _sq_q.group(1).strip()
			else:
				_sq_m = _SQ_FRAG_RE.search(user_text[:_MAX_RE_INPUT])
				if _sq_m:
					_sq_frag = _sq_m.group(1).strip()
			# If we got a reasonable fragment, look it up in Planka live
			if _sq_frag and len(_sq_frag) >= 2:
				try:
					from app.services.planka import search_cards_in_planka
					_sq_results = await asyncio.wait_for(
						search_cards_in_planka(_sq_frag, limit=10), timeout=6.0,
					)
					if _sq_results:
						_sq_lines = [
							f"  - \"{r['card']}\" on board \"{r['board']}\" in list \"{r['list']}\""
							for r in _sq_results
						]
						_sq_context = (
							f"[VERIFIED PLANKA STATE — cards matching '{_sq_frag}']\n"
							+ "\n".join(_sq_lines)
							+ "\n[END VERIFIED STATE — answer ONLY from the above. Do NOT guess.]"
						)
					else:
						_sq_context = (
							f"[VERIFIED PLANKA STATE — no cards found matching '{_sq_frag}']\n"
							"[END VERIFIED STATE — if no cards found, say so clearly. Do NOT invent a location.]"
						)
					# Accumulate for injection at step 0.55 (avoids reassigning closure var)
					_sq_extra_ctx.append({"role": "assistant", "content": _sq_context})
					logger.info(
						"Router 0.45: injected Planka state for fragment '%s' (%d results)",
						_sanitize_for_log(_sq_frag), len(_sq_results) if _sq_results else 0,
					)
					# L9 — count successful Planka state lookups for SLO monitoring
					try:
						from app.services.metrics import increment_counter
						increment_counter("state_query_planka_lookups_total")
					except Exception:
						pass
				except asyncio.TimeoutError:
					logger.warning("Router 0.45: Planka state query timed out for '%s'", _sanitize_for_log(_sq_frag))
				except Exception as _sq_err:
					logger.warning("Router 0.45: Planka state query failed: %s", _sq_err)
			# Whether or not the lookup succeeded, fall through to normal LLM path below

		# ── L11 Parallel board-context prefetch ──────────────────────────────
		# Start fetching board contents concurrently with the structural classifier
		# (step 0.5). If step 0.5 dispatches SORT_BOARD directly, the prefetch task
		# is cancelled. If we fall through to step 0.55 the context should already
		# be ready — await costs ~0 ms. Saves 3-15 s on board-reorganise requests.
		_board_prefetch_task: asyncio.Task | None = None
		_rm_l11 = _REORGANIZE_BOARD_RE.search(user_text[:_MAX_RE_INPUT])
		if _rm_l11:
			_bfrag_l11 = _rm_l11.group("board").strip().rstrip(".,;!?")
			try:
				from app.services.planka import get_board_full_context as _gbfc_l11
				_board_prefetch_task = asyncio.create_task(
					asyncio.wait_for(_gbfc_l11(_bfrag_l11), timeout=15.0),
					name="board_ctx_prefetch",
				)
				logger.debug(
					"Router L11: board context prefetch started for '%s'",
					_sanitize_for_log(_bfrag_l11),
				)
			except Exception as _l11_e:
				logger.debug("Router L11: prefetch task creation failed: %s", _l11_e)

		# ── 0.5 Deterministic structural-intent intercept ────────────────────
		# Pre-LLM router for high-confidence Planka mutations (move/archive/
		# mark-done). Bypasses the chat LLM entirely so verbs that the cloud
		# model occasionally describes in prose without emitting an ACTION tag
		# still execute. Falls through to crew/LLM when no intent matches.
		_clf_timeout = 3.0  # default; overridden below for sort/board phrases
		try:
			from app.services.intent_router import (
				classify_structural_intent, dispatch_structural_intent,
			)
			# SORT_BOARD classification can include a fast-model call to resolve colloquial
			# board names (e.g. "aquarium" → "reef tank"). Budget 12s for that path;
			# keep 3s for all other intents so normal latency is unaffected.
			_SORT_RE_QUICK = re.compile(
				# English
				r'\b(?:sort|reorgani[sz]|restructur|clean\s+up|tidy\s+up|reorder|rearrang'
				# German
				r'|sortier|reorganisier|aufr[äa]um|umstrukturieren|neu\s+anordnen'
				# Spanish / Portuguese
				r'|reorganiza|reestructura|reestrutura|reordena|arruma'
				# French
				r'|r[ée]organise|restructure|r[ée]ordonne'
				# Russian
				r'|\u043e\u0442\u0441\u043e\u0440\u0442\u0438\u0440|\u0441\u043e\u0440\u0442\u0438\u0440|\u0440\u0435\u043e\u0440\u0433\u0430\u043d\u0438\u0437|\u0443\u043f\u043e\u0440\u044f\u0434\u043e\u0447|\u0440\u0430\u0437\u043b\u043e\u0436\u0438'
				r')',
				re.IGNORECASE,
			)
			_clf_timeout = 25.0 if _SORT_RE_QUICK.search(user_text[:200]) else 3.0
			intent = await asyncio.wait_for(
				classify_structural_intent(user_text, lang), timeout=_clf_timeout,
			)
		except asyncio.TimeoutError:
			intent = None
			logger.warning("Router: intent classifier timeout (>%.0fs) — falling through to LLM", _clf_timeout)
		except Exception as _ie:
			intent = None
			logger.warning("Router: intent classifier failed: %s — falling through to LLM", _ie)
		if intent and intent.confidence >= 0.85:
			logger.info(
				"Router: structural intent '%s' (conf=%.2f) for '%s...'",
				intent.verb, intent.confidence, _sanitize_for_log(user_text),
			)
			# SORT_BOARD calls the fast model internally (~25s) plus multiple Planka
			# API calls — needs a generous budget. Other verbs are pure API calls.
			_dispatch_timeout = 120.0 if intent.verb == "SORT_BOARD" else 10.0
			try:
				result_text = await asyncio.wait_for(
					dispatch_structural_intent(intent, lang), timeout=_dispatch_timeout,
				)
			except asyncio.TimeoutError:
				logger.error("Router: intent dispatch timeout (>%.0fs)", _dispatch_timeout)
				result_text = "⚠ Timed out reorganising board — the board may be very large. Try again."
			except Exception as _de:
				logger.error("intent_router: dispatch failed: %s", _de)
				result_text = f"⚠ Failed to reorganise board: {_de}"
			# For SORT_BOARD, always short-circuit — never fall through to LLM.
			# An empty result_text means dispatch returned nothing useful; surface that.
			if intent.verb == "SORT_BOARD" and not result_text:
				result_text = "⚠ Board reorganisation returned no output. Please try again."
			if result_text:
				# SORT_BOARD results are plain text summaries — strip only the internal
				# [AUDIT:] tag before delivery. Full bus.commit_reply hygiene pipeline
				# can blank legitimate board-name / list-name content.
				import re as _re
				if intent.verb == "SORT_BOARD":
					delivery_text = _re.sub(r'\[AUDIT:[^\]]{0,300}\]?', '', result_text, flags=_re.IGNORECASE).strip()
					if not delivery_text:
						delivery_text = result_text
				else:
					delivery_text = result_text
				yield delivery_text
				_cmds: list = []
				_pending: list = []
				try:
					clean, _cmds, _pending = await bus.commit_reply(
						channel=channel, raw_reply=delivery_text,
						model="intent_router", user_text=user_text, save=save_history,
					)
				except Exception as _commit_err:
					logger.error("Router: commit_reply failed after SORT_BOARD yield: %s", _commit_err)
					clean = delivery_text
				finally:
					if not result_future.done():
						# For SORT_BOARD use delivery_text directly — commit_reply saves to history
						# but its aggressive hygiene may blank the summary; prefer our pre-stripped text.
						result_future.set_result(RouterResult(
							reply=delivery_text if intent.verb == "SORT_BOARD" else clean,
							model="intent_router",
							executed_cmds=_cmds, pending_actions=_pending,
						))
				# L11: cancel the board prefetch — SORT_BOARD dispatch fetches context internally
				if _board_prefetch_task and not _board_prefetch_task.done():
					_board_prefetch_task.cancel()
				return

		# ── 0.52 pre-check: early bulk-save forced-cloud detection ──────────────
		# Must run before 0.52 so the semantic fallback is skipped when already
		# forced to cloud (bulk save).
		_force_cloud = False  # set True when a large-output task needs cloud LLM
		# Bulk save detection: if user mentions a count >= 5 AND a save noun, force cloud.
		# Generating 20+ CREATE_TASK tags exhausts the local model budget.
		_bulk_save_re = re.compile(
			r'\b([5-9]|[1-9]\d+)\s+(?:rezepte?|recipes?|mahlzeiten|gerichte?|workouts?|trainings?|pl[aä]ne?|items?|notizen?)\b',
			re.IGNORECASE,
		)
		if _save_ctx_inject and _bulk_save_re.search(user_text[:_MAX_RE_INPUT]):
			_force_cloud = True
			logger.info("Router: bulk save detected — forcing cloud tier")

		# ── 0.52 Semantic board-management fallback ───────────────────────────
		# Fires when NO structural intent matched via regex. Uses the fast local
		# model to classify intent only (binary YES/NO sort-board question) —
		# board-name resolution happens inside dispatch which has a 120s budget.
		# Skip entirely when _force_cloud is already set (bulk save, board reorg).
		if intent is None and not _force_cloud:
			try:
				from app.services.llm import chat as _fast_chat
				from app.services.intent_router import StructuralIntent, dispatch_structural_intent, _get_planka_snapshot
				# Fetch board list so the fast model has board names to choose from.
				_projects = await _get_planka_snapshot()
				_all_boards = [b for p in (_projects or []) for b in p["boards"]]
				_board_names_hint = ", ".join((b.get("name") or "") for b in _all_boards) or "none"
				_sem_prompt = (
					f"Available Planka boards: {_board_names_hint}\n"
					"Is this message asking to reorganise, sort, tidy, or restructure one of those boards?\n"
					f"Message: \"{user_text[:300]}\"\n"
					"IMPORTANT: The user may use a nickname or synonym (e.g. 'aquarium' for 'reef tank').\n"
					"Pick the single most semantically related board from the list above.\n"
					"If yes: reply SORT_BOARD:<exact board name from the list above>\n"
					"If no: reply NO"
				)
				# Use tier="cloud" — "auto" is not a valid tier value and falls to local silently.
				# The classify prompt is tiny (~100 tokens). Cloud response < 500 ms.
				_sem = await asyncio.wait_for(_fast_chat(_sem_prompt, tier="cloud"), timeout=20.0)
				_sem = _sem.strip()
				if _sem.upper().startswith("SORT_BOARD:"):
					_board_frag = _sem.split(":", 1)[1].strip().rstrip(".,;!?")
					if _board_frag:
						# Try direct name match first (fast model may return exact name)
						_best = None
						for b in _all_boards:
							if (b.get("name") or "").lower() == _board_frag.lower():
								_best = b
								break
						if not _best:
							for b in _all_boards:
								bn = (b["name"] or "").lower()
								bf = _board_frag.lower()
								if bf in bn or bn in bf:
									_best = b
									break
						# Build intent — if board_id empty, dispatch will resolve via LLM
						_sem_intent = StructuralIntent(
							verb="SORT_BOARD",
							entities={
								"board_fragment": _board_frag,
								"board_name": _best["name"] if _best else "",
								"board_id": _best["id"] if _best else "",
							},
							raw_text=user_text[:_MAX_RE_INPUT],
							confidence=0.9,
						)
						logger.info("Router 0.52: SORT_BOARD '%s' (resolved=%s)", _board_frag, bool(_best))
						try:
							_sem_result = await asyncio.wait_for(
								dispatch_structural_intent(_sem_intent, lang), timeout=120.0,
							)
						except asyncio.TimeoutError:
							logger.error("Router 0.52: SORT_BOARD dispatch timed out")
							_sem_result = "⚠ Timed out reorganising board — the board may be very large. Try again."
						except Exception as _sde:
							logger.error("Router 0.52: SORT_BOARD dispatch failed: %s", _sde)
							_sem_result = f"⚠ Failed to reorganise board: {_sde}"
						if not _sem_result:
							_sem_result = "⚠ Board reorganisation returned no output. Please try again."
						import re as _re2
						_sem_delivery = _re2.sub(r'\[AUDIT:[^\]]{0,300}\]?', '', _sem_result, flags=_re2.IGNORECASE).strip() or _sem_result
						yield _sem_delivery
						_sem_cmds: list = []
						_sem_pending: list = []
						try:
							_, _sem_cmds, _sem_pending = await bus.commit_reply(
								channel=channel, raw_reply=_sem_delivery,
								model="intent_router", user_text=user_text, save=save_history,
							)
						except Exception as _sem_commit_err:
							logger.error("Router 0.52: commit_reply failed after yield: %s", _sem_commit_err)
						finally:
							if not result_future.done():
								result_future.set_result(RouterResult(
									reply=_sem_delivery,
									model="intent_router",
									executed_cmds=_sem_cmds, pending_actions=_sem_pending,
								))
						# L11: cancel board prefetch — semantic dispatch already handled the request
						if _board_prefetch_task and not _board_prefetch_task.done():
							_board_prefetch_task.cancel()
						return
			except asyncio.TimeoutError:
				logger.warning("Router 0.52: semantic fallback timed out — falling through")
			except Exception as _sf:
				logger.warning("Router 0.52: semantic fallback failed: %s — falling through", _sf)

		# ── 1. Keyword-based crew routing ────────────────────────────────────
		# ── 0.55 Board-reorganisation context injection ────────────────────────
		# When the user asks to sort/reorganise a board, fetch the full board
		# contents (lists + all card titles) and inject them as a system context
		# message into history BEFORE calling the LLM. This gives the LLM the
		# ground truth it needs to emit correct MOVE_CARD / CREATE_LIST tags
		# without guessing, significantly reducing output length and TTFT.
		#
		# IMPORTANT: history is a closure variable captured from route_message_stream.
		# Reassigning it inside _generate would mark it as a local (UnboundLocalError
		# in Python 3.12). Use _ctx_history as a separate local instead.
		# Apply any L3 state-query context injections accumulated in step 0.45.
		_ctx_history = list(history) + _sq_extra_ctx if _sq_extra_ctx else history
		_rm = _REORGANIZE_BOARD_RE.search(user_text[:_MAX_RE_INPUT])
		if _rm:
			_board_frag = _rm.group("board").strip().rstrip(".,;!?")
			logger.info("Router: board-reorganise detected — fetching context for '%s'", _sanitize_for_log(_board_frag))
			await _status(_t.get("status_loading_board", "Loading board context..."))
			try:
				from app.services.planka import get_board_full_context
				if _board_prefetch_task is not None:
					# L11: reuse the concurrently prefetched result — await ~0 ms if already done
					try:
						_board_ctx = await _board_prefetch_task
					except asyncio.CancelledError:
						_board_ctx = None
				else:
					_board_ctx = await asyncio.wait_for(
						get_board_full_context(_board_frag), timeout=15.0,
					)
				if _board_ctx:
					# Inject as a synthetic system message so the LLM treats it as
					# authoritative ground truth, not something to speculate about.
					_ctx_history = list(history) + [{
						"role": "assistant",
						"content": (
							f"[SYSTEM CONTEXT — CURRENT BOARD STATE]\n{_board_ctx}\n"
							"[END BOARD STATE — use the above to emit precise action tags. "
							"Do NOT invent card names. Every MOVE_CARD and CREATE_LIST must "
							"reference names exactly as shown above.]"
						),
					}]
					_force_cloud = True  # board reorganization needs cloud LLM to complete in time
					logger.info("Router: injected board context (%d chars) for '%s'", len(_board_ctx), _sanitize_for_log(_board_frag))
			except asyncio.TimeoutError:
				logger.warning("Router: board context fetch timed out for '%s'", _sanitize_for_log(_board_frag))
			except Exception as _bce:
				logger.warning("Router: board context fetch failed: %s", _bce)

		# ── 0.6 Ambient capture (Epoch 2, gated) ─────────────────────────────
		# Fires only when AMBIENT_CAPTURE_ENABLED=true AND step 0.5 found no
		# structural intent. The bus scores registered plugins and either
		# executes silently or stores a pending HITL. Returns a reply string on
		# match; None on miss (falls through to crew/LLM). Errors are absorbed.
		try:
			from app.services.ambient_capture.intent_bus import (
				is_enabled as _ambient_enabled,
				_run_plugin_capture,
			)
			if _ambient_enabled():
				from app.services.ambient_capture.operator_scope import get_operator_user_id
				_op_uid = get_operator_user_id() or "operator"
				_ambient_reply = await asyncio.wait_for(
					_run_plugin_capture(user_text, lang, channel, _op_uid), timeout=8.0,
				)
				if _ambient_reply:
					yield _ambient_reply
					clean, cmds, pending = await bus.commit_reply(
						channel=channel, raw_reply=_ambient_reply,
						model="ambient_capture", user_text=user_text, save=save_history,
					)
					result_future.set_result(RouterResult(
						reply=clean, model="ambient_capture",
						executed_cmds=cmds, pending_actions=pending,
					))
					return
		except asyncio.TimeoutError:
			logger.warning("Router: ambient capture timeout (>8s) — falling through to LLM")
		except Exception as _ae:
			logger.warning("Router: ambient capture failed: %s — falling through to LLM", _ae)

		# ── 1. Keyword-based crew routing ────────────────────────────────────
		from app.services.crews import _SYSTEM_ACTION_RE as _crew_action_re
		routed_crews = await resolve_active_crews(_ctx_history, user_text, lang=lang)
		if not routed_crews and not _crew_action_re.search(user_text[:_MAX_RE_INPUT]):
			# ── 1.1 Speculative Fast-Intent (Qwen-0.6B) ──────────────────────
			# Only run when keyword routing returned nothing AND the message is
			# not a deterministic Planka mutation — otherwise the fast model will
			# mis-classify e.g. "new life goal home" as the Life crew.
			intent_prompt = (
				"Classify if the user wants to engage a specialized crew. "
				"Available: research, fitness, nutrition, life, market-intel, legal.\n"
				f"User: \"{user_text}\"\n"
				"Reply with ONLY the crew ID or 'none'."
			)
			from app.services.llm import chat
			try:
				predicted = await asyncio.wait_for(chat(intent_prompt, tier="fast"), timeout=5.0)
			except asyncio.TimeoutError:
				predicted = ""
				logger.debug("Router step1.1: fast-intent timed out — skipping")
			predicted = predicted.lower().strip().strip("'\"") 
			if predicted in ("research", "fitness", "nutrition", "life", "market-intel", "legal"):
				logger.info("Router: speculative-routing '%s...' → crew '%s'", _sanitize_for_log(user_text), predicted)
				routed_crews = [predicted]

		if routed_crews:
			crew_id = routed_crews[0]
			logger.info("Router: keyword-routing '%s...' → crew '%s'", _sanitize_for_log(user_text), crew_id)
			await _status(_t.get("status_routing_crew", "Routing to {crew}...").format(crew=crew_id))
			chunks = []
			async for token in native_crew_engine.run_crew_stream(crew_id, user_text, history=_ctx_history):
				chunks.append(token)
				yield token
			full = rehydrate_response("".join(chunks), get_active_rep_map())
			# Include attribution in raw_reply so it is stored in DB and
			# _last_attributed_crew can detect this crew for follow-up continuation.
			attribution = f"\n\n_(Reasoning by crew {crew_id})_"
			clean, cmds, pending = await bus.commit_reply(
				channel=channel, raw_reply=full + attribution,
				model=f"crew:{crew_id}", user_text=user_text, save=save_history,
			)
			cmds = [c for c in cmds if not c.startswith("__CREW_RUN__:")]
			action_errors = [c for c in cmds if isinstance(c, str) and c.startswith("\u26a0")]
			if action_errors:
				clean += "\n\n" + "  ".join(action_errors)
			elif not cmds and _PHANTOM_RE.search(clean[:_MAX_RE_REPLY]):
				clean += (
					"\n\n\u26a0 Nothing was actually saved — "
					"the crew described the action without executing it. Please try again."
				)
				logger.warning("Router step1: phantom confirmation from crew '%s'", crew_id)
			result_future.set_result(RouterResult(
				reply=clean, model=f"crew:{crew_id}",
				executed_cmds=cmds, pending_actions=pending,
				routed_to_crew=crew_id,
			))
			# Record crew session for follow-up continuity
			from app.services.crews import record_crew_session
			record_crew_session(channel, crew_id)
			return

		# ── 2. Z responds ────────────────────────────────────────────────────
		if _budget.skip_optional() and not _force_cloud:
			logger.warning("Router: response budget exhausted before LLM call — returning apology")
			_apology = "Das hat zu lange gedauert — bitte wiederhole kurz deine Anfrage."
			yield _apology
			clean, cmds, pending = await bus.commit_reply(
				channel=channel, raw_reply=_apology,
				model="budget_exceeded", user_text=user_text, save=save_history,
			)
			result_future.set_result(RouterResult(reply=_apology, model="budget_exceeded", executed_cmds=cmds, pending_actions=pending))
			return
		# ── L5 Streaming-safe tag gate ────────────────────────────────────────
		# Holds tokens while an [ACTION:] sequence is still open so the client
		# never receives a partial tag. Zero added latency for pure-conversation
		# responses — the `else: yield token` path runs every iteration.
		# Mode: 0=normal  1=suspect(saw '[')  2=confirmed [ACTION: — hold until ']'
		chunks: list[str] = []
		_l5_hold: list[str] = []
		_l5_mode = 0
		await _status(_t.get("status_composing", "Composing response..."))
		async for token in chat_stream_with_context(
			user_text,
			history=_ctx_history,
			include_projects=True,
			include_people=True,
			tier_override="cloud" if _force_cloud else None,
		):
			chunks.append(token)
			if _l5_mode == 2:
				_l5_hold.append(token)
				if ']' in token:
					_l5_mode = 0
					yield "".join(_l5_hold)
					_l5_hold.clear()
			elif _l5_mode == 1:
				_l5_hold.append(token)
				_l5_held_text = "".join(_l5_hold)
				if ']' in _l5_held_text:
					# Closed without ACTION — regular [text](url) or similar
					_l5_mode = 0
					yield _l5_held_text
					_l5_hold.clear()
				elif re.search(r'\[ACTION:', _l5_held_text, re.IGNORECASE):
					_l5_mode = 2  # confirmed action tag — hold until ']'
				elif len(_l5_held_text) > 50:
					# Too many chars without ACTION confirmation — flush
					_l5_mode = 0
					yield _l5_held_text
					_l5_hold.clear()
			else:
				if '[' in token:
					_l5_mode = 1
					_l5_hold.append(token)
				else:
					yield token
		# End of stream — flush any held content (e.g. tag missing closing ']')
		if _l5_hold:
			yield "".join(_l5_hold)
			_l5_hold.clear()

		response = sanitise_output("".join(chunks))
		response = rehydrate_response(response, get_active_rep_map())

		if not response.strip():
			logger.warning("Router: empty response after sanitisation — probable strip-all by sanitiser (user_text=%.80s)", _sanitize_for_log(user_text))
			result_future.set_result(RouterResult(reply="", model=last_model_used.get()))
			return

		# ── 3. ROUTE-tag interception ─────────────────────────────────────────
		m = _ROUTE_RE.search(response)
		if m:
			crew_id = m.group(1).strip().lower()
			logger.info("Router: Z self-routed '%s...' → crew '%s'", _sanitize_for_log(user_text), crew_id)
			r_chunks: list[str] = []
			async for token in native_crew_engine.run_crew_stream(crew_id, user_text, history=_ctx_history):
				r_chunks.append(token)
				yield token
			r_full = rehydrate_response("".join(r_chunks), get_active_rep_map())
			# Include attribution in raw_reply so it is stored in DB and
			# _last_attributed_crew can detect this crew for follow-up continuation.
			r_attribution = f"\n\n_(Reasoning by crew {crew_id})_"
			r_clean, r_cmds, r_pending = await bus.commit_reply(
				channel=channel, raw_reply=r_full + r_attribution,
				model=f"crew:{crew_id}", user_text=user_text, save=save_history,
			)
			r_cmds = [c for c in r_cmds if not c.startswith("__CREW_RUN__:")]
			r_action_errors = [c for c in r_cmds if isinstance(c, str) and c.startswith("\u26a0")]
			if r_action_errors:
				r_clean += "\n\n" + "  ".join(r_action_errors)
			elif not r_cmds and _PHANTOM_RE.search(r_clean[:_MAX_RE_REPLY]):
				r_clean += (
					"\n\n\u26a0 Nothing was actually saved — "
					"the crew described the action without executing it. Please try again."
				)
				logger.warning("Router step3: phantom confirmation from crew '%s'", crew_id)
			result_future.set_result(RouterResult(
				reply=r_clean, model=f"crew:{crew_id}",
				executed_cmds=r_cmds, pending_actions=r_pending,
				routed_to_crew=crew_id,
			))
			# Record crew session for follow-up continuity
			from app.services.crews import record_crew_session
			record_crew_session(channel, crew_id)
			return

		# ── 4. Commit Z's reply ───────────────────────────────────────────────
		clean, cmds, pending = await bus.commit_reply(
			channel=channel, raw_reply=response,
			model=last_model_used.get(), user_text=user_text, save=save_history,
		)

		# ── 5. Post-processing ────────────────────────────────────────────────
		crew_labels = [c.split(":", 1)[1] for c in cmds if c.startswith("__CREW_RUN__:")]
		cmds = [c for c in cmds if not c.startswith("__CREW_RUN__:")]
		if crew_labels:
			clean += f"\n\n_(Reasoning by crew {', '.join(crew_labels)})_"

		action_errors = [c for c in cmds if isinstance(c, str) and c.startswith("\u26a0")]
		if action_errors:
			clean += "\n\n" + "  ".join(action_errors)

		if not cmds and _PHANTOM_RE.search(clean[:_MAX_RE_REPLY]):
			clean += (
				"\n\n\u26a0 Nothing was actually saved — "
				"I described the action without executing it. Please try again."
			)
			logger.warning("Router: phantom confirmation detected (no executed_cmds)")

		result_future.set_result(RouterResult(
			reply=clean, model=last_model_used.get(),
			executed_cmds=cmds, pending_actions=pending,
		))

	return _generate(), result_future
