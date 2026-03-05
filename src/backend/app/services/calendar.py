import os
import datetime
import asyncio
from typing import Optional, List
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = [
	"https://www.googleapis.com/auth/calendar.readonly",
]
TOKEN_PATH = "/app/tokens/token.json"
CREDS_PATH = "/app/tokens/credentials.json"

def get_calendar_service():
	"""Authenticate and return Google Calendar API service."""
	creds = None
	if os.path.exists(TOKEN_PATH):
		creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
	if not creds or not creds.valid:
		if creds and creds.expired and creds.refresh_token:
			creds.refresh(Request())
		else:
			if not os.path.exists(CREDS_PATH):
				return None
			flow = InstalledAppFlow.from_client_secrets_file(CREDS_PATH, SCOPES)
			creds = flow.run_local_server(port=3000) # Use a specific port for stability
		with open(TOKEN_PATH, "w") as token:
			token.write(creds.to_json())
	return build("calendar", "v3", credentials=creds)

async def fetch_calendar_events(calendar_id: str = "primary", max_results: int = 250, days_ahead: int = 30, start_date: datetime.datetime = None, end_date: datetime.datetime = None) -> list[dict]:
	"""Fetch events for a specific calendar within a time range."""
	service = get_calendar_service()
	if not service:
		return []

	try:
		if not start_date:
			start_date = datetime.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

		if not end_date:
			end_date = start_date + datetime.timedelta(days=days_ahead)

		time_min = start_date.isoformat() + "Z"
		time_max = end_date.isoformat() + "Z"

		# Wrap the synchronous .execute() call so it doesn't block the asyncio event loop
		loop = asyncio.get_event_loop()
		events_result = await loop.run_in_executor(
			None,
			lambda: service.events().list(
				calendarId=calendar_id,
				timeMin=time_min,
				timeMax=time_max,
				maxResults=max_results,
				singleEvents=True,
				orderBy="startTime",
			).execute()
		)

		events = events_result.get("items", [])
		return [{
			"summary": e.get("summary", "No Title"),
			"start": e["start"].get("dateTime", e["start"].get("date")),
			"end": e["end"].get("dateTime", e["end"].get("date")),
			"id": e.get("id"),
			"source": "google"
		} for e in events]
	except Exception as e:
		print(f"Error fetching calendar events for {calendar_id}: {e}")
		return []

async def fetch_caldav_events(start_date: datetime.datetime, end_date: datetime.datetime) -> list[dict]:
	"""Fetch events from the private CalDAV server via REPORT (RFC 4791)."""
	from app.config import settings
	import httpx
	if not settings.CALDAV_URL or not settings.CALDAV_USERNAME:
		return []

	body = (
		'<?xml version="1.0" encoding="utf-8" ?>'
		'<C:calendar-query xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">'
		'<D:prop><D:getetag/><C:calendar-data/></D:prop>'
		'<C:filter><C:comp-filter name="VCALENDAR">'
		'<C:comp-filter name="VEVENT">'
		'<C:time-range '
		f'start="{start_date.strftime("%Y%m%dT%H%M%SZ")}" '
		f'end="{end_date.strftime("%Y%m%dT%H%M%SZ")}"/>'
		'</C:comp-filter></C:comp-filter></C:filter>'
		'</C:calendar-query>'
	)

	try:
		auth = (settings.CALDAV_USERNAME, settings.CALDAV_PASSWORD)
		headers = {
			"Depth": "1",
			"Content-Type": "application/xml; charset=utf-8",
		}
		async with httpx.AsyncClient(auth=auth, timeout=15.0) as client:
			resp = await client.request(
				"REPORT", settings.CALDAV_URL, content=body, headers=headers
			)
			if resp.status_code >= 400:
				print(f"CalDAV REPORT returned {resp.status_code}")
				return []

		return _parse_caldav_multistatus(resp.text)
	except Exception as e:
		print(f"CalDAV Read Error: {e}")
		return []


def _parse_caldav_multistatus(xml_text: str) -> list[dict]:
	"""Extract VEVENT data from a CalDAV multistatus XML response."""
	import re
	from icalendar import Calendar

	events: list[dict] = []
	# Extract all calendar-data CDATA from the multistatus response
	pattern = re.compile(
		r"<(?:[A-Za-z0-9_-]+:)?calendar-data[^>]*>(.*?)</(?:[A-Za-z0-9_-]+:)?calendar-data>",
		re.DOTALL,
	)
	for match in pattern.finditer(xml_text):
		ics_text = match.group(1).strip()
		try:
			cal = Calendar.from_ical(ics_text)
			for component in cal.walk():
				if component.name != "VEVENT":
					continue
				dt_start = component.get("dtstart")
				dt_end = component.get("dtend")
				start_val = dt_start.dt if dt_start else None
				end_val = dt_end.dt if dt_end else start_val
				if start_val is None:
					continue
				# Normalise to ISO string
				if isinstance(start_val, datetime.datetime):
					start_iso = start_val.isoformat()
				else:
					start_iso = start_val.isoformat()
				if isinstance(end_val, datetime.datetime):
					end_iso = end_val.isoformat()
				else:
					end_iso = end_val.isoformat()

				events.append({
					"summary": str(component.get("summary", "No Title")),
					"start": start_iso,
					"end": end_iso,
					"id": str(component.get("uid", "")),
					"source": "caldav",
				})
		except Exception:
			continue
	return events

async def create_caldav_event(title: str, start: datetime.datetime, end: datetime.datetime) -> bool:
	"""Sync a local event to the private CalDAV server."""
	from app.config import settings
	import httpx
	import uuid
	if not settings.CALDAV_URL or not settings.CALDAV_USERNAME:
		return False

	uid = str(uuid.uuid4())
	# Construct a minimal iCalendar object
	ics_content = (
		"BEGIN:VCALENDAR\n"
		"VERSION:2.0\n"
		"PRODID:-//openZero//Nonspecific//EN\n"
		"BEGIN:VEVENT\n"
		f"UID:{uid}\n"
		f"DTSTAMP:{datetime.datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}\n"
		f"DTSTART:{start.strftime('%Y%m%dT%H%M%SZ')}\n"
		f"DTEND:{end.strftime('%Y%m%dT%H%M%SZ')}\n"
		f"SUMMARY:{title}\n"
		"END:VEVENT\n"
		"END:VCALENDAR"
	)

	try:
		auth = (settings.CALDAV_USERNAME, settings.CALDAV_PASSWORD)
		# CalDAV uses PUT to create an event at a specific path
		url = settings.CALDAV_URL.rstrip('/') + f"/{uid}.ics"
		async with httpx.AsyncClient(auth=auth, timeout=10.0) as client:
			resp = await client.put(url, content=ics_content, headers={"Content-Type": "text/calendar"})
			return resp.status_code in [201, 204]
	except Exception as e:
		print(f"CalDAV Create Error: {e}")
		return False

async def fetch_unified_events(days_ahead: int = 30, start_date: Optional[datetime.datetime] = None) -> list[dict]:
	"""
	The Single Source of Truth for Calendar queries.
	Merges Google Calendar, private CalDAV, and Local DB events.
	"""
	from app.models.db import LocalEvent, AsyncSessionLocal
	from sqlalchemy import select
	
	if not start_date:
		start_date = datetime.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
	end_date = start_date + datetime.timedelta(days=days_ahead)

	# 1. Start fetching in parallel
	tasks = [
		fetch_calendar_events(start_date=start_date, end_date=end_date),
		fetch_caldav_events(start_date, end_date)
	]
	results = await asyncio.gather(*tasks, return_exceptions=True)
	
	google_evs = results[0] if not isinstance(results[0], Exception) else []
	caldav_evs = results[1] if not isinstance(results[1], Exception) else []
	
	# 2. Local Database Events
	async with AsyncSessionLocal() as db:
		res = await db.execute(select(LocalEvent).where(
			LocalEvent.start_time >= start_date,
			LocalEvent.start_time <= end_date
		))
		local_evs = res.scalars().all()

	# 3. Deduplication and Merging
	final_events = []
	# Treat CalDAV/Google IDs as master
	seen_titles = set()
	
	for e in caldav_evs:
		final_events.append(e)
		seen_titles.add((e['summary'], e['start']))
		
	for e in google_evs:
		if (e['summary'], e['start']) not in seen_titles:
			final_events.append(e)
			seen_titles.add((e['summary'], e['start']))

	for e in local_evs:
		start_iso = e.start_time.isoformat() + "Z"
		# If this local event was already synced (same title and time), skip it
		if (e.summary, start_iso) not in seen_titles:
			final_events.append({
				"summary": e.summary,
				"start": start_iso,
				"end": e.end_time.isoformat() + "Z",
				"id": f"local_{e.id}",
				"source": "local"
			})

	final_events.sort(key=lambda x: x['start'])
	return final_events
