import os
import datetime
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

		events_result = service.events().list(
			calendarId=calendar_id,
			timeMin=time_min,
			timeMax=time_max,
			maxResults=max_results,
			singleEvents=True,
			orderBy="startTime",
		).execute()
		
		events = events_result.get("items", [])
		return [{
			"summary": e.get("summary", "No Title"),
			"start": e["start"].get("dateTime", e["start"].get("date")),
			"end": e["end"].get("dateTime", e["end"].get("date")),
		} for e in events]
	except Exception as e:
		print(f"Error fetching calendar events for {calendar_id}: {e}")
		return []
