from app.models.db import AsyncSessionLocal, Briefing

async def monthly_review():
	"""Generate and store the monthly review."""
	from app.services.llm import chat, last_model_used
	from app.services.planka import get_project_tree, get_activity_report

	tree = await get_project_tree(as_html=False)
	activity = await get_activity_report(days=30)

	prompt = (
		"Z, it's been a full month — write the monthly review.\n"
		"Write like a smart colleague giving a frank summary after a month of work. Natural, direct, slightly informal — not a literary essay, not a raw data dump.\n"
		"Short sentences. Plain words. Sections are fine — the language inside should sound like a person, not a report generator.\n"
		"Be specific: name actual boards, cards, and progress. Don't be vague.\n"
		"Aim for 250-400 words. Use bullets for lists; use short prose for observations and context.\n\n"
		"STRICT OPERATIONAL DATA (THE ONLY TRUTH):\n"
		f"{activity}\n\n"
		f"FULL PROJECT TREE:\n{tree}\n\n"
		"RULES:\n"
		"1. Respond ONLY based on the OPERATIONAL DATA and PROJECT TREE above.\n"
		"2. If OPERATIONAL DATA starts with '### OPERATIONAL DATA FAILURE', tell the user about the disconnection honestly — don't list specific card names from memory.\n"
		"3. CRITICAL: Ignore any placeholder or '[e.g., ...]' values from personal/business context (like Acme Studio, WebGPU, etc.).\n"
		"4. Suggest 3 meaningful goals for next month.\n"
		"5. NO metaphors, NO literary prose, NO filler phrases. Write like a human, not an LLM trying to sound reflective.\n"
		"6. NEVER use emoji or unicode decorative symbols.\n"
	)
	
	content = await chat(prompt, _feature="monthly_review")
	
	# Store in Database
	async with AsyncSessionLocal() as session:
		briefing = Briefing(type="month", content=content, model=last_model_used.get())
		session.add(briefing)
		await session.commit()
	
	# Send Telegram Notification
	from app.services.notifier import send_notification
	from app.config import settings
	await send_notification(f"---\n{content}\n\n[Dashboard]({settings.BASE_URL}/dashboard)")
	
	return content
