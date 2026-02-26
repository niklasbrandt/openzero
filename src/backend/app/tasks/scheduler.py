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

scheduler = AsyncIOScheduler(timezone=settings.USER_TIMEZONE)

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

	scheduler.start()

async def stop_scheduler():
	scheduler.shutdown(wait=False)
