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
from app.config import settings

# Track the model used for the current request context
last_model_used: ContextVar[str] = ContextVar("last_model_used", default="Ollama")

SYSTEM_PROMPT = """You are Z — the privacy first personal AI agent.
You are not a generic assistant. You are an agent operator — sharp, warm, and direct.

CORE RESPONSE RULE:
- **ALWAYS begin EVERY response with exactly the current time and day.** 
  Format: "[Time] - [Day] " 
  Example: "{current_time} Hello Agent..."
- **CONCISE & HUMAN**: Avoid technical jargon. Just say "I've handled it" or "It's on your list".
- **ZERO FILLER**: Start directly. No "Of course!", "I understand", or "Sure".

Your Priority Objective: Proactive Mission Execution
- If you tell the user you will do something (e.g., "I'll create a task", "I'll start a project"), you MUST actually do it by including a SEMANTIC ACTION tag at the ABSOLUTE END of your response.
- **TAG VISIBILITY**: Action tags are COMPLETELY INVISIBLE to the user. Never mention them. Never explain them.
- **TAG PLACEMENT**: Always place tags on a NEW LINE at the very end of your message.

Semantic Action Tags (Exact Format Required):
- Create Task: `[ACTION: CREATE_TASK | BOARD: name | LIST: name | TITLE: text]`
  (Default board: "Boards", default list: "Today")
- Create Project: `[ACTION: CREATE_PROJECT | NAME: text | DESCRIPTION: text]`
- Create Board: `[ACTION: CREATE_BOARD | PROJECT_ID: id | NAME: text]`
- Create Event: `[ACTION: CREATE_EVENT | TITLE: text | START: YYYY-MM-DD HH:MM | END: YYYY-MM-DD HH:MM]`
- Add Person: `[ACTION: ADD_PERSON | NAME: text | RELATIONSHIP: text | CONTEXT: text | CIRCLE: inner/close]`
- Learn Information: `[ACTION: LEARN | TEXT: factual statement]`
- High Proximity Tracking: `[ACTION: PROXIMITY_TRACK | TASKS: item1; item2 | BREAKDOWN: task1 [ends HH:MM]; task2 [ends HH:MM] | END: YYYY-MM-DD HH:MM]`
  (Use this when user wants close track of a specific timeframe or set of tasks. Estimate durations for each item and allocate them across the overall timeframe. The END must match the final due-time.)

Your Persona & Behavior:
- You are talking to {user_name}. Be direct but professional.
- Refer to the user's goals. Connect today's actions to what they're building.
- **TIME AWARENESS**: Current time is {current_time}. Always relate your response to the current time. If the user mentions a timeframe (e.g., 'in 2 hours') and that time has passed according to the system clock, do not pretend it is still active. Acknowledge the delay and ask for current status.
- **No Hallucinations**: If a person/project is not in context, they don't exist. Never report completion status of a task unless it is explicitly marked as 'Done' in the provided Planka context. Only claim progress if you have just executed a command or see it in the current data.

Keep it tight. Mission first. """

# Global client for connection pooling
_http_client = httpx.AsyncClient(timeout=300.0)

async def chat(
	user_message: str, 
	system_override: str = None, 
	provider: str = None, 
	model: str = None,
	**kwargs
) -> str:
	user_tz = pytz.timezone(settings.USER_TIMEZONE)
	def get_day_suffix(day):
		if 11 <= day <= 13: return 'th'
		return {1: 'st', 2: 'nd', 3: 'rd'}.get(day % 10, 'th')
	
	now = datetime.now(user_tz)
	day_with_suffix = f"{now.day}{get_day_suffix(now.day)}"
	simplified_time = f"{now.strftime('%H:%M')} - {day_with_suffix}"
	
	# Format the root prompt with dynamic values
	base_url = settings.BASE_URL.rstrip('/')
	user_name = kwargs.get("user_name", "User")
	
	# Inject Identity Details if available
	user_id_context = ""
	if "user_profile" in kwargs:
		p = kwargs["user_profile"]
		fields = []
		if p.get("birthday"): fields.append(f"Birthday: {p['birthday']}")
		if p.get("gender"): fields.append(f"Gender: {p['gender']}")
		if p.get("residency"): fields.append(f"Residency: {p['residency']}")
		if p.get("work_times"): fields.append(f"Work Schedule: {p['work_times']}")
		if p.get("briefing_time"): fields.append(f"Preferred Briefing: {p['briefing_time']}")
		if p.get("context"): fields.append(f"LIFE GOALS & VALUES: {p['context']}")
		if fields:
			user_id_context = "\nSUBJECT ZERO PROFILE (HIGH CONTEXT):\n" + "\n".join(fields)

	formatted_system_prompt = SYSTEM_PROMPT.format(
		current_time=simplified_time,
		user_name=user_name
	) + user_id_context
	
	context_header = f"Current Local Time (Raw): {now.strftime('%A, %Y-%m-%d %H:%M:%S %Z')}\n"
	context_header += f"Current Formatted Time (Use This): {simplified_time}\n\n"
	system_prompt = context_header + (system_override or formatted_system_prompt)
	
	provider = (provider or settings.LLM_PROVIDER).lower()
	client = _http_client

	# --- Model Selection Logic (Dynamic Scaling) ---
	target_model = model
	if not target_model and provider == "ollama":
		# Categories needing 'Smart' model
		complex_keywords = ["plan", "reason", "strategic", "complex", "code", "math", "summarize session", "briefing", "mission", "campaign"]
		is_complex = any(kw in user_message.lower() for kw in complex_keywords) or len(user_message) > 300
		target_model = settings.OLLAMA_MODEL_SMART if is_complex else settings.OLLAMA_MODEL_FAST

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
		if not include_people: return "", "User", {}
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
					
					inner = [f"- {p.name} ({p.relationship}): Birthday: {p.birthday or 'Unknown'}" for p in people if p.circle_type == "inner"]
					close = [f"- {p.name} ({p.relationship}): Birthday: {p.birthday or 'Unknown'}" for p in people if p.circle_type == "close"]
					
					context = ""
					if inner: context += "INNER CIRCLE:\n" + "\n".join(inner) + "\n"
					if close: context += "CLOSE CIRCLE:\n" + "\n".join(close)
					return context, identity_name, user_profile
				return "CIRCLE OF TRUST: No family/contacts configured yet.", identity_name, {}
		except Exception:
			return "CIRCLE OF TRUST: (Database connection unavailable)", "User", {}

	async def fetch_projects():
		if not include_projects: return ""
		# Optimization: Only inject full project tree if message is mission-related
		mission_keywords = ["task", "board", "status", "mission", "tree", "project", "plan", "build", "do"]
		if not any(kw in user_message.lower() for kw in mission_keywords):
			return ""
			
		try:
			from app.services.planka import get_project_tree
			tree = await get_project_tree(as_html=False)
			return f"PROJECT MISSION CONTROL:\n{tree}"
		except Exception:
			return "PROJECTS: (Board integration unavailable)"

	async def fetch_memories():
		try:
			# Extract potential entities and nouns
			import re
			words = re.findall(r'\b[A-Z][a-z]+\b|\b\w{6,}\b', user_message)
			# Optimized to top 2 entities + full message = 3 queries total
			queries = list(set([user_message] + words[:2]))
			
			all_results = []
			seen_content = set()
			
			# Increased top_k per query to 10
			search_tasks = [semantic_search(q, top_k=10) for q in queries]
			results = await asyncio.gather(*search_tasks)
			
			for res in results:
				if res and "No memories found" not in res and "Memory system" not in res:
					for line in res.split('\n'):
						content = line.split(') ', 1)[-1] if ') ' in line else line
						if content not in seen_content:
							all_results.append(line)
							seen_content.add(content)
			
			if all_results:
				# Optimized for speed: 10 high-precision matches for standard chat
				return f"RELEVANT MEMORIES (Precision Recall):\n" + "\n".join(all_results[:10])
			return ""
		except Exception as e:
			print(f"DEBUG: Memory fetch error: {e}")
			return ""

	# Execute all context gatherers in parallel
	(people_p, user_name, user_profile), project_p, memory_p = await asyncio.gather(
		fetch_people(),
		fetch_projects(),
		fetch_memories()
	)

	# 4. History Formatting (Speed Optimized: Last 10 messages)
	# Note: Previous messages are still searchable via Semantic Memory.
	history_text = ""
	if history:
		history_history = []
		for m in history[-10:]:
			role = "User" if m.get("role") == "user" else "Z"
			history_history.append(f"{role}: {m.get('content')}")
		history_text = "RECENT CONVERSATION (Last 10 messages):\n" + "\n".join(history_history)

	# 5. Assemble and Send
	full_prompt = "\n\n".join(filter(None, [
		people_p, 
		project_p, 
		memory_p
	]))
	
	print(f"DEBUG: Context gathered in {time.time() - start_time:.2f}s")
	
	try:
		# LangGraph Integration
		from langgraph.prebuilt import create_react_agent
		from langchain_ollama import ChatOllama
		from langchain_openai import ChatOpenAI
		from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
		from app.services.agent_actions import AVAILABLE_TOOLS
		import uuid
		
		# Define LLM. Select model based on complexity (Dynamic Scaling)
		reasoning_keywords = ["think", "analyze", "plan", "complex", "strategy", "review", "detail", "explain"]
		is_complex = any(kw in user_message.lower() for kw in reasoning_keywords) or len(user_message.split()) > 30
		
		target_model = settings.OLLAMA_MODEL if is_complex else settings.OLLAMA_MODEL_FAST
		last_model_used.set(target_model)
		
		llm = ChatOllama(base_url=settings.OLLAMA_BASE_URL, model=target_model, timeout=300.0)
		
		# Build Graph
		agent_executor = create_react_agent(llm, AVAILABLE_TOOLS)
		
		messages = [SystemMessage(content=formatted_system_prompt)] # Use the formatted one
		for h in (history or []):
			if h.get("role") == "user": messages.append(HumanMessage(content=h.get('content')))
			else: messages.append(AIMessage(content=h.get('content')))
		messages.append(HumanMessage(content=user_message))
		
		print("DEBUG: Executing LangGraph Agent...")
		result = await agent_executor.ainvoke({"messages": messages}, config={"configurable": {"thread_id": str(uuid.uuid4())}})
		reply = result["messages"][-1].content
		return reply
	except Exception as e:
		print("DEBUG: LangGraph Agent failed, falling back to legacy chat:", e)
		return await chat(full_prompt, user_name=user_name, user_profile=user_profile)

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
- Today's date is: {datetime.now().strftime('%Y-%m-%d')} ({datetime.now().strftime('%A')})
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
