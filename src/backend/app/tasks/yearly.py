from app.services.llm import chat, last_model_used
from app.services.planka import get_project_tree, get_activity_report
from app.models.db import AsyncSessionLocal, Briefing

async def yearly_review():
	"""Generate and store the yearly review."""
	
	tree = await get_project_tree(as_html=False)
	activity = await get_activity_report(days=365)

	activity_block = activity if activity and not str(activity).strip().startswith("### OPERATIONAL DATA FAILURE") else "[EMPTY — omit the activity/accomplishments section entirely]"
	tree_block = tree if tree and str(tree).strip() else "[EMPTY — omit the project tree section entirely]"

	prompt = (
		"Z, it's been a full year — write the yearly review.\n"
		"Write like a smart colleague summing up twelve months: natural, direct, slightly informal — not a literary reflection, not a bullet dump.\n"
		"Short sentences. Plain words. Sections are fine — the language inside should sound human, not generated.\n"
		"What actually moved, what themes emerged, what the year looked like from the data. Be specific.\n\n"
		"OPERATIONAL DATA (PAST 365 DAYS ACTIVITY):\n"
		f"{activity_block}\n\n"
		f"FULL PROJECT TREE:\n{tree_block}\n\n"
		"HALLUCINATION RULES (never break these):\n"
		"- Only include a section if real data for it was provided in the context above.\n"
		"- If a data block is marked [EMPTY] or contains no items — omit that section entirely. No heading, no placeholder text.\n"
		"- Never invent board cards, calendar events, emails, metrics, or completed tasks.\n"
		"- Never assume what happened during the year if no data confirms it.\n"
		"- The 'What was accomplished' section must only contain items explicitly present in OPERATIONAL DATA or PROJECT TREE above. If no cards moved, state that plainly — do not invent progress.\n"
		"- Proposed goals for next year are allowed but must be clearly framed as suggestions, not as confirmed plans.\n\n"
		"INSTRUCTIONS:\n"
		"1. Summarize high-level progress and identify themes based ONLY on the data above.\n"
		"2. If OPERATIONAL DATA is marked [EMPTY], do not list any specific card names or board progress — acknowledge honestly that no activity data is available for this period.\n"
		"3. CRITICAL: Ignore any placeholder or '[e.g., ...]' values in your personal context.\n"
		"4. Be specific about what the data shows — no fabricated accomplishments, no assumed themes.\n"
		"5. Propose 3 year-long goals — frame them as suggestions, not scheduled commitments.\n"
		"6. NO metaphors, NO literary prose, NO filler phrases. Write like a human, not an LLM trying to sound visionary.\n"
		"7. NEVER use emoji or unicode decorative symbols."
	)
	
	content = await chat(prompt, _feature="yearly_review", include_health=False)
	
	# Store in Database
	async with AsyncSessionLocal() as session:
		briefing = Briefing(type="yearly", content=content, model=last_model_used.get())
		session.add(briefing)
		await session.commit()
	
	return content
