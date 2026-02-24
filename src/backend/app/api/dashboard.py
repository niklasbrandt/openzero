"""
Dashboard API Endpoints
-----------------------
This module defines the primary REST API for the openZero Dashboard.
It handles:
1. Project & Task management (via Planka integration)
2. Semantic memory search (via Qdrant)
3. Calendar & People context
4. AI Chat (Z Agent)
5. Operator mission control (Task centralization)

Core Philosophy: 
No complex frontend state. The backend serves as the source of truth for all 
integrations, allowing the Web Components to stay lightweight and fast.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from app.models.db import AsyncSessionLocal, Project, EmailRule, Briefing, Person
from app.services.memory import semantic_search
from app.services.planka import get_project_tree
from app.services.operator_board import operator_service
from app.services.llm import chat as llm_chat
from pydantic import BaseModel
from typing import List, Optional
import datetime
import httpx
from app.config import settings

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
    msg = req.message.strip()
    
    # Handle Slash Commands
    if msg == "/day":
        from app.tasks.morning import morning_briefing
        await morning_briefing()
        return {"reply": "✅ Daily briefing generated and saved to History."}
    elif msg == "/week":
        from app.tasks.weekly import weekly_review
        report = await weekly_review()
        return {"reply": report}
    elif msg == "/month":
        from app.tasks.monthly import monthly_review
        report = await monthly_review()
        return {"reply": report}
    elif msg == "/year":
        from app.tasks.yearly import yearly_review
        report = await yearly_review()
        return {"reply": report}
    elif msg == "/tree":
        # Life Tree Overview - combines projects, inner circle, and status
        from app.services.planka import get_project_tree
        tree = await get_project_tree(as_html=False)
        
        # 1. Inner Circle
        result = await db.execute(select(Person).where(Person.circle_type == "inner"))
        inner_circle = result.scalars().all()
        circle_text = "\n".join([f"• {p.name} ({p.relationship})" for p in inner_circle]) if inner_circle else "No direct connections added yet."
        
        # 2. Upcoming Calendar
        from app.services.calendar import fetch_calendar_events
        events = await fetch_calendar_events(max_results=3, days_ahead=3)
        if not events:
            # Check local events if google is empty
            from app.models.db import LocalEvent
            today = datetime.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            end = today + datetime.timedelta(days=3)
            res = await db.execute(select(LocalEvent).where(LocalEvent.start_time >= today, LocalEvent.start_time <= end))
            events = res.scalars().all()
            if events:
                event_list = "\n".join([f"• {e.summary} ({e.start_time.strftime('%a %H:%M')})" for e in events[:3]])
            else:
                event_list = "No upcoming events for the next 3 days."
        else:
            event_list = "\n".join([f"• {e.summary} ({datetime.datetime.fromisoformat(e['start'].replace('Z', '')).strftime('%a %H:%M')})" for e in events[:3]])

        life_tree = (
            "🌳 **Your Life Tree Overview**\n\n"
            "**Mission Control (Projects & Progress):**\n"
            f"{tree}\n\n"
            "**Inner Circle (People):**\n"
            f"{circle_text}\n\n"
            "**Timeline (Next 3 Days):**\n"
            f"{event_list}\n\n"
            "*\"Z: Stay focused. I've got the mental tabs from here.\"*"
        )
        return {"reply": life_tree}
    elif msg.startswith("/memory "):
        query = msg.replace("/memory", "").strip()
        results = await semantic_search(query)
        return {"reply": results}
    elif msg.startswith("/add "):
        topic = msg.replace("/add", "").strip()
        from app.services.memory import store_memory
        await store_memory(topic)
        return {"reply": f"✅ Stored to memory: {topic}"}
    
    # Use consolidated chat with context
    from app.services.llm import chat_with_context
    history = [{"role": m.role, "content": m.content} for m in req.history]
    
    try:
        reply = await chat_with_context(
            msg, 
            history=history,
            include_projects=True,
            include_people=True
        )
        
        from app.services.agent_actions import parse_and_execute_actions
        clean_reply, executed_cmds = await parse_and_execute_actions(reply, db=db)

        # Auto-store to memory for Deep Recall
        try:
            import asyncio
            from app.services.memory import store_memory
            asyncio.create_task(store_memory(f"Conversation ({datetime.datetime.now().strftime('%Y-%m-%d')}):\nUser: {msg}\nZ: {clean_reply}", metadata={"type": "chat"}))
        except Exception as me:
            print(f"DEBUG: Auto-memory failed: {me}")

        return {
            "reply": clean_reply,
            "actions": executed_cmds
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- Life Tree & Onboarding ---
@router.get("/calendar")
async def calendar_shortcut():
    """Shortcut to open calendar from URL."""
    return RedirectResponse(url="/?open=calendar")

@router.get("/life-tree")
async def get_life_tree(db: AsyncSession = Depends(get_db)):
    """Fetch the rich Life Tree overview for the dashboard widget."""
    from app.services.planka import get_project_tree
    tree = await get_project_tree(as_html=True)
    
    # 1. Social Circles
    res_inner = await db.execute(select(Person).where(Person.circle_type == "inner"))
    inner_circle = res_inner.scalars().all()
    
    res_close = await db.execute(select(Person).where(Person.circle_type == "close"))
    close_circle = res_close.scalars().all()
    
    social_data = {
        "inner": [{"name": p.name, "relationship": p.relationship} for p in inner_circle],
        "close": [{"name": p.name, "relationship": p.relationship} for p in close_circle]
    }
    
    # 2. Upcoming Calendar & Birthdays
    from app.services.calendar import fetch_calendar_events
    events = await fetch_calendar_events(max_results=5, days_ahead=7)
    formatted_events = []

    # Inject Birthdays from People table
    res_people = await db.execute(select(Person).where(Person.birthday.isnot(None)))
    all_people = res_people.scalars().all()
    now = datetime.datetime.now()
    
    for p in all_people:
        try:
            # Parse birthday (expected DD.MM.YY or DD.MM.YYYY or DD.MM)
            parts = p.birthday.split('.')
            if len(parts) >= 2:
                day = int(parts[0])
                month = int(parts[1])
                bday_this_year = datetime.datetime(now.year, month, day)
                
                # If it already passed this year, look at next year
                if bday_this_year < now.replace(hour=0, minute=0, second=0):
                    bday_this_year = datetime.datetime(now.year + 1, month, day)
                
                days_until = (bday_this_year - now.replace(hour=0, minute=0, second=0)).days
                if 0 <= days_until <= 7:
                    formatted_events.append({
                        "summary": f"🎂 {p.name}'s Birthday",
                        "time": bday_this_year.strftime('%a, %d %b'),
                        "is_local": True,
                        "sort_key": bday_this_year
                    })
        except Exception as be:
            print(f"Error parsing birthday for {p.name}: {be}")
    
    if not events:
        from app.models.db import LocalEvent
        today = datetime.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        end = today + datetime.timedelta(days=3)
        res = await db.execute(select(LocalEvent).where(LocalEvent.start_time >= today, LocalEvent.start_time <= end))
        local_events = res.scalars().all()
        for e in local_events:
            formatted_events.append({
                "summary": e.summary,
                "time": e.start_time.strftime('%a %H:%M'),
                "is_local": True
            })
    else:
        for e in events:
            # Handle date-only and date-time
            start_str = e['start']
            try:
                dt = datetime.datetime.fromisoformat(start_str.replace('Z', ''))
                time_fmt = dt.strftime('%a %H:%M')
                sort_key = dt
            except:
                time_fmt = start_str # Fallback
                sort_key = now + datetime.timedelta(days=10) # Push to end
                
            formatted_events.append({
                "summary": e['summary'],
                "time": time_fmt,
                "is_local": False,
                "sort_key": sort_key
            })

    # Sort all events by date
    formatted_events.sort(key=lambda x: x.get('sort_key', now))

    return {
        "projects_tree": tree,
        "social_circles": social_data,
        "timeline": formatted_events[:5]
    }

    # 0. Check if explicitly dismissed
    from app.models.db import Preference
    res_dismiss = await db.execute(select(Preference).where(Preference.key == "onboarding_dismissed"))
    dismissed = res_dismiss.scalar_one_or_none()
    is_dismissed = dismissed and dismissed.value == "true"
    
    # 1. Check if any people are added
    result = await db.execute(select(Person))
    people_count = len(result.scalars().all())
    
    # 2. Check if about-me.md has been modified
    import os
    about_me_path = "/app/personal/about-me.md"
    has_profile = False
    if os.path.exists(about_me_path):
        size = os.path.getsize(about_me_path)
        if size > 100:
            has_profile = True
    
    if not has_profile:
        from app.services.memory import semantic_search
        memories = await semantic_search("my identity and goals", top_k=3)
        if memories and "No memories found" not in memories:
            has_profile = True
            
    # 3. Check calendar sync
    from app.services.calendar import get_calendar_service
    from app.models.db import LocalEvent
    has_google = get_calendar_service() is not None
    
    result = await db.execute(select(LocalEvent))
    local_count = len(result.scalars().all())
    
    has_calendar = has_google or (local_count > 0)
    
    needs_onboarding = (not is_dismissed) and ((people_count == 0) or not has_profile or not has_calendar)
    
    return {
        "needs_onboarding": needs_onboarding,
        "base_url": settings.BASE_URL,
        "steps": {
            "inner_circle": people_count > 0,
            "profile": has_profile,
            "calendar": has_calendar
        }
    }

@router.post("/onboarding-dismiss")
async def dismiss_onboarding(db: AsyncSession = Depends(get_db)):
    """Persistently dismiss the onboarding hints."""
    from app.models.db import Preference
    stmt = select(Preference).where(Preference.key == "onboarding_dismissed")
    res = await db.execute(stmt)
    pref = res.scalar_one_or_none()
    if not pref:
        pref = Preference(key="onboarding_dismissed", value="true")
        db.add(pref)
    else:
        pref.value = "true"
    await db.commit()
    return {"status": "ok"}

# --- Projects ---
@router.get("/projects")
async def get_projects():
    # Implementing a simplified JSON tree for the dashboard
    tree = await get_project_tree()
    return {"tree": tree}

@router.get("/planka-redirect")
async def planka_redirect(request: Request, target: str = "", background: bool = False):
    """
    Planka Autologin Bridge
    -----------------------
    Ensures the user is authenticated on the correct origin (Port 1337).
    """
    # 1. Origin Check: Must be on Port 1337 to set LocalStorage for Planka.
    # If called from the dashboard (Port 80), redirect to Port 1337.
    host_header = request.headers.get("host", "localhost")
    forwarded_port = request.headers.get("x-forwarded-port")
    
    if forwarded_port:
        current_port = int(forwarded_port)
    else:
        host_parts = host_header.split(':')
        current_port = int(host_parts[1]) if len(host_parts) > 1 else (80 if request.url.scheme == "http" else 443)
    
    host_name = host_header.split(':')[0]
    
    if current_port != 1337:
        new_url = f"http://{host_name}:1337{request.url.path}"
        if request.query_params:
            new_url += f"?{str(request.query_params)}"
        return RedirectResponse(url=new_url)

    # 2. Authenticate
    login_url = f"{settings.PLANKA_BASE_URL}/api/access-tokens?withHttpOnlyToken=true"
    payload = {
        "emailOrUsername": settings.PLANKA_ADMIN_EMAIL,
        "password": settings.PLANKA_ADMIN_PASSWORD
    }
    
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(login_url, json=payload, timeout=5.0)
            token_data = resp.json()
            cookie_val = resp.cookies.get("httpOnlyToken")
            access_token = token_data.get("item")
            
            if not access_token:
                raise Exception("Auth failed - no token")

            # 2.5 Fetch user ID (Planka's frontend often needs both token and userId in LocalStorage)
            user_id = None
            try:
                me_resp = await client.get(f"{settings.PLANKA_BASE_URL}/api/users/me", headers={"Authorization": f"Bearer {access_token}"})
                if me_resp.status_code == 200:
                    user_id = me_resp.json().get("id")
            except Exception as e:
                print(f"DEBUG: Could not fetch userId: {e}")

            # 3. Determine Redirect URL
            scheme = request.url.scheme
            planka_root = f"{scheme}://{host_name}:1337"
            redirect_url = f"{planka_root}/"
            target_board_id = request.query_params.get("target_board_id")
            target_project_id = request.query_params.get("target_project_id")
            
            if target_board_id:
                redirect_url = f"{planka_root}/boards/{target_board_id}"
            elif target_project_id:
                redirect_url = f"{planka_root}/projects/{target_project_id}"
            elif target == "operator":
                headers = {"Authorization": f"Bearer {access_token}"}
                proj_resp = await client.get(f"{settings.PLANKA_BASE_URL}/api/projects", headers=headers)
                items = proj_resp.json().get("items", [])
                project = next((p for p in items if p["name"].lower() == "openzero"), None)
                if project:
                    detail_resp = await client.get(f"{settings.PLANKA_BASE_URL}/api/projects/{project['id']}", headers=headers)
                    detail = detail_resp.json()
                    board = next((b for b in detail.get("included", {}).get("boards", []) if b["name"].lower() == "operator board"), None)
                    if board:
                        redirect_url = f"{planka_root}/boards/{board['id']}"

            # 4. Serve Bridge HTML
            js_redirect = "" if background else f"setTimeout(() => {{ window.location.replace('{redirect_url}'); }}, 500);"
            
            from fastapi.responses import HTMLResponse
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>openZero SSO</title>
                <script>
                    function setupSession() {{
                        try {{
                            const token = "{access_token}";
                            console.log("SSO: Setting tokens...");
                            
                            // 1. LocalStorage - Primary for Planka frontend
                            localStorage.setItem('accessToken', token);
                            localStorage.setItem('token', token);
                            const userId = "{user_id}";
                            if (userId && userId !== "None") {{
                                localStorage.setItem('userId', userId);
                            }}
                            
                            // 2. Document Cookies - Fallback for some API calls
                            const expiry = "; max-age=31536000; path=/; SameSite=Lax";
                            document.cookie = "accessToken=" + token + expiry;
                            document.cookie = "token=" + token + expiry;
                            
                            console.log("SSO: Success. Redirecting to {redirect_url}...");
                            {js_redirect}
                        }} catch (e) {{ 
                            console.error('SSO Error:', e);
                            document.getElementById('status').innerText = 'Error setting session. Please try again.';
                            document.getElementById('retry').style.display = 'block';
                        }}
                    }}
                    window.onload = setupSession;
                </script>
            </head>
            <body style="background: #0f172a; color: white; font-family: -apple-system, system-ui, sans-serif; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0;">
                <div style="text-align: center; max-width: 400px; padding: 2rem; background: #1e293b; border-radius: 12px; box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1);">
                    <div style="margin-bottom: 1.5rem;">
                        <svg style="width: 48px; height: 48px; color: #38bdf8;" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"></path>
                        </svg>
                    </div>
                    <h2 style="margin: 0 0 0.5rem 0; font-size: 1.25rem;">openZero SSO</h2>
                    <p id="status" style="color: #94a3b8; font-size: 0.875rem;">{ "Syncing session..." if background else "Connecting to your task board..." }</p>
                    <div id="retry" style="display: none; margin-top: 1rem;">
                        <a href="{redirect_url}" style="display: inline-block; padding: 0.5rem 1rem; background: #38bdf8; color: #0f172a; text-decoration: none; border-radius: 6px; font-weight: 600;">Continue to Planka</a>
                    </div>
                </div>
            </body>
            </html>
            """
            
            response = HTMLResponse(content=html_content)
            if cookie_val:
                response.set_cookie(
                    "httpOnlyToken", cookie_val, 
                    httponly=True, samesite="lax", path="/", 
                    max_age=31536000, secure=False
                )
            return response
            
        except Exception as e:
            print(f"DEBUG: Planka Auth Error: {e}")
            return RedirectResponse(url=settings.BASE_URL)

@router.post("/operator/sync")
async def sync_operator():
    """
    Operator Board Sync
    -------------------
    Centralizes tasks across all project boards.
    - Tasks with '!!' go to Today.
    - Tasks with '!' go to This Week.
    - Inbox cards move to Backlog.
    """
    result = await operator_service.sync_operator_tasks()
    return {"status": "success", "message": result}

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
async def get_briefings(limit: int = 10, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Briefing).order_by(Briefing.created_at.desc()).limit(limit))
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
    birthday: Optional[str] = None

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
        birthday=person.birthday
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
async def get_calendar(year: Optional[int] = None, month: Optional[int] = None, db: AsyncSession = Depends(get_db)):
    """Fetch user's primary calendar events (Google + Local) + Virtual Birthdays."""
    now = datetime.datetime.utcnow()
    
    # Calculate range: One month view based on year/month params, or 30 days ahead from now
    if year and month:
        start_date = datetime.datetime(year, month, 1)
        if month == 12:
            end_date = datetime.datetime(year + 1, 1, 1) - datetime.timedelta(seconds=1)
        else:
            end_date = datetime.datetime(year, month + 1, 1) - datetime.timedelta(seconds=1)
    else:
        # Default to a rolling 35-day window to cover current month view
        start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = start_date + datetime.timedelta(days=35)

    # 1. Fetch Google Events
    google_events = await fetch_calendar_events(
        calendar_id="primary", 
        max_results=100, 
        days_ahead=60 # Fetch a bit more to handle overlaps
    )
    
    # 2. Fetch Local Events from DB
    from app.models.db import LocalEvent
    result = await db.execute(
        select(LocalEvent).where(
            LocalEvent.start_time >= start_date - datetime.timedelta(days=7), # Buffer
            LocalEvent.start_time <= end_date + datetime.timedelta(days=7)
        )
    )
    local_events = result.scalars().all()
    
    # 3. Format Local Events
    formatted_local = []
    for e in local_events:
        formatted_local.append({
            "summary": e.summary,
            "start": e.start_time.isoformat() + "Z",
            "end": e.end_time.isoformat() + "Z",
            "is_local": True,
            "id": f"local_{e.id}"
        })

    # 4. Generate Virtual Birthdays
    result = await db.execute(select(Person))
    people = result.scalars().all()
    birthday_events = []
    
    for p in people:
        if p.birthday:
            # Flexible parsing for: DD.MM.YY, DD.MM.YYYY, MM-DD, YYYY-MM-DD
            import re
            match = re.search(r'(\d{1,4})[.-](\d{1,2})[.-](\d{1,4})', p.birthday)
            if not match:
                # Try just MM-DD or DD.MM
                match = re.search(r'(\d{1,2})[.-](\d{1,2})', p.birthday)
            
            if match:
                g = match.groups()
                try:
                    # Heuristic: 
                    # If 3 groups:
                    #   If g[0] > 31 -> YYYY-MM-DD
                    #   If g[2] > 31 -> DD-MM-YYYY or MM-DD-YYYY
                    # User style is DD.MM.YY (27.2.19)
                    if len(g) == 3:
                        v1, v2, v3 = int(g[0]), int(g[1]), int(g[2])
                        if v1 > 31: # YYYY-MM-DD
                            month, day = v2, v3
                        elif v1 <= 31 and v2 <= 12: # DD.MM.YYYY or DD.MM.YY
                            day, month = v1, v2
                        else: # Fallback
                            month, day = v1, v2
                    else:
                        # 2 groups: assume user style DD.MM
                        day, month = int(g[0]), int(g[1])
                    
                    # Generate for relevant years
                    for y in range(start_date.year, end_date.year + 1):
                        try:
                            # We treat birthdays as "local" dates by not forcing UTC Z if possible,
                            # but for the API consistency we'll use T00:00:00Z for all-day.
                            # Frontend should handle showing "All Day".
                            bday = datetime.datetime(y, month, day)
                            if start_date <= bday <= end_date:
                                birthday_events.append({
                                    "summary": f"🎂 {p.name}'s Birthday",
                                    "start": bday.isoformat(),
                                    "end": (bday + datetime.timedelta(days=1)).isoformat(),
                                    "is_local": True,
                                    "is_birthday": True,
                                    "person": p.name
                                })
                        except ValueError: continue
                except: continue

    all_events = google_events + formatted_local + birthday_events
    
    # 5. Enrich events with person info (for Google events)
    enriched_events = []
    for event in all_events:
        summary = event.get("summary", "")
        person_name = event.get("person") # Might be set by birthdays
        
        if not person_name:
            for p in people:
                if summary.startswith(f"{p.name}:"):
                    person_name = p.name
                    break
        
        enriched_events.append({
            **event,
            "person": person_name
        })
    
    # Sort by start time
    enriched_events.sort(key=lambda x: x["start"])
    
    return enriched_events

class LocalEventCreate(BaseModel):
    summary: str
    description: Optional[str] = ""
    start_time: datetime.datetime
    end_time: datetime.datetime

@router.post("/calendar/local")
async def create_local_event(event: LocalEventCreate, db: AsyncSession = Depends(get_db)):
    from app.models.db import LocalEvent
    db_event = LocalEvent(
        summary=event.summary,
        description=event.description,
        start_time=event.start_time,
        end_time=event.end_time
    )
    db.add(db_event)
    await db.commit()
    await db.refresh(db_event)
    return db_event

# --- System Status ---
@router.get("/system")
async def get_system_status():
    """Get system status and trigger an early LLM warmup."""
    from app.config import settings
    import asyncio
    
    provider = settings.LLM_PROVIDER.lower()
    model_name = "Unknown"
    
    if provider == "ollama":
        model_name = settings.OLLAMA_MODEL
        # Fire-and-forget an empty/dummy request to trick Ollama into loading the weights into memory
        asyncio.create_task(llm_chat("System boot ping.", system_override="Respond tightly: Online."))
    elif provider == "groq":
        model_name = "Cloud Engine"
    elif provider == "openai":
        model_name = "Cloud Engine"
        
    return {
        "status": "online",
        "llm_provider": provider,
        "llm_model": model_name
    }
