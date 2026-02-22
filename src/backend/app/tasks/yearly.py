from app.services.llm import chat
from app.services.planka import get_project_tree
from app.models.db import AsyncSessionLocal, Briefing
import datetime

async def yearly_review():
    """Generate and store the yearly review."""
    
    tree = await get_project_tree()
    
    prompt = (
        "Z, perform a yearly overview review. Look closely at these current projects and goals, "
        "summarize the high-level progress, and identify overarching themes or missing long-term "
        "objectives. Propose 3 major goals for the upcoming year.\n\n"
        f"PROJECTS:\n{tree}"
    )
    
    content = await chat(prompt)
    
    # Store in Database
    async with AsyncSessionLocal() as session:
        briefing = Briefing(type="yearly", content=content)
        session.add(briefing)
        await session.commit()
    
    return content
