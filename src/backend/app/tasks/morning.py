from app.services.automation import run_contextual_automation
from app.services.llm import chat
from app.services.planka import get_project_tree
from app.services.gmail import fetch_unread_emails
from app.services.calendar import fetch_calendar_events
from app.services.weather import get_weather_forecast
from app.services.tts import generate_speech
from app.api.telegram import send_notification, send_voice_message
from app.models.db import AsyncSessionLocal, Briefing, Project, Person
from sqlalchemy import select
import asyncio
import datetime

async def morning_briefing():
	"""Generate and store the daily morning briefing."""
	
	# 1. Zero-Noise Mode (Facts Only)
	
	# 2. Gather context
	async with AsyncSessionLocal() as session:
		people_result = await session.execute(select(Person))
		people = people_result.scalars().all()
	
	# --- Contextual Automation ---
	automation_actions = await run_contextual_automation(people)
	automation_summary = "\n".join([f"- {a}" for a in automation_actions]) if automation_actions else "No automated tasks created today."
	
	async def get_person_briefing_data(p: Person):
		data = f"- {p.name} ({p.relationship}): {p.context}"
		if p.birthday:
			data += f" | Birthday: {p.birthday}"
		return data

	inner_circle_tasks = [get_person_briefing_data(p) for p in people if p.circle_type == "inner"]
	close_circle_tasks = [get_person_briefing_data(p) for p in people if p.circle_type == "close"]
	
	inner_context_list = await asyncio.gather(*inner_circle_tasks)
	close_context_list = await asyncio.gather(*close_circle_tasks)
	
	inner_context = "\n".join(inner_context_list) if inner_context_list else "No primary family focus today."
	close_context = "\n".join(close_context_list) if close_context_list else "No specific friend connections planned."
	
	# 2.2 Gather Calendar & Weather Context
	try:
		calendar_events = await fetch_calendar_events(days_ahead=0)
	except Exception as ce:
		print(f"DEBUG: Calendar fetch during briefing skipped: {ce}")
		calendar_events = []

	calendar_summary_parts = []
	for e in calendar_events:
		time_str = e['start'].split('T')[1][:5] if 'T' in e['start'] else None
		if time_str == "00:00": time_str = None
		
		item = f"- {e['summary']}"
		if time_str: item += f" ({time_str})"
		calendar_summary_parts.append(item)
	
	calendar_summary = "\n".join(calendar_summary_parts) if calendar_summary_parts else "No events scheduled for today."
	
	# Simple travel detection
	detected_location = None
	for event in calendar_events:
		summary = event['summary'].lower()
		if any(kw in summary for kw in ["flight to", "trip to", "stay in", "travel to", "moving to"]):
			for kw in ["to ", "in "]:
				if kw in summary:
					detected_location = event['summary'].split(kw.strip())[-1].strip()
					break
		if detected_location: break
	
	weather_report = await get_weather_forecast(detected_location)
	
	tree = await get_project_tree(as_html=False)
	
	# 2.3 Gather latest email context
	from app.models.db import EmailSummary
	async with AsyncSessionLocal() as session:
		# Get summaries not yet included
		res = await session.execute(select(EmailSummary).where(EmailSummary.included_in_briefing == False))
		summaries = res.scalars().all()
		
		if summaries:
			email_summary = "\n".join([f"- {s.sender}: {s.subject} {f'[{s.badge}]' if s.badge else ''} (Summary: {s.summary})" for s in summaries])
			# Mark as read
			for s in summaries: s.included_in_briefing = True
			await session.commit()
		else:
			# Fallback to direct fetch if no cached summaries
			emails = await fetch_unread_emails(max_results=5)
			email_summary = "\n".join([f"- {e['from']}: {e['subject']}" for e in emails]) if emails else "No new emails."
	
	full_prompt = (
		"Z, morning briefing. Summarize the mission status based on CONTEXT.\n\n"
		f"CONTEXT:\n"
		f"AUTOMATED SYSTEM ACTIONS (Tasks created based on Circle Calendars):\n{automation_summary}\n\n"
		f"INNER CIRCLE (Family/Care):\n{inner_context}\n\n"
		f"CLOSE CIRCLE (Friends/Social):\n{close_context}\n\n"
		f"CALENDAR TODAY:\n{calendar_summary}\n\n"
		f"WEATHER FORECAST:\n{weather_report}\n\n"
		f"PROJECTS:\n{tree}\n\n"
		f"LATEST EMAILS:\n{email_summary}\n\n"
		"Format the output beautifully for Telegram. In the briefing, proactively suggest actions "
		"to maintain deep connections with both circles ONLY using information present in the CONTEXT. "
		"IF CONTEXT IS EMPTY for a section, acknowledge it or skip it. NEVER invent family names, tasks, or projects."
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
		briefing = Briefing(type="day", content=content)
		session.add(briefing)
		await session.commit()
	
	# 5. Send to Telegram (Proactive delivery)
	from app.config import settings
	await send_notification(f"☀️ *Good Morning!*\n\n{content}\n\n🔗 [Dashboard]({settings.BASE_URL})")
	if audio_briefing:
		await send_voice_message(audio_briefing, caption="🎙️ Audio Briefing")

	return content
