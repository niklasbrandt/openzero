from app.services.automation import run_contextual_automation
from app.services.llm import chat
from app.services.planka import get_project_tree
from app.services.gmail import fetch_unread_emails
from app.services.calendar import fetch_calendar_events
from app.services.tts import generate_speech
from app.api.telegram import send_notification, send_voice_message
from app.models.db import AsyncSessionLocal, Briefing, Project, Person
from sqlalchemy import select
import asyncio
import datetime

async def morning_briefing():
    """Generate and store the daily morning briefing."""
    
    # 1. Start with the Daily Mindsetter
    mindset_prompt = (
        "Z, start the morning briefing. First, lead with a small mindsetter exercise. "
        "Express 3 things we are thankful for today (generic but inspiring or based on my character). "
        "Then proceed with the actual briefing."
    )
    
    # 2. Gather context
    async with AsyncSessionLocal() as session:
        people_result = await session.execute(select(Person))
        people = people_result.scalars().all()
    
    # --- Contextual Automation ---
    automation_actions = await run_contextual_automation(people)
    automation_summary = "\n".join([f"- {a}" for a in automation_actions]) if automation_actions else "No automated tasks created today."
    
    async def get_person_briefing_data(p: Person):
        data = f"- {p.name} ({p.relationship}): {p.context}"
        if p.calendar_id:
            events = await fetch_calendar_events(calendar_id=p.calendar_id)
            if events:
                event_str = ", ".join([f"{e['summary']} ({e['start']})" for e in events])
                data += f" | Calendar: {event_str}"
            else:
                data += " | Calendar: No events today."
        return data

    inner_circle_tasks = [get_person_briefing_data(p) for p in people if p.circle_type == "inner"]
    close_circle_tasks = [get_person_briefing_data(p) for p in people if p.circle_type == "close"]
    
    inner_context_list = await asyncio.gather(*inner_circle_tasks)
    close_context_list = await asyncio.gather(*close_circle_tasks)
    
    inner_context = "\n".join(inner_context_list) if inner_context_list else "No primary family focus today."
    close_context = "\n".join(close_context_list) if close_context_list else "No specific friend connections planned."
    
    tree = await get_project_tree()
    emails = await fetch_unread_emails(max_results=5)
    
    email_summary = "\n".join([f"- {e['from']}: {e['subject']}" for e in emails]) if emails else "No new emails."
    
    full_prompt = (
        f"{mindset_prompt}\n\n"
        f"CONTEXT:\n"
        f"AUTOMATED SYSTEM ACTIONS (Tasks created based on Circle Calendars):\n{automation_summary}\n\n"
        f"INNER CIRCLE (Family/Care):\n{inner_context}\n\n"
        f"CLOSE CIRCLE (Friends/Social):\n{close_context}\n\n"
        f"PROJECTS:\n{tree}\n\n"
        f"LATEST EMAILS:\n{email_summary}\n\n"
        "Format the output beautifully for Telegram. In the briefing, proactively suggest actions "
        "to maintain deep connections with both circles (e.g. asking about homework, hobby progress, or suggesting a quick check-in call with a friend)."
    )
    
    # 3. Generate Briefing
    content = await chat(full_prompt)
    
    # --- Multi-Modal (TTS) ---
    audio_briefing = None
    try:
        # We strip some markdown characters for cleaner speech
        clean_text = content.replace("*", "").replace("#", "").replace("_", "")
        audio_briefing = await generate_speech(clean_text)
    except Exception as e:
        print(f"TTS Briefing generation failed: {e}")

    # 4. Store in Database for Dashboard
    async with AsyncSessionLocal() as session:
        briefing = Briefing(type="daily", content=content)
        session.add(briefing)
        await session.commit()
    
    # 5. Send to Telegram (Proactive delivery)
    await send_notification(f"☀️ *Good Morning!*\n\n{content}")
    if audio_briefing:
        await send_voice_message(audio_briefing, caption="🎙️ Audio Briefing")

    return content
