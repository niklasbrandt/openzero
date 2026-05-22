"""Tracks whether Recipe/Fitness crews have earned proactive messaging rights.

Earning rule (refocus_plan.md section 9g):
  A crew earns proactive messaging only after 2 consecutive weeks of the
  operator reading the daily briefing without skipping.

Briefing read = at least one user message on the same ISO week as the morning briefing.
Briefing skip = a briefing was sent this ISO week but no engagement within the same week.

Redis keys
  briefing_streak          INT   consecutive-week read streak (global)
  briefing_last_week       STR   ISO week string of last streak increment
  briefing_sent_week:{W}   STR   ISO timestamp of briefing send for week W (TTL 8d)
  proactive_earned:{id}    "1"   set when streak >= earning_weeks threshold
"""
import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

_PROACTIVE_CREW_IDS = ("recipe", "fitness")
_EARNING_WEEKS_DEFAULT = 2


def _earning_weeks() -> int:
	try:
		import yaml
		import os
		cfg_path = os.path.join(os.path.dirname(__file__), "../../../../config.yaml")
		with open(cfg_path) as fh:
			data = yaml.safe_load(fh)
		return int(data.get("proactive_nudges", {}).get("earning_weeks", _EARNING_WEEKS_DEFAULT))
	except Exception:
		return _EARNING_WEEKS_DEFAULT


async def _redis():
	import redis.asyncio as aioredis
	from app.config import settings
	url = f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}"
	return aioredis.from_url(url, password=settings.REDIS_PASSWORD or None, decode_responses=True)


def _current_iso_week() -> str:
	return datetime.now(timezone.utc).strftime("%G-W%V")


def _iso_week_offset(iso_week: str, delta: int) -> str:
	year_str, week_str = iso_week.split("-W")
	thursday = datetime.strptime(f"{year_str}-{week_str}-4", "%G-%V-%u")
	adjusted = thursday + timedelta(weeks=delta)
	return adjusted.strftime("%G-W%V")


async def record_briefing_sent() -> None:
	"""Record that the morning briefing was dispatched in the current ISO week."""
	try:
		week = _current_iso_week()
		async with await _redis() as r:
			await r.set(f"briefing_sent_week:{week}", datetime.now(timezone.utc).isoformat(), ex=8 * 24 * 3600)
		logger.debug("coach_earning: briefing sent recorded week=%s", week)
	except Exception as _e:
		logger.warning("coach_earning: record_briefing_sent failed: %s", _e)


async def record_briefing_read() -> None:
	"""Record operator engagement in the current ISO week.

	Called from router.py on every non-trivial user message.
	Increments the streak only if a briefing was sent this week and the
	streak has not already been incremented this week.
	"""
	try:
		week = _current_iso_week()
		async with await _redis() as r:
			if not await r.exists(f"briefing_sent_week:{week}"):
				return
			last_week = await r.get("briefing_last_week")
			if last_week == week:
				return
			streak_raw = await r.get("briefing_streak")
			streak = int(streak_raw) if streak_raw else 0
			prev_week = _iso_week_offset(week, -1)
			if last_week is not None and last_week != prev_week:
				streak = 0
			streak += 1
			await r.set("briefing_streak", str(streak))
			await r.set("briefing_last_week", week)
			logger.info("coach_earning: streak=%d week=%s", streak, week)
			threshold = _earning_weeks()
			if streak >= threshold:
				for crew_id in _PROACTIVE_CREW_IDS:
					await r.set(f"proactive_earned:{crew_id}", "1")
					logger.info("coach_earning: %s earned proactive status (streak=%d)", crew_id, streak)
	except Exception as _e:
		logger.warning("coach_earning: record_briefing_read failed: %s", _e)


async def reset_earning(crew_id: str) -> None:
	"""Reset the earning streak (called when a briefing is skipped)."""
	try:
		async with await _redis() as r:
			await r.delete(f"proactive_earned:{crew_id}")
			await r.delete("briefing_streak")
			await r.delete("briefing_last_week")
		logger.info("coach_earning: streak reset for crew %s", crew_id)
	except Exception as _e:
		logger.warning("coach_earning: reset_earning failed: %s", _e)


async def check_earning(crew_id: str) -> bool:
	"""Return True if the crew has earned proactive messaging status."""
	try:
		async with await _redis() as r:
			return await r.get(f"proactive_earned:{crew_id}") == "1"
	except Exception as _e:
		logger.warning("coach_earning: check_earning failed: %s", _e)
		return False


async def get_proactive_crews() -> list:
	"""Return list of crew_ids that have earned proactive messaging status."""
	return [c for c in _PROACTIVE_CREW_IDS if await check_earning(c)]
