from app.services.llm import chat, last_model_used
from app.services.planka import get_project_tree, get_activity_report
from app.models.db import AsyncSessionLocal, Briefing

async def yearly_review():
	"""Generate and store the yearly review."""
	
	tree = await get_project_tree(as_html=False)
	activity = await get_activity_report(days=365)

	prompt = (
		"Z, yearly review.\n\n"
		"OPERATIONAL DATA (PAST 365 DAYS ACTIVITY):\n"
		f"{activity}\n\n"
		f"FULL PROJECT TREE:\n{tree}\n\n"
		"INSTRUCTIONS:\n"
		"1. Summarize high-level progress and identify themes.\n"
		"2. CRITICAL: Ignore any placeholder or '[e.g., ...]' values in your personal context.\n"
		"3. Be visionary but concise. Propose 3 year-long goals."
	)
	
	content = await chat(prompt, _feature="yearly_review", include_health=False)
	
	# Store in Database
	async with AsyncSessionLocal() as session:
		briefing = Briefing(type="yearly", content=content, model=last_model_used.get())
		session.add(briefing)
		await session.commit()
	
	return content
