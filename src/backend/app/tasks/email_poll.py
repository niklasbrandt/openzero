from app.services.gmail import fetch_unread_emails
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
        for rule in rules:
            if rule.sender_pattern in sender:
                if rule.action == "urgent":
                    await send_notification(
                        f"⚠️ *URGENT EMAIL*\n"
                        f"From: {email['from']}\n"
                        f"Subject: {subject}"
                    )
                break
        else:
            # Non-urgent: store summary for morning briefing
            from app.models.db import AsyncSessionLocal, EmailSummary
            
            async with AsyncSessionLocal() as db:
                summary = await summarize_email(email["snippet"])
                db_summary = EmailSummary(
                    sender=email["from"],
                    subject=subject,
                    summary=summary,
                    is_urgent=False
                )
                db.add(db_summary)
                await db.commit()
