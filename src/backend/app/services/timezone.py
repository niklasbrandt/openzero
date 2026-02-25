import datetime
import pytz
import logging
from app.services.calendar import fetch_calendar_events
from app.services.llm import chat
from app.models.db import AsyncSessionLocal, Preference
from sqlalchemy import select
from app.config import settings

logger = logging.getLogger(__name__)

async def update_detected_timezone():
	"""
	Parses upcoming calendar events to deduce the user's current/future timezone.
	Updates the 'detected_timezone' preference in the database.
	"""
	if settings.USER_TIMEZONE.lower() != "auto":
		return
		
	try:
		# 1. Fetch upcoming events (next 14 days)
		events = await fetch_calendar_events(max_results=20, days_ahead=14)
		if not events:
			return

		event_data = "\n".join([f"- {e['summary']} ({e['start']})" for e in events])
		
		# 2. Use LLM to deduce location/timezone
		prompt = (
			"Based on these calendar events, deduce the user's likely current or upcoming location/city. "
			"Look for travel keywords like 'Flight to', 'Trip to', 'Stay in'. "
			"If found, return ONLY the IANA timezone string (e.g., 'Europe/Berlin'). "
			"If no travel is detected, return 'STAY'.\n\n"
			f"EVENTS:\n{event_data}"
		)
		
		tz_suggestion = await chat(prompt, system_override="You are a travel coordinator. Return ONLY a timezone string or 'STAY'.")
		tz_suggestion = tz_suggestion.strip()
		
		if tz_suggestion == "STAY" or "/" not in tz_suggestion:
			return

		# Validate timezone
		try:
			pytz.timezone(tz_suggestion)
		except pytz.UnknownTimeZoneError:
			logger.warning(f"LLM suggested unknown timezone: {tz_suggestion}")
			return

		# 3. Store in DB
		async with AsyncSessionLocal() as session:
			# Check current preference
			res = await session.execute(select(Preference).where(Preference.key == "detected_timezone"))
			pref = res.scalar_one_or_none()
			
			if not pref:
				pref = Preference(key="detected_timezone", value=tz_suggestion)
				session.add(pref)
			elif pref.value != tz_suggestion:
				logger.info(f"Timezone change detected: {pref.value} -> {tz_suggestion}")
				pref.value = tz_suggestion
			
			await session.commit()
			
	except Exception as e:
		logger.error(f"Error detecting timezone: {e}")

async def get_current_timezone() -> str:
	"""Returns the configured or detected timezone."""
	if settings.USER_TIMEZONE.lower() != "auto":
		return settings.USER_TIMEZONE
		
	async with AsyncSessionLocal() as session:
		res = await session.execute(select(Preference).where(Preference.key == "detected_timezone"))
		pref = res.scalar_one_or_none()
		return pref.value if pref else "UTC"
