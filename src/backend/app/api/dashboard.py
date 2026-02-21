from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from app.models.db import AsyncSessionLocal, Project, EmailRule, Briefing, Person
from app.services.memory import semantic_search
from app.services.planka import get_project_tree
from app.services.llm import chat as llm_chat
from pydantic import BaseModel
from typing import List, Optional
import datetime

router = APIRouter(prefix="/api/dashboard")

# Dependency to get DB session
async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

# --- Chat ---
class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    message: str
    history: List[ChatMessage] = []

@router.post("/chat")
async def dashboard_chat(req: ChatRequest, db: AsyncSession = Depends(get_db)):
    """Chat with Z from the dashboard."""
    # Get people info for context
    result = await db.execute(select(Person).where(Person.circle_type == "inner"))
    people = result.scalars().all()
    people_context = "\n".join([
        f"- {p.name} ({p.relationship}): Managed on my calendar: {p.use_my_calendar}"
        for p in people
    ])
    
    context_prefix = f"Inner Circle Context:\n{people_context}\n\n" if people_context else ""

    # Build conversation context from history
    history_text = ""
    if req.history:
        history_text = "\n".join(
            f"{'User' if m.role == 'user' else 'Z'}: {m.content}"
            for m in req.history[-10:]  # Last 10 messages for context
        )
        history_text = f"\n\nConversation so far:\n{history_text}\n\nUser: {req.message}"
    
    prompt = context_prefix + (history_text if history_text else req.message)
    
    try:
        reply = await llm_chat(prompt)
        return {"reply": reply}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- Projects ---
@router.get("/projects")
async def get_projects():
    # Implementing a simplified JSON tree for the dashboard
    tree = await get_project_tree()
    return {"tree": tree}

# --- Create Project ---
class ProjectCreate(BaseModel):
    name: str
    description: str = ""
    tags: List[str] = []

@router.post("/projects")
async def create_project(project: ProjectCreate):
    """Create a new project via Planka or local storage."""
    # For now, return success — wire to Planka or DB as needed
    return {"status": "created", "name": project.name}

# --- Memory ---
@router.get("/memory/search")
async def search_memory(query: str):
    if not query:
        return {"results": []}
    results = await semantic_search(query)
    # Parsing the string results back to a list for the UI
    lines = results.split("\n")
    return {"results": [line for line in lines if line.strip()]}

# --- Briefings ---
@router.get("/briefings")
async def get_briefings(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Briefing).order_by(Briefing.created_at.desc()).limit(10))
    briefings = result.scalars().all()
    return briefings

# --- Email Rules ---
class EmailRuleCreate(BaseModel):
    sender_pattern: str
    action: str = "urgent"

@router.get("/email-rules")
async def get_email_rules(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(EmailRule))
    return result.scalars().all()

@router.post("/email-rules")
async def create_email_rule(rule: EmailRuleCreate, db: AsyncSession = Depends(get_db)):
    db_rule = EmailRule(sender_pattern=rule.sender_pattern, action=rule.action)
    db.add(db_rule)
    await db.commit()
    await db.refresh(db_rule)
    return db_rule

@router.delete("/email-rules/{rule_id}")
async def delete_email_rule(rule_id: int, db: AsyncSession = Depends(get_db)):
    await db.execute(delete(EmailRule).where(EmailRule.id == rule_id))
    await db.commit()
    return {"status": "deleted"}

# --- People (Inner/Close Circle) ---
class PersonCreate(BaseModel):
    name: str
    relationship: str
    context: str = ""
    circle_type: str = "inner"
    calendar_id: Optional[str] = None
    use_my_calendar: bool = False

@router.get("/people")
async def get_people(circle_type: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    query = select(Person)
    if circle_type:
        query = query.where(Person.circle_type == circle_type)
    result = await db.execute(query)
    return result.scalars().all()

@router.post("/people")
async def create_person(person: PersonCreate, db: AsyncSession = Depends(get_db)):
    db_person = Person(
        name=person.name, 
        relationship=person.relationship, 
        context=person.context,
        circle_type=person.circle_type,
        calendar_id=person.calendar_id,
        use_my_calendar=person.use_my_calendar
    )
    db.add(db_person)
    await db.commit()
    await db.refresh(db_person)
    return db_person

@router.delete("/people/{person_id}")
async def delete_person(person_id: int, db: AsyncSession = Depends(get_db)):
    await db.execute(delete(Person).where(Person.id == person_id))
    await db.commit()
    return {"status": "deleted"}

# --- Calendar ---
from app.services.calendar import fetch_calendar_events

@router.get("/calendar")
async def get_calendar(db: AsyncSession = Depends(get_db)):
    """Fetch user's primary calendar events and detect family members."""
    events = await fetch_calendar_events(calendar_id="primary", max_results=20, days_ahead=7)
    
    # Get all people to match prefixes
    result = await db.execute(select(Person))
    people = result.scalars().all()
    
    # Enrich events with person info
    enriched_events = []
    for event in events:
        summary = event.get("summary", "")
        person_name = None
        for p in people:
            if summary.startswith(f"{p.name}:"):
                person_name = p.name
                break
        
        enriched_events.append({
            **event,
            "person": person_name
        })
    
    return enriched_events
