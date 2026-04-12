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
from dataclasses import dataclass, field
from typing import AsyncIterator

logger = logging.getLogger(__name__)

# Regex for Z-initiated ROUTE tags (tolerates missing 'ACTION:' prefix / closing ']')
_ROUTE_RE = re.compile(
	r'\[(?:ACTION:\s*)?ROUTE\s*\|\s*CREW:\s*([a-z0-9_-]+)\s*\]?',
	re.IGNORECASE,
)

# Phantom-confirmation guard — Z claimed success in prose without emitting a tag
_PHANTOM_RE = re.compile(
	r'\b(task added|board (added|created)|event (added|created)|card (added|created)'
	r'|added to (your )?(todo|list|board|today)'
	r'|done[\s\u2014\u2013-]+(task|board|card|event))\b',
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

		# ── 1. Keyword-based crew routing ────────────────────────────────────
		routed_crews = await resolve_active_crews(history, user_text, lang=lang)
		if routed_crews:
			crew_id = routed_crews[0]
			logger.info("Router: keyword-routing '%s...' → crew '%s'", user_text[:40], crew_id)
			chunks: list[str] = []
			async for token in native_crew_engine.run_crew_stream(crew_id, user_text):
				chunks.append(token)
				yield token
			full = rehydrate_response("".join(chunks), get_active_rep_map())
			clean, cmds, pending = await bus.commit_reply(
				channel=channel, raw_reply=full,
				model=f"crew:{crew_id}", user_text=user_text, save=save_history,
			)
			cmds = [c for c in cmds if not c.startswith("__CREW_RUN__:")]
			# Attribution footer — lets _last_attributed_crew detect this crew
			# in subsequent follow-up messages to enable single-turn continuation.
			clean += f"\n\n_(Reasoning by crew {crew_id})_"
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
			logger.info("Router: Z self-routed '%s...' → crew '%s'", user_text[:40], crew_id)
			r_chunks: list[str] = []
			async for token in native_crew_engine.run_crew_stream(crew_id, user_text):
				r_chunks.append(token)
				yield token
			r_full = rehydrate_response("".join(r_chunks), get_active_rep_map())
			r_clean, r_cmds, r_pending = await bus.commit_reply(
				channel=channel, raw_reply=r_full,
				model=f"crew:{crew_id}", user_text=user_text, save=save_history,
			)
			r_cmds = [c for c in r_cmds if not c.startswith("__CREW_RUN__:")]
			# Attribution footer — enables follow-up continuation via _last_attributed_crew
			r_clean += f"\n\n_(Reasoning by crew {crew_id})_"
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

		if not cmds and _PHANTOM_RE.search(clean):
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
