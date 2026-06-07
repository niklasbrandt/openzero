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
import hashlib
import logging
import time
from datetime import datetime, timedelta
from typing import Any, Awaitable, Callable
from uuid import uuid4

logger = logging.getLogger(__name__)


def _schedule_reactive_audit() -> None:
	"""Schedule a one-shot self-audit after AUDIT_REACTIVE_DELAY_SECONDS.

	Debounced: if a reactive job is already pending, skip scheduling a new one
	and let the existing job handle the batch of recent [AUDIT:...] claims.
	"""
	try:
		from app.common.scheduler_instance import scheduler
		from app.config import settings
		from app.tasks.self_audit import run_self_audit
		from apscheduler.triggers.date import DateTrigger

		pending = [j for j in scheduler.get_jobs() if j.id.startswith("self_audit_reactive_")]
		if pending:
			logger.debug("Reactive audit debounced — job %s already pending", pending[0].id)
			return

		job_id = f"self_audit_reactive_{uuid4().hex[:8]}"
		run_date = datetime.utcnow() + timedelta(seconds=settings.AUDIT_REACTIVE_DELAY_SECONDS)
		scheduler.add_job(
			run_self_audit,
			DateTrigger(run_date=run_date),
			id=job_id,
			replace_existing=False,
		)
		logger.info("Reactive audit scheduled: job=%s delay=%ds", job_id, settings.AUDIT_REACTIVE_DELAY_SECONDS)
	except Exception as exc:
		logger.warning("Failed to schedule reactive audit: %s", exc)

_PushFn = Callable[[str], Awaitable[None]]


class MessageBus:
	"""Persistence and routing hub for all Z messenger channels."""

	def __init__(self) -> None:
		# channel_id -> push function for proactive outbound messages
		self._channels: dict[str, _PushFn] = {}
		# Dedup cache: hash(normalised_text) -> timestamp
		self._dedup_cache: dict[str, float] = {}
		self._dedup_window_s: float = 15.0

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
			Returns an empty list if the message is a cross-channel duplicate.
		"""
		from app.models.db import save_global_message, get_rolling_history

		# ── Dedup: skip duplicate messages arriving within the sliding window ──
		_norm = user_text.strip().lower()
		_hash = hashlib.sha256(_norm.encode("utf-8", errors="replace")).hexdigest()
		_now = time.monotonic()

		# Prune expired entries
		expired = [k for k, ts in self._dedup_cache.items() if _now - ts > self._dedup_window_s]
		for k in expired:
			del self._dedup_cache[k]

		if _hash in self._dedup_cache:
			logger.info("MessageBus: dedup hit — skipping duplicate from %s (within %.0fs window)", channel, self._dedup_window_s)
			return []

		self._dedup_cache[_hash] = _now

		if save:
			await save_global_message(channel, "user", user_text)
		return await get_rolling_history(days=4, limit=60)

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
		crew_board_hint: str | None = None,
	) -> tuple[str, list, list]:
		"""Parse action tags, persist Z's reply, schedule background memory.

		Args:
			channel:          Destination channel id, e.g. "telegram", "dashboard".
			raw_reply:        Raw LLM output (may contain [ACTION:…] tags).
			model:            Model label for provenance tracking (last_model_used.get()).
			user_text:        Original user message used to trigger memory extraction.
			                  Pass empty string to skip memory extraction.
			db:               SQLAlchemy async session. A new session is opened if None.
			save:             Set False to skip persistence (regression tests, dry-runs).
			require_hitl:     If True, destructive actions are held for human confirmation.
			crew_board_hint:  When set, CREATE_TASK tags are forced onto this board name.
			                  Pass the crew's Planka board name (e.g. "Life" for crew "life").

		Returns:
			(clean_reply, executed_commands, pending_actions)
			clean_reply      — reply with action tags stripped, ready for delivery.
			executed_commands — list of command strings that were executed.
			pending_actions   — list of dicts for actions awaiting confirmation.
		"""
		from app.models.db import AsyncSessionLocal, save_global_message
		from app.services.agent_actions import parse_and_execute_actions
		from app.common.phantom import is_phantom, PHANTOM_HISTORY_PLACEHOLDER

		# Pre-process: inject crew board into any tags that lack a BOARD: field.
		if crew_board_hint:
			from app.services.crews_native import _inject_crew_board
			raw_reply = _inject_crew_board(raw_reply, crew_board_hint)

		if db is not None:
			clean_reply, executed_cmds, pending_actions = await parse_and_execute_actions(
				raw_reply, db=db, require_hitl=require_hitl, user_text=user_text,
				crew_board_hint=crew_board_hint,
			)
		else:
			async with AsyncSessionLocal() as _db:
				clean_reply, executed_cmds, pending_actions = await parse_and_execute_actions(
					raw_reply, db=_db, require_hitl=require_hitl, user_text=user_text,
					crew_board_hint=crew_board_hint,
				)

		if save:
			_save_reply = clean_reply
			if is_phantom(clean_reply, executed_cmds):
				_save_reply = PHANTOM_HISTORY_PLACEHOLDER
				logger.warning("MessageBus: phantom reply redacted from history (channel=%s)", channel)
				# L9 — telemetry counter: track phantom rate per channel for SLO monitoring
				try:
					from app.services.metrics import increment_counter
					increment_counter("phantom_confirmations_total", channel=channel)
				except Exception:
					pass
			await save_global_message(channel, "z", _save_reply, model=model)
			# L2 — SYSTEM RECEIPT: when actions actually executed, save a receipt
			# as a system message so the LLM can answer "where did you save X?"
			# from facts rather than imagination on the next turn.
			if executed_cmds:
				_real_cmds = [c for c in executed_cmds if isinstance(c, str) and not c.startswith("⚠") and not c.startswith("__")]
				if _real_cmds:
					_ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
					_receipt_lines = [f"[SYSTEM RECEIPT {_ts}]"] + _real_cmds
					_receipt_text = "\n".join(_receipt_lines)
					await save_global_message(channel, "system", _receipt_text, model="receipt")
					logger.debug("MessageBus: saved SYSTEM RECEIPT with %d actions", len(_real_cmds))
			# Reactive audit: if Z claimed a structural action, verify it shortly after
			if "[AUDIT:" in raw_reply:
				_schedule_reactive_audit()

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
