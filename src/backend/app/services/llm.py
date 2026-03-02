"""
Intelligence Service (LLM Integration)
--------------------------------------
This module acts as the 'brain' of openZero. It abstracts away the complexity 
of different LLM providers (Ollama, Groq, OpenAI) and manages the system 
persona 'Z'.

Core Functions:
- Context preparation: Merging memory, calendar, and project status.
- Provider fallback: Gracefully handling local engine timeouts.
- Character consistency: Enforcing the 'Agent Operator' persona.
"""

import httpx
from datetime import datetime
import pytz
from contextvars import ContextVar
import uuid
from app.config import settings
from app.services.agent_actions import AVAILABLE_TOOLS
from langchain_ollama import ChatOllama
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langgraph.prebuilt import create_react_agent

# Track the model used for the current request context
last_model_used: ContextVar[str] = ContextVar("last_model_used", default="Ollama")

# Lean system prompt for conversational messages (no action tag docs)
SYSTEM_PROMPT_CHAT = """You are Z — the privacy first personal AI agent.
You are not a generic assistant. You are an agent operator — sharp, warm, and direct.

CORE RESPONSE RULE:
- **ALWAYS begin EVERY response with exactly the current time and day.**
  Format: "[Time] - [Day] \n"
  Example: "{current_time}\nHello {user_name}..."
- **MATCH THE REQUEST TYPE**:
  - For **task confirmations**: be brief. "Done — task added."
  - For **creative/speculative requests**: give a real, engaged, thoughtful response.
  - For **questions**: answer directly and specifically.
  - For **conversation**: be warm and human.
- **ZERO FILLER**: No "Of course!", "I understand", "Sure".
- **NO TAG TALK**: Never explain what you have stored or learned unless explicitly asked.

Your Persona & Behavior:
- You are talking to {user_name}. Be direct but professional.
- **TIME AWARENESS**: Current time is {current_time}.
- **ZERO HALLUCINATION**: ONLY report facts explicitly present in the data you receive.
  - NEVER invent events, meetings, tasks, or project names not in context.
  - If context is empty for a section, say "nothing to report".

Keep it tight. Mission first. """

# Extended prompt with action tag documentation (only for agent path)
ACTION_TAG_DOCS = """
Semantic Action Tags (Exact Format Required):
- Create Task: `[ACTION: CREATE_TASK | BOARD: name | LIST: name | TITLE: text]`
  (Default board: "Boards", default list: "Today")
- Create Project: `[ACTION: CREATE_PROJECT | NAME: text | DESCRIPTION: text]`
- Create Board: `[ACTION: CREATE_BOARD | PROJECT_ID: id | NAME: text]`
- Create Event: `[ACTION: CREATE_EVENT | TITLE: text | START: YYYY-MM-DD HH:MM | END: YYYY-MM-DD HH:MM]`
- Add Person: `[ACTION: ADD_PERSON | NAME: text | RELATIONSHIP: text | CONTEXT: text | CIRCLE: inner/close]`
- Learn Information: `[ACTION: LEARN | TEXT: factual statement]`
- High Proximity Tracking: `[ACTION: PROXIMITY_TRACK | TASKS: item1; item2 | BREAKDOWN: task1 [ends HH:MM]; task2 [ends HH:MM] | END: YYYY-MM-DD HH:MM]`

Rules:
- Use tags ONLY when the user **explicitly** requests an action.
- **NEVER** use tags for hypothetical scenarios or suggestions.
- Tags are INVISIBLE to the user. Never mention them.
- Place tags on a NEW LINE at the very end of your message.
- Only use LEARN for new, permanent facts. Not for trivial observations.
"""

# Global client for connection pooling
_http_client = httpx.AsyncClient(timeout=300.0)

def build_system_prompt(user_name: str, user_profile: dict) -> tuple[str, str, str]:
	user_tz = pytz.timezone(settings.USER_TIMEZONE)
	def get_day_suffix(day):
		if 11 <= day <= 13: return 'th'
		return {1: 'st', 2: 'nd', 3: 'rd'}.get(day % 10, 'th')
	
	now = datetime.now(user_tz)
	day_with_suffix = f"{now.day}{get_day_suffix(now.day)}"
	simplified_time = f"{now.strftime('%H:%M')} - {day_with_suffix}"
	
	user_id_context = ""
	if user_profile:
		fields = []
		if user_profile.get("birthday"): fields.append(f"Birthday: {user_profile['birthday']}")
		if user_profile.get("gender"): fields.append(f"Gender: {user_profile['gender']}")
		if user_profile.get("residency"): fields.append(f"Residency: {user_profile['residency']}")
		if user_profile.get("work_times"): fields.append(f"Work Schedule: {user_profile['work_times']}")
		if user_profile.get("briefing_time"): fields.append(f"Preferred Briefing: {user_profile['briefing_time']}")
		if user_profile.get("context"): fields.append(f"LIFE GOALS & VALUES: {user_profile['context']}")
		if fields:
			user_id_context = "\nSUBJECT ZERO PROFILE (HIGH CONTEXT):\n" + "\n".join(fields)

	formatted_system_prompt = SYSTEM_PROMPT_CHAT.format(
		current_time=simplified_time,
		user_name=user_name
	) + user_id_context
	
	context_header = f"Current Local Time (Raw): {now.strftime('%A, %Y-%m-%d %H:%M:%S %Z')}\n"
	context_header += f"Current Formatted Time (Use This): {simplified_time}\n\n"
	
	return formatted_system_prompt, context_header, simplified_time

async def chat(
	user_message: str, 
	system_override: str = None, 
	provider: str = None, 
	model: str = None,
	**kwargs
) -> str:
	user_name = kwargs.get("user_name", "User")
	user_profile = kwargs.get("user_profile", {})
	
	# Only build from scratch if no override provided (avoids double-building)
	if system_override:
		system_prompt = system_override
	else:
		formatted_system_prompt, context_header, simplified_time = build_system_prompt(user_name, user_profile)
		system_prompt = context_header + formatted_system_prompt
	
	provider = (provider or settings.LLM_PROVIDER).lower()
	client = _http_client

	# --- Model Selection Logic (Dynamic Scaling) ---
	target_model = model
	if not target_model and provider == "ollama":
		# Categories needing 'Smart' model (8B)
		complex_keywords = ["plan", "reason", "strategic", "complex", "code", "math", "summarize session", "briefing", "mission", "campaign"]
		msg_len = len(user_message) if user_message else 0
		is_complex = any(kw in user_message.lower() for kw in complex_keywords) if user_message else False
		# Default to FAST (3B). Only use SMART (8B) for True strategy or very large queries.
		target_model = settings.OLLAMA_MODEL_SMART if (is_complex or msg_len > 1000) else settings.OLLAMA_MODEL_FAST

	# --- Option A: Local Ollama ---
	if provider == "ollama":
		import asyncio
		target_model = target_model or settings.OLLAMA_MODEL_FAST
		last_model_used.set(target_model)
		print(f"DEBUG: Calling Ollama with model: {target_model} (Reasoning Scaled)")
		
		last_err = None
		for attempt in range(3):
			try:
				response = await client.post(
					f"{settings.OLLAMA_BASE_URL}/api/chat",
					json={
						"model": target_model,
						"messages": [
							{"role": "system", "content": system_prompt},
							{"role": "user", "content": user_message},
						],
						"stream": False,
						"options": {
							"num_ctx": 6144 if target_model == settings.OLLAMA_MODEL_FAST else 8192,
							"temperature": 0.2,
							"num_predict": 768,
							"top_k": 20,
							"top_p": 0.9
						},
						"keep_alive": -1
					},
					timeout=600.0
				)
				response.raise_for_status()
				data = response.json()
				return data.get("message", {}).get("content", "No response from Ollama.")
			except httpx.ReadTimeout:
				last_err = "I'm still initializing my local core. One moment while I synchronize my reasoning parameters."
				if attempt < 2:
					print(f"⌛ Ollama timeout (attempt {attempt+1}/3). Retrying in 5s...")
					await asyncio.sleep(5)
				continue
			except Exception as e:
				return f"Error connecting to Ollama: {str(e)}"
		
		return last_err

	# --- Option B: Groq (Ultra-Fast Cloud API) ---
	elif provider == "groq":
		target_model = target_model or settings.GROQ_MODEL
		last_model_used.set(f"Groq: {target_model}")
		try:
			response = await client.post(
				"https://api.groq.com/openai/v1/chat/completions",
				headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}"},
				json={
					"model": model or "llama-3.1-70b-versatile",
					"messages": [
						{"role": "system", "content": system_prompt},
						{"role": "user", "content": user_message},
					],
				},
			)
			response.raise_for_status()
			data = response.json()
			return data.get("choices", [{}])[0].get("message", {}).get("content", "No response from Groq.")
		except Exception as e:
			return f"Error connecting to Groq: {str(e)}"

	# --- Option C: OpenAI ---
	elif provider == "openai":
		try:
			response = await client.post(
				"https://api.openai.com/v1/chat/completions",
				headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
				json={
					"model": model or "gpt-4o",
					"messages": [
						{"role": "system", "content": system_prompt},
						{"role": "user", "content": user_message},
					],
				},
			)
			response.raise_for_status()
			data = response.json()
			return data.get("choices", [{}])[0].get("message", {}).get("content", "No response from OpenAI.")
		except Exception as e:
			return f"Error connecting to OpenAI: {str(e)}"

		return f"Unknown LLM provider: {provider}"

async def chat_with_context(
	user_message: str, 
	history: list = None,
	include_projects: bool = False,
	include_people: bool = True
) -> str:
	"""
	Wraps the standard chat with a rich snapshot of the user's world.
	This ensures Z always knows who matters and what's being built.
	"""
	import asyncio
	import time
	from app.models.db import AsyncSessionLocal, Person
	from sqlalchemy import select
	from app.services.memory import semantic_search
	
	start_time = time.time()

	async def fetch_people():
		# Always fetch identity (needed for user_name/profile), but skip circle context for trivial messages
		try:
			async with AsyncSessionLocal() as session:
				result = await session.execute(select(Person))
				people = result.scalars().all()
				identity_name = "User"
				user_profile = {}
				if people:
					ident = next((p for p in people if p.circle_type == "identity"), None)
					if ident: 
						identity_name = ident.name
						user_profile = {
							"name": ident.name,
							"birthday": ident.birthday,
							"gender": ident.gender,
							"residency": ident.residency,
							"work_times": ident.work_times,
							"briefing_time": ident.briefing_time,
							"context": ident.context
						}
					
					# Skip full circle context for trivial/short messages
					if not include_people or len(user_message.strip()) < 20:
						return "", identity_name, user_profile
					
					def _birthday_tag(p):
						if not p.birthday: return ""
						try:
							import datetime as _dt
							today = _dt.date.today()
							parts = p.birthday.split(".")
							if len(parts) == 3:
								day, month = int(parts[0]), int(parts[1])
								next_bday = _dt.date(today.year, month, day)
								if next_bday < today:
									next_bday = _dt.date(today.year + 1, month, day)
								days = (next_bday - today).days
								if days <= 30:
									return f" ⚠️ BIRTHDAY IN EXACTLY {days} DAYS"
						except Exception: pass
						return ""
					
					inner = [f"- {p.name} ({p.relationship}){_birthday_tag(p)}" for p in people if p.circle_type == "inner"]
					close = [f"- {p.name} ({p.relationship}){_birthday_tag(p)}" for p in people if p.circle_type == "close"]
					
					context = ""
					if inner: context += "INNER CIRCLE:\n" + "\n".join(inner) + "\n"
					if close: context += "CLOSE CIRCLE:\n" + "\n".join(close)
					return context[:2000], identity_name, user_profile
				return "", identity_name, {}
		except Exception:
			return "", "User", {}

	async def fetch_projects():
		if not include_projects: return ""
		# Only fetch project tree for mission-related messages — avoids Planka round-trip on simple chat
		mission_keywords = ["task", "board", "status", "mission", "tree", "project", "plan", "build"]
		if not any(kw in user_message.lower() for kw in mission_keywords):
			return ""
			
		try:
			from app.services.planka import get_project_tree
			tree = await get_project_tree(as_html=False)
			if tree and len(tree) > 3000:
				tree = tree[:3000] + "... [Project Tree Truncated]"
			return f"PROJECT MISSION CONTROL:\n{tree}"
		except Exception:
			return "PROJECTS: (Board integration unavailable)"

	async def fetch_memories():
		# Skip memory search for trivial messages
		if len(user_message.strip()) < 15:
			return ""
		try:
			result = await semantic_search(user_message, top_k=3)
			if result and "No memories found" not in result and "Memory system" not in result:
				return f"RELEVANT MEMORIES:\n{result}"
			return ""
		except Exception as e:
			print(f"DEBUG: Memory fetch error: {e}")
			return ""

	try:
		# Execute all context gatherers in parallel
		(people_p, user_name, user_profile), project_p, memory_p = await asyncio.gather(
			fetch_people(),
			fetch_projects(),
			fetch_memories()
		)

		# Assemble context (people, projects, memories)
		full_prompt = "\n\n".join(filter(None, [
			people_p, 
			project_p, 
			memory_p
		]))
		
		# Now that we have the real user_name and user_profile from DB, build the system prompt
		formatted_system_prompt, _, _ = build_system_prompt(user_name, user_profile)
		
		print(f"DEBUG: Context gathered in {time.time() - start_time:.2f}s")

		# Model selection
		complex_keywords = ["plan", "reason", "strategic", "complex", "code", "math", "summarize session", "briefing", "mission", "campaign"]
		msg_len = len(user_message) if user_message else 0
		is_complex = any(kw in user_message.lower() for kw in complex_keywords) if user_message else False
		target_model = settings.OLLAMA_MODEL_SMART if (is_complex or msg_len > 1000) else settings.OLLAMA_MODEL_FAST
		last_model_used.set(target_model)

		# Only use the LangGraph ReAct agent when the user is explicitly requesting a tool action.
		# For all conversational messages, go direct to chat() — faster and no friction errors.
		TOOL_INTENT_KEYWORDS = [
			"create task", "add task", "new task", "make a task",
			"create event", "schedule", "set a reminder", "remind me",
			"create project", "new project", "add person", "remember that",
			"note that", "learn that", "store this", "track this",
		]
		needs_agent = any(kw in user_message.lower() for kw in TOOL_INTENT_KEYWORDS)

		if needs_agent:
			print(f"DEBUG: Tool intent detected — using LangGraph agent ({target_model})")
			llm = ChatOllama(
				base_url=settings.OLLAMA_BASE_URL,
				model=target_model,
				timeout=120.0,
				num_ctx=6144 if target_model == settings.OLLAMA_MODEL_FAST else 8192,
				temperature=0.2,
				keep_alive=-1
			)
			agent_executor = create_react_agent(llm, AVAILABLE_TOOLS)
			# Include action tag docs only for agent path
			rich_system_prompt = f"{formatted_system_prompt}\n{ACTION_TAG_DOCS}\n\n{full_prompt}"
			messages = [SystemMessage(content=rich_system_prompt)]
			for h in (history or []):
				content = h.get('content', '')
				if h.get("role") == "user":
					messages.append(HumanMessage(content=content))
				else:
					# Only truncate Z's responses
					if len(content) > 1200:
						content = content[:1200] + "... [Truncated]"
					messages.append(AIMessage(content=content))
			messages.append(HumanMessage(content=user_message))

			result = await agent_executor.ainvoke({"messages": messages}, config={"configurable": {"thread_id": str(uuid.uuid4())}})
			reply = result["messages"][-1].content

			# If agent returned an error string, fall through to direct chat
			_AGENT_ERROR_MARKERS = ["encountered friction", "thread was dropped", "local core is still active", "initializing my local core"]
			if not any(m in reply.lower() for m in _AGENT_ERROR_MARKERS):
				return reply
			print(f"DEBUG: Agent returned error string, falling back to direct chat")

		# Direct chat path — conversational messages and agent fallback
		print(f"DEBUG: Direct chat with model: {target_model}")
		history_text = ""
		if history:
			history_lines = []
			for m in history[-8:]:
				role = "User" if m.get("role") == "user" else "Z"
				raw = m.get('content', '') or ""
				# Keep user messages in full (they carry intent); only truncate Z's verbose output
				content = raw if role == "User" else raw[:300]
				history_lines.append(f"{role}: {content}")
			history_text = "RECENT CONVERSATION:\n" + "\n".join(history_lines)

		context_injection = "\n\n".join(filter(None, [full_prompt, history_text]))
		system_with_context = f"{formatted_system_prompt}\n\n{context_injection}" if context_injection else formatted_system_prompt
		return await chat(
			user_message,
			system_override=system_with_context,
			user_name=user_name,
			user_profile=user_profile,
			model=target_model
		)
	except Exception as e:
		print("DEBUG: chat_with_context failed, falling back to bare chat:", e)
		return await chat(
			user_message,
			system_override=formatted_system_prompt if 'formatted_system_prompt' in locals() else None,
			user_name=user_name if 'user_name' in locals() else "User",
			user_profile=user_profile if 'user_profile' in locals() else {},
			model=target_model if 'target_model' in locals() else settings.OLLAMA_MODEL_FAST
		)

async def generate_context_proposal(query: str) -> dict:
	"""Use Local LLM to identify relevant information for the user to approve."""
	from app.services.memory import semantic_search
	memories = await semantic_search(query, top_k=3)
	
	return {
		"summary": f"• Local memories related to: '{query[:30]}...'",
		"context_data": f"Relevant Memories:\n{memories}"
	}

async def summarize_email(snippet: str) -> str:
	"""Generate a one-line summary of an email snippet."""
	prompt = f"Summarize this email in one sentence:\n\n{snippet}"
	return await chat(prompt, system_override="You are a concise email summarizer.")
async def detect_calendar_events(text: str) -> list[dict]:
	"""Analyze text for potential calendar events. Returns a list of structured events."""
	import json
	import re
	
	prompt = f"""Analyze the following text and extract any potential calendar events (appointments, meetings, deadlines, celebrations).
If events are found, provide them in the following JSON format:
{{
  "events": [
	{{
	  "summary": "Event Title",
	  "start": "YYYY-MM-DD HH:MM",
	  "end": "YYYY-MM-DD HH:MM (estimate 1 hour if not specified)",
	  "description": "Brief context"
	}}
  ]
}}
If no event is found, return {{"events": []}}.

TEXT:
{text}

RULES:
- Today's date is: {datetime.now(pytz.timezone(settings.USER_TIMEZONE)).strftime('%Y-%m-%d')} ({datetime.now(pytz.timezone(settings.USER_TIMEZONE)).strftime('%A')})
- Use YYYY-MM-DD HH:MM format.
- If no year/time is specified, use common sense based on today's date.
- Output MUST be valid JSON and nothing else.
"""
	try:
		response = await chat(prompt, system_override="You are a data extraction agent. Return ONLY JSON.")
		# Sometimes LLMs wrap JSON in backticks
		clean_json = re.sub(r'```json\n?|\n?```', '', response).strip()
		data = json.loads(clean_json)
		return data.get("events", [])
	except Exception as e:
		print(f"DEBUG: Calendar detection failed: {e}")
		return []
