from app.services.gmail import fetch_unread_emails
from app.services.llm import summarize_email
from app.api.telegram import send_notification
from app.models.db import get_email_rules

async def poll_gmail():
    """Check for new emails, apply rules, notify if urgent."""
    rules = await get_email_rules()
    emails = await fetch_unread_emails(max_results=20)

    for email in emails:
        sender = email["from"].lower()
        subject = email["subject"]

        # Check against rules
        for rule in rules:
            if rule.sender_pattern in sender:
                if rule.action == "urgent":
                    await send_notification(
                        f" *URGENT EMAIL*\n"
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
