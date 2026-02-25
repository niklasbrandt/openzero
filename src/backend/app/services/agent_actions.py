from langchain_core.tools import tool
from typing import Optional, List
from app.services.planka import create_task as planka_create_task
from app.services.planka import create_project as planka_create_project
from app.services.planka import create_board as planka_create_board

@tool
def create_task(title: str, description: str = "", board_name: str = "Operator Board", list_name: str = "Today") -> str:
    """Create a task in a specific board and list."""
    import asyncio
    success = asyncio.run(planka_create_task(
        board_name=board_name,
        list_name=list_name,
        title=title,
        description=description
    ))
    return f"Task '{title}' created successfully." if success else f"Failed to create task '{title}'"

@tool
def create_project(name: str, description: str = "") -> str:
    """Create a new project."""
    import asyncio
    asyncio.run(planka_create_project(name=name, description=description))
    return f"Project '{name}' created."

@tool
def create_event(title: str, start_time: str, end_time: Optional[str] = None) -> str:
    """Create a new calendar event."""
    from app.models.db import LocalEvent, AsyncSessionLocal
    import datetime
    import asyncio
    async def _add():
        async with AsyncSessionLocal() as db:
            event = LocalEvent(
                summary=title,
                start_time=datetime.datetime.fromisoformat(start_time.replace('Z','')),
                end_time=datetime.datetime.fromisoformat(end_time.replace('Z','')) if end_time else None
            )
            db.add(event)
            await db.commit()
    asyncio.run(_add())
    return f"Calendar event '{title}' created."

@tool
def learn_memory(text: str) -> str:
    """Learn a new memory fact."""
    from app.services.memory import store_memory
    import asyncio
    asyncio.run(store_memory(text))
    return "Memory stored."

AVAILABLE_TOOLS = [create_task, create_project, create_event, learn_memory]

async def parse_and_execute_actions(reply: str, db=None):
    """Fallback stub for legacy tool parsing if LangGraph is disabled."""
    # We now use LangGraph, so we return the reply as-is and no executed cmds string-parsed
    return reply, []
