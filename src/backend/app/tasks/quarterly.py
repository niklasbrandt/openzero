from app.models.db import AsyncSessionLocal, Briefing

async def quarterly_review():
	"""Generate and store the quarterly strategic review."""
	from app.services.llm import chat, last_model_used
	from app.services.planka import get_project_tree, get_activity_report

	tree = await get_project_tree(as_html=False)
	activity = await get_activity_report(days=90)

	prompt = (
		"Z, three months have passed — write the quarterly review.\n"
		"Write like a smart colleague summing up a quarter: natural, direct, slightly informal — not a literary reflection, not a bullet dump.\n"
		"Short sentences. Plain words. Sections are fine — the language inside should sound human, not generated.\n"
		"What actually moved, what stalled, and what matters going forward. Be specific.\n\n"
		"OPERATIONAL DATA (PAST 90 DAYS ACTIVITY):\n"
		f"{activity}\n\n"
		f"FULL PROJECT TREE:\n{tree}\n\n"
		"RULES:\n"
		"1. Analyze the past 90 days based ONLY on the data above.\n"
		"2. Focus on what actually moved and what the longer arc looks like from here.\n"
		"3. CRITICAL: Ignore any placeholder or '[e.g., ...]' values in your personal context.\n"
		"4. NO metaphors, NO literary prose, NO filler phrases. Write like a human, not an LLM trying to sound thoughtful.\n"
		"5. NEVER use emoji or unicode decorative symbols.\n"
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
