from app.models.db import AsyncSessionLocal, Briefing

async def monthly_review():
	"""Generate and store the monthly review."""
	from app.services.llm import chat, last_model_used
	from app.services.planka import get_project_tree, get_activity_report

	tree = await get_project_tree(as_html=False)
	activity = await get_activity_report(days=30)

	activity_block = activity if activity and not str(activity).strip().startswith("### OPERATIONAL DATA FAILURE") else "[EMPTY — omit the activity/accomplishments section entirely]"
	tree_block = tree if tree and str(tree).strip() else "[EMPTY — omit the project tree section entirely]"

	prompt = (
		"Z, it's been a full month — write the monthly review.\n"
		"Write like a smart colleague giving a frank summary after a month of work. Natural, direct, slightly informal — not a literary essay, not a raw data dump.\n"
		"Short sentences. Plain words. Sections are fine — the language inside should sound like a person, not a report generator.\n"
		"Be specific: name actual boards, cards, and progress mentioned in the data. Don't be vague.\n"
		"Aim for 250-400 words. Use bullets for lists; use short prose for observations and context.\n\n"
		"STRICT OPERATIONAL DATA (THE ONLY TRUTH):\n"
		f"{activity_block}\n\n"
		f"FULL PROJECT TREE:\n{tree_block}\n\n"
		"HALLUCINATION RULES (never break these):\n"
		"- Only include a section if real data for it was provided in the context above.\n"
		"- If a data block is marked [EMPTY] or contains no items — omit that section entirely. No heading, no placeholder text.\n"
		"- Never invent board cards, calendar events, emails, metrics, or completed tasks.\n"
		"- Never assume what happened during the month if no data confirms it.\n"
		"- The 'What was accomplished' section must only contain items explicitly present in OPERATIONAL DATA or PROJECT TREE above. If no cards moved, state that plainly — do not invent progress.\n"
		"- Proactive goals for next month are allowed but must be clearly framed as suggestions, not as confirmed plans.\n\n"
		"RULES:\n"
		"1. Respond ONLY based on the OPERATIONAL DATA and PROJECT TREE above.\n"
		"2. If OPERATIONAL DATA is marked [EMPTY], do not list any specific card names or board progress — acknowledge honestly that no activity data is available for this period.\n"
		"3. CRITICAL: Ignore any placeholder or '[e.g., ...]' values from personal/business context (like Acme Studio, WebGPU, etc.).\n"
		"4. Suggest 3 meaningful goals for next month — frame them as suggestions, not scheduled commitments.\n"
		"5. NO metaphors, NO literary prose, NO filler phrases. Write like a human, not an LLM trying to sound reflective.\n"
		"6. NEVER use emoji or unicode decorative symbols.\n"
	)
	
	content = await chat(prompt, _feature="monthly_review", include_health=False)
	
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
