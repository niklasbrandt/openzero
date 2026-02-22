from app.services.llm import chat
from app.services.planka import get_project_tree
from app.models.db import AsyncSessionLocal, Briefing
import datetime

async def monthly_review():
    """Generate and store the monthly review."""
    
    tree = await get_project_tree()
    
    prompt = (
        "Z, perform a monthly review. Looking at these active projects and tasks over the last 30 days, "
        "summarize the progress made, point out any stalled initiatives, and propose 3 major goals "
        "to focus on for the upcoming month.\n\n"
        f"PROJECTS:\n{tree}"
    )
    
    content = await chat(prompt)
    
    # Store in Database
    async with AsyncSessionLocal() as session:
        briefing = Briefing(type="month", content=content)
        session.add(briefing)
        await session.commit()
    
    return content
