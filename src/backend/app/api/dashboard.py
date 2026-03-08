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

import hmac
import re
from fastapi import APIRouter, Depends, HTTPException, Request, Header
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from app.models.db import AsyncSessionLocal, Project, EmailRule, Briefing, Person
from app.services.memory import semantic_search, semantic_search_raw, list_memories as list_memories_svc, delete_memory
from app.services.planka import get_project_tree
from app.services.operator_board import operator_service
from pydantic import BaseModel
from typing import List, Optional
import datetime
import json
import httpx
import time as _time
from collections import defaultdict
from app.config import settings
import psutil
import platform
import subprocess
import os
import posixpath
import urllib.parse

import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Authentication (C3 / M-A3)
# ---------------------------------------------------------------------------
async def require_auth(
    request: Request,
    authorization: Optional[str] = Header(None, alias="authorization"),
):
    """Bearer-token guard for all dashboard API endpoints.

    In production (IS_DOCKER=True) a missing DASHBOARD_TOKEN is a
    hard configuration error — refuse all requests with HTTP 500 so
    the operator is forced to fix it rather than running open.
    In local dev (IS_DOCKER=False) an empty token disables auth with a warning.
    """
    token = settings.DASHBOARD_TOKEN
    if not token:
        if settings.IS_DOCKER:
            raise HTTPException(
                status_code=500,
                detail="DASHBOARD_TOKEN is not configured. Set it in .env and restart.",
            )
        # Local dev: allow without auth (backwards-compatible)
        logger.warning("DASHBOARD_TOKEN not set — auth disabled (dev mode).")
        return

    # Accept token from Authorization header or ?token= query param (needed for iframes)
    provided: Optional[str] = None
    if authorization and authorization.lower().startswith("bearer "):
        provided = authorization[7:]
    if not provided:
        provided = request.query_params.get("token")
    if not provided:
        provided = request.cookies.get("z_auth_token")

    if not provided:
        raise HTTPException(status_code=401, detail="Unauthorized") from None

    if not hmac.compare_digest(provided, token):
        raise HTTPException(status_code=401, detail="Unauthorized") from None


# ---------------------------------------------------------------------------
# Auth activation endpoint (no auth required)
# Sets an HTTP cookie so the token persists into the system browser on both
# iOS (SFSafariViewController shares cookies with Safari) and
# Android (Chrome Custom Tab shares cookies with Chrome).
# ---------------------------------------------------------------------------
auth_router = APIRouter()

@auth_router.get("/api/dashboard/auth", include_in_schema=False)
async def auth_activate(token: str, redirect: str = "/dashboard"):
    """Validate dashboard token, set a persistent cookie, redirect to destination."""
    if not settings.DASHBOARD_TOKEN or not hmac.compare_digest(token, settings.DASHBOARD_TOKEN):
        raise HTTPException(status_code=401, detail="Invalid token")
    # Sanitise redirect — CodeQL alert #239 / OWASP A1 open-redirect.
    # Strategy: parse-then-re-encode using only the path segment, then apply
    # an explicit character allow-list (alphanumeric + safe URL path chars).
    # This fully detaches safe_redirect from the tainted `redirect` string
    # so CodeQL's taint flow cannot trace a path from user input to the response.
    _SAFE_PATH_RE = re.compile(r'^[a-zA-Z0-9/_\-\.~%]*$')
    _FALLBACK = "/dashboard"
    try:
        _parsed = urllib.parse.urlparse(redirect)
        # Reject anything with a scheme, authority, or query/fragment component.
        if _parsed.scheme or _parsed.netloc or _parsed.query or _parsed.fragment:
            raise ValueError("absolute or parameterised URL rejected")
        _candidate = _parsed.path or _FALLBACK
        # Must start with exactly one "/" (not "//", which becomes //host on some UAs).
        if not _candidate.startswith("/") or _candidate.startswith("//"):
            raise ValueError("non-root path rejected")
        # Allow-list: only safe path characters permitted.
        if not _SAFE_PATH_RE.match(_candidate):
            raise ValueError("unsafe characters in path")
        # Normalise away any ../ traversal sequences.
        safe_redirect = urllib.parse.urlunparse(
            ("", "", posixpath.normpath(_candidate), "", "", "")
        )
        # normpath strips trailing slash — restore it for "/" → "/" edge-case.
        if not safe_redirect.startswith("/"):
            raise ValueError("normalised path lost leading slash")
    except (ValueError, AttributeError):
        safe_redirect = _FALLBACK
    response = RedirectResponse(url=safe_redirect, status_code=302)
    response.set_cookie(
        key="z_auth_token",
        value=settings.DASHBOARD_TOKEN,  # use server-side constant, not user-supplied param
        path="/",
        samesite="lax",
        httponly=False,  # must be JS-readable so frontend can inject as Bearer
        max_age=365 * 24 * 3600,
    )
    return response

# ---------------------------------------------------------------------------
# Rate limiting (M3)
# ---------------------------------------------------------------------------
_rate_limit_store: dict = defaultdict(list)
_RATE_LIMIT_MAX = 20
_RATE_LIMIT_WINDOW = 60  # seconds

# Stricter limiter for /chat and /chat/stream — LLM calls are expensive
_chat_rate_limit_store: dict = defaultdict(list)
_CHAT_RATE_LIMIT_MAX = 5
_CHAT_RATE_LIMIT_WINDOW = 60  # seconds

def _check_rate_limit(request: Request):
    """Sliding-window rate limiter: 20 requests per 60 s per client IP."""
    client_ip = (
        request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        or (request.client.host if request.client else "unknown")
    )
    now = _time.time()
    window_start = now - _RATE_LIMIT_WINDOW
    hits = _rate_limit_store[client_ip]
    hits[:] = [t for t in hits if t > window_start]
    if len(hits) >= _RATE_LIMIT_MAX:
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Try again shortly.")
    hits.append(now)

def _check_chat_rate_limit(request: Request):
    """Stricter sliding-window limiter for LLM chat endpoints: 5 requests per 60 s per client IP."""
    client_ip = (
        request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        or (request.client.host if request.client else "unknown")
    )
    now = _time.time()
    window_start = now - _CHAT_RATE_LIMIT_WINDOW
    hits = _chat_rate_limit_store[client_ip]
    hits[:] = [t for t in hits if t > window_start]
    if len(hits) >= _CHAT_RATE_LIMIT_MAX:
        raise HTTPException(status_code=429, detail="Chat rate limit exceeded. Please wait before sending another message.")
    hits.append(now)

_REPLY_ALLOWLIST_RE = re.compile(
    r'<(?!/?(?:b|i|code|pre|br|p)(?:\s[^>]*)?>)[^>]+>',
    re.IGNORECASE,
)

def _sanitise_reply_html(text: str) -> str:
    """Strip all HTML tags except the safe allowlist: b, i, code, pre, br, p."""
    return _REPLY_ALLOWLIST_RE.sub("", text) if text else text


router = APIRouter(prefix="/api/dashboard", dependencies=[Depends(require_auth)])

# High-speed cache for Planka IDs to avoid sequential network hops on every redirect
PLANKA_ID_CACHE = {
	"oz_project_id": None,
	"operator_board_id": None,
	"last_update": None
}

async def get_db():
	async with AsyncSessionLocal() as session:
		yield session

def parse_birthday(bday_str: str):
	"""Unified birthday parser supporting: DD.MM.YY, YYYY-MM-DD, DD.MM, etc."""
	if not bday_str: return None
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
		# Fallback to MM.DD format
		elif v1 <= 12:
			return v1, v2
	return None

# --- Chat ---
class ChatMessage(BaseModel):
	role: str
	content: str

class ChatRequest(BaseModel):
	message: str
	history: List[ChatMessage] = []
	skip_history: bool = False

@router.get("/chat/history")
async def chat_history(request: Request, limit: int = 30, _rl: None = Depends(_check_rate_limit)):
	"""Return the last N cross-channel messages for persistent chat UI."""
	limit = max(1, min(limit, 100))  # cap: 1–100
	from app.models.db import get_global_history
	msgs = await get_global_history(limit=limit)
	return {"messages": msgs}

@router.post("/chat")
async def dashboard_chat(req: ChatRequest, request: Request, db: AsyncSession = Depends(get_db), _rl: None = Depends(_check_chat_rate_limit)):
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
	elif msg == "/quarter":
		from app.tasks.quarterly import quarterly_review
		report = await quarterly_review()
		return {"reply": report}
	elif msg == "/tree":
		# Life Tree Overview - combines projects, inner circle, and status
		tree = await get_project_tree(as_html=False)
		
		# 1. Inner Circle
		result = await db.execute(select(Person).where(Person.circle_type == "inner"))
		inner_circle = result.scalars().all()
		circle_text = "\n".join([f"• {p.name} ({p.relationship})" for p in inner_circle]) if inner_circle else "No direct connections added yet."
		
		# 2. Upcoming Timeline (Calendar + Birthdays + Local Events)
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
				except Exception:
					pass  # malformed event date -- non-fatal
		except Exception:
			pass  # calendar fetch failed -- non-fatal
		
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
				except Exception:
					pass  # malformed birthday -- skip silently

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
	elif msg == "/help":
		from app.services.translations import get_user_lang, get_translations
		lang = await get_user_lang()
		t = get_translations(lang)
		help_text = t.get("help_msg_full")
		if not help_text:
			sb = t.get("help_section_briefings", "Briefings & Reviews")
			sm = t.get("help_section_missions", "Mission Control")
			si = t.get("help_section_memory", "Memory & Intelligence")
			ss = t.get("help_section_system", "System")
			help_text = (
				f"🤖 **Z Operator Controls**\n\n"
				f"**{sb}:**\n"
				"• `/day`, `/week`, `/month`, `/quarter`, `/year` — Strategic briefings\n\n"
				f"**{sm}:**\n"
				"• `/tree` — Life hierarchy & workspace overview\n"
				"• `/think <query>` — Complex multi-step reasoning\n"
				"• `/remind <text>` — Set a temporary recurring reminder\n"
				"• `/custom <text>` — Create a persistent scheduled task\n"
				"• `/protocols` — Inspect Z's agentic tools\n\n"
				f"**{si}:**\n"
				"• `/search <query>` — Semantic search\n"
				"• `/memories` — List all stored facts\n"
				"• `/add <topic>` — Commit a fact to memory\n"
				"• `/unlearn <query>` — Remove a fact from the vault\n\n"
				f"**{ss}:**\n"
				"• `/personal` — Show compressed personal context Z loaded from /personal\n"
				"• `/skills` — Show agent skill modules loaded from /agent\n"
				"• `/status` — Deep integration health check\n"
				"• `/purge` — Permanently wipe all semantic memory\n\n"
				"Type any message to chat with Z directly."
			)
		return {"reply": help_text}
	elif msg.startswith("/search ") or msg.startswith("/memory "):
		query = msg.replace("/search", "").replace("/memory", "").strip()
		results = await semantic_search(query)
		return {"reply": results}
	elif msg == "/memories":
		from app.services.memory import get_qdrant, COLLECTION_NAME
		client = get_qdrant()
		results, _ = client.scroll(collection_name=COLLECTION_NAME, limit=100)
		if not results:
			return {"reply": "No memories stored in the vault."}
		
		memory_list = "\n".join([f"• {p.payload.get('text')}" for p in results])
		return {"reply": f"🧠 **Semantic Vault: Core Knowledge Vault**\n\n{memory_list}"}
	elif msg.startswith("/unlearn "):
		query = msg.replace("/unlearn", "").strip()
		from app.services.memory import get_qdrant, COLLECTION_NAME, get_embedder
		client = get_qdrant()
		query_vector = get_embedder().encode(query).tolist()
		results = client.query_points(collection_name=COLLECTION_NAME, query=query_vector, limit=1)
		
		if not results.points:
			return {"reply": "No matching knowledge found to unlearn."}
		
		point = results.points[0]
		text = point.payload.get('text', '[No Text]')
		await delete_memory(point.id)
		return {"reply": f"✅ Unlearned: \"{text}\". Z has evolved past this specific context."}
	elif msg.startswith("/add "):
		topic = msg.replace("/add", "").strip()
		from app.services.memory import store_memory
		await store_memory(topic)
		return {"reply": f"✅ Stored to memory: {topic}"}
	elif msg.startswith("/remind "):
		remind_msg = msg.replace("/remind", "").strip()
		from app.services.llm import chat
		from app.services.agent_actions import parse_and_execute_actions
		prompt = (
			"Convert this reminder request into a [ACTION: REMIND ...] tag.\n"
			"Format: [ACTION: REMIND | MESSAGE: <text> | INTERVAL: <minutes> | DURATION: <hours>]\n\n"
			f"Input: {remind_msg}"
		)
		response = await chat(prompt)
		clean_reply, executed = await parse_and_execute_actions(response)
		if executed:
			return {"reply": f"✅ {' '.join(executed)}"}
		else:
			return {"reply": "Could not parse reminder. Try: '/remind 30m for 2h drink water'"}
	elif msg.startswith("/custom "):
		custom_msg = msg.replace("/custom", "").strip()
		from app.services.llm import chat
		from app.services.agent_actions import parse_and_execute_actions
		prompt = (
			"Convert this custom schedule request into a [ACTION: SCHEDULE_CUSTOM ...] tag.\n"
			"Format: [ACTION: SCHEDULE_CUSTOM | NAME: <short_name> | MESSAGE: <text> | TYPE: <cron/interval> | SPEC: <spec>]\n"
			"CRON SPEC: minute hour day month day_of_week\n"
			"INTERVAL SPEC: minutes=N or hours=N\n\n"
			f"Input: {custom_msg}"
		)
		response = await chat(prompt)
		clean_reply, executed = await parse_and_execute_actions(response)
		if executed:
			return {"reply": f"✅ {' '.join(executed)}"}
		else:
			return {"reply": "Could not parse custom turnus. Try: '/custom every Monday at 10am remind me...'"}
	elif msg == "/protocols":
		from app.services.agent_actions import AVAILABLE_TOOLS
		tools_info = "\n".join([f"• **{t.name}**: {t.description}" for t in AVAILABLE_TOOLS])
		protocols_reply = (
			"🤖 **Z Operator Protocols**\n\n"
			"I command the environment using **Semantic Action Tags**. These allow me to transition from passive reasoning to active intervention.\n\n"
			f"**Available Strategic Actions:**\n{tools_info}\n\n"
			"*Every thought is an opportunity for evolution.*"
		)
		return {"reply": protocols_reply}
	elif msg == "/personal":
		from app.services.personal_context import get_personal_context_debug_report
		report = get_personal_context_debug_report()
		return {"reply": report}
	elif msg == "/skills":
		from app.services.agent_context import get_agent_skills_debug_report
		report = get_agent_skills_debug_report()
		return {"reply": report}
	elif msg == "/purge":
		from app.services.translations import get_user_lang, get_translations
		from app.services.memory import wipe_collection
		lang = await get_user_lang()
		t = get_translations(lang)
		success = await wipe_collection(confirm=True)
		if success:
			return {"reply": t.get("purge_success", "\u2705 Semantic memory has been completely wiped.")}
		else:
			return {"reply": t.get("purge_failed", "\u274c Failed to wipe memory. Check backend logs.")}
	elif msg.startswith("[ACTION:"):
		from app.services.agent_actions import parse_and_execute_actions
		clean_reply, executed_cmds = await parse_and_execute_actions(msg, db=db)
		return {
			"reply": clean_reply or "Direct execution complete.",
			"actions": executed_cmds,
			"model": "operator_direct"
		}

	from app.services.llm import chat_with_context, last_model_used
	from app.models.db import get_global_history, save_global_message

	# Recover Cross-Channel History
	merged_history = await get_global_history(limit=10)
	
	try:
		reply = await chat_with_context(
			msg, 
			history=merged_history,
			include_projects=True,
			include_people=True
		)
		
		from app.services.agent_actions import parse_and_execute_actions
		clean_reply, executed_cmds = await parse_and_execute_actions(reply, db=db)

		# Sync to Global Central Memory
		if not req.skip_history:
			await save_global_message("dashboard", "user", msg)
			await save_global_message("dashboard", "z", clean_reply, model=last_model_used.get())

		# Memory is user-driven only (via /add or LEARN action tag)

		return {
			"reply": _sanitise_reply_html(clean_reply),
			"actions": executed_cmds,
			"model": last_model_used.get()
		}
	except Exception as e:
		logger.error("dashboard_chat error: %s", e)
		raise HTTPException(status_code=500, detail="Internal server error") from None

@router.post("/regression-cleanup")
async def regression_cleanup(request: Request, db: AsyncSession = Depends(get_db)):
	"""Server-side cleanup of regression test artifacts.
	
	Called by the test script after each run (including failed runs) to ensure
	no test data pollutes the live system.
	"""
	results = []
	
	# 1. Clean Planka projects with REGRESSION prefix
	try:
		from app.services.planka import find_and_delete_projects_by_prefix
		deleted_projects = await find_and_delete_projects_by_prefix("REGRESSION_TEST_")
		for name in deleted_projects:
			results.append(f"🧹 Deleted Planka project: {name}")
	except Exception as e:
		logger.warning("Planka regression cleanup failed: %s", e)
		results.append("⚠️ Planka cleanup failed")
	
	# 2. Clean regression test people
	try:
		res = await db.execute(select(Person).where(Person.name.like("TEST_%")))
		test_people = res.scalars().all()
		for p in test_people:
			await db.delete(p)
			results.append(f"🧹 Deleted test person: {p.name}")
		await db.commit()
	except Exception as e:
		logger.warning("People regression cleanup failed: %s", e)
		results.append("⚠️ People cleanup failed")
	
	# 3. Clean regression test events
	try:
		from app.models.db import LocalEvent
		res = await db.execute(select(LocalEvent).where(LocalEvent.summary.like("REGRESSION_%")))
		test_events = res.scalars().all()
		for ev in test_events:
			await db.delete(ev)
			results.append(f"🧹 Deleted test event: {ev.summary}")
		await db.commit()
	except Exception as e:
		logger.warning("Events regression cleanup failed: %s", e)
		results.append("⚠️ Events cleanup failed")
	
	# 4. Clean regression test memories from Qdrant
	try:
		from app.services.memory import get_qdrant, COLLECTION_NAME
		client = get_qdrant()
		points, _ = client.scroll(collection_name=COLLECTION_NAME, limit=200)
		import re as _re
		_REGRESSION_PAT = _re.compile(r'TEST.?MEMORY.?TOKEN|TEST.?UNLEARN.?TOKEN', _re.IGNORECASE)
		regression_ids = [p.id for p in points if _REGRESSION_PAT.search(p.payload.get("text", "") if p.payload else "")]
		if regression_ids:
			from qdrant_client.models import PointIdsList
			client.delete(collection_name=COLLECTION_NAME, points_selector=PointIdsList(points=regression_ids))
			results.append(f"🧹 Deleted {len(regression_ids)} test memory vectors")
	except Exception as e:
		logger.warning("Memory regression cleanup failed: %s", e)
		results.append("⚠️ Memory cleanup failed")
	
	if not results:
		results.append("✅ No regression artifacts found to clean.")
	
	return {"cleaned": results}

@router.get("/calibration")
async def get_calibration():
	"""Fetch the daily calibration exercise for the dashboard."""
	import datetime
	methods = [
		("🙏 Gratitude", "Name 3 specific things you are grateful for right now. Be concrete — not 'family' but 'the way Mom called yesterday to check in'."),
		("🎯 Intention Setting", "Set one clear intention for today. Not a task — an intention for HOW you want to show up."),
		("🔄 Cognitive Reframe", "Think of something that's been bothering you. Now reframe it: What's the hidden opportunity or lesson?"),
		("🫁 Box Breathing", "Pause for 60 seconds. Breathe in for 4 counts, hold for 4, out for 4, hold for 4. Repeat 3 times."),
		("🌄 Visualization", "Close your eyes for 30 seconds. Picture your ideal version of today — how does it end?"),
		("🧘 Body Scan", "Scan down slowly from head to toes. Where do you feel tension? Breathe into that spot."),
		("💎 Affirmation", "Repeat: 'I am exactly where I need to be. Today I take one step closer to who I'm becoming.'"),
		("🖐️ 5-4-3-2-1 Grounding", "Notice 5 things you see, 4 you touch, 3 you hear, 2 you smell, 1 you taste."),
		("🌬️ 4-7-8 Breathing", "Inhale 4. Hold 7. Exhale 8. Repeat 3 times. Reduces anxiety by up to 15% cortisol."),
		("☕ Mindful First Sip", "With your first drink, pause. Feel the warmth, smell it, take one slow sip."),
		("📝 Micro-Journal", "1) How do I feel? 2) What am I avoiding? 3) What would make today a win?"),
		("⚓ Anchor Breath", "Feet flat on the ground. Take 3 deep breaths focusing only on the contact. You are here."),
	]
	day_of_year = datetime.date.today().timetuple().tm_yday
	method_name, method_prompt = methods[day_of_year % len(methods)]
	return {"name": method_name, "prompt": method_prompt}

@router.get("/protocols")
async def get_protocols():
	"""Fetch Z's operational protocols (action tags)."""
	from app.services.agent_actions import AVAILABLE_TOOLS
	return {"tools": [{"name": t.name, "description": t.description} for t in AVAILABLE_TOOLS]}

@router.get("/personality")
async def get_personality(db: AsyncSession = Depends(get_db)):
	"""Fetch the agent's personality traits/configuration."""
	from app.models.db import Preference
	res = await db.execute(select(Preference).where(Preference.key == "agent_personality"))
	pref = res.scalar_one_or_none()
	
	default_personality = {
		"agent_name": "Z",
		"directness": 4, 
		"warmth": 3,     
		"agency": 4,     
		"critique": 3,   
		"humor": 2,       
		"honesty": 5,     
		"depth": 4,      
		"roast": 0,       # 0: None, 5: Brutal
		"theme": "default",
		"color_primary": "#14B8A6",
		"color_secondary": "#0066FF",
		"color_tertiary": "#6366F1",
		"role": "Agent Operator",
		"questions": [
			{"id": "agent_name", "label": "Agent Name", "type": "text", "placeholder": "e.g. Z, Jarvis, Hal"},
			{"id": "directness", "label": "Communication Style", "type": "range", "min": 1, "max": 5, "low": "Elaborate", "high": "Concise"},
			{"id": "warmth", "label": "Emotional Tone", "type": "range", "min": 1, "max": 5, "low": "Clinical", "high": "Empathetic"},
			{"id": "agency", "label": "Agency Level", "type": "range", "min": 1, "max": 5, "low": "Reactive", "high": "Proactive"},
			{"id": "critique", "label": "Intellectual Friction", "type": "range", "min": 1, "max": 5, "low": "Agreeable", "high": "Challenging"},
			{"id": "humor", "label": "Humor Score", "type": "range", "min": 0, "max": 10, "low": "0%", "high": "100%"},
			{"id": "honesty", "label": "Honesty Score", "type": "range", "min": 1, "max": 10, "low": "Low", "high": "Absolute"},
			{"id": "roast", "label": "Roast Level", "type": "range", "min": 0, "max": 5, "low": "None", "high": "Brutal"},
			{"id": "cringe", "label": "Cringeness", "type": "range", "min": 0, "max": 10, "low": "Normal", "high": "Super Cringe"},
			{"id": "depth", "label": "Analysis Depth", "type": "range", "min": 1, "max": 5, "low": "Surface", "high": "Deep Dive"},
			{"id": "role", "label": "Core Identity / Archetype", "type": "text", "placeholder": "e.g. Master Architect, Stoic Mentor, Sharp Assistant"},
			{"id": "relationship", "label": "Relational Context", "type": "text", "placeholder": "Who are you to the user? (e.g. Mentor, Tool, Equal Partner)"},
			{"id": "values", "label": "Core Values & Principles", "type": "textarea", "placeholder": "What drives your decision making? (e.g. Efficiency above all, or Ethics first)"},
			{"id": "behavior", "label": "Linguistic & Behavioral Style", "type": "textarea", "placeholder": "Specific quirks, metaphors, or formal/informal speech patterns."},
			{"id": "theme", "label": "Dashboard Theme", "type": "select", "options": [
				{"value": "fusion", "label": "Default Fusion", "group": "default", "colors": {"primary": "#14B8A6", "secondary": "#0066FF", "tertiary": "#6366F1"}},
				{"value": "wind", "label": "Wind", "group": "elements", "colors": {"primary": "#7DB8C9", "secondary": "#A8D4E0", "tertiary": "#5B8FA3"}},
				{"value": "water", "label": "Water", "group": "elements", "colors": {"primary": "#0077B6", "secondary": "#00B4D8", "tertiary": "#023E8A"}},
				{"value": "fire", "label": "Fire", "group": "elements", "colors": {"primary": "#E85D04", "secondary": "#DC2F02", "tertiary": "#F48C06"}},
				{"value": "earth", "label": "Earth", "group": "elements", "colors": {"primary": "#8B6914", "secondary": "#606C38", "tertiary": "#BC6C25"}},
				{"value": "polar", "label": "Polar", "group": "environments", "colors": {"primary": "#A8DADC", "secondary": "#457B9D", "tertiary": "#1D3557"}},
				{"value": "mountain", "label": "Mountain", "group": "environments", "colors": {"primary": "#6C757D", "secondary": "#495057", "tertiary": "#8D99AE"}},
				{"value": "forest", "label": "Forest", "group": "environments", "colors": {"primary": "#2D6A4F", "secondary": "#40916C", "tertiary": "#52B788"}},
				{"value": "desert", "label": "Desert", "group": "environments", "colors": {"primary": "#C2956B", "secondary": "#D4A373", "tertiary": "#9C6644"}},
				{"value": "coast", "label": "Coast", "group": "environments", "colors": {"primary": "#0096C7", "secondary": "#48CAE4", "tertiary": "#F4A261"}},
				{"value": "sky", "label": "Sky", "group": "environments", "colors": {"primary": "#4895EF", "secondary": "#4CC9F0", "tertiary": "#F9C74F"}},
				{"value": "aurora", "label": "Aurora", "group": "phenomena", "colors": {"primary": "#22C55E", "secondary": "#A855F7", "tertiary": "#06B6D4"}},
				{"value": "storm", "label": "Storm", "group": "phenomena", "colors": {"primary": "#475569", "secondary": "#38BDF8", "tertiary": "#E2E8F0"}},
				{"value": "jungle", "label": "Jungle", "group": "phenomena", "colors": {"primary": "#15803D", "secondary": "#A3E635", "tertiary": "#CA8A04"}},
				{"value": "solarized", "label": "Solarized", "group": "ide", "colors": {"primary": "#CB4B16", "secondary": "#268BD2", "tertiary": "#2AA198"}},
				{"value": "monokai", "label": "Monokai", "group": "ide", "colors": {"primary": "#F92672", "secondary": "#FD971F", "tertiary": "#A6E22E"}},
				{"value": "dracula", "label": "Dracula", "group": "ide", "colors": {"primary": "#BD93F9", "secondary": "#FF79C6", "tertiary": "#8BE9FD"}},
				{"value": "gruvbox", "label": "Gruvbox", "group": "ide", "colors": {"primary": "#FABD2F", "secondary": "#FE8019", "tertiary": "#B8BB26"}},
				{"value": "nord", "label": "Nord", "group": "ide", "colors": {"primary": "#88C0D0", "secondary": "#81A1C1", "tertiary": "#5E81AC"}},
				{"value": "catppuccin", "label": "Catppuccin", "group": "ide", "colors": {"primary": "#CBA6F7", "secondary": "#89B4FA", "tertiary": "#A6E3A1"}},
				{"value": "tokyo_night", "label": "Tokyo Night", "group": "ide", "colors": {"primary": "#7AA2F7", "secondary": "#BB9AF7", "tertiary": "#7DCFFF"}},
				{"value": "mono_silver", "label": "Monochrome Silver", "group": "mono", "colors": {"primary": "#ADB5BD", "secondary": "#6C757D", "tertiary": "#CED4DA"}},
				{"value": "mono_teal", "label": "Monochrome Teal", "group": "mono", "colors": {"primary": "#14B8A6", "secondary": "#0D9488", "tertiary": "#2DD4BF"}},
				{"value": "mono_violet", "label": "Monochrome Violet", "group": "mono", "colors": {"primary": "#8B5CF6", "secondary": "#7C3AED", "tertiary": "#A78BFA"}},
				{"value": "color_red", "label": "Red", "group": "colors", "colors": {"primary": "#E53E3E", "secondary": "#B91C1C", "tertiary": "#F87171"}},
				{"value": "color_blue", "label": "Blue", "group": "colors", "colors": {"primary": "#3B82F6", "secondary": "#2563EB", "tertiary": "#60A5FA"}},
				{"value": "color_green", "label": "Green", "group": "colors", "colors": {"primary": "#22C55E", "secondary": "#16A34A", "tertiary": "#4ADE80"}},
				{"value": "color_purple", "label": "Purple", "group": "colors", "colors": {"primary": "#A855F7", "secondary": "#9333EA", "tertiary": "#C084FC"}},
				{"value": "color_orange", "label": "Orange", "group": "colors", "colors": {"primary": "#F97316", "secondary": "#EA580C", "tertiary": "#FB923C"}},
				{"value": "color_cyan", "label": "Cyan", "group": "colors", "colors": {"primary": "#22D3EE", "secondary": "#0891B2", "tertiary": "#A5F3FC"}},
				{"value": "color_gold", "label": "Gold", "group": "colors", "colors": {"primary": "#EAB308", "secondary": "#CA8A04", "tertiary": "#FACC15"}},
				{"value": "color_indigo", "label": "Indigo", "group": "colors", "colors": {"primary": "#6366F1", "secondary": "#4F46E5", "tertiary": "#818CF8"}},
				{"value": "glass_frost", "label": "Glass Frost", "group": "glass", "colors": {"primary": "#67E8F9", "secondary": "#A5F3FC", "tertiary": "#22D3EE"}},
				{"value": "glass_ember", "label": "Glass Ember", "group": "glass", "colors": {"primary": "#FB923C", "secondary": "#FDBA74", "tertiary": "#F97316"}},
				{"value": "neon", "label": "Neon", "group": "style", "colors": {"primary": "#FF00FF", "secondary": "#00FFFF", "tertiary": "#FFFF00"}},
				{"value": "hc_1", "label": "High Contrast I", "group": "hc", "colors": {"primary": "#38BDF8", "secondary": "#FB923C", "tertiary": "#A78BFA"}},
				{"value": "hc_2", "label": "High Contrast II", "group": "hc", "colors": {"primary": "#FACC15", "secondary": "#F472B6", "tertiary": "#34D399"}},
				{"value": "hc_3", "label": "High Contrast III", "group": "hc", "colors": {"primary": "#FFFFFF", "secondary": "#FFFF00", "tertiary": "#00FFFF"}}
			]}
		]
	}

	if pref:
		saved = json.loads(pref.value)
		# Ensure all fields exist and merge questions
		for k, v in default_personality.items():
			if k not in saved: saved[k] = v
		saved["questions"] = default_personality["questions"]
	else:
		saved = default_personality

	# Identity Person colors override personality preference so themes
	# chosen in UserCard (which writes to the Person model) always win.
	res2 = await db.execute(select(Person).where(Person.circle_type == "identity"))
	identity = res2.scalar_one_or_none()
	if identity:
		if identity.color_primary:
			saved["color_primary"] = identity.color_primary
		if identity.color_secondary:
			saved["color_secondary"] = identity.color_secondary
		if identity.color_tertiary:
			saved["color_tertiary"] = identity.color_tertiary

	return saved

@router.put("/personality")
async def save_personality(data: dict, db: AsyncSession = Depends(get_db)):
	"""Save updated agent personality traits."""
	from app.models.db import Preference
	# Remove metadata before saving
	data.pop("questions", None)
	
	res = await db.execute(select(Preference).where(Preference.key == "agent_personality"))
	pref = res.scalar_one_or_none()
	
	val_str = json.dumps(data)
	if pref:
		pref.value = val_str
	else:
		pref = Preference(key="agent_personality", value=val_str)
		db.add(pref)
	
	await db.commit()
	return {"status": "ok", "personality": data}

@router.post("/chat/stream")
async def dashboard_chat_stream(req: ChatRequest, request: Request, _rl: None = Depends(_check_chat_rate_limit)):
	"""SSE streaming chat endpoint for real-time token delivery to dashboard."""
	from starlette.responses import StreamingResponse
	from app.services.llm import chat_stream_with_context, last_model_used
	from app.models.db import get_global_history, save_global_message
	from app.services.agent_actions import parse_and_execute_actions

	msg = req.message.strip()

	async def event_generator():
		merged_history = await get_global_history(limit=10)
		chunks = []

		async for chunk in chat_stream_with_context(
			msg,
			history=merged_history,
			include_projects=True,
			include_people=True
		):
			chunks.append(chunk)
			yield f"data: {json.dumps({'token': chunk})}\n\n"

		full_response = "".join(chunks)

		async with AsyncSessionLocal() as db:
			clean_reply, executed_cmds = await parse_and_execute_actions(full_response, db=db)

		await save_global_message("dashboard", "user", msg)
		model_label = last_model_used.get()
		await save_global_message("dashboard", "z", clean_reply, model=model_label)

		# Background memory extraction — learn from user message without blocking reply
		import asyncio
		from app.services.memory import extract_and_store_facts
		asyncio.create_task(extract_and_store_facts(msg))

		yield f"data: {json.dumps({'done': True, 'reply': _sanitise_reply_html(clean_reply), 'actions': executed_cmds, 'model': model_label})}\n\n"

	return StreamingResponse(
		event_generator(),
		media_type="text/event-stream",
		headers={
			"Cache-Control": "no-cache",
			"Connection": "keep-alive",
			"X-Accel-Buffering": "no",
		}
	)

# --- Life Tree & Onboarding ---
# Handle by main.py /calendar

@router.get("/life-tree")
async def get_life_tree(db: AsyncSession = Depends(get_db)):
	"""Fetch the rich Life Tree overview for the dashboard widget."""
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
	try:
		events = await fetch_calendar_events(max_results=5, days_ahead=7)
	except Exception as ce:
		logger.warning("Calendar fetch failed: %s", ce)
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
				if 0 <= days_until <= 3:
					formatted_events.append({
						"summary": f"🎂 {p.name}'s Birthday",
						"time": bday_this_year.strftime('%a, %d %b'),
						"is_local": True,
						"sort_key": bday_this_year
					})
			except Exception as be:
				logger.debug("Error creating birthday event for %s: %s", p.name, be)
	
	# 3. Add Google Events
	for ev in events:
		# Handle date-only (2024-01-01) and date-time (2024-01-01T12:00:00Z)
		start_str = ev['start']
		try:
			dt = datetime.datetime.fromisoformat(start_str.replace('Z', ''))
			time_fmt = dt.strftime('%a %H:%M')
			sort_key = dt.replace(tzinfo=None)
		except Exception:
			# Fallback for unexpected formats
			time_fmt = start_str
			sort_key = now + datetime.timedelta(days=10) # Push to end
		
		formatted_events.append({
			"summary": ev['summary'],
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
	for lev in local_events:
		formatted_events.append({
			"summary": lev.summary,
			"time": lev.start_time.strftime('%a %H:%M'),
			"is_local": True,
			"sort_key": lev.start_time
		})

	# Sort all events (Birthdays, Google, Local) by the original datetime object
	formatted_events.sort(key=lambda x: x.get('sort_key', now))  # type: ignore[arg-type, return-value]

	return {
		"projects_tree": tree,
		"social_circles": social_data,
		"timeline": formatted_events[:5]
	}

@router.get("/onboarding-status")
async def onboarding_status(db: AsyncSession = Depends(get_db)):
	"""Check whether the user still needs the onboarding walkthrough."""
	from app.models.db import Preference
	stmt = select(Preference).where(Preference.key == "onboarding_dismissed")
	res = await db.execute(stmt)
	pref = res.scalar_one_or_none()
	dismissed = pref is not None and pref.value == "true"
	if dismissed:
		return {"needs_onboarding": False, "steps": []}
	# Return onboarding steps for first-time users
	return {
		"needs_onboarding": True,
		"steps": [
			{"key": "profile", "label": "Set up your profile", "done": False},
			{"key": "circles", "label": "Add people to your circles", "done": False},
			{"key": "calendar", "label": "Connect your calendar", "done": False},
		]
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

@router.get("/debug-planka")
async def debug_planka(_: None = Depends(require_auth)):
	"""Return the exact project → board → lists that operator_service targets.

	Use this to diagnose 'tasks created but not visible' issues.
	Resets the in-memory cache so the response always reflects the live Planka state.
	"""
	try:
		from app.services.planka import get_planka_auth_token
		import httpx as _httpx
		from app.config import settings as _s

		token = await get_planka_auth_token()
		async with _httpx.AsyncClient(base_url=_s.PLANKA_BASE_URL, timeout=10.0,
									  headers={"Authorization": f"Bearer {token}"}) as client:
			# Force full re-resolve (bypass cache)
			operator_service._project_id = None
			operator_service._board_id = None
			project_id, board_id = await operator_service.initialize_board(client)

			proj_resp = await client.get(f"/api/projects/{project_id}")
			proj_name = proj_resp.json().get("item", {}).get("name", "Unknown")

			b_resp = await client.get(f"/api/boards/{board_id}", params={"included": "lists"})
			b_data = b_resp.json()
			board_name = b_data.get("item", {}).get("name", "Unknown")
			lists = b_data.get("included", {}).get("lists", [])

		base_url = _s.BASE_URL.rstrip('/')
		board_link = f"{base_url}/api/dashboard/planka-redirect?target_board_id={board_id}"
		return {
			"project": {"name": proj_name, "id": project_id},
			"board": {"name": board_name, "id": board_id, "link": board_link},
			"lists": [{"name": l["name"], "id": l["id"]} for l in lists],
		}
	except Exception as e:
		logger.error("debug-planka failed: %s", e)
		raise HTTPException(status_code=500, detail="Planka diagnostic failed") from None


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
	# Use standard session (no withHttpOnlyToken) — session.httpOnlyToken will be
	# null, so the auth middleware only needs the Bearer JWT, no matching cookie.
	login_url = f"{settings.PLANKA_BASE_URL}/api/access-tokens"
	payload = {
		"emailOrUsername": settings.PLANKA_ADMIN_EMAIL,
		"password": settings.PLANKA_ADMIN_PASSWORD
	}
	
	async with httpx.AsyncClient(timeout=10.0) as client:
		try:
			resp = await client.post(login_url, json=payload)
			
			# Handle pending ToS acceptance (common on first login)
			if resp.status_code == 403:
				data = resp.json()
				pending_token = data.get("pendingToken")
				if pending_token:
					logger.debug("Planka SSO requires ToS acceptance (pendingToken found). Accepting...")
					accept_url = f"{settings.PLANKA_BASE_URL}/api/access-tokens/{pending_token}/actions/accept"
					accept_resp = await client.post(accept_url)
					accept_resp.raise_for_status()
					# After accepting, retry the login to get the real token and cookies
					resp = await client.post(login_url, json=payload)

			resp.raise_for_status()
			token_data = resp.json()
			access_token = token_data.get("item")

			if not access_token:
				raise Exception("Failed to retrieve access token from Planka")

			# 3. Verify the token works (sanity check)
			try:
				me_resp = await client.get(
					f"{settings.PLANKA_BASE_URL}/api/users/me",
					headers={"Authorization": f"Bearer {access_token}"}
				)
				if me_resp.status_code != 200:
					logger.warning("Planka token sanity-check failed: %s", me_resp.status_code)
			except Exception as e:
				logger.debug("Could not verify token: %s", e)

			# 4. Determine Target Redirect URL
			target_board_id = request.query_params.get("target_board_id") or request.query_params.get("targetboardid")
			target_project_id = request.query_params.get("target_project_id") or request.query_params.get("targetprojectid")
			
			if target_board_id:
				redirect_url = f"{public_base}/boards/{target_board_id}"
			elif target_project_id:
				redirect_url = f"{public_base}/projects/{target_project_id}"
			elif target == "operator":
				# Use Cache or Fetch
				op_id = PLANKA_ID_CACHE.get("operator_board_id")
				if not op_id:
					from app.services.translations import get_all_values
					all_proj_names = {n.lower() for n in get_all_values("project_name")} | {"openzero", "boards"}
					all_brd_names = {n.lower() for n in get_all_values("board_name")} | {"operator board"}
					headers = {"Authorization": f"Bearer {access_token}"}
					proj_resp = await client.get(f"{settings.PLANKA_BASE_URL}/api/projects", headers=headers)
					projects = proj_resp.json().get("items", [])
					oz_proj = next((p for p in projects if p["name"].lower() in all_proj_names), None)
					if oz_proj:
						PLANKA_ID_CACHE["oz_project_id"] = oz_proj["id"]
						det_resp = await client.get(f"{settings.PLANKA_BASE_URL}/api/projects/{oz_proj['id']}", headers=headers)
						boards = det_resp.json().get("included", {}).get("boards", [])
						op_board = next((b for b in boards if b["name"].lower() in all_brd_names), None)
						if op_board:
							PLANKA_ID_CACHE["operator_board_id"] = op_board["id"]
				
				op_id = PLANKA_ID_CACHE.get("operator_board_id")
				if op_id:
					redirect_url = f"{public_base}/boards/{op_id}"
				else:
					# Fallback to project root if operator board not found
					proj_id = PLANKA_ID_CACHE.get("oz_project_id")
					if proj_id:
						redirect_url = f"{public_base}/projects/{proj_id}"
					else:
						redirect_url = f"{public_base}/projects" # Planka may still 404 but it's the expected path
			else:
				# Default 'Board Overview' -> Dynamically find first project to avoid /boards 404
				proj_id = PLANKA_ID_CACHE.get("oz_project_id")
				if not proj_id:
					try:
						from app.services.translations import get_all_values as _gav
						_all_pn = {n.lower() for n in _gav("project_name")} | {"openzero", "boards"}
						headers = {"Authorization": f"Bearer {access_token}"}
						proj_resp = await client.get(f"{settings.PLANKA_BASE_URL}/api/projects", headers=headers)
						projects = proj_resp.json().get("items", [])
						oz_proj = next((p for p in projects if p["name"].lower() in _all_pn), None)
						if oz_proj:
							proj_id = oz_proj["id"]
							PLANKA_ID_CACHE["oz_project_id"] = proj_id
						elif projects:
							proj_id = projects[0]["id"]
							PLANKA_ID_CACHE["oz_project_id"] = proj_id
					except Exception:
						pass  # project lookup optional -- continue with redirect fallback

				if proj_id:
					redirect_url = f"{public_base}/projects/{proj_id}"
				else:
					redirect_url = f"{public_base}/boards" # Absolute fallback

			# 5. Build Bridge HTML
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

							// Planka 2.x stores the JWT in browser cookies (not localStorage).
							// The React app reads api$2.get("accessToken") on boot, which
							// is js-cookie reading document.cookie["accessToken"].
							// It also validates that "accessTokenVersion" === "1" before
							// trusting the token — if missing, it wipes the token.
							if (token) {{
								try {{
									const parts = token.split('.');
									const payload = JSON.parse(atob(parts[1]));
									const expiry = new Date(payload.exp * 1000).toUTCString();
									document.cookie = 'accessToken=' + encodeURIComponent(token) + '; path=/; expires=' + expiry + '; SameSite=Strict';
									document.cookie = 'accessTokenVersion=1; path=/; expires=' + expiry + '; SameSite=Strict';
								}} catch (cookieErr) {{
									console.warn('Failed to parse JWT for cookie expiry, using session cookie:', cookieErr);
									document.cookie = 'accessToken=' + encodeURIComponent(token) + '; path=/; SameSite=Strict';
									document.cookie = 'accessTokenVersion=1; path=/; SameSite=Strict';
								}}
							}}

							window.location.replace('{redirect_url}');
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
			return response

		except Exception as e:
			logger.warning("Planka Auth Error: %s", e)
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
    """Create a new project in Planka."""
    from app.services.planka import create_project as planka_create_project
    try:
        result = await planka_create_project(project.name, project.description)
        return {"status": "created", "name": project.name, "id": result.get("id")}
    except Exception as e:
        logger.error("Failed to create project in Planka: %s", e)
        raise HTTPException(status_code=500, detail="Failed to create project") from None

# --- Memory ---
@router.get("/memory/search")
async def search_memory(query: str, db: AsyncSession = Depends(get_db)):
	"""
	Semantic + DB memory search.
	Returns structured objects: {id, text, type, score?}
	so the frontend can show delete buttons.
	"""
	if not query:
		return {"results": []}

	final_hits = []

	# 1. Qdrant semantic search (returns structured objects with IDs)
	try:
		semantic_results = await semantic_search_raw(query, top_k=10)
		for hit in semantic_results:
			final_hits.append({
				"id": hit["id"],
				"text": hit["text"],
				"score": hit["score"],
				"type": "memory",
				"stored_at": hit.get("stored_at"),
			})
	except Exception as e:
			logger.warning("Semantic search failed: %s", e)
	# 2. People DB Search (no Qdrant ID — not deletable from here)
	res_people = await db.execute(select(Person).where(Person.name.ilike(f"%{query}%")))
	people = res_people.scalars().all()
	for p in people:
		final_hits.append({
			"id": None,
			"text": f"\U0001f464 PERSONAL PROFILE: {p.name} ({p.relationship}) — {p.context[:150]}",
			"type": "profile",
			"score": None,
			"stored_at": None,
		})

	# 3. Project Search
	res_proj = await db.execute(select(Project).where(Project.name.ilike(f"%{query}%")))
	projs = res_proj.scalars().all()
	for prj in projs:
		final_hits.append({
			"id": None,
			"text": f"\U0001f333 MISSION: {prj.name} (Status: {prj.status})",
			"type": "project",
			"score": None,
			"stored_at": None,
		})

	return {"results": final_hits[:20]}


@router.get("/memory/list")
async def memory_list(offset: int = 0, limit: int = 50, _auth=Depends(require_auth)):
	"""Paginated scroll of all Qdrant memories."""
	return await list_memories_svc(offset=offset, limit=min(limit, 200))


@router.delete("/memory/{point_id}")
async def memory_delete(point_id: str, _auth=Depends(require_auth)):
	"""Hard-delete a single memory point from Qdrant by UUID."""
	success = await delete_memory(point_id)
	if not success:
		raise HTTPException(status_code=404, detail="Memory point not found or delete failed")
	return {"deleted": point_id}

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
	language: Optional[str] = "en"
	color_primary: Optional[str] = None
	color_secondary: Optional[str] = None
	color_tertiary: Optional[str] = None

@router.put("/people/identity")
async def update_identity(person: PersonCreate, db: AsyncSession = Depends(get_db)):
	"""Update the 'Self' identity record."""
	res = await db.execute(select(Person).where(Person.circle_type == "identity"))
	me = res.scalar_one_or_none()

	# Track language change BEFORE updating
	old_lang = (me.language if me and me.language else "en") if me else "en"
	new_lang = person.language or "en"

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
	me.language = person.language
	me.color_primary = person.color_primary
	me.color_secondary = person.color_secondary
	me.color_tertiary = person.color_tertiary
	me.relationship = "Self"
	
	await db.commit()
	await db.refresh(me)

	# Refresh cached timezone/location so services pick up the new values immediately
	from app.services.timezone import refresh_user_settings
	await refresh_user_settings()

	# If language changed, rename Planka entities in background
	if old_lang != new_lang:
		import asyncio
		asyncio.create_task(operator_service.rename_planka_entities(old_lang, new_lang))

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

	# 1. Fetch Aggregated Events (Google + CalDAV + Local DB)
	from app.services.calendar import fetch_unified_events
	try:
		all_events = await fetch_unified_events(
			days_ahead=35, 
			start_date=start_date
		)
	except Exception as ce:
		logger.warning("Unified Calendar fetch failed: %s", ce)
		all_events = []
	
	# 2. Add Virtual Birthdays (Not yet in unified fetcher as they are generated)
	result = await db.execute(select(Person))
	people = result.scalars().all()
	birthday_events = []
	
	for p in people:
		if p.birthday:
			parsed = parse_birthday(p.birthday)
			if parsed:
				month, day = parsed
				for y in range(start_date.year, end_date.year + 1):
					try:
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

	all_events = all_events + birthday_events
	
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
		raise HTTPException(status_code=400, detail="Invalid event ID") from None

# --- Server Info (RAM, uptime, LLM tier health) ---
@router.get("/server-info")
async def server_info():
	"""Return host RAM, uptime, and per-tier LLM configuration from llama-server /props."""
	import os

	info: dict = {
		"ram_total_gb": 0,
		"ram_available_gb": 0,
		"ram_used_pct": 0,
		"uptime_seconds": 0,
		"uptime_human": "",
		"tiers": {},
	}

	# --- RAM ---
	try:
		if platform.system() == "Linux":
			with open("/proc/meminfo", "r") as f:
				meminfo = f.read()
			mem = {}
			for line in meminfo.split("\n"):
				parts = line.split(":")
				if len(parts) == 2:
					key = parts[0].strip()
					val = parts[1].strip().split()[0]  # kB
					mem[key] = int(val)
			total_kb = mem.get("MemTotal", 0)
			free_kb = mem.get("MemFree", 0)
			avail_kb = mem.get("MemAvailable", free_kb)
			buffers_kb = mem.get("Buffers", 0)
			# Cached in /proc/meminfo excludes SReclaimable on Linux 3.14+;
			# add SReclaimable to match what `free` shows as buff/cache.
			cached_kb = mem.get("Cached", 0) + mem.get("SReclaimable", 0)
			apps_kb = max(total_kb - free_kb - buffers_kb - cached_kb, 0)
			bufcache_kb = buffers_kb + cached_kb
			info["ram_total_gb"] = round(total_kb / 1048576, 1)
			info["ram_available_gb"] = round(avail_kb / 1048576, 1)
			info["ram_free_gb"] = round(free_kb / 1048576, 1)
			info["ram_apps_gb"] = round(apps_kb / 1048576, 1)
			info["ram_bufcache_gb"] = round(bufcache_kb / 1048576, 1)
			info["ram_used_pct"] = round((1 - avail_kb / max(total_kb, 1)) * 100, 1)
			info["ram_apps_pct"] = round(apps_kb / max(total_kb, 1) * 100, 1)
		elif platform.system() == "Darwin":
			import subprocess
			total = int(subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True, timeout=5).strip())
			info["ram_total_gb"] = round(total / (1024**3), 1)
	except Exception as ram_err:
		logger.debug("RAM info unavailable: %s", ram_err)

	# --- Uptime ---
	try:
		if platform.system() == "Linux":
			with open("/proc/uptime", "r") as f:
				uptime_s = float(f.read().split()[0])
			info["uptime_seconds"] = int(uptime_s)
			days = int(uptime_s // 86400)
			hours = int((uptime_s % 86400) // 3600)
			info["uptime_human"] = f"{days}d {hours}h" if days else f"{hours}h {int((uptime_s % 3600) // 60)}m"
	except Exception as up_err:
		logger.debug("Uptime info unavailable: %s", up_err)

	# --- Per-tier LLM props (threads, ctx, etc.) ---
	tier_urls = {
		"instant": settings.LLM_INSTANT_URL,
		"standard": settings.LLM_STANDARD_URL,
		"deep": settings.LLM_DEEP_URL,
	}
	physical_cores = os.cpu_count() or 0

	async with httpx.AsyncClient(timeout=5.0) as client:
		for tier_name, base_url in tier_urls.items():
			tier_info: dict = {
				"status": "offline",
				"threads": 0,
				"ctx_size": 0,
				"n_predict": 0,
				"model_file": "",
				"using_all_cores": True,
				"thread_warning": "",
			}
			try:
				resp = await client.get(f"{base_url}/props")
				if resp.status_code == 200:
					tier_info["status"] = "online"
					# Try /health for slot data
					try:
						health_resp = await client.get(f"{base_url}/health")
						if health_resp.status_code == 200:
							health = health_resp.json()
							tier_info["status"] = health.get("status", "online")
					except Exception:
						tier_info["status"] = "online"  # ignore /health probe failures
				# Also try /slots for thread info
				try:
					slots_resp = await client.get(f"{base_url}/slots")
					if slots_resp.status_code == 200:
						slots = slots_resp.json()
						if isinstance(slots, list) and len(slots) > 0:
							tier_info["n_predict"] = slots[0].get("n_predict", 0)
							tier_info["ctx_size"] = slots[0].get("n_ctx", 0)
				except Exception:
					tier_info["ctx_size"] = 0  # /slots probe optional
			except Exception:
				tier_info["status"] = "offline"

			# Thread detection from env (the actual configured value)
			env_thread_map = {
				"instant": os.environ.get("LLM_INSTANT_THREADS", "7"),
				"standard": os.environ.get("LLM_STANDARD_THREADS", "7"),
				"deep": os.environ.get("LLM_DEEP_THREADS", "7"),
			}
			configured_threads = int(env_thread_map.get(tier_name, "4"))
			tier_info["threads"] = configured_threads

			if configured_threads < 2:
				tier_info["thread_warning"] = f"Only {configured_threads} thread(s) configured -- likely a misconfigured env var."
				tier_info["using_all_cores"] = False
			elif configured_threads <= physical_cores // 3:
				tier_info["thread_warning"] = f"Using {configured_threads}/{physical_cores} cores -- may be underutilizing CPU."
				tier_info["using_all_cores"] = False

			info["tiers"][tier_name] = tier_info

	info["physical_cores"] = physical_cores
	return info


# --- System Benchmark ---

@router.get("/llm-config")
async def get_llm_config():
	"""Return the configured LLM tier setup for the dashboard."""
	def _model_display(file_env: str, fallback: str) -> str:
		"""Derive a human-readable name from the GGUF filename, falling back to the legacy label."""
		fname = os.environ.get(file_env, "").strip()
		if fname:
			return fname.removesuffix(".gguf")
		return fallback

	return {
		"tiers": [
			{
				"tier": "instant",
				"model": _model_display("LLM_INSTANT_MODEL_FILE", settings.LLM_MODEL_INSTANT),
				"use_case": "Greetings, confirmations, trivial Q&A, memory distillation",
				"threads": int(os.environ.get("LLM_INSTANT_THREADS", "0")),
			},
			{
				"tier": "standard",
				"model": _model_display("LLM_STANDARD_MODEL_FILE", settings.LLM_MODEL_STANDARD),
				"use_case": "Normal conversation, moderate reasoning, tool-intent",
				"threads": int(os.environ.get("LLM_STANDARD_THREADS", "0")),
			},
			{
				"tier": "deep",
				"model": _model_display("LLM_DEEP_MODEL_FILE", settings.LLM_MODEL_DEEP),
				"use_case": "Complex reasoning, briefings, creative, strategic analysis",
				"threads": int(os.environ.get("LLM_DEEP_THREADS", "0")),
			},
		],
		"provider": settings.LLM_PROVIDER,
		"deep_timeout_s": settings.DEEP_MODEL_TIMEOUT_S,
	}
@router.get("/benchmark/cpu")
async def benchmark_cpu():
	"""Fetch VPS CPU info: model, cores, architecture, SIMD flags."""
	import subprocess
	import os

	info = {
		"cpu_model": "Unknown",
		"architecture": platform.machine(),
		"cores_physical": os.cpu_count() or 0,
		"cores_logical": os.cpu_count() or 0,
		"avx2": False,
		"avx512": False,
		"sse4_2": False,
		"flags": [],
		"platform": platform.system(),
	}

	try:
		# Linux: parse /proc/cpuinfo
		if platform.system() == "Linux":
			with open("/proc/cpuinfo", "r") as f:
				cpuinfo = f.read()
			for line in cpuinfo.split("\n"):
				if line.startswith("model name"):
					info["cpu_model"] = line.split(":")[1].strip()
					break
			# Parse flags
			for line in cpuinfo.split("\n"):
				if line.startswith("flags"):
					flags = line.split(":")[1].strip().split()
					info["flags"] = flags
					info["avx2"] = "avx2" in flags
					info["avx512"] = any(f.startswith("avx512") for f in flags)
					info["sse4_2"] = "sse4_2" in flags
					break
			# Physical cores via lscpu
			try:
				lscpu_out = subprocess.check_output(["lscpu"], text=True, timeout=5)
				for line in lscpu_out.split("\n"):
					if "Core(s) per socket:" in line:
						cores_per = int(line.split(":")[1].strip())
					if "Socket(s):" in line:
						sockets = int(line.split(":")[1].strip())
				info["cores_physical"] = cores_per * sockets
			except Exception as lscpu_err:
				logger.debug("lscpu unavailable: %s", lscpu_err)
		elif platform.system() == "Darwin":
			try:
				brand = subprocess.check_output(["sysctl", "-n", "machdep.cpu.brand_string"], text=True, timeout=5).strip()
				info["cpu_model"] = brand
				info["cores_physical"] = int(subprocess.check_output(["sysctl", "-n", "hw.physicalcpu"], text=True, timeout=5).strip())
				info["cores_logical"] = int(subprocess.check_output(["sysctl", "-n", "hw.logicalcpu"], text=True, timeout=5).strip())
				features = subprocess.check_output(["sysctl", "-n", "machdep.cpu.features"], text=True, timeout=5).strip().lower().split()
				info["avx2"] = "avx2" in features
				info["sse4_2"] = "sse4_2" in features or "sse4.2" in features
			except Exception as mac_err:
				logger.debug("macOS sysctl cpu info unavailable: %s", mac_err)
	except Exception as cpu_err:
		logger.debug("CPU info unavailable: %s", cpu_err)

	return info


@router.post("/benchmark/llm")
async def benchmark_llm(tier: str = "instant"):
	"""Run a fixed-prompt benchmark against a specific LLM tier and measure tokens/second."""
	import time

	tier_map = {
		"instant": (settings.LLM_INSTANT_URL, settings.LLM_MODEL_INSTANT),
		"standard": (settings.LLM_STANDARD_URL, settings.LLM_MODEL_STANDARD),
		"deep": (settings.LLM_DEEP_URL, settings.LLM_MODEL_DEEP),
	}
	if tier not in tier_map:
		raise HTTPException(status_code=400, detail="Invalid tier")

	base_url, model_name = tier_map[tier]
	# Short, deterministic prompt -- produces ~30-50 tokens for reliable measurement
	# without wasting time on runaway generation.
	prompt = "List the planets of our solar system in order from the Sun, one per line."

	try:
		start = time.monotonic()
		first_token_time = None
		token_count = 0

		# Qwen3 models consume all tokens in the reasoning phase if thinking is
		# not suppressed — inject /no_think for instant/standard so the tokens
		# budget goes to actual output, not CoT.
		bench_messages: list[dict] = []
		if tier != "deep":
			bench_messages.append({"role": "system", "content": "/no_think"})
		bench_messages.append({"role": "user", "content": prompt})

		async with httpx.AsyncClient(timeout=120) as client:
			async with client.stream(
				"POST",
				f"{base_url}/v1/chat/completions",
				json={
					"model": "local",
					"messages": bench_messages,
					"stream": True,
					"max_tokens": 60,
					"temperature": 0.0,
				},
			) as resp:
				if resp.status_code != 200:
					return {"tier": tier, "model": model_name, "error": f"HTTP {resp.status_code}"}

				async for line in resp.aiter_lines():
					if not line.startswith("data: "):
						continue
					payload = line[6:].strip()
					if payload == "[DONE]":
						break
					try:
						chunk = json.loads(payload)
						delta = chunk.get("choices", [{}])[0].get("delta", {})
						content = delta.get("content", "")
						if content:
							token_count += 1
							if first_token_time is None:
								first_token_time = time.monotonic()
					except (json.JSONDecodeError, IndexError):
						continue

		end = time.monotonic()
		total_s = end - start
		ttft = (first_token_time - start) if first_token_time else total_s
		gen_time = (end - first_token_time) if first_token_time else total_s
		tps = token_count / gen_time if gen_time > 0 else 0

		# Fetch thread config for this tier
		import os
		thread_env_map = {
			"instant": "LLM_INSTANT_THREADS",
			"standard": "LLM_STANDARD_THREADS",
			"deep": "LLM_DEEP_THREADS",
		}
		configured_threads = int(os.environ.get(thread_env_map.get(tier, ""), "0"))
		physical_cores = os.cpu_count() or 0
		thread_warning = ""
		if configured_threads and configured_threads < 2:
			thread_warning = f"Only {configured_threads} thread -- likely misconfigured env var"
		elif configured_threads and configured_threads <= physical_cores // 3:
			thread_warning = f"Using {configured_threads}/{physical_cores} cores -- CPU underutilized"

		return {
			"tier": tier,
			"model": model_name,
			"tokens": token_count,
			"total_seconds": round(total_s, 2),
			"time_to_first_token": round(ttft, 2),
			"generation_seconds": round(gen_time, 2),
			"tokens_per_second": round(tps, 1),
			"configured_threads": configured_threads,
			"physical_cores": physical_cores,
			"thread_warning": thread_warning,
		}
	except httpx.TimeoutException:
		return {"tier": tier, "model": model_name, "error": "Timeout (120s)"}
	except Exception as e:
		# tier is validated against tier_map allow-list above; safe to log
		logger.error("LLM benchmark failed (tier=%s): %s", tier.replace('\n', ' ').replace('\r', ' '), e)
		return {"tier": tier, "model": model_name, "error": "Benchmark failed"}


# --- Translations ---
@router.get("/translations")
async def get_translations_endpoint(db: AsyncSession = Depends(get_db)):
	"""Return the full i18n translation dict for the user's configured language."""
	from app.services.translations import get_translations
	res = await db.execute(select(Person).where(Person.circle_type == "identity"))
	me = res.scalar_one_or_none()
	lang = (me.language if me and me.language else "en")
	return {
		"lang": lang,
		"keys": get_translations(lang)
	}


# --- System Status ---
@router.get("/system")
async def get_system_status(db: AsyncSession = Depends(get_db)):
    """Deep health check of all OS subsystems."""
    from app.services.llm import last_model_used
    from app.services.memory import get_memory_stats

    try:
        mem_stats = await get_memory_stats()
    except Exception:
        mem_stats = {"points": 0}

    # System RAM for health metrics
    ram = psutil.virtual_memory()
    ram_total_gb = round(ram.total / (1024**3), 1)
    ram_used_pct = ram.percent

    # Identity Health
    res_people = await db.execute(select(Person).where(Person.circle_type == "identity"))
    identity_set = res_people.scalar_one_or_none() is not None

    # DNS Health — test Pi-hole can resolve open.zero.
    # Pi-hole runs network_mode:host; UFW blocks port 53 from Docker bridge
    # subnets (Tailscale-only). Run dig inside the pihole container via docker
    # exec, which the backend can do via its mounted Docker socket.
    dns_ok = False
    try:
        dig = subprocess.run(
            ["docker", "exec", "openzero-pihole-1", "dig",
             "@127.0.0.1", "open.zero", "+short", "+time=2", "+tries=1"],
            capture_output=True, text=True, timeout=8
        )
        if dig.returncode == 0 and dig.stdout.strip():
            dns_ok = True
            dns_detail = dig.stdout.strip().split("\n")[0]
        else:
            dns_detail = "no answer"
    except FileNotFoundError:
        dns_detail = "docker not found"
    except Exception as e:
        logger.warning("DNS health check failed: %s", e)
        dns_detail = "check failed"

    return {
        "status": "online",
        "llm_provider": settings.LLM_PROVIDER,
        "llm_model": last_model_used.get() or settings.LLM_MODEL_STANDARD,
        "memory_points": mem_stats.get("points", 0),
        "identity_active": identity_set,
        "dns_ok": dns_ok,
        "dns_detail": dns_detail,
        "ram_total_gb": ram_total_gb,
        "ram_used_pct": ram_used_pct,
        "timestamp": datetime.datetime.now().isoformat()
    }
