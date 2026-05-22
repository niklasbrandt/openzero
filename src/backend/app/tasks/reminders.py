"""Recurring reminder task.

Runs every minute; fires any enabled reminder whose scheduled time matches
the current local time.  Uses a Redis dedup key (TTL 90 s) to prevent
double-firing within the same minute.
"""
import logging

import pytz

logger = logging.getLogger(__name__)

_DOW_MAP: dict[str, int] = {
	"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6,
}


async def check_reminders() -> None:
	"""Check all enabled reminders and fire those due in the current minute."""
	try:
		from datetime import datetime
		from sqlalchemy import select
		import redis.asyncio as aioredis

		from app.config import settings
		from app.models.db import AsyncSessionLocal, RecurringReminder
		from app.services.timezone import get_current_timezone

		tz_str = await get_current_timezone()
		try:
			tz = pytz.timezone(tz_str)
		except Exception:
			tz = pytz.utc

		now = datetime.now(tz)
		current_hour = now.hour
		current_minute = now.minute
		current_dow = now.weekday()  # 0=Monday

		async with AsyncSessionLocal() as session:
			result = await session.execute(
				select(RecurringReminder).where(RecurringReminder.enabled == True)  # noqa: E712
			)
			reminders = list(result.scalars().all())

		if not reminders:
			return

		redis_url = f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}"
		async with aioredis.from_url(redis_url, password=settings.REDIS_PASSWORD or None, decode_responses=True) as r:
			for reminder in reminders:
				if reminder.hour != current_hour or reminder.minute != current_minute:
					continue
				if reminder.cadence == "weekly":
					expected_dow = _DOW_MAP.get((reminder.day_of_week or "").lower(), -1)
					if current_dow != expected_dow:
						continue

				# Dedup key — TTL 90 s prevents double-firing within the same minute
				fire_key = f"reminder_fired:{reminder.id}:{now.strftime('%Y-%m-%d-%H-%M')}"
				already_fired = await r.get(fire_key)
				if already_fired:
					continue
				await r.set(fire_key, "1", ex=90)

				await _dispatch_reminder(reminder.channel, reminder.text)
				logger.info("check_reminders: fired reminder #%d (%s)", reminder.id, reminder.text[:60])

	except Exception as _e:
		logger.warning("check_reminders: error: %s", _e)


async def _dispatch_reminder(channel: str, text: str) -> None:
	"""Send the reminder text via the appropriate channel."""
	try:
		msg = f"Reminder: {text}"
		if channel == "telegram":
			from app.services.notifier import send_notification
			await send_notification(msg)
		elif channel == "whatsapp":
			from app.api.whatsapp import send_whatsapp_message
			await send_whatsapp_message(msg)
		elif channel == "dashboard":
			from app.models.db import save_global_message
			await save_global_message("dashboard", "z", msg)
		else:
			logger.warning("check_reminders: unknown channel '%s' — dropping reminder", channel)
	except Exception as _e:
		logger.warning("check_reminders: dispatch to '%s' failed: %s", channel, _e)
