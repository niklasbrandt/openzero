from app.services.llm import chat
from app.services.planka import get_project_tree
from app.models.db import AsyncSessionLocal, Briefing
import datetime

async def yearly_review():
    """Generate and store the yearly review."""
    
    tree = await get_project_tree()
    
    prompt = (
        "Z, yearly review. Summarize high-level progress, identifying themes or missing objectives. "
        "Propose 3 year-long goals. Be visionary but concise.\n\n"
        f"PROJECTS:\n{tree}"
    )
    
    content = await chat(prompt)
    
    # Store in Database
    async with AsyncSessionLocal() as session:
        briefing = Briefing(type="yearly", content=content)
        session.add(briefing)
        await session.commit()
    
    return content
