from app.services.automation import run_contextual_automation
from app.services.llm import chat
from app.services.planka import get_project_tree
from app.services.gmail import fetch_unread_emails
from app.services.calendar import fetch_calendar_events
from app.services.weather import get_weather_forecast
from app.services.tts import generate_speech
from app.api.telegram import send_notification, send_voice_message, get_nav_markup
from app.models.db import AsyncSessionLocal, Briefing, Project, Person
from app.config import settings
from sqlalchemy import select
import asyncio
import datetime
import logging

logger = logging.getLogger(__name__)

_CLOSING_REFLECTIONS = [
	"Two roads diverged in a wood, and I — I took the one less traveled by, and that has made all the difference. — Robert Frost",
	"In the depths of winter, I finally learned that within me there lay an invincible summer. — Albert Camus",
	"Tell me, what is it you plan to do with your one wild and precious life? — Mary Oliver",
	"You are not a drop in the ocean. You are the entire ocean in a drop. — Rumi",
	"In the middle of difficulty lies opportunity. The obstacle is not the end — it is the door. — Albert Einstein",
	"The earth laughs in flowers. — Ralph Waldo Emerson",
	"We shall not cease from exploration, and the end of all our exploring will be to arrive where we started and know the place for the first time. — T.S. Eliot",
	"You were born with wings. Why prefer to crawl through life? — Rumi",
	"Dwell on the beauty of life. Watch the stars, and see yourself running with them. — Marcus Aurelius",
	"Even after all this time, the sun never says to the earth, 'You owe me.' Look what happens with a love like that — it lights the whole world. — Hafiz",
	"You do not have to be good. You do not have to walk on your knees for a hundred miles through the desert, repenting. You only have to let the soft animal of your body love what it loves. — Mary Oliver",
	"In every walk with nature, one receives far more than he seeks. — John Muir",
	"The most beautiful thing we can experience is the mysterious. It is the source of all true art and science. — Albert Einstein",
	"I live my life in widening circles that reach out across the world. — Rainer Maria Rilke",
	"And those who were seen dancing were thought to be insane by those who could not hear the music. — Friedrich Nietzsche",
	"How we spend our days is, of course, how we spend our lives. — Annie Dillard",
	"To see a World in a Grain of Sand and a Heaven in a Wild Flower, hold Infinity in the palm of your hand and Eternity in an hour. — William Blake",
	"I have loved the stars too fondly to be fearful of the night. — Sarah Williams",
	"Not all those who wander are lost. — J.R.R. Tolkien",
	"Instructions for living a life: Pay attention. Be astonished. Tell about it. — Mary Oliver",
	"The world is charged with the grandeur of God. It will flame out, like shining from shook foil. — Gerard Manley Hopkins",
	"Every human language ever spoken contains words for love, for home, and for tomorrow. No matter how different the culture, these three things have always mattered.",
	"I am not an Athenian or a Greek, but a citizen of the world. — Socrates",
	"It may be that when we no longer know what to do, we have come to our real work, and when we no longer know which way to go, we have begun our real journey. — Wendell Berry",
	"At the still point of the turning world, there the dance is. — T.S. Eliot",
	"What lies behind us and what lies before us are tiny matters compared to what lies within us. — Ralph Waldo Emerson",
	"The most wasted of all days is one without laughter. — E.E. Cummings",
	"Live in the sunshine, swim the sea, drink the wild air. — Ralph Waldo Emerson",
	"The invariable mark of wisdom is to see the miraculous in the common. — Ralph Waldo Emerson",
	"Enough. These few words are enough. If not these words, this breath. If not this breath, this sitting here. This opening to the life we have refused again and again until now. — David Whyte",
]

async def morning_briefing():
	"""Generate and store the daily morning briefing."""
	
	# 1. Zero-Noise Mode (Facts Only)
	
	# 2. Gather context
	async with AsyncSessionLocal() as session:
		people_result = await session.execute(select(Person))
		people = people_result.scalars().all()
	
	# --- Contextual Automation ---
	async def get_person_briefing_data(p: Person):
		data = f"- {p.name} ({p.relationship}): {p.context}"
		if p.birthday:
			from app.services.timezone import get_birthday_proximity
			tag = get_birthday_proximity(p.birthday)
			if tag:
				data += f" | ⚠️ BIRTHDAY {tag} ({p.birthday})"
		return data

	inner_circle_tasks = [get_person_briefing_data(p) for p in people if p.circle_type == "inner"]
	close_circle_tasks = [get_person_briefing_data(p) for p in people if p.circle_type == "close"]

	inner_context_list, close_context_list = await asyncio.gather(
		asyncio.gather(*inner_circle_tasks),
		asyncio.gather(*close_circle_tasks),
	)

	inner_context = "\n".join(inner_context_list) if inner_context_list else "No primary family focus today."
	close_context = "\n".join(close_context_list) if close_context_list else "No specific friend connections planned."

	# 2.2 Batch 1 — calendar + automation in parallel (both independent)
	logger.debug("morning_briefing — starting batch-1 gather (calendar + automation)")
	_t1 = asyncio.get_event_loop().time()

	async def _fetch_calendar_safe():
		try:
			return await fetch_calendar_events(days_ahead=0)
		except Exception as ce:
			logger.debug("Calendar fetch during briefing skipped: %s", ce)
			return []

	calendar_events, automation_actions = await asyncio.gather(
		_fetch_calendar_safe(),
		run_contextual_automation(people),
	)
	logger.debug("morning_briefing — batch-1 done in %.1fs", asyncio.get_event_loop().time() - _t1)

	automation_summary = "\n".join([f"- {a}" for a in automation_actions]) if automation_actions else "No automated tasks created today."

	calendar_summary_parts = []
	for e in calendar_events:
		time_str = e['start'].split('T')[1][:5] if 'T' in e['start'] else None
		if time_str == "00:00": time_str = None
		item = f"- {e['summary']}"
		if time_str: item += f" ({time_str})"
		calendar_summary_parts.append(item)
	calendar_summary = "\n".join(calendar_summary_parts) if calendar_summary_parts else "No events scheduled for today."

	# Simple travel detection (needs calendar result — done before batch 2)
	detected_location = None
	for event in calendar_events:
		summary = event['summary'].lower()
		if any(kw in summary for kw in ["flight to", "trip to", "stay in", "travel to", "moving to"]):
			for kw in ["to ", "in "]:
				if kw in summary:
					detected_location = event['summary'].split(kw.strip())[-1].strip()
					break
		if detected_location: break

	# 2.3 Batch 2 — weather + project tree + email context + memories (all independent)
	logger.debug("morning_briefing — starting batch-2 gather (weather + tree + emails + memories)")
	_t2 = asyncio.get_event_loop().time()

	from app.models.db import EmailSummary
	from app.services.memory import get_recent_memories

	async def _get_email_summary():
		async with AsyncSessionLocal() as session:
			res = await session.execute(select(EmailSummary).where(EmailSummary.included_in_briefing == False))
			summaries = res.scalars().all()
			if summaries:
				result = "\n".join([f"- {s.sender}: {s.subject} {f'[{s.badge}]' if s.badge else ''} (Summary: {s.summary})" for s in summaries])
				for s in summaries: s.included_in_briefing = True
				await session.commit()
				return result
		# Fallback to direct fetch if no cached summaries
		emails = await fetch_unread_emails(max_results=5)
		return "\n".join([f"- {e['from']}: {e['subject']}" for e in emails]) if emails else "No new emails."

	weather_report, tree, email_summary, recent_memories = await asyncio.gather(
		get_weather_forecast(detected_location),
		get_project_tree(as_html=False),
		_get_email_summary(),
		get_recent_memories(hours=24),
	)
	logger.debug("morning_briefing — batch-2 done in %.1fs", asyncio.get_event_loop().time() - _t2)

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
	
	# 3. Generate Briefing — deep tier with 90s hard timeout, fallback to standard
	logger.debug("morning_briefing — starting LLM generation")
	_t3 = asyncio.get_event_loop().time()
	try:
		raw_content = await asyncio.wait_for(chat(full_prompt, tier="deep"), timeout=90.0)
	except asyncio.TimeoutError:
		logger.warning("morning_briefing — deep tier timed out after 90s, falling back to standard tier")
		raw_content = await chat(full_prompt, tier="standard")
	logger.debug("morning_briefing — LLM done in %.1fs", asyncio.get_event_loop().time() - _t3)
	
	# 3.2 Post-Processing & Cleanup
	from app.services.agent_actions import parse_and_execute_actions
	content, _ = await parse_and_execute_actions(raw_content)
	
	# 3.3 Append Memory Review (raw, not via LLM — user sees exactly what was stored)
	if memory_review:
		content += "\n\n🧠 *New Memories (Last 24h):*\n" + memory_review + "\n_Use /unlearn <topic> to remove incorrect memories._"
	
	# 3.4 Calibration (configurable, rotates daily)
	if settings.BRIEFING_CALIBRATION:
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
		content += f"\n\n{method_name} *Calibration:*\n_{method_prompt}_"
	
	# 3.5 Closing Reflection (rotating poem or scientific fact)
	if settings.BRIEFING_CLOSING_REFLECTION:
		day_of_year = datetime.date.today().timetuple().tm_yday
		reflection = _CLOSING_REFLECTIONS[day_of_year % len(_CLOSING_REFLECTIONS)]
		content += f"\n\n✨ *Reflection:*\n_{reflection}_"

	# --- Multi-Modal (TTS) — fire as background task so text delivery is not blocked ---
	clean_text = content.replace("*", "").replace("#", "").replace("_", "")
	tts_task = asyncio.create_task(generate_speech(clean_text))

	# 4. Store in Database for Dashboard
	async with AsyncSessionLocal() as session:
		briefing = Briefing(type="day", content=content)
		session.add(briefing)
		await session.commit()

	# 5. Send text notification to Telegram immediately (does not wait for TTS)
	from app.services.translations import get_translations
	lang = "en"
	async with AsyncSessionLocal() as session:
		res = await session.execute(select(Person).where(Person.circle_type == "identity"))
		ident = res.scalar_one_or_none()
		if ident and ident.language:
			lang = ident.language
	t = get_translations(lang)

	separator = "---"
	await send_notification(
		f"{separator}\n☀️ *Good Morning!*\n\n{content}",
		reply_markup=get_nav_markup(t)
	)

	# 5b. Wait for TTS to finish and send voice (with generous timeout — non-blocking for text above)
	try:
		audio_briefing = await asyncio.wait_for(tts_task, timeout=90.0)
		if audio_briefing:
			await send_voice_message(audio_briefing, caption="🎙️ Audio Briefing")
	except (asyncio.TimeoutError, Exception) as e:
		logger.warning("TTS briefing skipped: %s", e)

	return content
