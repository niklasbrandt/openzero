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

# Recall-history detector: user wants a retrospective of their own messages for a given day.
_RECALL_HISTORY_RE = re.compile(
	r'(?:'
	r'\b(?:recall|look\s+up|review|show\s+me|list|go\s+through)\b'
	r'\s+(?:.{0,60}\s+)?(?:i\s+)?(?:asked|sent|gave|told|messaged)\s+you\b'
	r'|\brecall\b.{0,80}\b(?:today|this\s+morning|earlier\s+today|yesterday|\d+\s+days?\s+ago|last\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|week))\b'
	r'|\bwhat\s+(?:did\s+i|have\s+i)\s+ask(?:ed)?.{0,60}\b(?:today|this\s+morning|yesterday|\d+\s+days?\s+ago)\b'
	r'|\b(?:list|show\s+me|review|go\s+through)\b.{0,60}\b(?:my\s+messages?|what\s+i\s+ask(?:ed)?)\b'
	r'|\b(?:my\s+)?(?:tasks?|requests?|things?)\s+(?:i\s+)?(?:asked|gave|told|sent).{0,40}\b(?:today|yesterday|\d+\s+days?\s+ago)\b'
	r')',
	re.IGNORECASE,
)

# Relative-date extractor used by the recall intercept
_DAYS_AGO_RE = re.compile(r'(\d+)\s+days?\s+ago', re.IGNORECASE)
_WEEKDAY_MAP = {
	'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
	'friday': 4, 'saturday': 5, 'sunday': 6,
}

def _resolve_days_ago(text: str) -> int:
	"""Parse a days_ago offset from natural language. Returns 0 (today) as default."""
	import datetime as _dt
	lower = text.lower()
	if 'yesterday' in lower:
		return 1
	m = _DAYS_AGO_RE.search(lower)
	if m:
		return int(m.group(1))
	for day_name, weekday_num in _WEEKDAY_MAP.items():
		if f'last {day_name}' in lower:
			today_num = _dt.datetime.utcnow().weekday()
			delta = (today_num - weekday_num) % 7
			return delta if delta > 0 else 7
	return 0  # default: today

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
			from app.models.db import get_user_messages_for_day
			days_ago = _resolve_days_ago(user_text)
			day_msgs = await get_user_messages_for_day(days_ago)
			# Strip the current recall request itself (only relevant when days_ago == 0)
			day_msgs = [m for m in day_msgs if m["content"].strip() != user_text.strip()]
			if days_ago == 0:
				day_label = "today (since midnight UTC)"
			elif days_ago == 1:
				day_label = "yesterday"
			else:
				day_label = f"{days_ago} days ago"
			if day_msgs:
				block = "\n".join(
					f"[{m['at'][11:16]}] {m['content']}" for m in day_msgs
				)
				injected = (
					f"The user is asking you to recall what they asked you to do {day_label}.\n"
					f"Below is every message they sent that day. Your job:\n"
					f"1. Read through all messages and identify only those that were actual requests, tasks, or instructions directed at you.\n"
					f"   - Include: 'create a task', 'add to board', 'look up X', 'remind me', 'plan Y', explicit questions expecting action.\n"
					f"   - Exclude: emotional venting, follow-up confirmations like 'and now?', reports of what they did themselves, and system commands like '/crew life ...'.\n"
					f"2. For each identified request, write one concise line: [HH:MM] short description of what was asked.\n"
					f"3. If a request appears multiple times (user re-sent unchanged), list it once with the first timestamp.\n"
					f"4. Do NOT emit any [ACTION: ...] tags. Do NOT re-execute anything. This is read-only.\n"
					f"5. If no clear task requests are found in the messages, say so honestly.\n\n"
					f"MESSAGES for {day_label}:\n{block}\n\n---\n{user_text}"
				)
			else:
				injected = (
					f"No messages found in the database for {day_label}. "
					f"Inform the user honestly that there are no messages recorded for that day.\n\n{user_text}"
				)
			chunks: list[str] = []
			async for token in chat_stream_with_context(
				injected,
				history=[],
				include_projects=False,
				include_people=False,
			):
				chunks.append(token)
				yield token
			response = sanitise_output("".join(chunks))
			response = rehydrate_response(response, get_active_rep_map())
			clean, cmds, pending = await bus.commit_reply(
				channel=channel, raw_reply=response,
				model=last_model_used.get(), user_text=user_text, save=save_history,
			)
			# Phantom guard for recall path: any action-confirmation language here is
			# always wrong — this is a read-only summary, actions can never legitimately run.
			if _PHANTOM_RE.search(clean[:_MAX_RE_REPLY]):
				clean += (
					"\n\n\u26a0 Note: the list above shows requests from your history — "
					"nothing was re-executed now."
				)
				logger.warning("Router: phantom-style language in recall reply")
			result_future.set_result(RouterResult(
				reply=clean, model=last_model_used.get(),
				executed_cmds=cmds, pending_actions=pending,
			))
			return

		# ── 1. Keyword-based crew routing ────────────────────────────────────
		routed_crews = await resolve_active_crews(history, user_text, lang=lang)
		if routed_crews:
			crew_id = routed_crews[0]
			logger.info("Router: keyword-routing '%s...' → crew '%s'", _sanitize_for_log(user_text), crew_id)
			chunks = []
			async for token in native_crew_engine.run_crew_stream(crew_id, user_text):
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
			async for token in native_crew_engine.run_crew_stream(crew_id, user_text):
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
