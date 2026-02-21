from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, Enum
from sqlalchemy.dialects.postgresql import UUID
import datetime
import uuid
from app.config import settings

Base = declarative_base()
engine = create_async_engine(settings.DATABASE_URL, echo=True)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

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
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class EmailSummary(Base):
    __tablename__ = "email_summaries"
    id = Column(Integer, primary_key=True)
    sender = Column(String, nullable=False)
    subject = Column(String, nullable=False)
    summary = Column(Text)
    is_urgent = Column(Boolean, default=False)
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
    type = Column(String, nullable=False)  # daily, weekly, monthly
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class Person(Base):
    __tablename__ = "people"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    relationship = Column(String)
    context = Column(Text)  # Homework, hobbies, special dates
    circle_type = Column(String, default="inner")  # inner, close
    calendar_id = Column(String)  # Optional Google Calendar ID/Email
    last_interaction = Column(DateTime)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Utility functions
async def get_email_rules() -> list[EmailRule]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(EmailRule))
        return result.scalars().all()

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
