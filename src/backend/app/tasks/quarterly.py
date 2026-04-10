from app.models.db import AsyncSessionLocal, Briefing

async def quarterly_review():
	"""Generate and store the quarterly strategic review."""
	from app.services.llm import chat, last_model_used
	from app.services.planka import get_project_tree, get_activity_report

	tree = await get_project_tree(as_html=False)
	activity = await get_activity_report(days=90)

	prompt = (
		"Z, three months have passed — write a genuine, flowing reflection on the quarter.\n"
		"What actually happened? What shifted, what stalled, and what feels important as you look ahead?\n"
		"Write it like a thoughtful friend who's been paying attention — no corporate structure, no bullet headers, just honest prose.\n\n"
		"OPERATIONAL DATA (PAST 90 DAYS ACTIVITY):\n"
		f"{activity}\n\n"
		f"FULL PROJECT TREE:\n{tree}\n\n"
		"RULES:\n"
		"1. Analyze the past 90 days based ONLY on the data above.\n"
		"2. Focus on what actually moved and what the longer arc looks like from here.\n"
		"3. CRITICAL: Ignore any placeholder or '[e.g., ...]' values in your personal context.\n"
	)
	
	content = await chat(prompt)
	
	# Store in Database
	async with AsyncSessionLocal() as session:
		briefing = Briefing(type="quarter", content=content, model=last_model_used.get())
		session.add(briefing)
		await session.commit()
	
	# Send Telegram Notification
	from app.services.notifier import send_notification
	await send_notification(f"---\n{content}")
	
	return content
