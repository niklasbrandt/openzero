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
			"Z, it's the end of the week — write the weekly review.\n"
			"Write like a smart colleague summing up the week in a message. Natural, direct, slightly informal — not a literary reflection, not a bullet dump.\n"
			"Short sentences. Plain words. Sections with headers are fine — the language inside should sound like a person, not a report generator.\n"
			"Be specific: name actual boards, cards, and progress. Don't be vague.\n"
			"Aim for 200-350 words. Use bullets for lists of items; use short prose for observations and context.\n\n"
			"OPERATIONAL DATA (7-DAY ACTIVITY):\n"
			f"{activity}\n\n"
			f"PROJECT TREE:\n{tree}\n\n"
			"RULES:\n"
			"- Base your message ONLY on the OPERATIONAL DATA and TREE provided above.\n"
			"- If OPERATIONAL DATA shows an 'OPERATIONAL DATA FAILURE/EMPTY' state, tell the user honestly without guessing at specifics.\n"
			"- Do not mention placeholder examples from personal files (like Acme Studio).\n"
			"- Suggest 3 concrete things worth focusing on next week.\n"
			"- NO metaphors, NO literary prose, NO filler ('honestly?', 'that screams', etc.). Write like a human, not an LLM trying to sound thoughtful.\n"
			"- NEVER use emoji or unicode decorative symbols."
		)
		
		content = await chat(prompt, _feature="weekly_review", include_health=False)
		
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
