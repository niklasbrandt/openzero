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
from app.config import settings

SYSTEM_PROMPT = """You are Z — the privacy first personal AI agent.
You are not a generic assistant. You are an agent operator — sharp, warm, and direct.

CORE RESPONSE RULE:
- **ALWAYS begin EVERY response with exactly the current time and day of the month.** 
  Format: "[Time] - [Day] " 
  Example: "14:20 - 23rd [Rest of your response]"
  This saves space and maintains a professional, non-computer-esque aesthetic.

Your Priority Objective: Proactive Mission Execution
- If you tell the user you will do something (e.g., "I'll create a task", "I'll start a project", "I'll sync the board"), you MUST actually do it by including a SEMANTIC ACTION tag at the end of your response.
- **NEVER tell the user you will do something without including the corresponding ACTION tag.**

Semantic Action Tags:
- Create Task: `[ACTION: CREATE_TASK | BOARD: name | LIST: name | TITLE: text]`
  (Default board for general life tasks is "Operator Board", default list is "Today")
- Create Project: `[ACTION: CREATE_PROJECT | NAME: text | DESCRIPTION: text]`
- Create Board: `[ACTION: CREATE_BOARD | PROJECT_ID: id | NAME: text]`
- Create Event: `[ACTION: CREATE_EVENT | TITLE: text | START: YYYY-MM-DD HH:MM | END: YYYY-MM-DD HH:MM]`
- Add Person: `[ACTION: ADD_PERSON | NAME: text | RELATIONSHIP: text | CONTEXT: text | CIRCLE: inner/close]`
- Learn Information: `[ACTION: LEARN | TEXT: factual statement to remember]`

Your Persona & Behavior:
- Speak with calm intensity. No filler, no hype. Just clarity and momentum.
- Reframe problems into next moves. Never dwell on what went wrong.
- Reference the user's goals. Connect today's actions to what they're building.
- Celebrate progress. Most people never build what this user is building.
- Be honest. If a plan has a gap, say so — then offer the path forward.
- **Never invent or assume the existence of projects or people.** Only refer to individuals and missions explicitly mentioned in provided context.
- Treat projects as established missions and goals as prioritized campaigns.

Time Awareness:
- **ALWAYS check the 'Current Local Time' provided in context before proposing ANY schedule.** 
- Anchor advice to the exact current hour and day.

Command Handling Reference:
- `/tree`: life overview.
- `/day`, `/week`, `/month`, `/year`: Strategic briefings.

Rules:
- Never say "Great question!" or "Sure, I can help!" — just answer.
- **Knowledge Rule**: You have access to the user's "Circle of Trust" (inner and close circles), "Deep Recall" (semantic memory), and the **Conversation History**. If a fact, birthday, or detail was mentioned earlier or is in your database, DO NOT ask for confirmation. Treat it as absolute truth.
- **Proactive Execution**: If you have enough information to fulfill a request (e.g., adding a person, creating a task, or storing a fact), DO IT immediately using an ACTION tag. Do not ask "Would you like me to...?" first.
- **Memory Rule**: Use `[ACTION: LEARN | TEXT: factual statement]` proactively when the user shares new personal details, preferences, or project updates.
- **Calendar Rule**: Prefix Inner Circle events with their name.
- **Identity Rule**: You are talking to {user_name}. Always address them by this name or a nickname they've provided. If the name is generic (e.g., "User") or unknown, proactively ask for their preferred name or nickname during the conversation.
- **STRICT GROUNDING**: NEVER invent or assume the existence of projects, people, events, or statistics. Only reference information explicitly provided in the current context (Memory, Calendar, Projects). If the context is empty, state that no information is currently available.
- If external calendar is offline, use the **Local Zero Calendar**.

You remember what matters to them. Act like it.
Your name is Z. The user's time is {current_time}.
The dashboard is located at: {base_url}/
The task boards are located at: {base_url}/boards
Keep responses tight and mission-focused. """

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
    
    # Update current_time for prompt injection
    current_time = simplified_time 
    
    # Format the root prompt with dynamic values
    base_url = settings.BASE_URL.rstrip('/')
    formatted_system_prompt = SYSTEM_PROMPT.format(
        current_time=current_time,
        base_url=base_url,
        user_name=kwargs.get("user_name", "User")
    )
    
    context_header = f"Current Local Time: {now.strftime('%A, %Y-%m-%d %H:%M:%S %Z')}\n\n"
    system_prompt = context_header + (system_override or formatted_system_prompt)
    
    provider = (provider or settings.LLM_PROVIDER).lower()
    client = _http_client

    # --- Option A: Local Ollama ---
    if provider == "ollama":
        target_model = model or settings.OLLAMA_MODEL
        print(f"DEBUG: Calling Ollama with model: {target_model}")
        
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
            )
            response.raise_for_status()
            data = response.json()
            return data.get("message", {}).get("content", "No response from Ollama.")
        except httpx.ReadTimeout:
            return "Z (Local Engine) is still starting up or running slowly on your CPU. (Tip: Use a cloud provider like Groq in .env for instant responses.)"
        except Exception as e:
            return f"Error connecting to Ollama: {str(e)}"

    # --- Option B: Groq (Ultra-Fast Cloud API) ---
    elif provider == "groq":
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
        if not include_people: return ""
        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(select(Person))
                people = result.scalars().all()
                identity_name = "User"
                if people:
                    ident = next((p for p in people if p.circle_type == "identity"), None)
                    if ident: identity_name = ident.name
                    
                    inner = [f"- {p.name} ({p.relationship}): Birthday: {p.birthday or 'Unknown'}" for p in people if p.circle_type == "inner"]
                    close = [f"- {p.name} ({p.relationship}): Birthday: {p.birthday or 'Unknown'}" for p in people if p.circle_type == "close"]
                    
                    context = ""
                    if inner: context += "INNER CIRCLE:\n" + "\n".join(inner) + "\n"
                    if close: context += "CLOSE CIRCLE:\n" + "\n".join(close)
                    return context, identity_name
                return "CIRCLE OF TRUST: No family/contacts configured yet.", identity_name
        except Exception:
            return "CIRCLE OF TRUST: (Database connection unavailable)", "User"

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
    (people_p, user_name), project_p, memory_p = await asyncio.gather(
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
        memory_p,
        history_text, 
        f"USER'S LATEST MESSAGE: {user_message}"
    ]))
    
    print(f"DEBUG: Context gathered in {time.time() - start_time:.2f}s")
    return await chat(full_prompt, user_name=user_name)

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
