import datetime
import pytz
import logging
from app.services.calendar import fetch_calendar_events
from app.services.llm import chat
from app.models.db import AsyncSessionLocal, Preference, Person
from sqlalchemy import select
from app.config import settings

logger = logging.getLogger(__name__)

# Module-level cache for user settings from DB (refreshed at startup + on identity update)
_cached_timezone: str | None = None
_cached_location: str | None = None

async def refresh_user_settings():
	"""Load timezone and location from the identity record in the DB into cache.
	Falls back to .env values if no identity record exists."""
	global _cached_timezone, _cached_location
	try:
		async with AsyncSessionLocal() as session:
			res = await session.execute(select(Person).where(Person.circle_type == "identity"))
			identity = res.scalar_one_or_none()
			if identity:
				if identity.timezone and identity.timezone.strip():
					_cached_timezone = identity.timezone.strip()
				if identity.town and identity.town.strip():
					cc = (identity.country or "").strip()
					_cached_location = f"{identity.town.strip()}, {cc}" if cc else identity.town.strip()
			logger.info(f"User settings refreshed: tz={_cached_timezone or settings.USER_TIMEZONE}, loc={_cached_location or settings.USER_LOCATION}")
	except Exception as e:
		logger.error(f"Failed to refresh user settings from DB: {e}")

def get_user_timezone() -> str:
	"""Returns the user's timezone from DB identity record, defaults to Europe/Berlin."""
	return _cached_timezone or "Europe/Berlin"

def get_user_location() -> str:
	"""Returns the user's location (City, CC) from DB identity, or empty."""
	return _cached_location or ""

async def update_detected_timezone():
	"""
	Parses upcoming calendar events to deduce the user's current/future timezone.
	Updates the 'detected_timezone' preference in the database.
	"""
	if get_user_timezone().lower() != "auto":
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
	user_tz = get_user_timezone()
	if user_tz.lower() != "auto":
		return user_tz

	async with AsyncSessionLocal() as session:
		res = await session.execute(select(Preference).where(Preference.key == "detected_timezone"))
		pref = res.scalar_one_or_none()
		return pref.value if pref else "UTC"

def get_now() -> datetime.datetime:
	"""Single source of truth for current time in user's timezone."""
	tz = pytz.timezone(get_user_timezone())
	return datetime.datetime.now(tz)

def format_time(dt: datetime.datetime = None) -> str:
	"""
	Format datetime as 'HH:MM - We. 2nd' (weekday abbrev + ordinal day).
	If no dt provided, uses current time.
	"""
	if dt is None:
		dt = get_now()
	
	# Full weekday name
	day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
	weekday = day_names[dt.weekday()]
	
	# Ordinal suffix
	day = dt.day
	if 11 <= day <= 13:
		suffix = 'th'
	else:
		suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(day % 10, 'th')
	
	return f"{dt.strftime('%H:%M')} - {weekday}. {day}{suffix}"

def format_date_full(dt: datetime.datetime = None) -> str:
	"""Full date string: 'Monday, 2026-03-02 16:40:00 CET'"""
	if dt is None:
		dt = get_now()
	return dt.strftime('%A, %Y-%m-%d %H:%M:%S %Z')
