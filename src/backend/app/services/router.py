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
from typing import AsyncIterator

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

# Phantom-confirmation guard — Z claimed success in prose without emitting a tag.
# Covers English and German (and partial Spanish/French) confirmation patterns.
_PHANTOM_RE = re.compile(
	r'\b(task added|board (added|created)|event (added|created)|card (added|created)'
	r'|added to (your )?(todo|list|board|today)'
	r'|done[\s\u2014\u2013-]+(task|board|card|event|create|add)'
	r'|done\s*[\u2014\u2013\-]+\s*(create|add|new)'
	# German phantom patterns
	r'|erledigt[\s\u2014\u2013\-]+(board|karte|aufgabe|liste)'
	r'|board[^.]{0,80}(neu\s+strukturiert|reorganisiert|sortiert|umstrukturiert)'
	r'|karten?[^.]{0,80}(verschoben|sortiert|erstellt)'
	r'|listen?[^.]{0,80}(erstellt|angelegt|umbenannt)'
	# Spanish / French
	r'|tablero[^.]{0,80}(reorganizado|reestructurado)'
	r'|tableau[^.]{0,80}(réorganisé|restructuré)'
	r')\b',
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
				for m, status in zip(task_msgs, statuses):
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
				result_text = f"⚠ Timed out reorganising board — the board may be very large. Try again."
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
				return

		# ── 0.52 Semantic board-management fallback ───────────────────────────
		# Fires when NO structural intent matched via regex. Uses the fast local
		# model to classify intent only (binary YES/NO sort-board question) —
		# board-name resolution happens inside dispatch which has a 120s budget.
		if intent is None:
			try:
				from app.services.llm import chat as _fast_chat
				from app.services.intent_router import StructuralIntent, dispatch_structural_intent, _get_planka_snapshot, _match_name
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
				# Use tier="auto" so cloud takes over when the local fast model is busy/slow.
				# The classify prompt is tiny (~100 tokens). Cloud response < 500 ms.
				_sem = await asyncio.wait_for(_fast_chat(_sem_prompt, tier="auto"), timeout=20.0)
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
		_ctx_history = history
		_force_cloud = False  # set True when a large-output task needs cloud LLM
		_rm = _REORGANIZE_BOARD_RE.search(user_text[:_MAX_RE_INPUT])
		if _rm:
			_board_frag = _rm.group("board").strip().rstrip(".,;!?")
			logger.info("Router: board-reorganise detected — fetching context for '%s'", _sanitize_for_log(_board_frag))
			try:
				from app.services.planka import get_board_full_context
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
			predicted = await chat(intent_prompt, tier="fast")
			predicted = predicted.lower().strip().strip("'\"")
			if predicted in ("research", "fitness", "nutrition", "life", "market-intel", "legal"):
				logger.info("Router: speculative-routing '%s...' → crew '%s'", _sanitize_for_log(user_text), predicted)
				routed_crews = [predicted]

		if routed_crews:
			crew_id = routed_crews[0]
			logger.info("Router: keyword-routing '%s...' → crew '%s'", _sanitize_for_log(user_text), crew_id)
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
		chunks = []
		async for token in chat_stream_with_context(
			user_text,
			history=_ctx_history,
			include_projects=True,
			include_people=True,
			tier_override="cloud" if _force_cloud else None,
		):
			chunks.append(token)
			yield token

		response = sanitise_output("".join(chunks))
		response = rehydrate_response(response, get_active_rep_map())

		if not response.strip():
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
