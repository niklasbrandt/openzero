from app.models.db import AsyncSessionLocal, Briefing

async def monthly_review():
	"""Generate and store the monthly review."""
	from app.services.llm import chat, last_model_used
	from app.services.planka import get_project_tree
	
	prompt = (
		"Z, monthly review. Summarize 30-day progress, stalled initiatives, and 3 major goals for next month. "
		"Strictly data-driven.\n\n"
		f"PROJECTS:\n{tree}"
	)
	
	content = await chat(prompt)
	
	# Store in Database
	async with AsyncSessionLocal() as session:
		briefing = Briefing(type="month", content=content, model=last_model_used.get())
		session.add(briefing)
		await session.commit()
	
	# Send Telegram Notification
	from app.api.telegram import send_notification
	from app.config import settings
	await send_notification(f"🗓️ *Monthly Mission Review*\n\n{content}\n\n🔗 [Dashboard]({settings.BASE_URL}/home)")
	
	return content
