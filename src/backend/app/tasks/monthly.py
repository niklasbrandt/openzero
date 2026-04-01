from app.models.db import AsyncSessionLocal, Briefing

async def monthly_review():
	"""Generate and store the monthly review."""
	from app.services.llm import chat, last_model_used
	from app.services.planka import get_project_tree, get_activity_report

	tree = await get_project_tree(as_html=False)
	activity = await get_activity_report(days=30)

	prompt = (
		"Z, monthly review. Summarize 30-day progress, stalled initiatives, and 3 major goals for next month.\n\n"
		"STRICT OPERATIONAL DATA (THE ONLY TRUTH):\n"
		f"{activity}\n\n"
		f"FULL PROJECT TREE:\n{tree}\n\n"
		"INSTRUCTIONS:\n"
		"1. Respond ONLY based on the OPERATIONAL DATA and PROJECT TREE above.\n"
		"2. If OPERATIONAL DATA starts with '### OPERATIONAL DATA FAILURE', report the failure to the user and DO NOT list specific card names from your own memory or personal files.\n"
		"3. CRITICAL: Ignore any placeholder or '[e.g., ...]' values found in your personal/business context (like Acme Studio, WebGPU, etc.). If you see them, they are NOT your user's data.\n"
		"4. Be sharp, direct, and data-driven. No filler.\n"
		"5. Format with clear headers: ### 1. 30-Day Progress | ### 2. 3 Major Goals for Next Month"
	)
	
	content = await chat(prompt)
	
	# Store in Database
	async with AsyncSessionLocal() as session:
		briefing = Briefing(type="month", content=content, model=last_model_used.get())
		session.add(briefing)
		await session.commit()
	
	# Send Telegram Notification
	from app.services.notifier import send_notification
	from app.config import settings
	await send_notification(f"🗓️ *Monthly Mission Review*\n\n{content}\n\n🔗 [Dashboard]({settings.BASE_URL}/dashboard)")
	
	return content
