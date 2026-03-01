from app.services.llm import chat
from app.services.planka import get_project_tree
from app.models.db import AsyncSessionLocal, Briefing
from app.api.telegram import send_notification
import datetime

async def quarterly_review():
	"""Generate and store the quarterly strategic review."""
	
	tree = await get_project_tree(as_html=False)
	
	prompt = (
		"Z, QUARTERLY STRATEGIC REVIEW. \n\n"
		"Analyze the past 90 days. Focus on:\n"
		"1. Major mission completions.\n"
		"2. Long-term trajectory shifts (Are we following the 'Universal Context'?)\n"
		"3. High-level roadblocks needing architectural changes.\n"
		"4. Strategic roadmap for the next 3 months.\n\n"
		"Format this as a professional high-level report for the operator.\n\n"
		f"PROJECTS:\n{tree}"
	)
	
	content = await chat(prompt)
	
	# Store in Database
	async with AsyncSessionLocal() as session:
		briefing = Briefing(type="quarter", content=content)
		session.add(briefing)
		await session.commit()
	
	# Send Telegram Notification
	await send_notification(f"📊 *Quarterly Strategic Review*\n\n{content}")
	
	return content
