import os
import asyncio
import logging
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = [
	"https://www.googleapis.com/auth/gmail.readonly",
	"https://www.googleapis.com/auth/gmail.compose",
	"https://www.googleapis.com/auth/calendar.readonly",
]
TOKEN_PATH = "/app/tokens/token.json"
CREDS_PATH = "/app/tokens/credentials.json"

logger = logging.getLogger(__name__)

def get_gmail_service():
	"""Authenticate and return email API service."""
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
			creds = flow.run_local_server(port=0)
		with open(TOKEN_PATH, "w") as token:
			token.write(creds.to_json())
	return build("gmail", "v1", credentials=creds)

async def fetch_unread_emails(max_results: int = 20) -> list[dict]:
	"""Fetch recent unread emails."""
	service = get_gmail_service()
	if not service:
		return []

	try:
		loop = asyncio.get_event_loop()

		# Wrap the synchronous list call so it doesn't block the asyncio event loop
		results = await loop.run_in_executor(
			None,
			lambda: service.users().messages().list(
				userId="me",
				q="is:unread",
				maxResults=max_results,
			).execute()
		)

		messages = results.get("messages", [])

		# Fetch each message detail in parallel (non-blocking)
		async def _fetch_detail(msg_id: str):
			return await loop.run_in_executor(
				None,
				lambda: service.users().messages().get(
					userId="me", id=msg_id, format="metadata",
					metadataHeaders=["From", "Subject"],
				).execute()
			)

		details = await asyncio.gather(*[_fetch_detail(m["id"]) for m in messages])

		emails = []
		for msg, detail in zip(messages, details):
			headers = {h["name"]: h["value"] for h in detail["payload"]["headers"]}
			emails.append({
				"id": msg["id"],
				"from": headers.get("From", ""),
				"subject": headers.get("Subject", ""),
				"snippet": detail.get("snippet", ""),
			})
		return emails
	except Exception as e:
		logger.warning("Error fetching emails: %s", e)
		return []
async def create_draft_reply(message_id: str, reply_text: str):
	"""Creates a draft reply to a specific message in the user's Gmail."""
	service = get_gmail_service()
	if not service:
		return False
		
	try:
		# 1. Get original message headers for threading
		original = service.users().messages().get(userId='me', id=message_id).execute()
		headers = {h['name']: h['value'] for h in original['payload']['headers']}
		
		# 2. Construct the reply headers
		subject = headers.get('Subject', '')
		if not subject.lower().startswith('re:'):
			subject = f"Re: {subject}"
			
		to = headers.get('From', '')
		message_id_header = headers.get('Message-ID', '')
		references = headers.get('References', '') + ' ' + message_id_header
		
		# 3. Build the email
		from email.message import EmailMessage
		import base64
		
		msg = EmailMessage()
		msg.set_content(reply_text)
		msg['To'] = to
		msg['Subject'] = subject
		msg['In-Reply-To'] = message_id_header
		msg['References'] = references.strip()
		
		raw_message = base64.urlsafe_b64encode(msg.as_bytes()).decode()
		
		# 4. Create Draft
		service.users().drafts().create(userId='me', body={
			'message': {
				'raw': raw_message,
				'threadId': original['threadId']
			}
		}).execute()
		return True
	except Exception as e:
		logger.warning("Error creating draft: %s", e)
		return False
