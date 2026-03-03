from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from app.tasks.morning import morning_briefing
from app.tasks.weekly import weekly_review
from app.tasks.email_poll import poll_gmail
from app.tasks.operator_sync import run_operator_sync
from app.services.timezone import update_detected_timezone, get_current_timezone, get_user_timezone
from app.config import settings
import pytz
import logging
import re
import subprocess
import os

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone=pytz.utc)

# ---------------------------------------------------------------------------
# DNS Watchdog state
# ---------------------------------------------------------------------------
_dns_fail_count: int = 0
_dns_alert_sent: bool = False  # avoids spamming on sustained failure

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

	# Morning Briefing — Every day at Configured Time
	scheduler.add_job(
		morning_briefing,
		CronTrigger(hour=brief_hour, minute=brief_min),
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

	# Table Cleanup — PendingThought rows older than 24 h (every 6 hours)
	scheduler.add_job(
		cleanup_pending_thoughts,
		IntervalTrigger(hours=6),
		id="cleanup_pending_thoughts",
		replace_existing=True,
	)

	# Table Cleanup — Keep only last 500 GlobalMessage rows (every 12 hours)
	scheduler.add_job(
		cleanup_global_messages,
		IntervalTrigger(hours=12),
		id="cleanup_global_messages",
		replace_existing=True,
	)

	# DNS Watchdog — test Pi-hole DNS every 5 minutes, alert + auto-fix on failure
	scheduler.add_job(
		check_pihole_dns,
		IntervalTrigger(minutes=5),
		id="dns_watchdog",
		replace_existing=True,
	)

	# 2. Load User-Defined Persistent Custom Tasks
	await load_custom_tasks()

	scheduler.start()
	logger.info(f"Z: Missions scheduled. Morning Briefing set to {brief_hour:02d}:{brief_min:02d} {user_tz_str}")

async def cleanup_pending_thoughts():
	"""Delete PendingThought rows older than 24 hours."""
	from app.models.db import AsyncSessionLocal, PendingThought
	from sqlalchemy import delete as sa_delete
	import datetime
	try:
		async with AsyncSessionLocal() as session:
			cutoff = datetime.datetime.utcnow() - datetime.timedelta(hours=24)
			result = await session.execute(
				sa_delete(PendingThought).where(PendingThought.created_at < cutoff)
			)
			await session.commit()
			logger.info("Cleanup: deleted %d expired PendingThought rows.", result.rowcount)
	except Exception as e:
		logger.error("cleanup_pending_thoughts failed: %s", e)


async def cleanup_global_messages():
	"""Keep only the most recent 500 GlobalMessage rows."""
	from app.models.db import AsyncSessionLocal
	from sqlalchemy import text
	try:
		async with AsyncSessionLocal() as session:
			await session.execute(text("""
				DELETE FROM global_messages
				WHERE id NOT IN (
					SELECT id FROM global_messages
					ORDER BY created_at DESC
					LIMIT 500
				)
			"""))
			await session.commit()
			logger.info("Cleanup: trimmed GlobalMessage table to 500 rows.")
	except Exception as e:
		logger.error("cleanup_global_messages failed: %s", e)


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
					# Validate before loading (defense-in-depth against stale bad rows)
					fields = t.spec.strip().split()
					if len(fields) != 5 or not all(re.match(r'^[\d*/,\-]+$', f) for f in fields):
						logger.warning("Skipping custom task '%s': invalid cron spec '%s'", t.name, t.spec)
						continue
					trigger = CronTrigger.from_crontab(t.spec)
				elif t.job_type == "interval":
					# Spec: "minutes=30" or "hours=2" or "days=1"
					allowed_keys = {"minutes", "hours", "days"}
					kwargs = {}
					for part in t.spec.split(","):
						if "=" in part:
							k, v = part.split("=", 1)
							if k.strip() in allowed_keys:
								try:
									v_int = int(v.strip())
									if v_int >= 1:
										kwargs[k.strip()] = v_int
								except ValueError:
									pass
					if not kwargs:
						logger.warning("Skipping custom task '%s': invalid interval spec '%s'", t.name, t.spec)
						continue
					logger.info(f"Loaded persistent custom task: {t.name} ({t.job_type})")
	except Exception as e:
		logger.error(f"Failed to load custom tasks: {e}")

async def stop_scheduler():
	scheduler.shutdown(wait=False)


# ---------------------------------------------------------------------------
# DNS Watchdog
# ---------------------------------------------------------------------------
async def check_pihole_dns():
	"""
	Runs every 5 minutes.
	- Queries Pi-hole on 127.0.0.1 for 'open.zero' via dig.
	- Alerts via Telegram after 2 consecutive failures.
	- Attempts auto-fix (pihole -g gravity rebuild) if FTL.log shows gravity DB errors.
	- Sends a recovery notification once DNS comes back.
	"""
	global _dns_fail_count, _dns_alert_sent

	try:
		result = subprocess.run(
			["dig", "@127.0.0.1", "open.zero", "+short", "+time=3", "+tries=1"],
			capture_output=True, text=True, timeout=8
		)
		dns_ok = result.returncode == 0 and result.stdout.strip() != ""
	except Exception as e:
		logger.error("dns_watchdog: dig failed with exception: %s", e)
		dns_ok = False

	if dns_ok:
		if _dns_fail_count > 0:
			logger.info("dns_watchdog: DNS recovered after %d failed checks.", _dns_fail_count)
			if _dns_alert_sent:
				try:
					from app.api.telegram import send_notification_html
					await send_notification_html(
						"<b>✅ DNS recovered</b> — Pi-hole is resolving <code>open.zero</code> again."
					)
				except Exception as te:
					logger.error("dns_watchdog: failed to send recovery alert: %s", te)
		_dns_fail_count = 0
		_dns_alert_sent = False
		return

	# DNS failed
	_dns_fail_count += 1
	logger.warning("dns_watchdog: DNS failure #%d — 127.0.0.1:53 not answering for open.zero", _dns_fail_count)

	# Inspect FTL log for gravity DB corruption signature
	gravity_broken = False
	try:
		ftl_check = subprocess.run(
			["docker", "exec", "openzero-pihole-1", "tail", "-50", "/var/log/pihole/FTL.log"],
			capture_output=True, text=True, timeout=10
		)
		if "no such table" in ftl_check.stdout or "gravityDB" in ftl_check.stdout:
			gravity_broken = True
			logger.error("dns_watchdog: gravity DB corruption detected in FTL.log")
	except Exception as e:
		logger.error("dns_watchdog: could not read FTL.log: %s", e)

	# Auto-fix: rebuild gravity DB if corruption detected
	auto_fix_result = "not attempted"
	if gravity_broken:
		logger.warning("dns_watchdog: attempting auto-fix — deleting and rebuilding gravity.db")
		try:
			subprocess.run(
				["docker", "exec", "openzero-pihole-1", "rm", "-f",
				 "/etc/pihole/gravity.db", "/etc/pihole/gravity.db_temp"],
				timeout=10
			)
			rebuild = subprocess.run(
				["docker", "exec", "openzero-pihole-1", "pihole", "-g"],
				capture_output=True, text=True, timeout=120
			)
			if rebuild.returncode == 0:
				auto_fix_result = "gravity DB rebuilt successfully"
				logger.info("dns_watchdog: gravity DB rebuild succeeded")
			else:
				auto_fix_result = f"rebuild failed (exit {rebuild.returncode}): {rebuild.stderr[:200]}"
				logger.error("dns_watchdog: gravity rebuild failed: %s", rebuild.stderr[:400])
		except Exception as e:
			auto_fix_result = f"exception during rebuild: {e}"
			logger.error("dns_watchdog: auto-fix exception: %s", e)

	# Alert after 2 consecutive failures (skip transient single-poll blips)
	if _dns_fail_count >= 2 and not _dns_alert_sent:
		_dns_alert_sent = True
		try:
			from app.api.telegram import send_notification_html
			fix_line = f"\n<b>Auto-fix:</b> <code>{auto_fix_result}</code>" if gravity_broken else ""
			gravity_line = "\n<b>Cause:</b> gravity DB corruption detected in FTL.log" if gravity_broken else "\n<b>Cause:</b> unknown — check FTL.log manually"
			await send_notification_html(
				f"<b>🚨 DNS DOWN</b> — Pi-hole not resolving <code>open.zero</code>\n"
				f"<b>Failures:</b> {_dns_fail_count} consecutive checks{gravity_line}{fix_line}\n\n"
				f"Run: <code>docker exec openzero-pihole-1 pihole -g</code> if auto-fix failed."
			)
		except Exception as te:
			logger.error("dns_watchdog: failed to send Telegram alert: %s", te)
