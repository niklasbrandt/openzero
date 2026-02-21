from app.services.llm import chat
from app.services.planka import get_project_tree
from app.models.db import AsyncSessionLocal, Briefing
import datetime

async def weekly_review():
    """Generate and store the weekly review."""
    
    tree = await get_project_tree()
    
    prompt = (
        "Z, perform a weekly review. Looking at these projects, summarize progress, "
        "highlight roadblocks, and propose 3 main goals for next week.\n\n"
        f"PROJECTS:\n{tree}"
    )
    
    content = await chat(prompt)
    
    # Store in Database
    async with AsyncSessionLocal() as session:
        briefing = Briefing(type="weekly", content=content)
        session.add(briefing)
        await session.commit()
    
    return content
