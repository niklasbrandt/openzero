from app.services.llm import chat
from app.services.planka import get_project_tree
from app.models.db import AsyncSessionLocal, Briefing
import datetime

async def weekly_review():
    """Generate and store the weekly review."""
    
    tree = await get_project_tree()
    
    prompt = (
        "Z, weekly review. Summarize progress, roadblocks, and 3 goals for next week. "
        "Be direct. No filler.\n\n"
        f"PROJECTS:\n{tree}"
    )
    
    content = await chat(prompt)
    
    # Store in Database
    async with AsyncSessionLocal() as session:
        briefing = Briefing(type="week", content=content)
        session.add(briefing)
        await session.commit()
    
    return content
