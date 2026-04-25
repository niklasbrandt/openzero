from app.models.db import AsyncSessionLocal, Briefing

async def quarterly_review():
	"""Generate and store the quarterly strategic review."""
	from app.services.llm import chat, last_model_used
	from app.services.planka import get_project_tree, get_activity_report

	tree = await get_project_tree(as_html=False)
	activity = await get_activity_report(days=90)

	activity_block = activity if activity and not str(activity).strip().startswith("### OPERATIONAL DATA FAILURE") else "[EMPTY — omit the activity/accomplishments section entirely]"
	tree_block = tree if tree and str(tree).strip() else "[EMPTY — omit the project tree section entirely]"

	prompt = (
		"Z, three months have passed — write the quarterly review.\n"
		"Write like a smart colleague summing up a quarter: natural, direct, slightly informal — not a literary reflection, not a bullet dump.\n"
		"Short sentences. Plain words. Sections are fine — the language inside should sound human, not generated.\n"
		"What actually moved, what stalled, and what matters going forward — based only on the data provided. Be specific.\n\n"
		"OPERATIONAL DATA (PAST 90 DAYS ACTIVITY):\n"
		f"{activity_block}\n\n"
		f"FULL PROJECT TREE:\n{tree_block}\n\n"
		"HALLUCINATION RULES (never break these):\n"
		"- Only include a section if real data for it was provided in the context above.\n"
		"- If a data block is marked [EMPTY] or contains no items — omit that section entirely. No heading, no placeholder text.\n"
		"- Never invent board cards, calendar events, emails, metrics, or completed tasks.\n"
		"- Never assume what happened during the quarter if no data confirms it.\n"
		"- The 'What was accomplished' section must only contain items explicitly present in OPERATIONAL DATA or PROJECT TREE above. If no cards moved, state that plainly — do not invent progress.\n"
		"- Proactive suggestions for the next quarter are allowed but must be clearly framed as suggestions, not as confirmed facts.\n\n"
		"RULES:\n"
		"1. Analyze the past 90 days based ONLY on the data above.\n"
		"2. If OPERATIONAL DATA is marked [EMPTY], do not list any specific card names or board progress — acknowledge honestly that no activity data is available for this period.\n"
		"3. Focus on what actually moved in the data and what the longer arc looks like from here.\n"
		"4. CRITICAL: Ignore any placeholder or '[e.g., ...]' values in your personal context.\n"
		"5. NO metaphors, NO literary prose, NO filler phrases. Write like a human, not an LLM trying to sound thoughtful.\n"
		"6. NEVER use emoji or unicode decorative symbols.\n"
	)
	
	content = await chat(prompt, _feature="quarterly_review", include_health=False)
	
	# Store in Database
	async with AsyncSessionLocal() as session:
		briefing = Briefing(type="quarter", content=content, model=last_model_used.get())
		session.add(briefing)
		await session.commit()
	
	# Send Telegram Notification
	from app.services.notifier import send_notification
	await send_notification(f"---\n{content}")
	
	return content
