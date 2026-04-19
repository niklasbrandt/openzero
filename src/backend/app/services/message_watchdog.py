"""Message & Action Integrity Watchdog.

Two independent checks run on a schedule:

1. check_unanswered_messages()
   Scans global history for user turns that have no real Z reply after them.
   Fires the router on any found, so Z picks up mid-conversation even if
   the process crashed, the model was loading, or the Telegram listener
   dropped a message.  De-duplicates via an in-memory set so the same user
   message is never recovered twice in the same process lifetime.

2. audit_action_integrity()
   Scans recent Z messages for known failure markers:
     - ⚠ prefix  — an action tag was emitted but the API call failed
     - phantom pattern — Z claimed success (prose) but zero commands executed
   If any unacknowledged failures are found (i.e., the user has not already
   been told about them AND there is no subsequent user message acknowledging
   the failure), Z surfaces a concise alert so the user can retry.
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# ── Failure-marker patterns ────────────────────────────────────────────────

_WARNING_RE = re.compile(r'^⚠', re.MULTILINE)

_PHANTOM_CLAIM_RE = re.compile(
	r'\b(task added|board (added|created)|event (added|created)|card (added|created)'
	r'|added to (your )?(todo|list|board|today)'
	r'|done[\s\u2014\u2013-]+(task|board|card|event))\b',
	re.IGNORECASE,
)

# Z messages that are themselves watchdog alerts — don't re-alert on them.
_WATCHDOG_MARKER = "watchdog:"

# In-memory set of (content_hash) that have already been recovered this
# process lifetime — prevents spamming the user on repeated polls.
_recovered_message_hashes: set[str] = set()
# action-failure message hashes already surfaced this process lifetime
_surfaced_failure_hashes: set[str] = set()


# ── Lock: only one watchdog run at a time ─────────────────────────────────

_watchdog_lock = asyncio.Lock()


def _msg_hash(content: str) -> str:
	return str(hash(content.strip()[:120]))


# ── 1. Unanswered messages ─────────────────────────────────────────────────

async def check_unanswered_messages() -> None:
	"""Find user messages with no real Z reply and route them through the router.

	Called on a schedule (every 5 minutes).  Idempotent — already-recovered
	messages are skipped via _recovered_message_hashes.
	"""
	if _watchdog_lock.locked():
		logger.debug("Watchdog: previous run still in progress, skipping.")
		return

	async with _watchdog_lock:
		try:
			await _do_check_unanswered()
		except Exception:
			logger.exception("Watchdog: check_unanswered_messages failed")


async def _do_check_unanswered() -> None:
	from app.models.db import get_global_history
	from app.api.telegram_bot import (
		_is_error_stub, _is_system_message, send_notification_html, get_nav_footer,
		strip_llm_time_header, _md_to_html,
	)
	from app.services.translations import get_user_lang, get_translations

	history = await get_global_history(limit=30)
	if not history:
		return

	now_utc = datetime.now(timezone.utc)
	unanswered: list[str] = []

	for msg in reversed(history):
		role = msg["role"]
		content = msg.get("content", "")

		if role in ("z", "assistant"):
			if _is_error_stub(content) or _is_system_message(content):
				continue
			# Real Z reply — everything before this point is answered
			break

		# role == "user"
		h = _msg_hash(content)
		if h in _recovered_message_hashes:
			continue
		try:
			msg_ts = datetime.fromisoformat(msg["at"]).replace(tzinfo=timezone.utc)
			age_s = (now_utc - msg_ts).total_seconds()
			if age_s < 90:
				# Too recent — live handle_freetext may still be processing
				continue
		except Exception as _e:
			logger.debug("Watchdog: could not parse message timestamp: %s", _e)

		unanswered.append(content)

	if not unanswered:
		return

	unanswered.reverse()  # chronological
	combined = "\n".join(unanswered)
	logger.info("Watchdog: %d unanswered message(s) found — routing now.", len(unanswered))

	# Mark them immediately so a parallel scheduler tick won't double-recover
	for content in unanswered:
		_recovered_message_hashes.add(_msg_hash(content))

	from app.services.router import route_message_stream

	merged_history = await get_global_history(limit=10)
	merged_history = list(merged_history) + [{
		"role": "assistant",
		"content": "(You were offline and just came back. These messages came in while you were down — pick up like a friend would, naturally, no announcements.)",
	}]

	token_stream, result_fut = await route_message_stream(
		user_text=combined,
		history=merged_history,
		channel="telegram",
		save_history=True,
	)
	async for _ in token_stream:
		pass
	result = await result_fut

	if not result.reply or _is_error_stub(result.reply):
		logger.warning("Watchdog: recovery router returned empty/error reply.")
		return

	lang = await get_user_lang()
	t = get_translations(lang)
	clean = strip_llm_time_header(result.reply)
	await send_notification_html(
		f"<blockquote>{_md_to_html(clean)}</blockquote>",
		nav_footer=get_nav_footer(t),
	)
	logger.info("Watchdog: recovery reply delivered.")


# ── 2. Action integrity audit ──────────────────────────────────────────────

async def audit_action_integrity() -> None:
	"""Scan recent Z messages for action failures and surface unacknowledged ones.

	Looks for:
	  - ⚠ lines (API call returned an error)
	  - Phantom confirmations (Z claimed success but no command executed)

	Skips messages that are already watchdog alerts or that are followed by a
	user acknowledgement (user replied after the failure — they already know).
	"""
	if _watchdog_lock.locked():
		return

	async with _watchdog_lock:
		try:
			await _do_audit_actions()
		except Exception:
			logger.exception("Watchdog: audit_action_integrity failed")


async def _do_audit_actions() -> None:
	from app.models.db import get_global_history
	from app.api.telegram_bot import send_notification_html, get_nav_footer, _md_to_html
	from app.services.translations import get_user_lang, get_translations

	history = await get_global_history(limit=20)
	if not history:
		return

	# Build a list of (z_msg, followed_by_user) pairs from recent history
	failures: list[str] = []

	for idx, msg in enumerate(history):
		role = msg["role"]
		if role not in ("z", "assistant"):
			continue
		content = msg.get("content", "")

		# Skip if this is already a watchdog alert
		if _WATCHDOG_MARKER in content.lower():
			continue

		h = _msg_hash(content)
		if h in _surfaced_failure_hashes:
			continue

		# Check if a real user message came AFTER this Z message
		subsequent = history[idx + 1:]
		user_followed_up = any(
			m["role"] == "user" for m in subsequent
		)
		if user_followed_up:
			# User continued — they're aware of the state
			continue

		# Detect failure markers
		has_warning = bool(_WARNING_RE.search(content))
		has_phantom = bool(_PHANTOM_CLAIM_RE.search(content))

		if has_warning or has_phantom:
			failures.append(content)
			_surfaced_failure_hashes.add(h)

	if not failures:
		return

	logger.info("Watchdog: %d unacknowledged action failure(s) found.", len(failures))

	lang = await get_user_lang()
	t = get_translations(lang)

	for failure in failures:
		# Extract the ⚠ lines, or synthesise a note about the phantom
		warning_lines = [l.strip() for l in failure.splitlines() if l.strip().startswith("⚠")]
		if warning_lines:
			alert_body = "\n".join(warning_lines)
			alert = (
				f"<i>watchdog: action failed and was never retried</i>\n\n"
				f"{_md_to_html(alert_body)}"
			)
		else:
			alert = (
				"<i>watchdog: Z described saving something but no action was executed. "
				"You may want to repeat the request.</i>"
			)

		await send_notification_html(
			f"<blockquote>{alert}</blockquote>",
			nav_footer=get_nav_footer(t),
		)

	logger.info("Watchdog: %d action failure alert(s) delivered.", len(failures))
