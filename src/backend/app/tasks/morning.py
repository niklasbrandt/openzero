from app.services.automation import run_contextual_automation
from app.services.llm import chat
from app.services.planka import get_project_tree
from app.services.gmail import fetch_unread_emails
from app.services.calendar import fetch_calendar_events
from app.services.weather import get_weather_forecast
from app.services.tts import generate_speech
from app.api.telegram import send_notification, send_voice_message, get_nav_markup
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
			try:
				# Parse birthday and compute exact days until next occurrence
				today = datetime.date.today()
				parts = p.birthday.split(".")
				if len(parts) == 3:
					day, month = int(parts[0]), int(parts[1])
					next_bday = datetime.date(today.year, month, day)
					if next_bday < today:
						next_bday = datetime.date(today.year + 1, month, day)
					days_until = (next_bday - today).days
					if days_until <= 30:
						data += f" | ⚠️ BIRTHDAY IN EXACTLY {days_until} DAYS ({p.birthday})"
					# If > 30 days away: do NOT mention birthday at all to prevent hallucination
			except Exception:
				pass  # Unparseable birthday format — skip silently
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
	
	# 2.4 Gather yesterday's new memories for quality review
	from app.services.memory import get_recent_memories
	recent_memories = await get_recent_memories(hours=24)
	memory_review = ""
	if recent_memories:
		memory_review = "\n".join([f"• {m['text']}" for m in recent_memories])
	
	full_prompt = (
		"Z, morning briefing. Summarize based ONLY on the CONTEXT below.\n"
		"STRICT RULES:\n"
		"- NEVER invent names, tasks, projects, or events not present in CONTEXT.\n"
		"- ONLY mention a birthday if CONTEXT explicitly contains '⚠️ BIRTHDAY IN EXACTLY'.\n"
		"- If a section is empty, skip it or say 'nothing to report'.\n"
		"- Do NOT summarize the NEW MEMORIES section — it will be appended separately.\n\n"
		f"AUTOMATED SYSTEM ACTIONS:\n{automation_summary}\n\n"
		f"INNER CIRCLE (Family/Care):\n{inner_context}\n\n"
		f"CLOSE CIRCLE (Friends/Social):\n{close_context}\n\n"
		f"CALENDAR TODAY:\n{calendar_summary}\n\n"
		f"WEATHER FORECAST:\n{weather_report}\n\n"
		f"PROJECTS:\n{tree}\n\n"
		f"LATEST EMAILS:\n{email_summary}\n"
	)
	
	# 3. Generate Briefing
	raw_content = await chat(full_prompt)
	
	# 3.2 Post-Processing & Cleanup
	from app.services.agent_actions import parse_and_execute_actions
	content, _ = await parse_and_execute_actions(raw_content)
	
	# 3.3 Append Memory Review (raw, not via LLM — user sees exactly what was stored)
	if memory_review:
		content += "\n\n🧠 *New Memories (Last 24h):*\n" + memory_review + "\n_Use /unlearn <topic> to remove incorrect memories._"
	
	# 3.4 Mental Yoga (configurable, rotates daily)
	from app.config import settings
	if settings.BRIEFING_MENTAL_YOGA:
		methods = [
			("🙏 Gratitude", "Name 3 specific things you are grateful for right now. Be concrete — not 'family' but 'the way Mom called yesterday to check in'."),
			("🎯 Intention Setting", "Set one clear intention for today. Not a task — an intention for HOW you want to show up. Example: 'I will be patient and present in every conversation.'"),
			("🔄 Cognitive Reframe", "Think of something that's been bothering you. Now reframe it: What's the hidden opportunity or lesson? Write the reframe in one sentence."),
			("🫁 Box Breathing", "Pause for 60 seconds. Breathe in for 4 counts, hold for 4, out for 4, hold for 4. Repeat 3 times. Notice how your body feels after."),
			("🌄 Visualization", "Close your eyes for 30 seconds. Picture your ideal version of today — how does it end? What does success look and feel like tonight?"),
			("🧘 Body Scan", "Starting from the top of your head, scan down slowly to your toes. Where do you feel tension? Breathe into that spot for 3 breaths and let it soften."),
			("💎 Affirmation", "Repeat this to yourself: 'I am exactly where I need to be. Today I take one step closer to who I'm becoming.' Now add your own sentence."),
			("🖐️ 5-4-3-2-1 Grounding", "Notice 5 things you can see, 4 you can touch, 3 you can hear, 2 you can smell, 1 you can taste. This activates your parasympathetic nervous system in under 60 seconds."),
			("🌬️ 4-7-8 Breathing", "Inhale through nose for 4 counts. Hold for 7 counts. Exhale slowly through mouth for 8 counts. Repeat 3 times. This technique reduces anxiety by up to 15% cortisol."),
			("☕ Mindful First Sip", "With your first drink of the day, pause. Feel the warmth in your hands. Smell it. Take one slow sip — notice the temperature, the flavor, the sensation. 30 seconds of presence."),
			("📝 Micro-Journal", "Write exactly 3 sentences: 1) How do I feel right now? 2) What is one thing I'm avoiding? 3) What would make today a win? No editing, raw honesty."),
			("⚓ Anchor Breath", "Place both feet flat on the ground. Feel the contact. Take 3 deep breaths while focusing only on the sensation of your feet touching the floor. You are here. You are grounded."),
		]
		day_of_year = datetime.date.today().timetuple().tm_yday
		method_name, method_prompt = methods[day_of_year % len(methods)]
		content += f"\n\n{method_name} *Mental Yoga:*\n_{method_prompt}_"
	
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
	separator = "---"
	await send_notification(
		f"{separator}\n☀️ *Good Morning!*\n\n{content}",
		reply_markup=get_nav_markup()
	)
	if audio_briefing:
		await send_voice_message(audio_briefing, caption="🎙️ Audio Briefing")

	return content
