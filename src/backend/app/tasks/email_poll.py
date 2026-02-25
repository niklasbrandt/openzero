from app.services.gmail import fetch_unread_emails, create_draft_reply
from app.services.llm import summarize_email, detect_calendar_events
from app.api.telegram import send_notification
from app.models.db import get_email_rules, store_pending_thought
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
import json

async def poll_gmail():
	"""Check for new emails, apply rules, notify if urgent or detect events."""
	rules = await get_email_rules()
	emails = await fetch_unread_emails(max_results=20)

	for email in emails:
		sender = email["from"].lower()
		subject = email["subject"]
		content = f"Subject: {subject}\n\n{email['snippet']}"

		# 1. Proactive Event Detection
		events = await detect_calendar_events(content)
		for event in events:
			# Store in pending queue for user approval
			event_id = await store_pending_thought("CALENDAR_APPROVAL", json.dumps(event))
			
			keyboard = [
				[
					InlineKeyboardButton("✅ Add to Calendar", callback_data=f"cal_approve_{event_id}"),
					InlineKeyboardButton("❌ Ignore", callback_data=f"cal_ignore_{event_id}"),
				]
			]
			markup = InlineKeyboardMarkup(keyboard)
			
			await send_notification(
				f"📅 *Z Detected an Event*\n\n"
				f"*Title:* {event['summary']}\n"
				f"*Start:* {event['start']}\n"
				f"*Context:* From {email['from']}\n\n"
				f"Shall I add this to your schedule?",
				reply_markup=markup
			)

		# 2. Check against rules
		rule_matched = False
		for rule in rules:
			if rule.sender_pattern.lower() in sender or rule.sender_pattern.lower() in subject.lower():
				rule_matched = True
				badge = rule.badge
				
				if rule.action == "urgent":
					await send_notification(
						f"⚠️ *URGENT EMAIL* {f'[{badge}]' if badge else ''}\n"
						f"From: {email['from']}\n"
						f"Subject: {subject}\n\n"
						f"Z: I am preparing a draft reply for you."
					)
					# Also summarize it so it's in the briefing as important
					await store_email_summary(email, is_urgent=True, badge=badge)
					
					# 3. Create Draft Reply
					await prepare_draft_reply(email)
				elif rule.action == "summarize":
					await store_email_summary(email, is_urgent=False, badge=badge)
				elif rule.action == "ignore":
					# Do nothing
					pass
				break
		
		if not rule_matched:
			# Default behavior: store summary for morning briefing
			await store_email_summary(email, is_urgent=False)

async def store_email_summary(email, is_urgent=False, badge=None):
	from app.models.db import AsyncSessionLocal, EmailSummary
	from app.services.llm import summarize_email
	
	async with AsyncSessionLocal() as db:
		summary = await summarize_email(email["snippet"])
		db_summary = EmailSummary(
			sender=email["from"],
			subject=email["subject"],
			summary=summary,
			is_urgent=is_urgent,
			badge=badge
		)
		db.add(db_summary)
		await db.commit()

async def prepare_draft_reply(email: dict):
	"""Generates and stores a draft reply via LLM."""
	from app.services.llm import chat
	
	prompt = (
		"You are Z, the user's AI assistant. Draft a professional, warm, and helpful reply to the following email. "
		"Assume the user will review it before sending. Strictly provide the message body only.\n\n"
		f"EMAIL SNIPPET:\n{email['snippet']}"
	)
	
	reply_body = await chat(prompt)
	success = await create_draft_reply(email["id"], reply_body)
	if success:
		print(f"DEBUG: Successfully created draft for {email['id']}")
	else:
		print(f"DEBUG: Failed to create draft for {email['id']}")
