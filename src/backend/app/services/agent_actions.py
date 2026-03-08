import re
import logging
from langchain_core.tools import tool
from typing import Optional

logger = logging.getLogger(__name__)

@tool
async def create_task(title: str, description: str = "", board_name: str = "Operator Board", list_name: str = "Today") -> str:
    """Create a task in a specific board and list."""
    from app.services.planka import create_task as planka_create_task
    path = await planka_create_task(
        board_name=board_name,
        list_name=list_name,
        title=title,
        description=description
    )
    if path:
        return f"Task '{title}' created in {path}."
    return f"Failed to create task '{title}'. Check Planka connection."

@tool
async def create_project(name: str, description: str = "") -> str:
    """Create a new project."""
    from app.services.planka import create_project as planka_create_project
    try:
        result = await planka_create_project(name=name, description=description)
        if result:
            return f"Project '{name}' created."
        return f"Failed to create project '{name}'."
    except Exception as _e:
        logger.error("create_project tool failed: %s", _e)
        return f"Failed to create project '{name}'."

@tool
async def create_event(title: str, start_time: str, end_time: Optional[str] = None) -> str:
    """Create a new calendar event."""
    from app.models.db import LocalEvent, AsyncSessionLocal
    from app.services.calendar import create_caldav_event
    import datetime
    
    # Validate and parse start datetime (M-A1)
    try:
        start_dt = datetime.datetime.fromisoformat(start_time.replace('Z', ''))
    except ValueError:
        return f"Error: invalid start date '{start_time}'. Use YYYY-MM-DDThh:mm or YYYY-MM-DD HH:MM format."
    try:
        end_dt = datetime.datetime.fromisoformat(end_time.replace('Z', '')) if end_time else start_dt + datetime.timedelta(hours=1)
    except ValueError:
        return f"Error: invalid end date '{end_time}'. Use YYYY-MM-DDThh:mm or YYYY-MM-DD HH:MM format."
    
    # 1. Sync to Private CalDAV if available
    await create_caldav_event(title, start_dt, end_dt)

    # 2. Local fallback/audit write
    async with AsyncSessionLocal() as db:
        event = LocalEvent(
            summary=title,
            start_time=start_dt,
            end_time=end_dt
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
    # --- Input validation (H-A1) ---
    if not (1 <= interval_minutes <= 10080):
        return "Error: interval_minutes must be between 1 and 10080 (max 1 week)."
    if duration_hours is not None and not (1 <= duration_hours <= 168):
        return "Error: duration_hours must be between 1 and 168 (max 1 week)."
    message = message[:500]

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
    # --- Input validation (H3) ---
    job_type = job_type.strip().lower()
    if job_type not in {"cron", "interval"}:
        return f"Error: job_type must be 'cron' or 'interval', got '{job_type}'."

    if job_type == "cron":
        fields = spec.strip().split()
        if len(fields) != 5 or not all(re.match(r'^[\d*/,\-]+$', f) for f in fields):
            return "Error: cron spec must be exactly 5 fields (e.g. '0 12 * * 1') using only digits, *, /, ,, -."
    elif job_type == "interval":
        allowed_keys = {"minutes", "hours", "days"}
        for part in spec.split(","):
            if "=" not in part:
                return f"Error: interval spec must be 'key=N' pairs (e.g. 'minutes=30'), got '{part.strip()}'."
            k, v = part.split("=", 1)
            if k.strip() not in allowed_keys:
                return f"Error: interval key must be one of {sorted(allowed_keys)}, got '{k.strip()}'."
            try:
                if int(v.strip()) < 1:
                    raise ValueError
            except ValueError:
                return f"Error: interval value must be a positive integer, got '{v.strip()}'."

    from app.models.db import AsyncSessionLocal, CustomTask
    from sqlalchemy import select, func as sa_func
    async with AsyncSessionLocal() as session:
        count_result = await session.execute(
            select(sa_func.count()).select_from(CustomTask).where(CustomTask.is_active.is_(True))
        )
        if count_result.scalar() >= 20:
            return "Error: maximum of 20 active custom tasks reached. Deactivate an existing task first."
        task = CustomTask(name=name[:100], message=message[:500], job_type=job_type, spec=spec)
        session.add(task)
        await session.commit()
    from app.tasks.scheduler import load_custom_tasks
    await load_custom_tasks()
    return f"Persistent custom task '{name}' created and scheduled."

@tool
async def move_card(card_title_fragment: str, destination_list: str, board_name: str = "") -> str:
	"""Move a Planka card to a different list/column by searching for it by name fragment."""
	from app.services.planka import move_card as planka_move_card
	success = await planka_move_card(
		card_title_fragment=card_title_fragment,
		destination_list=destination_list,
		board_name=board_name
	)
	if success:
		return f"Card '{card_title_fragment}' moved to '{destination_list}'."
	return f"Could not find card matching '{card_title_fragment}' to move."

AVAILABLE_TOOLS = [create_task, create_project, create_event, learn_memory, schedule_reminder, schedule_persistent_custom, move_card]

async def parse_and_execute_actions(reply: str, db=None):
    """
    Parses Semantic Action Tags from the AI reply and executes them.
    Robust fallback for both legacy [ACTION: ...] and modern tool-like strings.
    """
    from app.services.planka import create_task as planka_create_task
    from app.services.planka import create_project as planka_create_project
    from app.services.planka import create_board as planka_create_board
    from app.services.planka import create_list as planka_create_list
    from app.services.planka import move_card as planka_move_card
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
        path = await planka_create_task(board_name=board.strip(), list_name=llist.strip(), title=title.strip())
        if path:
            executed_cmds.append(f"Task '{title.strip()}' created in {path}.")
        else:
            executed_cmds.append(f"\u26a0 Failed to create task '{title.strip()}'. Check Planka connection.")
        clean_reply = strip_tag(clean_reply, raw_tag)

    # 2. Create Project Tag
    # [ACTION: CREATE_PROJECT | NAME: text | DESCRIPTION: text]
    proj_pattern = r"\[?ACTION: CREATE_PROJECT \| NAME: ([^\|\]]+) \| DESCRIPTION: ([^\|\]]+)\]?"
    for match in re.finditer(proj_pattern, reply):
        raw_tag = match.group(0)
        name, desc = match.groups()
        try:
            result = await planka_create_project(name=name.strip(), description=desc.strip())
            if result:
                executed_cmds.append(f"Project '{name.strip()}' created.")
            else:
                executed_cmds.append(f"\u26a0 Failed to create project '{name.strip()}'. Check Planka connection.")
        except Exception as _e:
            logger.error("CREATE_PROJECT failed: %s", _e)
            executed_cmds.append(f"\u26a0 Failed to create project '{name.strip()}'. Check Planka connection.")
        clean_reply = strip_tag(clean_reply, raw_tag)

    # 2b. Create Board Tag
    # [ACTION: CREATE_BOARD | PROJECT: name | NAME: text]
    board_pattern = r"\[?ACTION: CREATE_BOARD \| PROJECT: ([^\|\]]+) \| NAME: ([^\|\]]+)\]?"
    for match in re.finditer(board_pattern, reply):
        raw_tag = match.group(0)
        proj_name, board_name = match.groups()
        try:
            from app.services.planka import get_planka_auth_token
            import httpx
            from app.config import settings
            token = await get_planka_auth_token()
            async with httpx.AsyncClient(base_url=settings.PLANKA_BASE_URL, headers={"Authorization": f"Bearer {token}"}) as client:
                resp = await client.get("/api/projects")
                projects = resp.json().get("items", [])
                proj_id = None
                for p in projects:
                    if p["name"].lower() == proj_name.strip().lower():
                        proj_id = p["id"]
                        break
                if proj_id:
                    board_result = await planka_create_board(project_id=proj_id, name=board_name.strip())
                    if board_result:
                        executed_cmds.append(f"Board '{board_name.strip()}' created in '{proj_name.strip()}'.")
                    else:
                        executed_cmds.append(f"\u26a0 Failed to create board '{board_name.strip()}'. Check Planka.")
                else:
                    logger.warning("Project %r not found for CREATE_BOARD", proj_name.strip())
                    executed_cmds.append(f"\u26a0 Project '{proj_name.strip()}' not found. Board not created.")
        except Exception as _e:
            logger.error("CREATE_BOARD failed: %s", _e)
            executed_cmds.append(f"\u26a0 Failed to create board '{board_name.strip()}'. Check Planka connection.")
        clean_reply = strip_tag(clean_reply, raw_tag)

    # 2c. Create List (Column) Tag
    # [ACTION: CREATE_LIST | BOARD: name | NAME: text]
    list_pattern = r"\[?ACTION: CREATE_LIST \| BOARD: ([^\|\]]+) \| NAME: ([^\|\]]+)\]?"
    for match in re.finditer(list_pattern, reply):
        raw_tag = match.group(0)
        board_name, list_name = match.groups()
        try:
            result = await planka_create_list(board_name=board_name.strip(), list_name=list_name.strip())
            if result:
                executed_cmds.append(f"List '{list_name.strip()}' created in '{board_name.strip()}'.")
            else:
                executed_cmds.append(f"\u26a0 Failed to create list '{list_name.strip()}' — board '{board_name.strip()}' not found or Planka error.")
        except Exception as _e:
            logger.error("CREATE_LIST failed: %s", _e)
            executed_cmds.append(f"\u26a0 Failed to create list '{list_name.strip()}'. Check Planka connection.")
        clean_reply = strip_tag(clean_reply, raw_tag)

    # 3. Create Event Tag
    # [ACTION: CREATE_EVENT | TITLE: text | START: YYYY-MM-DD HH:MM | END: YYYY-MM-DD HH:MM]
    event_pattern = r"\[?ACTION: CREATE_EVENT \| TITLE: ([^\|\]]+) \| START: ([^\|\]]+) \| END: ([^\|\]]+)\]?"
    for match in re.finditer(event_pattern, reply):
        raw_tag = match.group(0)
        title, start, end = match.groups()
        # Clean potential quotes from model output
        title = title.strip().strip('"').strip("'")
        try:
            event_result = await create_event.ainvoke({"title": title, "start_time": start.strip(), "end_time": end.strip()})
            # The tool returns an error string starting with "Error:" on failure
            if isinstance(event_result, str) and event_result.lower().startswith("error"):
                executed_cmds.append(f"\u26a0 Event '{title}' not created: {event_result}")
            else:
                executed_cmds.append(f"Event '{title}' scheduled.")
        except Exception as _e:
            logger.error("CREATE_EVENT failed: %s", _e)
            executed_cmds.append(f"\u26a0 Failed to create event '{title}'. Check calendar configuration.")
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
            if isinstance(res, str) and res.lower().startswith("error"):
                executed_cmds.append(f"\u26a0 Reminder not set: {res}")
            else:
                executed_cmds.append(res)
        except Exception as _e:
            logger.error("REMIND failed: %s", _e)
            executed_cmds.append(f"\u26a0 Failed to schedule reminder '{message.strip()[:60]}'. Check scheduler.")
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
            if isinstance(res, str) and res.lower().startswith("error"):
                executed_cmds.append(f"\u26a0 Custom task not scheduled: {res}")
            else:
                executed_cmds.append(res)
        except Exception as _e:
            logger.error("SCHEDULE_CUSTOM failed: %s", _e)
            executed_cmds.append(f"\u26a0 Failed to schedule custom task '{name.strip()[:60]}'. Check scheduler.")
        clean_reply = strip_tag(clean_reply, raw_tag)

    # 7. Add Person Tag
    # [ACTION: ADD_PERSON | NAME: text | RELATIONSHIP: text | CONTEXT: text | CIRCLE: inner/close]
    person_pattern = r"\[?ACTION: ADD_PERSON \| NAME: ([^\|\]]+) \| RELATIONSHIP: ([^\|\]]+) \| CONTEXT: ([^\|\]]+) \| CIRCLE: ([^\|\]]+)\]?"
    for match in re.finditer(person_pattern, reply):
        raw_tag = match.group(0)
        name, rel, ctx, circle = match.groups()
        try:
            from app.models.db import Person, AsyncSessionLocal
            # --- Input validation (M-A2) ---
            circle_clean = circle.strip().lower()
            if circle_clean not in {"inner", "close", "outer", "identity"}:
                circle_clean = "outer"
            name_clean = name.strip()[:100]
            rel_clean = rel.strip()[:100]
            ctx_clean = ctx.strip()[:1000]
            async with AsyncSessionLocal() as session:
                p = Person(name=name_clean, relationship=rel_clean, context=ctx_clean, circle_type=circle_clean)
                session.add(p)
                await session.commit()
            executed_cmds.append(f"Added {name_clean} to your circle.")
        except Exception as _e:
            logger.error("ADD_PERSON failed: %s", _e)
            executed_cmds.append(f"\u26a0 Failed to add '{name.strip()[:60]}' to circle. Check database.")
        clean_reply = strip_tag(clean_reply, raw_tag)

    # 5. Learn Memory Tag
    # [ACTION: LEARN | TEXT: factual statement]
    learn_pattern = r"\[?ACTION: LEARN \| TEXT: ([^\]]+)\]?"
    for match in re.finditer(learn_pattern, reply):
        raw_tag = match.group(0)
        text = match.group(1)
        try:
            from app.services.memory import store_memory
            await store_memory(text.strip())
            # store_memory returns None; it only raises on Qdrant/embed failure
            # (noise-filtered inputs are silently dropped — that is expected behaviour)
            executed_cmds.append("Memory updated.")
        except Exception as _e:
            logger.error("LEARN failed: %s", _e)
            executed_cmds.append("\u26a0 Failed to store memory. Check Qdrant connection.")
        clean_reply = strip_tag(clean_reply, raw_tag)

    # 6. Proximity Track Tag
    # [ACTION: PROXIMITY_TRACK | TASKS: item1; item2 | BREAKDOWN: task1 [ends 08:30]; task2 [ends 09:15] | END: YYYY-MM-DD HH:MM]
    prox_pattern = r"\[?ACTION: PROXIMITY_TRACK \| TASKS: ([^\|\]]+) \| BREAKDOWN: ([^\|\]]+) \| END: ([^\|\]]+)\]?"
    for match in re.finditer(prox_pattern, reply):
        raw_tag = match.group(0)
        tasks, breakdown, end_val = match.groups()
        try:
            from app.models.db import TrackingSession, AsyncSessionLocal
            import datetime
            import json
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
                    except (ValueError, AttributeError): continue  # malformed HH:MM -- skip milestone

                try:
                    # Handle YYYY-MM-DD HH:MM for overall END
                    end_dt = datetime.datetime.strptime(end_val.strip(), "%Y-%m-%d %H:%M")
                except ValueError:
                    # Fallback
                    end_dt = datetime.datetime.utcnow() + datetime.timedelta(hours=2)

                session.add(TrackingSession(
                    tasks=tasks.strip(),
                    milestones_json=json.dumps(milestones),
                    end_time=end_dt
                ))
                await session.commit()
            executed_cmds.append("Precision Tracking initiated.")
        except Exception as _e:
            logger.error("PROXIMITY_TRACK failed: %s", _e)
            executed_cmds.append("\u26a0 Failed to initiate Precision Tracking. Check database.")
        clean_reply = strip_tag(clean_reply, raw_tag)

    # 9. Move Card Tag
    # [ACTION: MOVE_CARD | CARD: title fragment | LIST: destination list | BOARD: board name (optional)]
    move_card_pattern = r"\[?ACTION: MOVE_CARD \| CARD: ([^\|\]]+) \| LIST: ([^\|\]]+)(?: \| BOARD: ([^\|\]]+))?\]?"
    for match in re.finditer(move_card_pattern, reply):
        raw_tag = match.group(0)
        card_frag = match.group(1).strip()
        dest_list = match.group(2).strip()
        board = (match.group(3) or "").strip()
        success = await planka_move_card(card_title_fragment=card_frag, destination_list=dest_list, board_name=board)
        if success:
            executed_cmds.append(f"Card '{card_frag}' moved to '{dest_list}'.")
        else:
            executed_cmds.append(f"\u26a0 Could not find card matching '{card_frag}'. Check Planka board.")
        clean_reply = strip_tag(clean_reply, raw_tag)

    # 10. Mark Done Tag (shortcut: moves card to Done list)
    # [ACTION: MARK_DONE | CARD: title fragment]
    mark_done_pattern = r"\[?ACTION: MARK_DONE \| CARD: ([^\|\]]+)\]?"
    for match in re.finditer(mark_done_pattern, reply):
        raw_tag = match.group(0)
        card_frag = match.group(1).strip()
        success = await planka_move_card(card_title_fragment=card_frag, destination_list="Done", board_name="")
        if success:
            executed_cmds.append(f"Card '{card_frag}' marked done.")
        else:
            executed_cmds.append(f"\u26a0 Could not find card matching '{card_frag}'. Check Planka board.")
        clean_reply = strip_tag(clean_reply, raw_tag)

    # 8. Set Nudge Interval Tag
    # [ACTION: SET_NUDGE_INTERVAL | TASK: text | INTERVAL: minutes]
    nudge_interval_pattern = r"\[?ACTION: SET_NUDGE_INTERVAL \| TASK: ([^\|\]]+) \| INTERVAL: ([^\|\]]+)\]?"
    for match in re.finditer(nudge_interval_pattern, reply):
        raw_tag = match.group(0)
        task_fragment, interval_raw = match.groups()
        try:
            minutes = int(interval_raw.strip())
            if minutes < 1:
                raise ValueError("interval must be >= 1")
            from app.services.follow_up import set_nudge_override
            set_nudge_override(task_fragment.strip(), minutes)
            executed_cmds.append(f"Nudge interval for '{task_fragment.strip()}' set to {minutes} min.")
        except ValueError as _ve:
            logger.warning("SET_NUDGE_INTERVAL parse error: %s", _ve)
            executed_cmds.append(f"\u26a0 Could not set nudge interval for '{task_fragment.strip()[:60]}'. Invalid interval value.")
        except Exception as _e:
            logger.error("SET_NUDGE_INTERVAL failed: %s", _e)
            executed_cmds.append(f"\u26a0 Failed to set nudge interval for '{task_fragment.strip()[:60]}'. Check scheduler.")
        clean_reply = strip_tag(clean_reply, raw_tag)

    # --- FINAL AGGRESSIVE HYGIENE ---
    # This prevents 'leaking' of internal agent thoughts or malformed tags to the user.
    
    # 1. First Pass: Strip known bracketed action tags
    # Use [^\]] to avoid polynomial backtracking on adversarial input.
    clean_reply = re.sub(r'\[?ACTION:[^\]]*\]?', '', clean_reply, flags=re.IGNORECASE)
    
    # 2. Second Pass: Split into lines and filter out anything that looks like internal metadata
    lines = clean_reply.split('\n')
    filtered_lines = []
    
    # Markers that indicate a line is internal metadata/action logging
    # We catch these anywhere in the line now for maximum safety
    bad_tokens = ["ACTION:", "CONTEXT:", "MEMORY:", "UPDATE_CONTEXT", "TAGGED:", "MISSION:", "LEARN", "ADD_FACT"]
    
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

    # If execution produced any failure notices (⚠), surface them even when the
    # LLM already wrote a success-sounding reply (prevents silent false-confirms).
    # This must run BEFORE the empty-reply fallback so failures aren't duplicated.
    failure_notices = [c for c in executed_cmds if c.startswith("\u26a0")]
    if failure_notices and clean_reply:
        clean_reply = clean_reply.rstrip() + "\n\n" + "\n".join(failure_notices)

    # If the LLM response contained ONLY tags (all stripped → empty), fall back to
    # a summary of what was executed.  Because executed_cmds already contains the
    # ⚠ notices we must NOT append them again — just join everything once.
    if not clean_reply and executed_cmds:
        clean_reply = "\n".join(executed_cmds)

    return clean_reply, executed_cmds
