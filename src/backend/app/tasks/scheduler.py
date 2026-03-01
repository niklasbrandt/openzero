from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from app.tasks.morning import morning_briefing
from app.tasks.weekly import weekly_review
from app.tasks.email_poll import poll_gmail
from app.tasks.operator_sync import run_operator_sync
from app.services.timezone import update_detected_timezone, get_current_timezone
from app.config import settings

import subprocess
import os
import logging

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()

async def run_backup():
	"""Runs the daily system backup script."""
	logger.info("Starting automated backup...")
	try:
		# Get absolute path to scripts/backup.sh relative to this file
		current_dir = os.path.dirname(os.path.abspath(__file__))
		script_path = os.path.abspath(os.path.join(current_dir, "../../../scripts/backup.sh"))
		
		if not os.path.exists(script_path):
			logger.error(f"Backup script not found at: {script_path}")
			return
			
		result = subprocess.run(["/bin/bash", script_path], capture_output=True, text=True)
		if result.returncode == 0:
			logger.info("Backup completed successfully.")
		else:
			logger.error(f"Backup script failed with exit code {result.returncode}: {result.stderr}")
	except Exception as e:
		logger.error(f"Automated backup failed: {e}")

async def start_scheduler():
	# 1. Identify user's actual timezone and preferred briefing time
	from app.models.db import AsyncSessionLocal, Person
	from sqlalchemy import select
	from app.services.timezone import get_current_timezone
	import pytz
	from datetime import datetime
	
	user_tz_str = await get_current_timezone()
	try:
		# Configure scheduler with correct timezone to respect DST
		scheduler.configure(timezone=pytz.timezone(user_tz_str))
		logger.info(f"Scheduler initialized with timezone: {user_tz_str}")
	except Exception as te:
		logger.error(f"Invalid timezone configuration: {user_tz_str}. Falling back to UTC.")
		scheduler.configure(timezone=pytz.utc)

	brief_hour, brief_min = 7, 30 # Default
	try:
		async with AsyncSessionLocal() as session:
			res = await session.execute(select(Person).where(Person.circle_type == "identity"))
			me = res.scalar_one_or_none()
			if me and me.briefing_time:
				# Format: "HH:MM"
				parts = me.briefing_time.split(":")
				if len(parts) == 2:
					brief_hour, brief_min = int(parts[0]), int(parts[1])
	except Exception as e:
		logger.warning(f"Failed to fetch dynamic briefing time: {e}")

	# Log the precise next triggers for debugging
	tz = pytz.timezone(user_tz_str)
	now = datetime.now(tz)
	logger.info(f"System Time Check: {now.strftime('%Y-%m-%d %H:%M:%S %Z')} (Offset: {now.utcoffset()})")

	# Morning Briefing — Mon–Fri at Configured Time
	scheduler.add_job(
		morning_briefing,
		CronTrigger(day_of_week="mon-fri", hour=brief_hour, minute=brief_min),
		id="morning_briefing",
		replace_existing=True,
	)

	# Weekly Review — Sunday at 10:00 (or slightly after briefing)
	scheduler.add_job(
		weekly_review,
		CronTrigger(day_of_week="sun", hour=10, minute=0),
		id="weekly_review",
		replace_existing=True,
	)

	# Monthly Review — 1st of every month at 09:00
	from app.tasks.monthly import monthly_review
	scheduler.add_job(
		monthly_review,
		CronTrigger(day=1, hour=9, minute=0),
		id="monthly_review",
		replace_existing=True,
	)

	# Quarterly Review — 1st of Jan, Apr, Jul, Oct at 10:30
	from app.tasks.quarterly import quarterly_review
	scheduler.add_job(
		quarterly_review,
		CronTrigger(month="1,4,7,10", day=1, hour=10, minute=30),
		id="quarter_review",
		replace_existing=True,
	)

	# Email Polling (via Gmail API or other mail client API) — every 10 minutes
	scheduler.add_job(
		poll_gmail,
		IntervalTrigger(minutes=10),
		id="poll_gmail",
		replace_existing=True,
	)

	# Operator Board Sync — Interval from config
	scheduler.add_job(
		run_operator_sync,
		IntervalTrigger(minutes=settings.TASK_BOARD_SYNC_INTERVAL_MINUTES),
		id="operator_sync",
		replace_existing=True,
	)

	# Daily System Backup — Every night at 04:00
	scheduler.add_job(
		run_backup,
		CronTrigger(hour=4, minute=0),
		id="system_backup",
		replace_existing=True,
	)

	# Timezone Detection Sync — Every 4 hours
	scheduler.add_job(
		update_detected_timezone,
		IntervalTrigger(hours=4),
		id="timezone_sync",
		replace_existing=True,
	)

	# Proactive Mission Follow-up — Every 3 hours from 9 AM to 9 PM
	from app.services.follow_up import run_proactive_follow_up, check_active_tracking_sessions
	scheduler.add_job(
		run_proactive_follow_up,
		CronTrigger(hour="9,12,15,18,21", minute=0),
		id="proactive_follow_up",
		replace_existing=True,
	)

	# High Proximity Tracking Monitor — Every 5 minutes
	scheduler.add_job(
		check_active_tracking_sessions,
		IntervalTrigger(minutes=5),
		id="proximity_monitor",
		replace_existing=True,
	)

	# 2. Load User-Defined Persistent Custom Tasks
	await load_custom_tasks()

	scheduler.start()
	logger.info(f"Z: Missions scheduled. Morning Briefing set to {brief_hour:02d}:{brief_min:02d} {user_tz_str}")

async def load_custom_tasks():
	"""Loads persistent custom tasks from the database into the scheduler."""
	from app.models.db import AsyncSessionLocal, CustomTask
	from sqlalchemy import select
	from app.api.telegram import send_notification
	
	try:
		async with AsyncSessionLocal() as session:
			res = await session.execute(select(CustomTask).where(CustomTask.is_active == True))
			tasks = res.scalars().all()
			
			for t in tasks:
				# Use a wrapper to capture the specific message for this job
				def make_task(msg):
					async def notify_task():
						await send_notification(f"🔔 *Custom Turnus Alert*\n\n{msg}")
					return notify_task
				
				trigger = None
				if t.job_type == "cron":
					# Spec: "minute hour day month day_of_week" (standard crontab)
					trigger = CronTrigger.from_crontab(t.spec)
				elif t.job_type == "interval":
					# Spec: "minutes=30" or "hours=2" or "days=1"
					kwargs = {}
					for part in t.spec.split(","):
						if "=" in part:
							k, v = part.split("=")
							kwargs[k.strip()] = int(v.strip())
					trigger = IntervalTrigger(**kwargs)
				
				if trigger:
					scheduler.add_job(
						make_task(t.message),
						trigger,
						id=f"persistent_custom_{t.id}",
						replace_existing=True
					)
					logger.info(f"Loaded persistent custom task: {t.name} ({t.job_type})")
	except Exception as e:
		logger.error(f"Failed to load custom tasks: {e}")

async def stop_scheduler():
	scheduler.shutdown(wait=False)
