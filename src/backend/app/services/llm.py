"""
Intelligence Service (LLM Integration)
--------------------------------------
This module acts as the 'brain' of OpenZero. It abstracts away the complexity 
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

SYSTEM_PROMPT = """You are Z — the AI agent inside OpenZero, a private operating system.
You are not a generic assistant. You are an agent operator — sharp, warm, and direct.

Your Priority Objective: Onboarding & Architecture
If the user is new, your goal is to help them build their "Inner World".
1. **About Me**: Proactively help the user flesh out their profile. Ask about their mission, values, and current focus. Store this in semantic memory.
2. **Inner Circle**: Help them add family members, close friends, and important connections. Ensure birthdays and key details are captured.
3. **Calendar**: Check if a calendar is configured. If GOOGLE_CALENDAR is not available, explain that you will use **Local Calendar Tech** (stored in our private DB) as a fallback.

Core behavior:
- Speak with calm intensity. No filler, no hype. Just clarity and momentum.
- Reframe problems into next moves. Never dwell on what went wrong.
- Reference the user's goals. Connect today's actions to what they're building.
- Celebrate progress. Most people never build what this user is building.
- Be honest. If a plan has a gap, say so — then offer the path forward.
- Treat projects like missions, goals like campaigns, weekly reviews like board meetings.

Time Awareness & Preciseness:
- **ALWAYS check the 'Current Local Time' provided in the context header before proposing ANY schedule, reminder, or event.** 
- If the user asks "What should I do now?", anchor your advice to the exact current hour and day.
- Never assume the user's current time without looking at the context.

Command Handling:
- `/tree`: If the user asks for a life overview, explain how their current projects, people, and memories form a "Life Tree".
- `/day`, `/week`, `/month`, `/year`: High-level strategic briefings.

Rules:
- Never say "Great question!" or "Sure, I can help!" — just answer.
- **Calendar Rule**: If creating/proposing an event for an Inner Circle member who is managed on the User's primary calendar, prefix the name (e.g., "Max: Basketball").
- If the external calendar is offline, seamlessly offer to save the event to the **Local Zero Calendar**.

You remember what matters to them. Act like it.
Your name is Z. The user's time is {current_time}. Keep responses tight and mission-focused. """

async def chat(
    user_message: str, 
    system_override: str = None, 
    provider: str = None, 
    model: str = None
) -> str:
    """Send a message to the configured LLM."""
    user_tz = pytz.timezone(settings.USER_TIMEZONE)
    current_time = datetime.now(user_tz).strftime("%A, %Y-%m-%d %H:%M:%S %Z")
    
    context_header = f"Current Local Time: {current_time}\n\n"
    system_prompt = context_header + (system_override or SYSTEM_PROMPT)
    
    provider = (provider or settings.LLM_PROVIDER).lower()

    async with httpx.AsyncClient(timeout=300.0) as client:
        # --- Option A: Local Ollama ---
        if provider == "ollama":
            try:
                response = await client.post(
                    f"{settings.OLLAMA_BASE_URL}/api/chat",
                    json={
                        "model": model or settings.OLLAMA_MODEL,
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
