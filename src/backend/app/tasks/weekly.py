from app.services.llm import chat
from app.services.planka import get_project_tree
from app.models.db import AsyncSessionLocal, Briefing, Project
from sqlalchemy import select
import datetime

async def weekly_review():
	"""Generate and store the weekly review with project stagnation checks."""
	
	tree = await get_project_tree(as_html=False)
	
	# Identify stagnant projects (Active but not updated in > 7 days)
	stagnant_list = []
	async with AsyncSessionLocal() as session:
		today = datetime.datetime.utcnow()
		week_ago = today - datetime.timedelta(days=7)
		
		# In a real Planka integration, 'updated_at' would come from Planka API.
		# For now, we use our local DB 'projects' as a mirror or secondary source.
		result = await session.execute(
			select(Project).where(
				Project.status == "active",
				Project.updated_at < week_ago
			)
		)
		stagnant_projects = result.scalars().all()
		stagnant_list = [f"- {p.name} (Stagnant for {(today - p.updated_at).days} days)" for p in stagnant_projects]

	stagnant_text = "\n".join(stagnant_list) if stagnant_list else "All active projects show recent momentum."
	
	prompt = (
		"Z, weekly review. Summarize progress, roadblocks, and 3 goals for next week. "
		"Identify STAGNANT PROJECTS and suggest micro-tasks to unblock them.\n\n"
		f"PROJECT TREE:\n{tree}\n\n"
		f"STAGNANT PROJECTS (DATA-DRIVEN):\n{stagnant_text}\n"
	)
	
	content = await chat(prompt)
	
	# Store in Database
	async with AsyncSessionLocal() as session:
		briefing = Briefing(type="week", content=content)
		session.add(briefing)
		await session.commit()
	
	# Send Telegram Notification
	from app.api.telegram import send_notification
	from app.config import settings
	await send_notification(f"📊 *Weekly Review Ready*\n\n{content}\n\n🔗 [Dashboard]({settings.BASE_URL}/home)")
	
	return content
