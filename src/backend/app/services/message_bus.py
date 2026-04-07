"""
Universal Message Bus
─────────────────────
Single point of truth for ALL channel I/O in openZero.

Every inbound message — from any channel — flows through two calls:

	1.  history = await bus.ingest(channel, user_text)
	        Saves the user turn to global_messages BEFORE calling the LLM, so the
	        message is never lost even if the LLM times out or the process restarts.
	        Returns cross-channel history ready to pass to the LLM.

	2.  reply, actions, pending = await bus.commit_reply(channel, raw_llm_response, ...)
	        Parses [ACTION:...] tags, saves Z's turn, schedules background memory
	        extraction, and returns the cleaned reply to the caller for delivery.

Channel adapters own only the channel-specific parts:
	- LLM call style  (blocking / SSE streaming / Telegram progressive edit)
	- Reply delivery  (HTTP return / SSE yield / Bot.send_message)

┌──────────────────────────────────────────────────────────┐
│  Telegram     Dashboard    WhatsApp    Signal    …        │
│  (adapter)    (adapter)    (adapter)   (adapter)          │
│      │            │            │           │              │
│      └────────────┴────────────┴───────────┘              │
│                        │                                  │
│              MessageBus.ingest()                          │
│                        │                                  │
│              <channel runs its LLM call>                  │
│                        │                                  │
│              MessageBus.commit_reply()                    │
│                        │                                  │
│      ┌─────────────────┴──────────────────┐              │
│  global_messages    action tags    bg memory              │
└──────────────────────────────────────────────────────────┘

─── Adding a new messenger (WhatsApp, Signal, …) ───────────────────────────

1.  Create   src/backend/app/api/<messenger>.py

2.  At startup, register the channel's push function so proactive
    notifications (recovery, follow-ups) reach that channel:

        from app.services.message_bus import bus
        bus.register_channel("whatsapp", push_fn=send_whatsapp_message)

3.  In your inbound message handler call the two bus methods:

        from app.services.message_bus import bus
        from app.services.llm import chat_with_context, last_model_used

        # Save user turn immediately, get cross-channel context
        history = await bus.ingest("whatsapp", user_text)

        # Your channel owns the LLM call
        raw = await chat_with_context(user_text, history=history, ...)

        # Parse actions, save Z reply, fire background memory
        reply, actions, _ = await bus.commit_reply(
            channel="whatsapp",
            raw_reply=raw,
            model=last_model_used.get(),
            user_text=user_text,
        )

        # Your channel owns the delivery
        await send_whatsapp_message(reply)

4.  Done. The reply is automatically visible in the Dashboard (which polls
    global_messages) and in any other channel that reads history.

─── Push notifications ─────────────────────────────────────────────────────

    Registered push functions are called by bus.push(channel, text) when Z
    needs to proactively reach out — e.g. on-startup recovery, follow-up
    nudges, morning briefings delivered via messenger.
"""

import asyncio
import logging
from typing import Any, Awaitable, Callable, Optional

logger = logging.getLogger(__name__)

_PushFn = Callable[[str], Awaitable[None]]


class MessageBus:
	"""Persistence and routing hub for all Z messenger channels."""

	def __init__(self) -> None:
		# channel_id → push function for proactive outbound messages
		self._channels: dict[str, _PushFn] = {}

	# ─── Channel Registration ──────────────────────────────────────────────

	def register_channel(self, channel_id: str, push_fn: _PushFn) -> None:
		"""Register a channel's outbound push function.

		push_fn(text) is called by bus.push() when Z needs to proactively
		reach out on that channel (restart recovery, follow-up nudges, etc.).

		Call this once at startup from the channel's integration module.
		"""
		self._channels[channel_id] = push_fn
		logger.debug("MessageBus: channel %r registered", channel_id)

	# ─── Inbound ──────────────────────────────────────────────────────────

	async def ingest(
		self,
		channel: str,
		user_text: str,
		save: bool = True,
	) -> list[dict]:
		"""Persist the user turn BEFORE calling the LLM, return cross-channel history.

		Saving first guarantees the message survives LLM timeouts and container
		restarts — the restart-recovery scanner will pick it up next boot.

		Args:
			channel:   Source channel id, e.g. "telegram", "dashboard", "whatsapp".
			user_text: Raw user message exactly as received.
			save:      Set False to skip persistence (regression tests, dry-runs).

		Returns:
			Cross-channel history list ready to pass to chat_with_context(history=…).
		"""
		from app.models.db import get_global_history, save_global_message
		if save:
			await save_global_message(channel, "user", user_text)
		return await get_global_history(limit=10)

	# ─── Outbound ─────────────────────────────────────────────────────────

	async def commit_reply(
		self,
		channel: str,
		raw_reply: str,
		model: str = "",
		user_text: str = "",
		db: Any = None,
		save: bool = True,
		require_hitl: bool = False,
	) -> tuple[str, list, list]:
		"""Parse action tags, persist Z's reply, schedule background memory.

		Args:
			channel:      Destination channel id, e.g. "telegram", "dashboard".
			raw_reply:    Raw LLM output (may contain [ACTION:…] tags).
			model:        Model label for provenance tracking (last_model_used.get()).
			user_text:    Original user message used to trigger memory extraction.
			              Pass empty string to skip memory extraction.
			db:           SQLAlchemy async session. A new session is opened if None.
			save:         Set False to skip persistence (regression tests, dry-runs).
			require_hitl: If True, destructive actions are held for human confirmation.

		Returns:
			(clean_reply, executed_commands, pending_actions)
			clean_reply      — reply with action tags stripped, ready for delivery.
			executed_commands — list of command strings that were executed.
			pending_actions   — list of dicts for actions awaiting confirmation.
		"""
		from app.models.db import AsyncSessionLocal, save_global_message
		from app.services.agent_actions import parse_and_execute_actions

		if db is not None:
			clean_reply, executed_cmds, pending_actions = await parse_and_execute_actions(
				raw_reply, db=db, require_hitl=require_hitl
			)
		else:
			async with AsyncSessionLocal() as _db:
				clean_reply, executed_cmds, pending_actions = await parse_and_execute_actions(
					raw_reply, db=_db, require_hitl=require_hitl
				)

		if save:
			await save_global_message(channel, "z", clean_reply, model=model)

		if user_text:
			from app.services.learning import extract_and_store_facts
			asyncio.create_task(extract_and_store_facts(user_text))

		# Cross-channel sync: push the conversation to all other registered
		# channels so the user sees it regardless of which surface they're on.
		# Fire-and-forget to never block the originating channel's response.
		if save and user_text and self._channels:
			for ch, fn in self._channels.items():
				if ch != channel:
					sync_msg = (
						f"<i>[via {channel}]</i>\n"
						f"<b>You:</b> {user_text}\n\n"
						f"<b>Z:</b> {clean_reply}"
					)
					asyncio.create_task(
						self._safe_push(ch, fn, sync_msg),
						name=f"cross_channel_sync_{channel}_to_{ch}",
					)

		return clean_reply, executed_cmds, pending_actions

	async def _safe_push(self, channel: str, fn: "_PushFn", text: str) -> None:
		"""Push helper with per-channel error isolation."""
		try:
			await fn(text)
		except Exception as exc:
			logger.warning("MessageBus cross-channel push to %r failed: %s", channel, exc)

	# ─── Proactive push ───────────────────────────────────────────────────

	async def push(self, channel: str, text: str) -> None:
		"""Push a proactive message to a registered channel.

		No-op (with a warning) if the channel has not been registered.
		"""
		fn = self._channels.get(channel)
		if fn is None:
			logger.warning("MessageBus.push: no push function registered for channel %r", channel)
			return
		try:
			await fn(text)
		except Exception as exc:
			logger.warning("MessageBus.push(%r) failed: %s", channel, exc)

	async def push_all(self, text: str) -> None:
		"""Push a message to every registered channel simultaneously."""
		if not self._channels:
			logger.warning("MessageBus.push_all: no channels registered")
			return
		await asyncio.gather(
			*(self.push(ch, text) for ch in self._channels),
			return_exceptions=True,
		)


# Module-level singleton — import this everywhere:
#   from app.services.message_bus import bus
bus = MessageBus()
