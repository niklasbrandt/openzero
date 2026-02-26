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

async def get_db():
	async with AsyncSessionLocal() as session:
		yield session

def parse_birthday(bday_str: str):
	"""Unified birthday parser supporting: DD.MM.YY, YYYY-MM-DD, DD.MM, etc."""
	if not bday_str: return None
	import re
	# Try YYYY-MM-DD first
	match = re.search(r'(\d{4})[.-](\d{1,2})[.-](\d{1,2})', bday_str)
	if match:
		return int(match.group(2)), int(match.group(3)) # month, day
	
	# Try DD.MM.YY or DD.MM
	match = re.search(r'(\d{1,2})[.-](\d{1,2})', bday_str)
	if match:
		v1, v2 = int(match.group(1)), int(match.group(2))
		# Prioritize DD.MM if v1 <= 31 and v2 <= 12
		if v1 <= 31 and v2 <= 12:
			return v2, v1 # month, day
		# Fallback to MM.DD if v2 > 12
		elif v1 <= 12 and v2 > 12:
			return v1, v2
	return None

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
		
		# 2. Upcoming Timeline (Calendar + Birthdays + Local Events)
		from app.services.calendar import fetch_calendar_events
		from app.models.db import LocalEvent
		
		timeline_events = []
		now = datetime.datetime.now()
		today = now.replace(hour=0, minute=0, second=0, microsecond=0)
		end_limit = today + datetime.timedelta(days=3)
		
		# A. Google Events
		try:
			g_events = await fetch_calendar_events(max_results=5, days_ahead=3)
			for e in g_events:
				try:
					dt = datetime.datetime.fromisoformat(e['start'].replace('Z', ''))
					timeline_events.append({
						"summary": e['summary'],
						"time": dt.strftime('%a %H:%M'),
						"sort_key": dt
					})
				except: pass
		except: pass
		
		# B. Local Events
		res_local = await db.execute(select(LocalEvent).where(LocalEvent.start_time >= today, LocalEvent.start_time <= end_limit))
		for e in res_local.scalars().all():
			timeline_events.append({
				"summary": e.summary,
				"time": e.start_time.strftime('%a %H:%M'),
				"sort_key": e.start_time
			})
			
		# C. Birthdays
		res_people = await db.execute(select(Person).where(Person.birthday.isnot(None)))
		for p in res_people.scalars().all():
			parsed = parse_birthday(p.birthday)
			if parsed:
				month, day = parsed
				try:
					bday_this_year = datetime.datetime(now.year, month, day)
					if bday_this_year < today:
						bday_this_year = datetime.datetime(now.year + 1, month, day)
					
					if today <= bday_this_year <= end_limit:
						timeline_events.append({
							"summary": f"🎂 {p.name}'s Birthday",
							"time": bday_this_year.strftime('%a, %d %b'),
							"sort_key": bday_this_year
						})
				except: pass

		timeline_events.sort(key=lambda x: x["sort_key"])
		event_list = "\n".join([f"• {e['summary']} ({e['time']})" for e in timeline_events[:5]])
		if not event_list:
			event_list = "No upcoming events for the next 3 days."

		life_tree = (
			"🌳 **Boards**\n\n"
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

		# Auto-store USER part only to memory for Deep Recall
		try:
			import asyncio
			from app.services.memory import store_memory
			# Store ONLY user message to reduce noise from AI responses/formatting
			asyncio.create_task(store_memory(f"User Perspective ({datetime.datetime.now().strftime('%Y-%m-%d')}): {msg}", metadata={"type": "user_input"}))
		except Exception as me:
			print(f"DEBUG: Auto-memory failed: {me}")

		from app.services.llm import last_model_used
		return {
			"reply": clean_reply,
			"actions": executed_cmds,
			"model": last_model_used.get()
		}
	except Exception as e:
		raise HTTPException(status_code=500, detail=str(e))

# --- Life Tree & Onboarding ---
# Handle by main.py /calendar

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
	try:
		events = await fetch_calendar_events(max_results=5, days_ahead=7)
	except Exception as ce:
		print(f"Calendar fetch failed: {ce}")
		events = []
	formatted_events = []

	# Inject Birthdays from People table
	res_people = await db.execute(select(Person).where(Person.birthday.isnot(None)))
	all_people = res_people.scalars().all()
	now = datetime.datetime.now()
	
	for p in all_people:
		parsed = parse_birthday(p.birthday)
		if parsed:
			month, day = parsed
			try:
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
				print(f"Error creating birthday event for {p.name}: {be}")
	
	# 3. Add Google Events
	for e in events:
		# Handle date-only (2024-01-01) and date-time (2024-01-01T12:00:00Z)
		start_str = e['start']
		try:
			dt = datetime.datetime.fromisoformat(start_str.replace('Z', ''))
			time_fmt = dt.strftime('%a %H:%M')
			sort_key = dt
		except:
			# Fallback for unexpected formats
			time_fmt = start_str
			sort_key = now + datetime.timedelta(days=10) # Push to end
			
		formatted_events.append({
			"summary": e['summary'],
			"time": time_fmt,
			"is_local": False,
			"sort_key": sort_key
		})

	# 4. Add Local Events
	from app.models.db import LocalEvent
	today = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
	end_limit = today + datetime.timedelta(days=3)
	res = await db.execute(select(LocalEvent).where(LocalEvent.start_time >= today, LocalEvent.start_time <= end_limit))
	local_events = res.scalars().all()
	for e in local_events:
		formatted_events.append({
			"summary": e.summary,
			"time": e.start_time.strftime('%a %H:%M'),
			"is_local": True,
			"sort_key": e.start_time
		})

	# Sort all events (Birthdays, Google, Local) by the original datetime object
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
	Ensures the user is authenticated on the correct origin and sets session tokens.
	"""
	# 1. Origin Normalization
	# We MUST be on the public BASE_URL origin for localStorage/cookies to work for Planka.
	public_base = settings.BASE_URL.rstrip('/')
	current_url = str(request.url)
	
	# If we are not on the public base URL, redirect the browser there first.
	if not current_url.startswith(public_base) and "localhost" not in current_url:
		new_url = f"{public_base}/api/dashboard/planka-redirect"
		if request.query_params:
			new_url += f"?{str(request.query_params)}"
		return RedirectResponse(url=new_url)

	# 2. Authenticate Backend-to-Backend
	login_url = f"{settings.PLANKA_BASE_URL}/api/access-tokens?withHttpOnlyToken=true"
	payload = {
		"emailOrUsername": settings.PLANKA_ADMIN_EMAIL,
		"password": settings.PLANKA_ADMIN_PASSWORD
	}
	
	async with httpx.AsyncClient(timeout=10.0) as client:
		try:
			resp = await client.post(login_url, json=payload)
			resp.raise_for_status()
			token_data = resp.json()
			access_token = token_data.get("item")
			cookie_val = resp.cookies.get("httpOnlyToken")
			
			if not access_token:
				raise Exception("Failed to retrieve access token from Planka")

			# 3. Fetch User ID for LocalStorage enrichment
			user_id = "None"
			try:
				me_resp = await client.get(
					f"{settings.PLANKA_BASE_URL}/api/users/me", 
					headers={"Authorization": f"Bearer {access_token}"}
				)
				if me_resp.status_code == 200:
					user_id = me_resp.json().get("id", "None")
			except Exception as e:
				print(f"DEBUG: Could not fetch userId: {e}")

			# 4. Determine Target Redirect URL
			# CRITICAL: We redirect to Planka paths, NOT / (which is the dashboard).
			target_board_id = request.query_params.get("target_board_id") or request.query_params.get("targetboardid")
			target_project_id = request.query_params.get("target_project_id") or request.query_params.get("targetprojectid")
			
			if target_board_id:
				redirect_url = f"{public_base}/boards/{target_board_id}"
			elif target_project_id:
				redirect_url = f"{public_base}/projects/{target_project_id}"
			else:
				# Find the 'openZero' (aka Boards) project ID for the default landing
				headers = {"Authorization": f"Bearer {access_token}"}
				proj_resp = await client.get(f"{settings.PLANKA_BASE_URL}/api/projects", headers=headers)
				projects = proj_resp.json().get("items", [])
				oz_proj = next((p for p in projects if p["name"].lower() == "openzero"), None)
				
				if target == "operator" and oz_proj:
					det_resp = await client.get(f"{settings.PLANKA_BASE_URL}/api/projects/{oz_proj['id']}", headers=headers)
					boards = det_resp.json().get("included", {}).get("boards", [])
					op_board = next((b for b in boards if b["name"].lower() == "operator board"), None)
					if op_board:
						redirect_url = f"{public_base}/boards/{op_board['id']}"
					else:
						redirect_url = f"{public_base}/projects/{oz_proj['id']}"
				elif oz_proj:
					# Landing on the 'Boards' overview
					redirect_url = f"{public_base}/projects/{oz_proj['id']}"
				else:
					redirect_url = f"{public_base}/projects"

			# 5. Build Bridge HTML
			from fastapi.responses import HTMLResponse
			html_content = f"""
			<!DOCTYPE html>
			<html>
			<head>
				<title>openZero SSO</title>
				<script>
					async function setupSession() {{
						try {{
							const token = "{access_token}";
							const userId = "{user_id}";
							const email = "{settings.PLANKA_ADMIN_EMAIL}";
							const password = "{settings.PLANKA_ADMIN_PASSWORD}";
							console.log("SSO: Initiating autologin for " + email);
							
							// 1. Sync Storage
							localStorage.setItem('accessToken', token);
							localStorage.setItem('token', token);
							if (userId && userId !== "None") {{
								localStorage.setItem('userId', userId);
							}}
							
							// 2. The "Mask Submitter" (User Requested)
							// Deep-Sim filling for React-based forms
							const iframe = document.createElement('iframe');
							iframe.src = '/login';
							iframe.style.width = '1px';
							iframe.style.height = '1px';
							iframe.style.border = 'none';
							iframe.style.position = 'absolute';
							iframe.style.visibility = 'hidden';
							document.body.appendChild(iframe);
							
							let attempt = 0;
							const maxAttempts = 30; // Try for 6 seconds
							
							const checkIframe = setInterval(() => {{
								attempt++;
								try {{
									const doc = iframe.contentDocument || iframe.contentWindow.document;
									if (!doc) return;
									
									const emailField = doc.querySelector('input[name="emailOrUsername"]');
									const passField = doc.querySelector('input[name="password"]');
									const btn = doc.querySelector('button.ui.primary.button');
									
									if (emailField && passField && btn) {{
										clearInterval(checkIframe);
										console.log("SSO: Mask detected. Simulating human input...");
										
										// Native Setter Bypass for React
										const setReactValue = (el, val) => {{
											const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
											setter.call(el, val);
											el.dispatchEvent(new Event('input', {{ bubbles: true }}));
											el.dispatchEvent(new Event('change', {{ bubbles: true }}));
											el.dispatchEvent(new Event('blur', {{ bubbles: true }}));
										}};

										setReactValue(emailField, email);
										setReactValue(passField, password);
										
										// Short delay to let React process events
										setTimeout(() => {{
											console.log("SSO: Triggering submission...");
											btn.click();
											// Monitor for redirect
											setTimeout(() => {{ window.location.replace('{redirect_url}'); }}, 2000);
										}}, 600);
										
									}} else if (doc.location.pathname.includes('/projects') || doc.location.pathname.includes('/boards')) {{
										clearInterval(checkIframe);
										console.log("SSO: Session already active in bridge. Redirecting...");
										window.location.replace('{redirect_url}');
									}} else if (attempt > maxAttempts) {{
										clearInterval(checkIframe);
										console.log("SSO: Polling timeout. Proceeding to destination...");
										window.location.replace('{redirect_url}');
									}}
								}} catch (err) {{
									if (attempt > maxAttempts) {{
										clearInterval(checkIframe);
										window.location.replace('{redirect_url}');
									}}
								}}
							}}, 200);
							
							// 3. Cookie Synchronization (Legacy/Redundancy)
							const expiry = "; max-age=31536000; path=/; SameSite=Lax";
							document.cookie = "accessToken=" + token + expiry;
							document.cookie = "token=" + token + expiry;
							
						}} catch (e) {{ 
							console.error('SSO Error:', e);
							window.location.replace('{redirect_url}');
						}}
					}}
					window.onload = setupSession;
				</script>
			</head>
			<body style="background: #0f172a; color: white; font-family: sans-serif; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0;">
				<div style="text-align: center; max-width: 400px; padding: 2rem; background: #1e293b; border-radius: 12px;">
					<h2 id="status" style="margin-bottom: 0.5rem;">Connecting...</h2>
					<p style="color: #94a3b8; font-size: 0.875rem;">Initializing your secure session for Planka.</p>
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
			return RedirectResponse(url=f"{public_base}/projects")


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

@router.post("/morning-briefing")
async def trigger_morning_briefing():
	"""Manually trigger the morning briefing generation."""
	from app.tasks.morning import morning_briefing
	content = await morning_briefing()
	return {"status": "success", "content": content}

@router.post("/follow-up")
async def trigger_follow_up():
	"""Manually trigger the proactive follow-up nudge."""
	from app.services.follow_up import run_proactive_follow_up
	await run_proactive_follow_up()
	return {"status": "success"}

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
async def search_memory(query: str, db: AsyncSession = Depends(get_db)):
	if not query:
		return {"results": []}
	
	# 1. Semantic Search (Qdrant)
	try:
		semantic_results = await semantic_search(query)
		semantic_lines = semantic_results.split("\n")
	except:
		semantic_lines = []

	final_hits = []

	# 2. People DB Search
	res_people = await db.execute(select(Person).where(Person.name.ilike(f"%{query}%")))
	people = res_people.scalars().all()
	for p in people:
		final_hits.append(f"👤 PERSONAL PROFILE: {p.name} ({p.relationship}) - {p.context[:150]}...")

	# 3. Project Search (Placeholder or direct DB)
	# If Planka is used, this might be partial, but let's check local if any
	from app.models.db import Project
	res_proj = await db.execute(select(Project).where(Project.name.ilike(f"%{query}%")))
	projs = res_proj.scalars().all()
	for prj in projs:
		final_hits.append(f"🌳 MISSION: {prj.name} (Status: {prj.status})")

	# Merge semantic lines (cleaning out scores/formatting if possible)
	for line in semantic_lines:
		if line.strip() and "No memories found" not in line and "Memory system not" not in line:
			# Strip the index "1. (score: 0.90)"
			clean_line = line.split(")", 1)[-1].strip() if ")" in line else line
			final_hits.append(f"🧠 RECALL: {clean_line}")

	# Return top 15 results
	return {"results": final_hits[:15]}

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
	badge: Optional[str] = None

@router.get("/email-rules")
async def get_email_rules(db: AsyncSession = Depends(get_db)):
	result = await db.execute(select(EmailRule))
	return result.scalars().all()

@router.post("/email-rules")
async def create_email_rule(rule: EmailRuleCreate, db: AsyncSession = Depends(get_db)):
	db_rule = EmailRule(sender_pattern=rule.sender_pattern, action=rule.action, badge=rule.badge)
	db.add(db_rule)
	await db.commit()
	await db.refresh(db_rule)
	return db_rule

@router.delete("/email-rules/{rule_id}")
async def delete_email_rule(rule_id: int, db: AsyncSession = Depends(get_db)):
	await db.execute(delete(EmailRule).where(EmailRule.id == rule_id))
	await db.commit()
	return {"status": "deleted"}

@router.put("/email-rules/{rule_id}")
async def update_email_rule(rule_id: int, rule: EmailRuleCreate, db: AsyncSession = Depends(get_db)):
	res = await db.execute(select(EmailRule).where(EmailRule.id == rule_id))
	db_rule = res.scalar_one_or_none()
	if not db_rule: raise HTTPException(status_code=404, detail="Not found")
	db_rule.sender_pattern = rule.sender_pattern
	db_rule.action = rule.action
	db_rule.badge = rule.badge
	await db.commit()
	await db.refresh(db_rule)
	return db_rule

# --- People (Inner/Close Circle) ---
class PersonCreate(BaseModel):
	name: str
	relationship: str
	context: str = ""
	circle_type: str = "inner"
	birthday: Optional[str] = None
	gender: Optional[str] = None
	residency: Optional[str] = None
	timezone: Optional[str] = None
	town: Optional[str] = None
	country: Optional[str] = None
	work_times: Optional[str] = None
	briefing_time: Optional[str] = "08:00"

@router.put("/people/identity")
async def update_identity(person: PersonCreate, db: AsyncSession = Depends(get_db)):
	"""Update the 'Self' identity record."""
	res = await db.execute(select(Person).where(Person.circle_type == "identity"))
	me = res.scalar_one_or_none()
	if not me:
		me = Person(circle_type="identity", relationship="Self")
		db.add(me)
	
	me.name = person.name
	me.birthday = person.birthday
	me.context = person.context
	me.gender = person.gender
	me.residency = person.residency
	me.timezone = person.timezone
	me.town = person.town
	me.country = person.country
	me.work_times = person.work_times
	me.briefing_time = person.briefing_time
	me.relationship = "Self"
	
	await db.commit()
	await db.refresh(me)
	return me

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
		birthday=person.birthday,
		gender=person.gender,
		residency=person.residency,
		timezone=person.timezone,
		town=person.town,
		country=person.country,
		work_times=person.work_times,
		briefing_time=person.briefing_time
	)
	db.add(db_person)
	await db.commit()
	await db.refresh(db_person)
	return db_person

@router.put("/people/{person_id}")
async def update_person(person_id: int, person: PersonCreate, db: AsyncSession = Depends(get_db)):
	res = await db.execute(select(Person).where(Person.id == person_id))
	db_p = res.scalar_one_or_none()
	if not db_p: raise HTTPException(status_code=404, detail="Not found")
	
	db_p.name = person.name
	db_p.relationship = person.relationship
	db_p.context = person.context
	db_p.circle_type = person.circle_type
	db_p.birthday = person.birthday
	db_p.gender = person.gender
	db_p.residency = person.residency
	db_p.timezone = person.timezone
	db_p.town = person.town
	db_p.country = person.country
	db_p.work_times = person.work_times
	db_p.briefing_time = person.briefing_time
	
	await db.commit()
	await db.refresh(db_p)
	return db_p

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
	try:
		google_events = await fetch_calendar_events(
			calendar_id="primary", 
			max_results=100, 
			start_date=start_date,
			end_date=end_date
		)
	except Exception as ce:
		print(f"Calendar fetch failed in get_calendar: {ce}")
		google_events = []
	
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
			parsed = parse_birthday(p.birthday)
			if parsed:
				month, day = parsed
				# Generate for relevant years
				for y in range(start_date.year, end_date.year + 1):
					try:
						# We treat birthdays as "local" dates by not forcing UTC Z if possible
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
					except ValueError:
						continue

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
	end_time: Optional[datetime.datetime] = None
	is_all_day: bool = True

class LocalEventUpdate(BaseModel):
	summary: Optional[str] = None
	start_time: Optional[datetime.datetime] = None
	end_time: Optional[datetime.datetime] = None
	is_completed: Optional[bool] = None

@router.post("/calendar/local")
async def create_local_event(event: LocalEventCreate, db: AsyncSession = Depends(get_db)):
	from app.models.db import LocalEvent
	
	start = event.start_time
	# If all day, ensure it covers the 24h span
	if event.is_all_day:
		start = start.replace(hour=0, minute=0, second=0, microsecond=0)
		end = start + datetime.timedelta(hours=23, minutes=59)
	else:
		end = event.end_time or (start + datetime.timedelta(hours=1))
	
	db_event = LocalEvent(
		summary=event.summary,
		description=event.description,
		start_time=start,
		end_time=end
	)
	db.add(db_event)
	await db.commit()
	await db.refresh(db_event)
	return db_event

@router.put("/calendar/local/{event_id}")
async def update_local_event(event_id: str, event: LocalEventUpdate, db: AsyncSession = Depends(get_db)):
	from app.models.db import LocalEvent
	clean_id = int(event_id.replace("local_", ""))
	res = await db.execute(select(LocalEvent).where(LocalEvent.id == clean_id))
	db_event = res.scalar_one_or_none()
	if not db_event: raise HTTPException(status_code=404)

	if event.summary is not None: db_event.summary = event.summary
	if event.start_time is not None: db_event.start_time = event.start_time
	if event.end_time is not None: db_event.end_time = event.end_time
	if event.is_completed is not None: db_event.is_completed = event.is_completed
	
	await db.commit()
	return db_event

@router.delete("/calendar/local/{event_id}")
async def delete_local_event(event_id: str, db: AsyncSession = Depends(get_db)):
	from app.models.db import LocalEvent
	# Handle both 'local_1' and '1' formats
	clean_id = event_id.replace("local_", "")
	try:
		id_int = int(clean_id)
		await db.execute(delete(LocalEvent).where(LocalEvent.id == id_int))
		await db.commit()
		return {"status": "deleted"}
	except ValueError:
		raise HTTPException(status_code=400, detail="Invalid event ID")

# --- System Status ---
@router.get("/system")
async def get_system_status():
	"""Get system status and trigger an early LLM warmup."""
	from app.config import settings
	import asyncio
	
	provider = settings.LLM_PROVIDER.lower()
	model_name = "Unknown"
	
	if provider == "ollama":
		model_name = settings.OLLAMA_MODEL_FAST
		# Explicitly pull model into RAM via a silent, tiny prompt
		asyncio.create_task(llm_chat("Warming up...", model=settings.OLLAMA_MODEL_FAST, system_override="Respond only with 'Ready'."))
	elif provider == "groq":
		model_name = "Cloud Engine"
	elif provider == "openai":
		model_name = "Cloud Engine"
		
	return {
		"status": "online",
		"llm_provider": provider,
		"llm_model": model_name
	}
