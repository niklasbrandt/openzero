"""Proactive coach nudges for Recipe and Fitness crews (section 9i Phase 3).

Fires when ALL conditions are true for a crew:
  1. Crew has earned proactive status (proactive_earned:{id} = "1" in Redis)
  2. Last nudge was >48 h ago
  3. No user messages containing domain keywords in the last 3 days
  4. No domain-related memories stored in the last 3 days

Dispatches to whichever channel the operator last used (Telegram as fallback).
One nudge per crew per day maximum (Redis dedup key TTL 25 h).
"""
import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

_CREW_DOMAINS: dict = {
	"recipe": [
		"recipe", "meal", "food", "cook", "cooking", "ingredient",
		"nutrition", "macro", "calories", "eat", "eating", "dinner",
		"lunch", "breakfast", "snack",
	],
	"fitness": [
		"workout", "training", "exercise", "gym", "run", "running",
		"cardio", "lift", "lifting", "programme", "program", "fitness",
		"strength", "endurance", "squat", "deadlift", "bench",
	],
	"life": [
		"feeling", "mood", "energy", "stress", "sleep", "overwhelm",
		"burnout", "tired", "exhausted", "traurig", "müde", "stress",
		"erschöpft",
	],
}

_NUDGE_PROMPTS: dict = {
	"recipe": (
		"Generate a single short sentence (under 15 words) nudging the user to plan their meals. "
		"Be direct and practical. No greeting, no closing. Output only the sentence."
	),
	"fitness": (
		"Generate a single short sentence (under 15 words) nudging the user to schedule their workout. "
		"Be direct and motivating. No greeting, no closing. Output only the sentence."
	),
	"life": (
		"Generate a single short sentence (under 15 words) checking in on the user's wellbeing. "
		"Be genuine, empathetic, and not clinical. No greeting, no closing. Output only the sentence."
	),
}

_FALLBACK_NUDGE: dict = {
	"recipe": "Time to plan your meals for the week.",
	"fitness": "Ready to schedule your next workout?",
	"life": "Haven't heard much lately -- how are you holding up?",
}


def _nudge_config() -> dict:
	try:
		import yaml
		import os
		cfg_path = os.path.join(os.path.dirname(__file__), "../../../../config.yaml")
		with open(cfg_path) as fh:
			data = yaml.safe_load(fh)
		return data.get("proactive_nudges", {})
	except Exception:
		return {}


async def _redis():
	import redis.asyncio as aioredis
	from app.config import settings
	url = f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}"
	return aioredis.from_url(url, password=settings.REDIS_PASSWORD or None, decode_responses=True)


async def _last_used_channel() -> str:
	"""Return the channel the operator last sent a message on (Telegram as fallback)."""
	try:
		from sqlalchemy import select
		from app.models.db import AsyncSessionLocal, GlobalMessage
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
	except Exception as _e:
		logger.warning("proactive_nudges: _last_used_channel failed: %s", _e)
	return "telegram"


async def _user_silent_domain(crew_id: str, days: int) -> bool:
	"""Return True if no user message containing domain keywords in the last N days."""
	try:
		from sqlalchemy import select
		from app.models.db import AsyncSessionLocal, GlobalMessage
		cutoff = datetime.now(timezone.utc) - timedelta(days=days)
		keywords = _CREW_DOMAINS.get(crew_id, [])
		async with AsyncSessionLocal() as session:
			result = await session.execute(
				select(GlobalMessage)
				.where(GlobalMessage.role == "user")
				.where(GlobalMessage.created_at >= cutoff)
				.order_by(GlobalMessage.created_at.desc())
				.limit(200)
			)
			messages = result.scalars().all()
		for msg in messages:
			text_lower = (msg.content or "").lower()
			for kw in keywords:
				if kw in text_lower:
					return False
		return True
	except Exception as _e:
		logger.warning("proactive_nudges: _user_silent_domain failed: %s", _e)
		return False


async def _memory_silent_domain(crew_id: str, days: int) -> bool:
	"""Return True if no domain-related memories stored in the last N days."""
	try:
		from app.services.memory import get_recent_memories
		keywords = _CREW_DOMAINS.get(crew_id, [])
		recent = await get_recent_memories(hours=days * 24)
		for mem in recent:
			text_lower = (mem.get("text") or "").lower()
			for kw in keywords:
				if kw in text_lower:
					return False
		return True
	except Exception as _e:
		logger.warning("proactive_nudges: _memory_silent_domain failed: %s", _e)
		return False


async def _dispatch_nudge(channel: str, text: str) -> None:
	"""Send the nudge text via the appropriate channel."""
	try:
		if channel == "telegram":
			from app.services.notifier import send_notification
			await send_notification(text)
		elif channel == "whatsapp":
			from app.api.whatsapp import send_whatsapp_message
			await send_whatsapp_message(text)
		elif channel == "dashboard":
			from app.models.db import save_global_message
			await save_global_message("dashboard", "z", text)
		else:
			from app.services.notifier import send_notification
			await send_notification(text)
	except Exception as _e:
		logger.warning("proactive_nudges: dispatch to '%s' failed: %s", channel, _e)


async def _generate_nudge_text(crew_id: str) -> str:
	"""Call local LLM to generate a short nudge sentence."""
	try:
		from app.services.llm import chat
		text = await chat(
			user_message=_NUDGE_PROMPTS[crew_id],
			tier="cloud",
			max_tokens=80,
		)
		text = (text or "").strip()
		if not text:
			raise ValueError("empty LLM response")
		return text
	except Exception as _e:
		logger.warning("proactive_nudges: LLM call failed for %s: %s", crew_id, _e)
		return _FALLBACK_NUDGE.get(crew_id, "")


async def check_nudges() -> None:
	"""Check all eligible crews and fire proactive nudges if conditions are met."""
	cfg = _nudge_config()
	if not cfg.get("enabled", True):
		return

	silence_days = int(cfg.get("silence_days", 3))
	nudge_interval_h = int(cfg.get("nudge_interval_hours", 48))

	try:
		from app.services.coach_earning import check_earning
		async with await _redis() as r:
			for crew_id in ("recipe", "fitness"):
				earned = await check_earning(crew_id)
				if not earned:
					continue

				today_key = f"nudge_sent:{crew_id}:{datetime.now(timezone.utc).strftime('%Y-%m-%d')}"
				if await r.get(today_key):
					continue

				last_key = f"last_nudge:{crew_id}"
				last_str = await r.get(last_key)
				if last_str:
					try:
						last_dt = datetime.fromisoformat(last_str)
						if (datetime.now(timezone.utc) - last_dt).total_seconds() < nudge_interval_h * 3600:
							continue
					except Exception:
						pass

				if not await _user_silent_domain(crew_id, silence_days):
					continue
				if not await _memory_silent_domain(crew_id, silence_days):
					continue

				nudge_text = await _generate_nudge_text(crew_id)
				if not nudge_text:
					continue

				channel = await _last_used_channel()
				await _dispatch_nudge(channel, nudge_text)

				now_str = datetime.now(timezone.utc).isoformat()
				await r.set(today_key, "1", ex=25 * 3600)
				await r.set(last_key, now_str)
				logger.info("proactive_nudges: nudge sent for %s via %s", crew_id, channel)

	except Exception as _e:
		logger.warning("proactive_nudges: check_nudges error: %s", _e)

# ---------------------------------------------------------------------------
# Stale high-priority card nudging (Feature 4)
# ---------------------------------------------------------------------------

# Card name urgency markers — any card with these in its name is treated as high-priority.
_URGENCY_MARKERS = (
	"dringend", "urgent", "asap", "wichtig", "priority", "!!", "kritisch", "critical",
)
# Active list names — cards in these lists are presumed in-flight and time-sensitive.
_ACTIVE_LIST_NAMES = (
	"doing", "in progress", "in bearbeitung", "active", "aktiv", "running", "laufend",
)


async def check_stale_cards() -> None:
	"""Nudge operator when a high-priority or in-progress Planka card has had no
	updates for more than STALE_CARD_HOURS hours (default 48).

	Deduplicates via Redis — at most one nudge per card per day.
	"""
	cfg = _nudge_config()
	if not cfg.get("enabled", True):
		return

	stale_hours = int(cfg.get("stale_card_hours", 48))

	try:
		from app.services.planka import get_stale_cards_raw
		all_stale = await get_stale_cards_raw(min_hours=stale_hours)
	except Exception as _e:
		logger.debug("proactive_nudges: get_stale_cards_raw failed: %s", _e)
		return

	if not all_stale:
		return

	# Further filter to only high-priority / actively-in-progress cards
	priority_cards = []
	for card in all_stale:
		name = (card.get("name") or "").lower()
		list_name = (card.get("listName") or "").lower()
		is_urgent = any(marker in name for marker in _URGENCY_MARKERS)
		is_active = any(ln in list_name for ln in _ACTIVE_LIST_NAMES)
		if is_urgent or is_active:
			priority_cards.append(card)

	if not priority_cards:
		return

	today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
	channel = await _last_used_channel()

	try:
		async with await _redis() as r:
			for card in priority_cards[:5]:  # cap at 5 nudges per run
				card_id = card.get("id", "")
				if not card_id:
					continue
				dedup_key = f"stale_card_nudge:{card_id}:{today_str}"
				if await r.get(dedup_key):
					continue

				card_name = card.get("name", "Unknown task")
				board_name = card.get("boardName", "")
				try:
					_raw_upd = (card.get("updatedAt") or "").replace("Z", "")
					_updated_dt = datetime.fromisoformat(_raw_upd).replace(tzinfo=timezone.utc) if _raw_upd else datetime.now(timezone.utc)
				except Exception:
					_updated_dt = datetime.now(timezone.utc)
				age_h = int((datetime.now(timezone.utc) - _updated_dt).total_seconds() / 3600)

				nudge_prompt = (
					f"Generate a single concise sentence (under 20 words) nudging the operator about "
					f"the stale task '{card_name}' (unchanged for {age_h}h). "
					f"Be direct and specific. No greeting, no sign-off. Output only the sentence."
				)
				try:
					from app.services.llm import chat
					nudge_text = await chat(user_message=nudge_prompt, tier="cloud", max_tokens=60)
					nudge_text = (nudge_text or "").strip()
				except Exception:
					nudge_text = f"'{card_name}' hasn't moved in {age_h}h. Still relevant?"

				if not nudge_text:
					continue

				board_ctx = f" ({board_name})" if board_name else ""
				full_nudge = f"⏳ Stale task{board_ctx}: {nudge_text}"
				await _dispatch_nudge(channel, full_nudge)
				await r.set(dedup_key, "1", ex=25 * 3600)
				logger.info("proactive_nudges: stale card nudge sent for '%s' via %s", card_name, channel)

	except Exception as _e:
		logger.warning("proactive_nudges: check_stale_cards error: %s", _e)
