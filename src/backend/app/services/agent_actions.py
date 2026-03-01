import re
import asyncio
import logging
from langchain_core.tools import tool
from typing import Optional, List
from app.services.planka import create_task as planka_create_task
from app.services.planka import create_project as planka_create_project
from app.services.planka import create_board as planka_create_board

logger = logging.getLogger(__name__)

@tool
async def create_task(title: str, description: str = "", board_name: str = "Operator Board", list_name: str = "Today") -> str:
    """Create a task in a specific board and list."""
    success = await planka_create_task(
        board_name=board_name,
        list_name=list_name,
        title=title,
        description=description
    )
    return f"Task '{title}' created successfully." if success else f"Failed to create task '{title}'"

@tool
async def create_project(name: str, description: str = "") -> str:
    """Create a new project."""
    await planka_create_project(name=name, description=description)
    return f"Project '{name}' created."

@tool
async def create_event(title: str, start_time: str, end_time: Optional[str] = None) -> str:
    """Create a new calendar event."""
    from app.models.db import LocalEvent, AsyncSessionLocal
    import datetime
    
    async with AsyncSessionLocal() as db:
        event = LocalEvent(
            summary=title,
            start_time=datetime.datetime.fromisoformat(start_time.replace('Z','')),
            end_time=datetime.datetime.fromisoformat(end_time.replace('Z','')) if end_time else None
        )
        db.add(event)
        await db.commit()
    return f"Calendar event '{title}' created."

@tool
async def learn_memory(text: str) -> str:
    """Learn a new memory fact."""
    from app.services.memory import store_memory
    await store_memory(text)
    return "Memory stored."

@tool
async def schedule_reminder(message: str, interval_minutes: int, duration_hours: Optional[int] = None) -> str:
    """Schedule a periodic reminder. Interval in minutes, duration in hours."""
    from app.tasks.scheduler import scheduler
    from app.api.telegram import send_notification
    from apscheduler.triggers.interval import IntervalTrigger
    from datetime import datetime, timedelta
    import pytz
    from app.services.timezone import get_current_timezone
    import uuid

    tz_str = await get_current_timezone()
    tz = pytz.timezone(tz_str)
    
    async def send_reminder_task():
        await send_notification(f"🔔 *Z: Periodic Reminder*\n\n{message}")

    end_date = None
    if duration_hours:
        end_date = datetime.now(tz) + timedelta(hours=duration_hours)
    
    reminder_id = f"reminder_{uuid.uuid4().hex[:8]}"
    
    scheduler.add_job(
        send_reminder_task,
        IntervalTrigger(minutes=interval_minutes, end_date=end_date, timezone=tz),
        id=reminder_id,
        replace_existing=True
    )
    
    return f"Reminder set: '{message}' every {interval_minutes}m for {duration_hours}h. (ID: {reminder_id})"

@tool
async def schedule_persistent_custom(name: str, message: str, job_type: str, spec: str) -> str:
    """Create a persistent scheduled task. job_type='cron' or 'interval'. spec is standard cron or 'minutes=N'."""
    from app.models.db import AsyncSessionLocal, CustomTask
    async with AsyncSessionLocal() as session:
        task = CustomTask(name=name, message=message, job_type=job_type, spec=spec)
        session.add(task)
        await session.commit()
    # Also hot-load it into the running scheduler
    from app.tasks.scheduler import load_custom_tasks
    await load_custom_tasks()
    return f"Persistent custom task '{name}' created and scheduled."

AVAILABLE_TOOLS = [create_task, create_project, create_event, learn_memory, schedule_reminder, schedule_persistent_custom]

async def parse_and_execute_actions(reply: str, db=None):
    """
    Parses Semantic Action Tags from the AI reply and executes them.
    Robust fallback for both legacy [ACTION: ...] and modern tool-like strings.
    """
    executed_cmds = []
    clean_reply = reply
    
    # helper to clean tag from reply
    def strip_tag(text, tag_match):
        # Escape for literal replacement
        return text.replace(tag_match, "").strip()

    # 1. Create Task Tag
    # [ACTION: CREATE_TASK | BOARD: name | LIST: name | TITLE: text]
    task_pattern = r"\[?ACTION: CREATE_TASK \| BOARD: ([^\|\]]+) \| LIST: ([^\|\]]+) \| TITLE: ([^\|\]]+)\]?"
    for match in re.finditer(task_pattern, reply):
        raw_tag = match.group(0)
        board, llist, title = match.groups()
        success = await planka_create_task(board_name=board.strip(), list_name=llist.strip(), title=title.strip())
        if success: executed_cmds.append(f"Task '{title.strip()}' created.")
        clean_reply = strip_tag(clean_reply, raw_tag)

    # 2. Create Project Tag
    # [ACTION: CREATE_PROJECT | NAME: text | DESCRIPTION: text]
    proj_pattern = r"\[?ACTION: CREATE_PROJECT \| NAME: ([^\|\]]+) \| DESCRIPTION: ([^\|\]]+)\]?"
    for match in re.finditer(proj_pattern, reply):
        raw_tag = match.group(0)
        name, desc = match.groups()
        await planka_create_project(name=name.strip(), description=desc.strip())
        executed_cmds.append(f"Project '{name.strip()}' created.")
        clean_reply = strip_tag(clean_reply, raw_tag)

    # 3. Create Event Tag
    # [ACTION: CREATE_EVENT | TITLE: text | START: YYYY-MM-DD HH:MM | END: YYYY-MM-DD HH:MM]
    event_pattern = r"\[?ACTION: CREATE_EVENT \| TITLE: ([^\|\]]+) \| START: ([^\|\]]+) \| END: ([^\|\]]+)\]?"
    for match in re.finditer(event_pattern, reply):
        raw_tag = match.group(0)
        title, start, end = match.groups()
        # Clean potential quotes from model output
        title = title.strip().strip('"').strip("'")
        await create_event.ainvoke({"title": title, "start_time": start.strip(), "end_time": end.strip()})
        executed_cmds.append(f"Event '{title}' scheduled.")
        clean_reply = strip_tag(clean_reply, raw_tag)

    # 5. Remind Tag
    # [ACTION: REMIND | MESSAGE: text | INTERVAL: minutes | DURATION: hours]
    remind_pattern = r"\[?ACTION: REMIND \| MESSAGE: ([^\|\]]+) \| INTERVAL: ([^\|\]]+) \| DURATION: ([^\|\]]+)\]?"
    for match in re.finditer(remind_pattern, reply):
        raw_tag = match.group(0)
        message, interval, duration = match.groups()
        try:
            res = await schedule_reminder.ainvoke({
                "message": message.strip(),
                "interval_minutes": int(interval.strip()),
                "duration_hours": int(duration.strip())
            })
            executed_cmds.append(res)
        except Exception as e:
            logger.error(f"Failed to schedule reminder: {e}")
        clean_reply = strip_tag(clean_reply, raw_tag)

    # 6. Persistent Custom Tag
    # [ACTION: SCHEDULE_CUSTOM | NAME: text | MESSAGE: text | TYPE: cron/interval | SPEC: text]
    custom_pattern = r"\[?ACTION: SCHEDULE_CUSTOM \| NAME: ([^\|\]]+) \| MESSAGE: ([^\|\]]+) \| TYPE: ([^\|\]]+) \| SPEC: ([^\|\]]+)\]?"
    for match in re.finditer(custom_pattern, reply):
        raw_tag = match.group(0)
        name, msg, ttype, spec = match.groups()
        try:
            res = await schedule_persistent_custom.ainvoke({
                "name": name.strip(),
                "message": msg.strip(),
                "job_type": ttype.strip().lower(),
                "spec": spec.strip()
            })
            executed_cmds.append(res)
        except Exception as e:
            logger.error(f"Failed to schedule persistent custom task: {e}")
        clean_reply = strip_tag(clean_reply, raw_tag)

    # 7. Add Person Tag
    # [ACTION: ADD_PERSON | NAME: text | RELATIONSHIP: text | CONTEXT: text | CIRCLE: inner/close]
    person_pattern = r"\[?ACTION: ADD_PERSON \| NAME: ([^\|\]]+) \| RELATIONSHIP: ([^\|\]]+) \| CONTEXT: ([^\|\]]+) \| CIRCLE: ([^\|\]]+)\]?"
    for match in re.finditer(person_pattern, reply):
        raw_tag = match.group(0)
        name, rel, ctx, circle = match.groups()
        from app.models.db import Person, AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            p = Person(name=name.strip(), relationship=rel.strip(), context=ctx.strip(), circle_type=circle.strip().lower())
            session.add(p)
            await session.commit()
        executed_cmds.append(f"Added {name.strip()} to your circle.")
        clean_reply = strip_tag(clean_reply, raw_tag)

    # 5. Learn Memory Tag
    # [ACTION: LEARN | TEXT: factual statement]
    learn_pattern = r"\[?ACTION: LEARN \| TEXT: ([^\]]+)\]?"
    for match in re.finditer(learn_pattern, reply):
        raw_tag = match.group(0)
        text = match.group(1)
        from app.services.memory import store_memory
        await store_memory(text.strip())
        executed_cmds.append("Memory updated.")
        clean_reply = strip_tag(clean_reply, raw_tag)

    # 6. Proximity Track Tag
    # [ACTION: PROXIMITY_TRACK | TASKS: item1; item2 | BREAKDOWN: task1 [ends 08:30]; task2 [ends 09:15] | END: YYYY-MM-DD HH:MM]
    prox_pattern = r"\[?ACTION: PROXIMITY_TRACK \| TASKS: ([^\|\]]+) \| BREAKDOWN: ([^\|\]]+) \| END: ([^\|\]]+)\]?"
    for match in re.finditer(prox_pattern, reply):
        raw_tag = match.group(0)
        tasks, breakdown, end_val = match.groups()
        from app.models.db import TrackingSession, AsyncSessionLocal
        import datetime, json
        async with AsyncSessionLocal() as session:
            # 1. Parse milestones
            milestones = []
            now = datetime.datetime.now()
            
            # Simple splitter for "task name [ends HH:MM]"
            items = [it.strip() for it in breakdown.split(';') if it.strip()]
            for it in items:
                try:
                    # Extract "task name" and "HH:MM"
                    parts = re.split(r'\s*\[ends\s+([^\]]+)\]', it)
                    if len(parts) >= 2:
                        task_name, due_val = parts[0], parts[1]
                        # Fix up HH:MM to absolute
                        h, m = map(int, due_val.strip().split(':'))
                        due_dt = now.replace(hour=h, minute=m, second=0, microsecond=0)
                        # Handle next-day rollover if needed (rare for short tracks)
                        if due_dt < now: due_dt += datetime.timedelta(days=1)
                        milestones.append({"task": task_name.strip(), "due_at": due_dt.isoformat(), "sent": False})
                except: continue

            try:
                # Handle YYYY-MM-DD HH:MM for overall END
                end_dt = datetime.datetime.strptime(end_val.strip(), "%Y-%m-%d %H:%M")
            except:
                # Fallback
                end_dt = datetime.datetime.utcnow() + datetime.timedelta(hours=2)
                
            session.add(TrackingSession(
                tasks=tasks.strip(), 
                milestones_json=json.dumps(milestones),
                end_time=end_dt
            ))
            await session.commit()
        executed_cmds.append("Precision Tracking initiated.")
        clean_reply = strip_tag(clean_reply, raw_tag)

    # --- FINAL AGGRESSIVE HYGIENE ---
    # This prevents 'leaking' of internal agent thoughts or malformed tags to the user.
    
    # 1. First Pass: Strip known bracketed action tags
    clean_reply = re.sub(r'\[?ACTION:\s*.*?\]', '', clean_reply, flags=re.IGNORECASE | re.DOTALL)
    
    # 2. Second Pass: Split into lines and filter out anything that looks like internal metadata
    lines = clean_reply.split('\n')
    filtered_lines = []
    
    # Markers that indicate a line is internal metadata/action logging
    # We catch these anywhere in the line now for maximum safety
    bad_tokens = ["ACTION:", "CONTEXT:", "MEMORY:", "UPDATE_CONTEXT", "TAGGED:", "MISSION:", "LEARN:"]
    
    for line in lines:
        trimmed = line.strip()
        if not trimmed:
            filtered_lines.append(line)
            continue
            
        # If any bad token exists in the line (case-insensitive)
        if any(token.upper() in trimmed.upper() for token in bad_tokens):
            continue
            
        # Skip lines that are purely symbols or brackets
        if re.match(r'^[\s\W\[\]\|]+$', trimmed):
            continue
            
        filtered_lines.append(line)
    
    clean_reply = "\n".join(filtered_lines).strip()

    # 3. Final Polish: Clean up hanging artifacts and excess whitespace
    clean_reply = re.sub(r'\]\s*$', '', clean_reply, flags=re.MULTILINE)
    clean_reply = re.sub(r'^\s*\|\s*', '', clean_reply, flags=re.MULTILINE)
    clean_reply = re.sub(r'\n{3,}', '\n\n', clean_reply).strip()
    
    return clean_reply, executed_cmds
