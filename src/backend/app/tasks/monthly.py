from app.services.llm import chat
from app.services.planka import get_project_tree
from app.models.db import AsyncSessionLocal, Briefing
import datetime

async def monthly_review():
	"""Generate and store the monthly review."""
	
	tree = await get_project_tree(as_html=False)
	
	prompt = (
		"Z, monthly review. Summarize 30-day progress, stalled initiatives, and 3 major goals for next month. "
		"Strictly data-driven.\n\n"
		f"PROJECTS:\n{tree}"
	)
	
	content = await chat(prompt)
	
	# Store in Database
	async with AsyncSessionLocal() as session:
		briefing = Briefing(type="month", content=content)
		session.add(briefing)
		await session.commit()
	
	return content
