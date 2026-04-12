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
	r'\s+(?:.{0,60}\s+)?(?:i\s+)?(?:asked|sent|gave|told|messaged)\s+you\b'
	r'|\brecall\b.{0,80}\b(?:today|this\s+morning|earlier\s+today|yesterday|\d+\s+days?\s+ago|last\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|week)|last\s+two\s+weeks?|past\s+(?:two\s+)?weeks?|this\s+week|recently)\b'
	r'|\bwhat\s+(?:did\s+i|have\s+i)\s+ask(?:ed)?.{0,60}\b(?:today|this\s+morning|yesterday|\d+\s+days?\s+ago)\b'
	r'|\b(?:list|show\s+me|review|go\s+through)\b.{0,60}\b(?:my\s+messages?|what\s+i\s+ask(?:ed)?)\b'
	r'|\b(?:my\s+)?(?:tasks?|requests?|things?)\s+(?:i\s+)?(?:asked|gave|told|sent).{0,40}\b(?:today|yesterday|\d+\s+days?\s+ago)\b'
	r'|(?:and\s+)?i\s+asked\s+(?:today\s+)?(?:about\s+)?(?:an?\s+)?other\s+thing\b'
	r'|\bdid\s+you\s+(?:do|create|add|make|get)\s+(?:it|that|them)\b'
	r'|\b(?:so\s+)?(?:are|were|was)\s+(?:they|it|those)\s+(?:created|added|saved|built|done|set\s+up|executed)\b'
	r'|\bdid\s+(?:those|they|it|that)\s+(?:get\s+)?(?:created|added|saved|go\s+through|work|execute)\b'
	r'|\bwas\s+(?:it|that|the\s+(?:task|board|card|todo))\s+(?:created|added|saved|done|executed)\b'
	r'|\bcheck\b.{0,60}\b(?:uncreated|missing|unfinished|pending|unexecuted)\b.{0,60}\b(?:tasks?|todos?|items?)\b'
	r'|\b(?:uncreated|missing)\s+(?:tasks?|todos?|items?)\b'
	r'|\bwhich\s+(?:tasks?|todos?|items?)\s+(?:were\s+not|weren.t|have\s+not\s+been|haven.t\s+been|did\s+not|didn.t)\s+(?:created|saved|added|executed|done)\b'
	r')',
	re.IGNORECASE,
)

# Server-side pre-filter: verbs that signal an actual task or request
_TASK_SIGNAL_RE = re.compile(
	r'\b(?:create|add|make|set\s+up|build|save|find|look\s+up|remind\s+me|send|'
	r'schedule|book|plan|update|edit|delete|remove|move|check|get|fetch|pull|'
	r'generate|write|draft|note|log|track|record|store|show\s+me|give\s+me|'
	r'finish|complete|finalize|prep|prepare|coordinate|sync|refresh|apply|'
	r'submit|fix|resolve|review|research|analyse|analyze|explore|test|deploy|'
	r'new\s+(?:board|task|todo|card|list|project)|open\s+a\b)\b',
	re.IGNORECASE,
)

# Messages to always skip in task recalls regardless of verb content
_SKIP_RECALL_RE = re.compile(
	r'^(?:/|and\s+now|ok|okay|sure|fine|great|thanks|yes|no\b|did\s+you|'
	r'i\s+(?:did|pressed|pushed|tried|went|feel|felt|am|was)\b)',
	re.IGNORECASE,
)

# Relative-date extractor used by the recall intercept
_DAYS_AGO_RE = re.compile(r'(\d+)\s+days?\s+ago', re.IGNORECASE)
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
	lower = text.lower()
	# Multi-day range patterns
	if re.search(r'two\s+weeks?', lower):
		return 14, True
	m_nw = re.search(r'(\d+)\s+weeks?', lower)
	if m_nw:
		return int(m_nw.group(1)) * 7, True
	m_nd = re.search(r'(?:last|past)\s+(\d+)\s+days?', lower)
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

# Phantom-confirmation guard — Z claimed success in prose without emitting a tag
_PHANTOM_RE = re.compile(
	r'\b(task added|board (added|created)|event (added|created)|card (added|created)'
	r'|added to (your )?(todo|list|board|today)'
	r'|done[\s\u2014\u2013-]+(task|board|card|event|create|add)'
	r'|done\s*[\u2014\u2013\-]+\s*(create|add|new))\b',
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
	import asyncio
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

		# ── 0. Recall-history intercept ──────────────────────────────────────
		# When the user asks to recall messages from today, yesterday, N days ago, etc.,
		# fetch the actual conversation from DB and inject it — never consult Planka.
		if _RECALL_HISTORY_RE.search(user_text[:_MAX_RE_INPUT]):
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
			for m in user_msgs:
				content = m["content"].strip()
				if _SKIP_RECALL_RE.match(content):
					continue
				if len(content.split()) < 3:
					continue
				if not _TASK_SIGNAL_RE.search(content):
					continue
				key = content.lower()
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

		# ── 1. Keyword-based crew routing ────────────────────────────────────
		routed_crews = await resolve_active_crews(history, user_text, lang=lang)
		if not routed_crews:
			# ── 1.1 Speculative Fast-Intent (Qwen-0.6B) ──────────────────────
			# If keywords failed, check for crew intent via the local fast model
			# before falling back to the heavy general LLM.
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
			async for token in native_crew_engine.run_crew_stream(crew_id, user_text, history=history):
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
			return

		# ── 2. Z responds ────────────────────────────────────────────────────
		chunks = []
		async for token in chat_stream_with_context(
			user_text,
			history=history,
			include_projects=True,
			include_people=True,
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
			async for token in native_crew_engine.run_crew_stream(crew_id, user_text, history=history):
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
