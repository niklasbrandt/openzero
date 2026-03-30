from app.services.llm import chat, last_model_used
from app.services.planka import get_project_tree
from app.models.db import AsyncSessionLocal, Briefing, Project
from sqlalchemy import select
import asyncio
import datetime

async def weekly_review():
	"""Generate and store the weekly review with project stagnation checks."""
	import logging
	logger = logging.getLogger(__name__)
	logger.info("Weekly Review initialization started (T-15m offset).")
	
	try:
		from app.services.crews import crew_registry
		
		# 1. Native Pre-Compilation Yield: Await active /week crews (if any were started in background)
		# While true 'active' tracking for native is lightweight, we sync with the registry loader.
		await crew_registry.load()
			
		_t1 = asyncio.get_event_loop().time()
		
		tree = await get_project_tree(as_html=False)
	
		# Identify stagnant projects (Active but not updated in > 7 days)
		stagnant_list = []
		async with AsyncSessionLocal() as session:
			today = datetime.datetime.utcnow()
			week_ago = today - datetime.timedelta(days=7)
			
			result = await session.execute(
				select(Project).where(
					Project.status == "active",
					Project.updated_at < week_ago
				)
			)
			stagnant_projects = result.scalars().all()
			stagnant_list = [f"- {p.name} (Stagnant for {(today - p.updated_at).days} days)" for p in stagnant_projects]

		stagnant_text = "\n".join(stagnant_list) if stagnant_list else "All active projects show recent momentum."
		
		prompt = (
			"Z, weekly review. Summarize progress, roadblocks, and 3 goals for next week. "
			"Identify STAGNANT PROJECTS and suggest micro-tasks to unblock them.\n\n"
			f"PROJECT TREE:\n{tree}\n\n"
			f"STAGNANT PROJECTS (DATA-DRIVEN):\n{stagnant_text}\n"
		)
		
		content = await chat(prompt)
		
		# Store in Database
		async with AsyncSessionLocal() as session:
			briefing = Briefing(type="week", content=content, model=last_model_used.get())
			session.add(briefing)
			await session.commit()
			
		# 5. Precision Delivery SLEEP logic
		# We kicked off exactly 15m early to provide LLM lead time.
		try:
			from app.services.timezone import get_current_timezone
			import pytz
			tz_str = await get_current_timezone()
			tz = pytz.timezone(tz_str)
			now = datetime.datetime.now(tz)
			target = now.replace(hour=10, minute=0, second=0, microsecond=0)
			delta = (target - now).total_seconds()
			if 0 < delta < 1800:
				logger.info("weekly_review — Pre-compilation finished in %.1fs. Precision SLEEP for %.1fs until exact 10:00AM delivery.", (now.timestamp() - _t1) if '_t1' in locals() else 0, delta)
				await asyncio.sleep(delta)
		except Exception as e:
			logger.warning("weekly_review — Precision SLEEP failed: %s", e)
		
		# Send Telegram Notification
		from app.services.notifier import send_notification
		from app.config import settings
		await send_notification(f"📊 *Weekly Review Ready*\n\n{content}\n\n🔗 [Dashboard]({settings.BASE_URL}/dashboard)")
		
		return content

	except Exception as e:
		logger.error("CRITICAL: Weekly Review failed: %s", e, exc_info=True)
		return None
