from app.services.llm import chat, last_model_used
from app.services.planka import get_project_tree, get_activity_report
from app.models.db import AsyncSessionLocal, Briefing
import asyncio
import datetime

async def weekly_review():
	"""Generate and store the weekly review based on live Planka activity."""
	import logging
	logger = logging.getLogger(__name__)
	logger.info("Weekly Review started...")
	
	try:
		tree = await get_project_tree(as_html=False)
		activity = await get_activity_report(days=7)
		
		prompt = (
			"Z, it's the end of the week — write a natural, flowing message to the user about how the week went.\n"
			"Think about what progressed, what stalled, and what feels important for next week.\n"
			"Write it like a thoughtful friend reflecting on the week — no formal headers, no bullet-point structure, just clear honest prose.\n\n"
			"OPERATIONAL DATA (7-DAY ACTIVITY):\n"
			f"{activity}\n\n"
			f"PROJECT TREE:\n{tree}\n\n"
			"RULES:\n"
			"- Base your message ONLY on the OPERATIONAL DATA and TREE provided above.\n"
			"- If OPERATIONAL DATA shows an 'OPERATIONAL DATA FAILURE/EMPTY' state, tell the user honestly without guessing at specifics.\n"
			"- Do not mention placeholder examples from personal files (like Acme Studio).\n"
			"- Suggest 3 things worth focusing on next week, woven naturally into the prose."
		)
		
		content = await chat(prompt, _feature="weekly_review")
		
		# Store in Database
		async with AsyncSessionLocal() as session:
			briefing = Briefing(type="week", content=content, model=last_model_used.get())
			session.add(briefing)
			await session.commit()
			
		# Precision Delivery SLEEP logic
		try:
			from app.services.timezone import get_current_timezone
			import pytz
			tz_str = await get_current_timezone()
			tz = pytz.timezone(tz_str)
			now = datetime.datetime.now(tz)
			target = now.replace(hour=10, minute=0, second=0, microsecond=0)
			delta = (target - now).total_seconds()
			if 0 < delta < 1800:
				logger.info("weekly_review — Precision SLEEP for %.1fs.", delta)
				await asyncio.sleep(delta)
		except Exception as e:
			logger.warning("weekly_review — Precision SLEEP failed: %s", e)
		
		# Send Telegram Notification
		from app.services.notifier import send_notification
		from app.config import settings
		await send_notification(f"---\n{content}\n\n[Dashboard]({settings.BASE_URL}/dashboard)")
		
		return content

	except Exception as e:
		logger.error("CRITICAL: Weekly Review failed: %s", e, exc_info=True)
		return None
