"""Proactive Executive Engine for openZero.

Acts as an autonomous, execution-focused partner. Instead of passively waiting
for the user to initiate contact or ping 'z?', this engine regularly evaluates
the substrate state (open loops, recently discussed projects/tasks, stalled cards)
and proactively initiates contact to drive momentum and get things done.

Hard constraints:
- Respects Quiet Hours (DB preference / user timezone).
- Respects active conversation (silent if user spoke < 25 mins ago).
- Anti-nag rate limiting: minimum 75 min between unprompted messages, max 4/day.
- Records all sent messages in global_messages for cross-channel context parity.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta
import logging
import time
from typing import Optional

from sqlalchemy import select
from app.config import settings
from app.models.db import AsyncSessionLocal, GlobalMessage, Preference, save_global_message

logger = logging.getLogger(__name__)

# Fallback in-memory rate-limit state in case Redis is temporarily unreachable
_last_contact_ts: float = 0.0
_daily_counter: dict[str, int] = {}
_proactive_lock = asyncio.Lock()


async def _get_redis():
	try:
		import redis.asyncio as aioredis
		url = f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}"
		return aioredis.from_url(url, password=settings.REDIS_PASSWORD or None, decode_responses=True)
	except Exception as _e:
		logger.debug("proactive_engine: redis connection unavailable: %s", _e)
		return None


async def is_quiet_hours() -> bool:
	"""Check if current local time falls into configured or default quiet hours."""
	try:
		import pytz
		from app.services.timezone import get_current_timezone
		user_tz_str = await get_current_timezone()
		tz = pytz.timezone(user_tz_str)
		now_local = datetime.now(tz)
		current_hour = now_local.hour
		current_minute = now_local.minute

		qh_enabled = False
		qh_start = 22
		qh_end = 7

		async with AsyncSessionLocal() as session:
			res = await session.execute(select(Preference).where(Preference.key == "quiet_hours_enabled"))
			pref = res.scalar_one_or_none()
			if pref and pref.value == "true":
				qh_enabled = True

			res_s = await session.execute(select(Preference).where(Preference.key == "quiet_hours_start"))
			pref_s = res_s.scalar_one_or_none()
			if pref_s and pref_s.value and ":" in pref_s.value:
				qh_start = int(pref_s.value.split(":")[0])

			res_e = await session.execute(select(Preference).where(Preference.key == "quiet_hours_end"))
			pref_e = res_e.scalar_one_or_none()
			if pref_e and pref_e.value and ":" in pref_e.value:
				qh_end = int(pref_e.value.split(":")[0])

		if not qh_enabled:
			# Default sensible night quiet hours: 23:00 to 07:30
			if current_hour >= 23 or current_hour < 7 or (current_hour == 7 and current_minute < 30):
				return True
			return False

		if qh_start > qh_end:
			# Spans midnight (e.g. 22 to 7)
			return current_hour >= qh_start or current_hour < qh_end
		else:
			return qh_start <= current_hour < qh_end
	except Exception as e:
		logger.warning("proactive_engine: quiet hours check failed: %s", e)
		return False


async def get_seconds_since_last_user_message() -> float:
	"""Return seconds elapsed since the user last sent a message across all channels."""
	try:
		async with AsyncSessionLocal() as session:
			result = await session.execute(
				select(GlobalMessage.created_at)
				.where(GlobalMessage.role == "user")
				.order_by(GlobalMessage.created_at.desc())
				.limit(1)
			)
			row = result.scalar_one_or_none()
			if row:
				if row.tzinfo is None:
					row = row.replace(tzinfo=timezone.utc)
				now = datetime.now(timezone.utc)
				return (now - row).total_seconds()
	except Exception as e:
		logger.warning("proactive_engine: error getting last user message age: %s", e)
	return 999999.0


async def get_last_used_channel() -> str:
	"""Return the channel the user last used (Telegram as fallback)."""
	try:
		async with AsyncSessionLocal() as session:
			result = await session.execute(
				select(GlobalMessage.channel)
				.where(GlobalMessage.role == "user")
				.order_by(GlobalMessage.created_at.desc())
				.limit(1)
			)
			row = result.scalar_one_or_none()
			if row and row in ("telegram", "dashboard", "whatsapp"):
				return row
	except Exception as e:
		logger.warning("proactive_engine: get_last_used_channel failed: %s", e)
	return "telegram"


async def check_rate_limits() -> tuple[bool, str]:
	"""Verify whether a proactive contact is permitted by rate limits."""
	global _last_contact_ts
	now_ts = time.time()
	today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

	r = await _get_redis()
	if r:
		try:
			last_contact = await r.get("openzero:proactive:last_contact_ts")
			if last_contact:
				elapsed = now_ts - float(last_contact)
				if elapsed < 75 * 60:  # 75 minutes cooldown
					return False, f"cooldown_active ({int((75 * 60 - elapsed) / 60)}m left)"

			count = await r.get(f"openzero:proactive:daily_count:{today_str}")
			if count and int(count) >= 4:
				return False, "daily_cap_reached"
			return True, "ok"
		except Exception as _re:
			logger.debug("proactive_engine: redis check error: %s", _re)

	# Memory fallback
	elapsed = now_ts - _last_contact_ts
	if _last_contact_ts > 0 and elapsed < 75 * 60:
		return False, f"cooldown_active ({int((75 * 60 - elapsed) / 60)}m left)"
	if _daily_counter.get(today_str, 0) >= 4:
		return False, "daily_cap_reached"

	return True, "ok"


async def record_contact_event() -> None:
	"""Persist contact event timestamp and increment daily counter."""
	global _last_contact_ts
	now_ts = time.time()
	_last_contact_ts = now_ts
	today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
	_daily_counter[today_str] = _daily_counter.get(today_str, 0) + 1

	r = await _get_redis()
	if r:
		try:
			await r.set("openzero:proactive:last_contact_ts", str(now_ts), ex=86400 * 2)
			pipe = r.pipeline()
			key = f"openzero:proactive:daily_count:{today_str}"
			pipe.incr(key)
			pipe.expire(key, 86400 * 2)
			await pipe.execute()
		except Exception as _re:
			logger.debug("proactive_engine: redis record error: %s", _re)


async def gather_substrate_snapshot() -> dict:
	"""Gather recent conversation, projects, and active cards across boards."""
	from app.models.db import get_global_history
	from app.services.planka import get_project_tree

	history = await get_global_history(limit=10)
	recent_chat_lines = []
	for h in history:
		role = h.get("role", "unknown").upper()
		content = h.get("content", "").strip()
		if len(content) > 300:
			content = content[:300] + "..."
		recent_chat_lines.append(f"[{role}]: {content}")
	recent_chat = "\n".join(recent_chat_lines)

	try:
		project_tree = await get_project_tree(as_html=False)
	except Exception as _pe:
		project_tree = f"Error fetching project tree: {_pe}"

	return {
		"recent_chat": recent_chat,
		"project_tree": project_tree,
	}


async def generate_proactive_nudge(snapshot: dict) -> Optional[str]:
	"""Generate an action-oriented executive partner message via LLM."""
	from app.services.llm import chat

	prompt = (
		"You are Z, the user's executive partner and personal operating system in openZero.\n"
		"The user has been idle for a while. Your job is to PROACTIVELY drive execution, eliminate roadblocks, "
		"and help them get shit done.\n\n"
		f"RECENT CONVERSATION (Tail):\n{snapshot.get('recent_chat', '')}\n\n"
		f"PROJECT MISSION CONTROL (Boards & Tasks):\n{snapshot.get('project_tree', '')}\n\n"
		"Task:\n"
		"1. Identify the single highest-leverage open thread, unfinished user request, newly created board, or pending task.\n"
		"   (e.g., if a board was recently discussed or created, propose the concrete next step or initial setup; "
		"   if an errand or action like curtains, insect screen, shopping, or project milestone is open, bring it up directly).\n"
		"2. If everything is completely quiet and there is absolutely nothing worth following up on, reply ONLY with 'NO_ACTION'.\n"
		"3. Otherwise, formulate a direct, crisp, natural message (1 to 3 sentences).\n"
		"   - Be a sharp peer/partner who pushes things forward.\n"
		"   - Suggest a concrete next physical action or ask a decisive question.\n"
		"   - Speak in the user's language (German if conversation was German, else English).\n"
		"   - NO polite filler, NO 'Hallo', NO 'Guten Morgen/Abend', NO 'Lass mich wissen', NO report formatting.\n"
		"   - Output ONLY the message text."
	)

	try:
		reply = await chat(prompt, tier="cloud", _feature="proactive_push")
		reply_clean = reply.strip()
		if "NO_ACTION" in reply_clean or not reply_clean:
			return None
		# Filter error stubs
		_ERRORS = ("having trouble reaching", "still waking up", "warming up my local", "could not process")
		if any(e in reply_clean.lower() for e in _ERRORS):
			return None
		return reply_clean
	except Exception as e:
		logger.warning("proactive_engine: LLM generation failed: %s", e)
		return None


async def dispatch_proactive_message(channel: str, text: str) -> bool:
	"""Send the proactive message through the active channel and record in history."""
	try:
		if channel == "telegram":
			from app.services.notifier import send_nudge_notification, get_nav_footer
			from app.services.translations import get_user_lang, get_translations
			lang = await get_user_lang()
			t = get_translations(lang)
			await send_nudge_notification(text, nav_footer=get_nav_footer(t))
		elif channel == "whatsapp":
			from app.api.whatsapp import send_whatsapp_message
			await send_whatsapp_message(text)
		elif channel == "dashboard":
			# Bus ingest / websocket push handled via global message
			pass
		else:
			from app.services.notifier import send_notification
			await send_notification(text)

		# Crucial: Always persist to global_messages with model attribution
		await save_global_message(channel, "z", text, model="proactive:executive")
		return True
	except Exception as e:
		logger.error("proactive_engine: dispatch failed on channel '%s': %s", channel, e)
		return False


async def run_proactive_cycle(force: bool = False) -> Optional[str]:
	"""Evaluate substrate state and send a proactive push if appropriate.

	Called periodically by APScheduler (e.g. every 15 minutes during active hours).
	"""
	if _proactive_lock.locked():
		logger.debug("proactive_engine: previous cycle still running, skipping")
		return None

	async with _proactive_lock:
		if not force:
			if await is_quiet_hours():
				logger.debug("proactive_engine: quiet hours active, skipping")
				return None

			user_idle_s = await get_seconds_since_last_user_message()
			if user_idle_s < 25 * 60:
				logger.debug("proactive_engine: user active recently (%.0f s ago), skipping", user_idle_s)
				return None

			allowed, reason = await check_rate_limits()
			if not allowed:
				logger.debug("proactive_engine: rate limit block: %s", reason)
				return None

		logger.info("proactive_engine: evaluating substrate opportunities...")
		snapshot = await gather_substrate_snapshot()
		nudge_text = await generate_proactive_nudge(snapshot)

		if not nudge_text:
			logger.info("proactive_engine: no proactive action warranted at this time")
			return None

		channel = await get_last_used_channel()
		success = await dispatch_proactive_message(channel, nudge_text)
		if success:
			await record_contact_event()
			logger.info("proactive_engine: successfully dispatched proactive message to '%s'", channel)
			return nudge_text

		return None
