from typing import Optional
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
import datetime
import uuid
from app.config import settings

class Base(DeclarativeBase):
	pass
engine = create_async_engine(settings.DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

class Project(Base):
    __tablename__ = "projects"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    parent_id = Column(Integer, ForeignKey("projects.id"), nullable=True)
    status = Column(String, default="active")
    priority = Column(Integer, default=3)
    domain = Column(String, default="general")
    last_reviewed = Column(DateTime)
    progress = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

class Preference(Base):
    __tablename__ = "preferences"
    id = Column(Integer, primary_key=True)
    key = Column(String, unique=True, nullable=False)
    value = Column(String, nullable=False)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

class EmailRule(Base):
    __tablename__ = "email_rules"
    id = Column(Integer, primary_key=True)
    sender_pattern = Column(String, nullable=False)
    subject_pattern = Column(String)
    action = Column(String, default="urgent")
    badge = Column(String) # Custom badge name (e.g. "School", "Taxes")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class EmailSummary(Base):
    __tablename__ = "email_summaries"
    id = Column(Integer, primary_key=True)
    sender = Column(String, nullable=False)
    subject = Column(String, nullable=False)
    summary = Column(Text)
    is_urgent = Column(Boolean, default=False)
    badge = Column(String) # Replicated badge from rule
    processed_at = Column(DateTime, default=datetime.datetime.utcnow)
    included_in_briefing = Column(Boolean, default=False)

class PendingThought(Base):
    __tablename__ = "pending_thoughts"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    query = Column(Text, nullable=False)
    context_data = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class Briefing(Base):
    __tablename__ = "briefings"
    id = Column(Integer, primary_key=True)
    type = Column(String, nullable=False)  # day, week, month, year
    content = Column(Text, nullable=False)
    model = Column(String, nullable=True)  # LLM tier/model that generated this briefing
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class Person(Base):
    __tablename__ = "people"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    relationship = Column(String)
    context = Column(Text)  # Homework, hobbies, special dates
    circle_type = Column(String, default="inner")  # inner, close, outer, identity
    birthday = Column(String)  # Optional birthday string (e.g. DD.MM.YYYY)
    gender = Column(String)
    residency = Column(String)
    timezone = Column(String) # e.g. "Europe/Berlin"
    town = Column(String) # e.g. "Berlin"
    country = Column(String) # e.g. "Germany"
    work_times = Column(String)
    work_start = Column(String, default="09:00")
    work_end = Column(String, default="17:00")
    briefing_time = Column(String) # e.g. "08:00"
    quiet_hours_enabled = Column(Boolean, default=True)
    quiet_hours_start = Column(String, default="00:00")
    quiet_hours_end = Column(String, default="06:00")
    language = Column(String, default="en") # ISO 639-1 code: en, zh, hi, es, fr, ar, pt, ru, ja, de
    color_primary = Column(String)  # Favorite primary color
    color_secondary = Column(String) # Favorite secondary color
    color_tertiary = Column(String)  # Favorite tertiary color
    last_interaction = Column(DateTime)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class TrackingSession(Base):
    __tablename__ = "tracking_sessions"
    id = Column(Integer, primary_key=True)
    tasks = Column(Text, nullable=False) # Original full list
    milestones_json = Column(Text) # JSON: [{"task": "desc", "due_at": "ISO", "sent": false}]
    end_time = Column(DateTime, nullable=False)
    final_nudge_sent = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class GlobalMessage(Base):
    __tablename__ = "global_messages"
    id = Column(Integer, primary_key=True)
    channel = Column(String) # "telegram", "dashboard"
    role = Column(String)    # "user", "z"
    content = Column(Text, nullable=False)
    model = Column(String, nullable=True)  # LLM tier + model used for Z responses
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class LLMMetric(Base):
    __tablename__ = "llm_metrics"
    id = Column(Integer, primary_key=True)
    tier = Column(String, nullable=False)       # "fast" or "deep"
    feature = Column(String, nullable=False)     # "user_chat", "memory_extraction", "urgency_classify", etc.
    model = Column(String)                       # e.g. "Qwen3-0.6B", "Qwen3-8B-Q3"
    tokens = Column(Integer)                     # estimated output tokens (chunk count)
    latency_ms = Column(Integer)                 # wall-clock milliseconds
    prompt_len = Column(Integer)                 # approximate input length (chars)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class LocalEvent(Base):
    __tablename__ = "local_events"
    id = Column(Integer, primary_key=True)
    summary = Column(String, nullable=False)
    description = Column(Text)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=True)   # nullable: defaults to start+1h if not provided
    person_id = Column(Integer, ForeignKey("people.id"), nullable=True)
    is_completed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class CustomTask(Base):
    __tablename__ = "custom_tasks"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    message = Column(Text, nullable=False)
    job_type = Column(String, default="cron") # cron, interval
    spec = Column(String, nullable=False) # e.g. "0 12 * * 1" (Cron) or "minutes=30" (Interval)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

from sqlalchemy import select

# Utility functions
async def get_email_rules() -> list[EmailRule]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(EmailRule))
        return list(result.scalars().all())

async def store_pending_thought(query: str, context_data: str) -> str:
    tid = uuid.uuid4()
    async with AsyncSessionLocal() as session:
        thought = PendingThought(id=tid, query=query, context_data=context_data)
        session.add(thought)
        await session.commit()
    return str(tid)

async def get_pending_thought(thought_id: str):
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(PendingThought).where(PendingThought.id == thought_id))
        thought = result.scalar_one_or_none()
        if thought:
            return {"query": thought.query, "context_data": thought.context_data}
        return None

async def save_global_message(channel: str, role: str, content: str, model: Optional[str] = None):
    async with AsyncSessionLocal() as session:
        msg = GlobalMessage(channel=channel, role=role, content=content, model=model)
        session.add(msg)
        await session.commit()

async def get_global_history(limit: int = 15):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(GlobalMessage).order_by(GlobalMessage.created_at.desc()).limit(limit)
        )
        messages = result.scalars().all()
        # Return in chronological order for the LLM
        return [{"role": m.role, "content": m.content, "channel": m.channel, "model": m.model, "at": m.created_at.isoformat()} for m in reversed(messages)]
