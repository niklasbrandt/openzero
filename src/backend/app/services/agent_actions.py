import re
import datetime
import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import settings
from app.services.planka import create_task, create_project, create_board, get_planka_auth_token

async def parse_and_execute_actions(reply: str, db: AsyncSession = None) -> (str, list):
    """
    Parses semantic action tags from a string and executes them.
    Returns (cleaned_reply, list_of_executed_action_types).
    """
    actions = re.findall(r'\[ACTION: (.*?)\]', reply)
    clean_reply = reply
    executed_cmds = []

    for action_str in actions:
        print(f"DEBUG: Detected semantic action: {action_str}")
        # Hide the action tag from the user
        clean_reply = clean_reply.replace(f"[ACTION: {action_str}]", "").strip()
        
        try:
            parts = {}
            for p in action_str.split('|'):
                if ':' in p:
                    key, val = p.split(':', 1)
                    parts[key.strip()] = val.strip()
            
            cmd = action_str.split('|')[0].strip()
            
            if cmd == "CREATE_TASK":
                success = await create_task(
                    board_name=parts.get("BOARD", "Operator Board"),
                    list_name=parts.get("LIST", "Today"),
                    title=parts.get("TITLE", "New Task")
                )
                if success:
                    executed_cmds.append("task")
            elif cmd == "CREATE_PROJECT":
                await create_project(
                    name=parts.get("NAME", "New Project"),
                    description=parts.get("DESCRIPTION", "")
                )
                executed_cmds.append("project")
            elif cmd == "CREATE_BOARD":
                project_id = parts.get("PROJECT_ID")
                project_name = parts.get("PROJECT", parts.get("BOARD"))
                if not project_id and project_name:
                    token = await get_planka_auth_token()
                    async with httpx.AsyncClient(base_url=settings.PLANKA_BASE_URL, headers={"Authorization": f"Bearer {token}"}) as client:
                        p_resp = await client.get("/api/projects")
                        match = next((p for p in p_resp.json().get("items", []) if p["name"].lower() == project_name.lower()), None)
                        if match: project_id = match["id"]
                
                if project_id:
                    await create_board(project_id=project_id, name=parts.get("NAME", "New Board"))
                    executed_cmds.append("board")
            elif cmd == "CREATE_EVENT" and db:
                from app.models.db import LocalEvent
                start_str = parts.get("START", datetime.datetime.utcnow().isoformat())
                end_str = parts.get("END", (datetime.datetime.fromisoformat(start_str.replace('Z','')) + datetime.timedelta(hours=1)).isoformat())
                db_event = LocalEvent(
                    summary=parts.get("TITLE", "New Event"), 
                    start_time=datetime.datetime.fromisoformat(start_str.replace('Z','')), 
                    end_time=datetime.datetime.fromisoformat(end_str.replace('Z',''))
                )
                db.add(db_event)
                await db.commit()
                executed_cmds.append("calendar")
            elif cmd == "ADD_PERSON" and db:
                from app.models.db import Person
                db_p = Person(
                    name=parts.get("NAME", "Unknown"),
                    relationship=parts.get("RELATIONSHIP", "Contact"),
                    context=parts.get("CONTEXT", ""),
                    circle_type=parts.get("CIRCLE", "inner").lower(),
                    birthday=parts.get("BIRTHDAY")
                )
                db.add(db_p)
                await db.commit()
                executed_cmds.append("people")
            elif cmd == "LEARN":
                from app.services.memory import store_memory
                await store_memory(parts.get("TEXT", "Empty memory"))
                executed_cmds.append("memory")

        except Exception as ae:
            print(f"ERROR: Action execution failed: {ae}")

    return clean_reply, executed_cmds
