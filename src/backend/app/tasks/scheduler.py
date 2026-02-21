from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from app.tasks.morning import morning_briefing
from app.tasks.weekly import weekly_review
from app.tasks.email_poll import poll_gmail
from app.config import settings

scheduler = AsyncIOScheduler(timezone=settings.USER_TIMEZONE)

async def start_scheduler():
    # Morning Briefing — Mon–Fri at 07:30
    scheduler.add_job(
        morning_briefing,
        CronTrigger(day_of_week="mon-fri", hour=7, minute=30),
        id="morning_briefing",
        replace_existing=True,
    )

    # Weekly Review — Sunday at 10:00
    scheduler.add_job(
        weekly_review,
        CronTrigger(day_of_week="sun", hour=10, minute=0),
        id="weekly_review",
        replace_existing=True,
    )

    # Email Polling (via Gmail API or other mail client API) — every 10 minutes
    scheduler.add_job(
        poll_gmail,
        IntervalTrigger(minutes=10),
        id="poll_gmail",
        replace_existing=True,
    )

    scheduler.start()

async def stop_scheduler():
    scheduler.shutdown(wait=False)
