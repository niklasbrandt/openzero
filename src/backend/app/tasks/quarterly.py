from app.models.db import AsyncSessionLocal, Briefing

async def quarterly_review():
	"""Generate and store the quarterly strategic review."""
	from app.services.llm import chat, last_model_used
	from app.services.planka import get_project_tree, get_activity_report

	tree = await get_project_tree(as_html=False)
	activity = await get_activity_report(days=90)

	prompt = (
		"Z, QUARTERLY STRATEGIC REVIEW. \n\n"
		"OPERATIONAL DATA (PAST 90 DAYS ACTIVITY):\n"
		f"{activity}\n\n"
		f"FULL PROJECT TREE:\n{tree}\n\n"
		"INSTRUCTIONS:\n"
		"1. Analyze the past 90 days based ONLY on the data above.\n"
		"2. Focus on major mission completions and long-term trajectory.\n"
		"3. CRITICAL: Ignore any placeholder or '[e.g., ...]' values in your personal context.\n"
		"4. Be professional and high-level."
	)
	
	content = await chat(prompt)
	
	# Store in Database
	async with AsyncSessionLocal() as session:
		briefing = Briefing(type="quarter", content=content, model=last_model_used.get())
		session.add(briefing)
		await session.commit()
	
	# Send Telegram Notification
	from app.services.notifier import send_notification
	await send_notification(f"*Quarterly Strategic Review*\n\n{content}")
	
	return content
