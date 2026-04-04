import os
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from app.config import settings
from app.common.scheduler_instance import scheduler
import pytz
import logging
import re
import subprocess
import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Subprocess security allowlist
# ---------------------------------------------------------------------------
_ALLOWED_SUBPROCESSES = {"/bin/bash"}
_BASH_EXEC = next(iter(_ALLOWED_SUBPROCESSES))  # "/bin/bash" — validated at module load
_ALLOWED_SCRIPT_DIR = os.path.abspath(
	os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../../scripts")
)

# ---------------------------------------------------------------------------
# DNS Watchdog state
# ---------------------------------------------------------------------------
_dns_state = {"fail_count": 0, "alert_sent": False}

async def run_backup():
	"""Runs the daily system backup script."""
	logger.info("Starting automated backup...")
	try:
		# Get absolute path to scripts/backup.sh relative to this file
		current_dir = os.path.dirname(os.path.abspath(__file__))
		script_path = os.path.abspath(os.path.join(current_dir, "../../../scripts/backup.sh"))

		# Security: allowlist check
		if not script_path.startswith(_ALLOWED_SCRIPT_DIR + os.sep) and script_path != _ALLOWED_SCRIPT_DIR:
			logger.error("Backup script path outside allowed directory: %s", script_path)
			return

		if not os.path.exists(script_path):
			logger.error("Backup script not found at: %s", script_path)
			return

		result = subprocess.run([_BASH_EXEC, script_path], capture_output=True, text=True)
		if result.returncode == 0:
			logger.info("Backup completed successfully.")
		else:
			logger.error("Backup script failed with exit code %s: %s", result.returncode, result.stderr)
	except Exception as e:
		logger.error("Automated backup failed: %s", e)

async def start_scheduler():
	# 1. Identify user's actual timezone and preferred briefing time
	from app.models.db import AsyncSessionLocal, Person
	from app.tasks.morning import morning_briefing
	from app.tasks.weekly import weekly_review
	from app.tasks.email_poll import poll_gmail
	from app.tasks.operator_sync import run_operator_sync
	from app.services.timezone import update_detected_timezone, get_current_timezone
	from sqlalchemy import select
	from datetime import datetime

	user_tz_str = await get_current_timezone()
	try:
		# Configure scheduler with correct timezone to respect DST
		scheduler.configure(timezone=pytz.timezone(user_tz_str))
		logger.info("Scheduler initialized with timezone: %s", user_tz_str)
	except Exception:
		logger.error("Invalid timezone configuration: %s. Falling back to UTC.", user_tz_str)
		scheduler.configure(timezone=pytz.utc)

	brief_hour, brief_min = 7, 30 # Default
	quiet_enabled = False
	qh_start_hour, qh_end_hour = 22, 6
	try:
		async with AsyncSessionLocal() as session:
			res = await session.execute(select(Person).where(Person.circle_type == "identity"))
			me = res.scalar_one_or_none()
			if me:
				if me.briefing_time:
					# Format: "HH:MM"
					parts = me.briefing_time.split(":")
					if len(parts) == 2:
						brief_hour, brief_min = int(parts[0]), int(parts[1])
				
				if me.quiet_hours_enabled:
					quiet_enabled = True
					if me.quiet_hours_start:
						qh_start_hour = int(me.quiet_hours_start.split(":")[0])
					if me.quiet_hours_end:
						qh_end_hour = int(me.quiet_hours_end.split(":")[0])
	except Exception as e:
		logger.warning("Failed to fetch dynamic schedule configurations: %s", e)

	# Log the precise next triggers for debugging
	tz = pytz.timezone(user_tz_str)
	now = datetime.now(tz)
	logger.info("System Time Check: %s (Offset: %s)", now.strftime('%Y-%m-%d %H:%M:%S %Z'), now.utcoffset())

	# Morning Briefing
	# Fire exactly 15 minutes before user's explicitly requested delivery time.
	# This ensures the LLM has already analyzed the overnight crew results.
	from datetime import datetime, timedelta, time
	target_time = datetime.combine(datetime.today(), time(hour=brief_hour, minute=brief_min))
	fire_time = target_time - timedelta(minutes=15)
	
	scheduler.add_job(
		morning_briefing,
		CronTrigger(hour=fire_time.hour, minute=fire_time.minute, timezone=tz),
		id="morning_briefing",
		replace_existing=True,
	)

	# Weekly Review — Trigger offset -15m to allow /week crews to resolve 
	# User target: Sunday at 10:00. Fire at 09:45.
	scheduler.add_job(
		weekly_review,
		CronTrigger(day_of_week="sun", hour=9, minute=45, timezone=tz),
		id="weekly_review",
		replace_existing=True,
	)

	# Monthly Review — 1st of every month at 09:00
	from app.tasks.monthly import monthly_review
	scheduler.add_job(
		monthly_review,
		CronTrigger(day=1, hour=9, minute=0, timezone=tz),
		id="monthly_review",
		replace_existing=True,
	)

	# Quarterly Review — 1st of Jan, Apr, Jul, Oct at 10:30
	from app.tasks.quarterly import quarterly_review
	scheduler.add_job(
		quarterly_review,
		CronTrigger(month="1,4,7,10", day=1, hour=10, minute=30, timezone=tz),
		id="quarter_review",
		replace_existing=True,
	)

	# Yearly Review — January 2nd at 11:00
	from app.tasks.yearly import yearly_review
	scheduler.add_job(
		yearly_review,
		CronTrigger(month=1, day=2, hour=11, minute=0, timezone=tz),
		id="yearly_review",
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

	# Proactive Mission Follow-up — Dynamic Activity Window
	from app.services.follow_up import run_proactive_follow_up, check_active_tracking_sessions, evening_reminder
	
	# Compute APScheduler hour ranges respecting Quiet Hours
	if quiet_enabled and qh_start_hour != qh_end_hour:
		if qh_end_hour < qh_start_hour:
			# Quiet hours span midnight (e.g. 22 to 6). Active hours: 6 to 21
			active_hours = f"{qh_end_hour}-{qh_start_hour - 1}"
		else:
			# Quiet hours in same day (e.g. 13 to 15). Active hours: 0-12, 16-23
			# Note: APScheduler handles comma-separated ranges: "0-12,16-23"
			p1 = f"0-{qh_start_hour - 1}" if qh_start_hour > 0 else ""
			p2 = f"{(qh_end_hour + 1) % 24}-23" if qh_end_hour < 23 else ""
			active_hours = f"{p1},{p2}".strip(",")
	else:
		active_hours = "6-23" # Fallback if disabled
	
	scheduler.add_job(
		run_proactive_follow_up,
		CronTrigger(hour=active_hours, minute="*/10", timezone=tz),
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

	# Evening Today-board sweep — 17:00 and 19:00 local time
	scheduler.add_job(
		evening_reminder,
		CronTrigger(hour="17,19", minute=0, timezone=tz),
		id="evening_reminder",
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

	# LLM Metrics Cleanup — Keep only last 2000 rows (every 24 hours)
	scheduler.add_job(
		cleanup_llm_metrics,
		IntervalTrigger(hours=24),
		id="cleanup_llm_metrics",
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

	# 3. Hourly personal context scan
	from app.services.personal_context import refresh_personal_context
	scheduler.add_job(
		refresh_personal_context,
		IntervalTrigger(hours=1),
		id="personal_context_scan",
		replace_existing=True,
	)

	# 4. Hourly agent context scan
	from app.services.agent_context import refresh_agent_context
	scheduler.add_job(
		refresh_agent_context,
		IntervalTrigger(hours=1),
		id="agent_context_scan",
		replace_existing=True,
	)

	# 5. Load Active Crews
	from app.services.crews import crew_registry
	from app.services.agent_actions import execute_crew_programmatically
	active_crews = crew_registry.list_active()
	for crew in active_crews:
		trigger = None
		# Determine dynamic briefing offset or legacy CRON schedule
		if crew.feeds_briefing:
			lead_time_m = crew.lead_time or 30
			# Create a dummy anchor to test the offset
			target_time = datetime.combine(datetime.today(), time(hour=brief_hour, minute=brief_min))
			crew_time = target_time - timedelta(minutes=lead_time_m)
			
			day_shift = (crew_time.date() - target_time.date()).days  # 0 or -1
			
			if crew.feeds_briefing == "/day":
				trigger = CronTrigger(hour=crew_time.hour, minute=crew_time.minute, timezone=tz)
			elif crew.feeds_briefing == "/week" and crew.briefing_day:
				# Convert "MON" string to 0-6 index, shift by day_shift, and map to apscheduler 'mon', 'tue' etc.
				days = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
				target_idx = [d[:3].lower() for d in days].index(crew.briefing_day[:3].lower())
				final_idx = (target_idx + day_shift) % 7
				trigger = CronTrigger(day_of_week=days[final_idx], hour=crew_time.hour, minute=crew_time.minute, timezone=tz)
			elif crew.feeds_briefing == "/month" and crew.briefing_dom:
				# DOM parsing simplifies to integer, shifting if day_shift == -1
				doms = [int(x.strip()) for x in str(crew.briefing_dom).split(",")]
				shifted_doms = [(d + day_shift) if (d + day_shift) > 0 else 28 for d in doms]
				trigger = CronTrigger(day=",".join(map(str, shifted_doms)), hour=crew_time.hour, minute=crew_time.minute, timezone=tz)
				
		elif crew.schedule:
			trigger = CronTrigger.from_crontab(crew.schedule, timezone=tz)

		if trigger:
			scheduler.add_job(
				execute_crew_programmatically,
				trigger,
				args=[crew.id, "Scheduled cron context window initialized."],
				id=f"crew_{crew.id}",
				replace_existing=True,
			)

	scheduler.start()
	logger.info("Z: Missions scheduled. Morning Briefing set to %02d:%02d %s", brief_hour, brief_min, user_tz_str)

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


async def cleanup_llm_metrics():
	"""Keep only the most recent 2000 LLMMetric rows."""
	from app.models.db import AsyncSessionLocal
	from sqlalchemy import text
	try:
		async with AsyncSessionLocal() as session:
			await session.execute(text("""
				DELETE FROM llm_metrics
				WHERE id NOT IN (
					SELECT id FROM llm_metrics
					ORDER BY created_at DESC
					LIMIT 2000
				)
			"""))
			await session.commit()
			logger.info("Cleanup: trimmed llm_metrics table to 2000 rows.")
	except Exception as e:
		logger.error("cleanup_llm_metrics failed: %s", e)


async def load_custom_tasks():
	"""Loads persistent custom tasks from the database into the scheduler."""
	from app.models.db import AsyncSessionLocal, CustomTask
	from sqlalchemy import select
	from app.services.notifier import send_notification

	try:
		async with AsyncSessionLocal() as session:
			res = await session.execute(select(CustomTask).where(CustomTask.is_active.is_(True)))
			tasks = res.scalars().all()

			for t in tasks:
				# Use a wrapper to capture the specific message for this job
				def make_task(msg):
					async def notify_task():
						await send_notification(f"*Custom Turnus Alert*\n\n{msg}")
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
								except ValueError as _ve:
									logger.debug("Scheduler: Invalid interval value in spec %s: %s", t.spec, _ve)
					if not kwargs:
						logger.warning("Skipping custom task '%s': invalid interval spec '%s'", t.name, t.spec)
						continue
					trigger = IntervalTrigger(**kwargs)

				if trigger:
					scheduler.add_job(
						make_task(t.message),
						trigger,
						id=f"custom_{t.id}",
						replace_existing=True,
					)
					logger.info("Loaded persistent custom task: %s (%s)", t.name, t.job_type)
	except Exception as e:
		logger.error("Failed to load custom tasks: %s", e)

async def stop_scheduler():
	scheduler.shutdown(wait=False)


# ---------------------------------------------------------------------------
# DNS Watchdog
# ---------------------------------------------------------------------------
async def check_pihole_dns():
	"""
	Runs every 5 minutes.
	- Queries Pi-hole on 'pihole' (host-gateway) for 'open.zero' via dig.
	- Alerts via Telegram after 2 consecutive failures.
	- Replaces docker exec ... dig @127.0.0.1 with dig @pihole.
	- Replaces docker exec ... tail FTL.log with httpx GET summary.
	- Sends a recovery notification once DNS comes back.
	"""
	import subprocess # Local import for subprocess
	try:
		# Query directly via internal network (pihole resolves to host-gateway)
		result = subprocess.run(
			["dig", "@pihole", "open.zero", "+short", "+time=3", "+tries=1"],
			capture_output=True, text=True, timeout=10
		)
		dns_ok = result.returncode == 0 and result.stdout.strip() != ""
	except Exception as e:
		logger.error("dns_watchdog: dig failed with exception: %s", e)
		dns_ok = False

	if dns_ok:
		if _dns_state["fail_count"] > 0:
			logger.info("dns_watchdog: DNS recovered after %d failed checks.", _dns_state["fail_count"])
			if _dns_state["alert_sent"]:
				try:
					from app.services.notifier import send_notification_html
					await send_notification_html(
						"<b>✅ DNS recovered</b> — Pi-hole is resolving <code>open.zero</code> again."
					)
				except Exception as te:
					logger.error("dns_watchdog: failed to send Telegram alert: %s", te)
		_dns_state["fail_count"] = 0
		_dns_state["alert_sent"] = False
		return

	# DNS failed
	_dns_state["fail_count"] += 1
	logger.warning("dns_watchdog: DNS failure #%d — pihole:53 not answering for open.zero", _dns_state["fail_count"])

	# Inspect FTL health via API instead of docker exec tail
	ftl_alive = False
	try:
		# Pi-hole v6 FTL port is 8081 in our compose. Use long timeout for slow VPS.
		async with httpx.AsyncClient(timeout=10) as client:
			resp = await client.get("http://pihole:8081/admin/api.php?summaryRaw")
			ftl_alive = resp.status_code == 200
	except Exception as e:
		logger.error("dns_watchdog: FTL health check failed: %s", e)

	# Alert after 2 consecutive failures (skip transient single-poll blips)
	if _dns_state["fail_count"] >= 2 and not _dns_state["alert_sent"]:
		_dns_state["alert_sent"] = True
		try:
			from app.services.notifier import send_notification_html
			# Removed auto-fix logic (docker exec rm/pihole -g) as it requires docker.sock mount
			cause_line = "\n<b>Cause:</b> FTL process unreachable (API 503/timeout)" if not ftl_alive else "\n<b>Cause:</b> unknown — FTL is alive but DNS failed"
			await send_notification_html(
				f"<b>🚨 DNS DOWN</b> — Pi-hole not resolving <code>open.zero</code>\n"
				f"<b>Failures:</b> {_dns_state['fail_count']} consecutive checks{cause_line}\n\n"
				f"Run: <code>docker exec -it openzero-pihole-1 pihole -g</code> on the VPS if gravity is corrupt."
			)
		except Exception as te:
			logger.error("dns_watchdog: failed to send Telegram alert: %s", te)
