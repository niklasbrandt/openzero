from app.models.db import AsyncSessionLocal, Briefing, Person
from app.config import settings
from sqlalchemy import select
import asyncio
import datetime
import logging

logger = logging.getLogger(__name__)

async def morning_briefing():
	"""Generate and store the daily morning briefing."""
	logger.info("Morning Briefing initialization started (T-15m offset applied).")
	try:
		from app.services.crews import crew_registry
		
		# 1. Native Pre-Compilation Yield: Await active /day crews (if any were started in background)
		# While true 'active' tracking for native is lightweight, we sync with the registry loader.
		await crew_registry.load()

		from app.services.automation import run_contextual_automation
		from app.services.llm import chat, last_model_used
		from app.services.planka import get_project_tree
		from app.services.gmail import fetch_unread_emails
		from app.services.calendar import fetch_calendar_events
		from app.services.weather import get_weather_forecast
		from app.services.tts import generate_speech
		from app.services.translations import get_translations

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
					data += f" | BIRTHDAY {tag} ({p.birthday})"
			return data

		inner_circle_tasks = [get_person_briefing_data(p) for p in people if p.circle_type == "inner"]

		inner_context_list = await asyncio.gather(*inner_circle_tasks)

		inner_context = "\n".join(inner_context_list) if inner_context_list else "No primary family focus today."

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
		calendar_summary = "\n".join(calendar_summary_parts) if calendar_summary_parts else "[EMPTY — omit Calendar section from output]"

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
				res = await session.execute(select(EmailSummary).where(EmailSummary.included_in_briefing.is_(False)))
				summaries = res.scalars().all()
				if summaries:
					result = "\n".join([f"- {s.sender}: {s.subject} {f'[{s.badge}]' if s.badge else ''} (Summary: {s.summary})" for s in summaries])
					for s in summaries: s.included_in_briefing = True
					await session.commit()
					return result
			# Fallback to direct fetch if no cached summaries
			emails = await fetch_unread_emails(max_results=5)
			return "\n".join([f"- {e['from']}: {e['subject']}" for e in emails]) if emails else "[EMPTY — omit Email section from output]"

		from app.services.planka import get_activity_report
		weather_report, tree, email_summary, activity = await asyncio.gather(
			get_weather_forecast(detected_location),
			get_project_tree(as_html=False),
			_get_email_summary(),
			get_activity_report(days=1),
		)
		logger.debug("morning_briefing — batch-2 done in %.1fs", asyncio.get_event_loop().time() - _t2)

		# 2. Get Recent Memories for context — handle failure gracefully
		try:
			recent_memories = await get_recent_memories(hours=24)
			memory_review = "\n".join([f"• {m['text']}" for m in recent_memories])
		except Exception as e:
			logger.warning("Optional memory retrieval skipped for briefing: %s", e)
			memory_review = "" # Ensure it's empty if retrieval fails

		# 2.5 Build crew context — summarise which crews are active and what they cover
		crew_context = ""
		try:
			active_crews = crew_registry.list_active()
			if active_crews:
				crew_lines = []
				for c in active_crews:
					feed = c.feeds_briefing or "on-demand"
					crew_lines.append(f"- {c.id} ({c.name}): {c.description} [cadence: {feed}]")
				crew_context = "\n".join(crew_lines)
		except Exception as ce:
			logger.debug("Crew context for briefing skipped: %s", ce)

		full_prompt = (
			"Z, it's morning. Write the daily briefing for the user.\n\n"
			"VOICE & STYLE:\n"
			"- Write like a smart colleague sending a quick message about your day. Natural, direct, slightly informal — not robotic, not literary.\n"
			"- Short sentences. Plain words. OK to drop a subject: 'Clear calendar today.' / 'Rain until noon.'\n"
			"- Sections and labels are expected. The language inside them should sound like a person wrote it, not a machine printing a table.\n"
			"- Use bullets for lists of items (board cards, emails, tasks). Use short prose for single-line observations like weather or agenda notes.\n"
			"- NEVER use emoji or unicode decorative symbols. Plain text only.\n"
			"- NO metaphors, NO atmospheric prose, NO literary devices. NO filler: 'honestly?', 'that screams', 'it's not about the result'.\n"
			"- Target 150-250 words total. Over 400 is a failure.\n\n"
			"REQUIRED OUTPUT FORMAT — follow this structure exactly:\n"
			"[One-line opener: temperature, conditions, one clothing note if relevant. Facts only. No narrative.]\n\n"
			"Calendar: [events with times, one line each — or 'clear']\n"
			"Email: [notable items one line each — or 'nothing urgent']\n\n"
			"Board (Today):\n"
			"- [card] -> [status] ([short reason])\n\n"
			"[One labeled block per active crew that has something relevant for today, e.g.:]\n"
			"Fitness: [session type, time, duration]\n"
			"Nutrition: [meal or prep note]\n"
			"[Kids / People: one line per person if relevant]\n\n"
			"ANTI-PATTERNS — these make the output invalid:\n"
			"WRONG (literary): 'You wake up to the kind of grey Bremen light that doesn\'t promise much but doesn\'t lie either...'\n"
			"WRONG (robotic dump): 'Weather: 12C. Rain: yes. Wind: damp. Clothing: layers required.'\n"
			"RIGHT (human): '12C, drizzle all morning, eases around 2pm. Take a jacket.'\n\n"
			"WRONG (robotic board): '- openZero backend -> In Progress (TURN server fix)'\n"
			"RIGHT (human board): '- openZero backend in progress (TURN fix done)\\n- Privacy dashboard still in review — needs a test pass'\n\n"
			"CONTENT — include only sections where real data was provided in the context blocks below:\n"
			"- Weather: temperature and conditions from WEATHER FORECAST. Always include — weather data is always provided.\n"
			"- Calendar: only if CALENDAR TODAY is not marked [EMPTY]. List real events only.\n"
			"- Board: only if PROJECT TREE has real cards. Never list cards not present in the tree.\n"
			"- People: only if INNER CIRCLE has someone with today-relevant context explicitly in the data.\n"
			"- Email: only if LATEST EMAILS has real emails. If marked [EMPTY], omit the section entirely.\n\n"
			"PROACTIVE SUGGESTIONS — allowed, but grounded:\n"
			"Based on the user's known personal context (health goals, career aspirations, family situation, "
			"fitness preferences, nutrition needs, life circumstances), actively suggest concrete things "
			"they could do today. Label suggestions clearly as suggestions, never as confirmed schedule items.\n"
			"- If the fitness or health crew has produced a plan, suggest today's workout window based on weather and calendar gaps.\n"
			"- If career goals exist, suggest a concrete skill-building action for today.\n"
			"- If there are kids in INNER CIRCLE, suggest something good for them based on weather — but NEVER infer school days, pickup times, or child logistics unless those appear verbatim in CALENDAR TODAY.\n"
			"- If nutrition crew is active, mention ONE warm meal suggestion. Do not suggest both lunch and dinner.\n"
			"- If stagnant projects exist in the tree, nudge on the most impactful one.\n"
			"- If the weather is good, suggest something outdoors. If bad, suggest something productive indoors.\n"
			"Add each suggestion as a labeled one-line bullet under the relevant section (Fitness:, Nutrition:, Kids:, etc.).\n\n"
			"CREW AWARENESS — the user has these active autonomous crews working for them:\n"
			f"{crew_context if crew_context else 'No active crews detected.'}\n"
			"Surface relevant crew output as labeled single-line facts in the structure above. "
			"If the fitness crew has a plan, one line under 'Fitness:'. If the nutrition crew has a meal, one line under 'Nutrition:'. "
			"Only include crews that have something concrete for TODAY. No prose linking them together.\n\n"
			"STRICT RULES:\n"
			"- NEVER invent names, tasks, projects, or events not present in CONTEXT.\n"
			"- IGNORE any placeholder or '[e.g., ...]' values in personal files.\n"
			"- ONLY mention a birthday if CONTEXT explicitly contains 'BIRTHDAY IN EXACTLY'.\n"
			"- If a section has nothing relevant, skip it entirely — don't note 'nothing to report'.\n"
			"- Do NOT summarize the NEW MEMORIES section — it will be appended separately.\n"
			"- In the WEATHER section, use the EXACT city and country names as they appear "
			"in the data. NEVER replace them with bracket placeholders like [CITY_1] or [LOCATION_2]. "
			"If the forecast says 'Bremen, Germany', write 'Bremen, Germany'.\n\n"
			"EXECUTABLE ACTIONS:\n"
			"You can trigger real system actions by embedding these tags ANYWHERE in your response.\n"
			"They will be parsed and executed automatically, then stripped from the final message.\n"
			"Use them whenever the context suggests a card should move, a task should be created, etc.\n"
			"Available tags:\n"
			"  [ACTION: MOVE_CARD | CARD: <title fragment> | LIST: <destination list>]\n"
			"  [ACTION: MOVE_CARD | CARD: <title fragment> | LIST: <destination list> | BOARD: <board name>]\n"
			"  [ACTION: MARK_DONE | CARD: <title fragment>]\n"
			"  [ACTION: CREATE_TASK | BOARD: <board name> | LIST: <list name> | TITLE: <task title>]\n"
			"  [ACTION: CREATE_LIST | BOARD: <board name> | NAME: <list name>]\n"
			"  [ACTION: LEARN | TEXT: <fact to remember>]\n"
			"Rules for actions:\n"
			"- CARD fragment must be a recognizable substring of an existing card title.\n"
			"- Only emit actions for things explicitly mentioned in CONTEXT — never invent cards or boards.\n"
			"- If the RECENT ACTIVITY section shows tasks that should move (e.g., started yesterday, stalled), move them.\n"
			"- You may create new tasks if the context clearly warrants it (e.g., upcoming deadlines, automation suggestions).\n"
			"- NEVER write prose narrating your own action tags. Do not say 'I am creating a task', 'I will add this to Planka', "
			"'Create new openZero Todo', or anything similar. Embed the tag silently. The user only reads the briefing prose, "
			"not the mechanical steps. Any sentence describing the action will appear verbatim to the user.\n\n"
			f"AUTOMATED SYSTEM ACTIONS:\n{automation_summary}\n\n"
			f"INNER CIRCLE (Family/Care):\n{inner_context}\n\n"
			f"CALENDAR TODAY:\n{calendar_summary}\n\n"
			f"WEATHER FORECAST:\n{weather_report}\n\n"
			f"RECENT ACTIVITY (LAST 24H):\n{activity}\n\n"
			f"PROJECT TREE:\n{tree}\n\n"
			f"LATEST EMAILS:\n{email_summary}\n"
		)

		# 3. Generate Briefing — cloud tier with 600s hard timeout, retry on failure
		logger.debug("morning_briefing — starting LLM generation")
		_t3 = asyncio.get_event_loop().time()
		try:
			logger.info("Generating morning briefing (600s budget)...")
			raw_content = await asyncio.wait_for(chat(full_prompt, tier="cloud", _feature="morning_briefing", include_health=False), timeout=600.0)
		except asyncio.TimeoutError:
			logger.warning("morning_briefing — cloud tier timed out after 600s, retrying")
			raw_content = await chat(full_prompt, tier="cloud", _feature="morning_briefing", include_health=False)
		logger.debug("morning_briefing — LLM done in %.1fs", asyncio.get_event_loop().time() - _t3)

		# 3.2 Post-Processing & Cleanup
		from app.services.agent_actions import parse_and_execute_actions
		content, _, _ = await parse_and_execute_actions(raw_content)

		# 3.3 Append Memory Review (raw, not via LLM — user sees exactly what was stored)
		if memory_review:
			content += "\n\n---\n*New Memories (Last 24h):*\n" + memory_review + "\n_Use /unlearn <topic> to remove incorrect memories._"

		# 3.4 Calibration (configurable, rotates daily — prose-style, in-character)
		if settings.BRIEFING_CALIBRATION:
			# Each method is a short prose passage written to be read in the agent's voice.
			# No emojis, no bullet points — just a grounded, human prompt.
			methods = [
				("Gratitude",
				 "Before the day pulls you in, name three things you are grateful for right now. "
				 "Be specific — not 'my kids' but 'the way Liya laughed at breakfast yesterday.' "
				 "Precision makes it real. Let each one land for a breath before moving to the next."),
				("Intention",
				 "Set one intention for how you want to move through today. Not a task — a way of being. "
				 "Something like 'I will stay patient, even when things stack up' or 'I will finish what I start "
				 "before opening something new.' One sentence. Hold it."),
				("Reframe",
				 "There is something sitting in the back of your mind that has been bothering you. Pick it up. "
				 "Now turn it over — what is the hidden opportunity? What is it teaching you? Write the reframe "
				 "in one sentence and put the original version down."),
				("Box Breathing",
				 "Sixty seconds. Breathe in for four counts, hold for four, out for four, hold for four. Three rounds. "
				 "Your nervous system does not care what your calendar says — it responds to your breath first. "
				 "Notice how the rest of you settles when the breathing is deliberate."),
				("Visualization",
				 "Close your eyes for thirty seconds. Picture the end of today — the version where things went well. "
				 "What does that look like? Where are you sitting? How does your body feel? "
				 "That image is not fantasy. It is a direction."),
				("Body Scan",
				 "Start at the top of your head and scan down slowly — neck, shoulders, chest, stomach, hips, "
				 "legs, feet. Wherever you find tension, stay there for three breaths and let it soften. "
				 "The body holds what the mind refuses to process. Give it a minute."),
				("Affirmation",
				 "Say this once, out loud if you can: 'I am exactly where I need to be. Today I take one step closer "
				 "to who I am becoming.' Then add your own line — whatever feels true right now. "
				 "Repetition is not performance. It is reprogramming."),
				("Grounding",
				 "Five things you can see. Four you can touch. Three you can hear. Two you can smell. One you can taste. "
				 "This takes less than a minute and it pulls your parasympathetic nervous system back online. "
				 "The day gets clearer when you are actually in the room."),
				("4-7-8 Breathing",
				 "Inhale through the nose for four counts. Hold for seven. Exhale slowly through the mouth for eight. "
				 "Three rounds of this measurably drops cortisol. It is one of the fastest ways to reset your "
				 "baseline before the first demand of the day arrives."),
				("Mindful First Sip",
				 "When you pick up your first drink, pause. Feel the warmth in your hands. Smell it before "
				 "you taste it. Take one slow sip and actually notice the temperature, the flavor, the sensation. "
				 "Thirty seconds of genuine presence. The rest of the day will try to take it from you."),
				("Micro-Journal",
				 "Write three sentences — raw, no editing. First: how do I actually feel right now? Second: "
				 "what is one thing I have been avoiding? Third: what would make today a win? "
				 "Honesty on paper is cheaper than honesty deferred."),
				("Anchor Breath",
				 "Put both feet flat on the floor. Feel the contact — the weight, the temperature, the surface. "
				 "Take three slow breaths with your full attention on that point of contact. "
				 "You are here. You are grounded. That is enough to start."),
			]
			day_of_year = datetime.date.today().timetuple().tm_yday
			method_name, method_prompt = methods[day_of_year % len(methods)]
			content += f"\n\n---\n*{method_name} Calibration:*\n_{method_prompt}_"

		# --- Multi-Modal (TTS) — fire as background task so text delivery is not blocked ---
		clean_text = content.replace("*", "").replace("#", "").replace("_", "")
		tts_task = asyncio.create_task(generate_speech(clean_text))

		# 4. Store in Database for Dashboard (briefing history widget)
		from app.models.db import save_global_message
		async with AsyncSessionLocal() as session:
			briefing = Briefing(type="day", content=content, model=last_model_used.get())
			session.add(briefing)
			await session.commit()

		# 5. Precision Delivery SLEEP logic
		# We kicked off 15m early. We now sleep the exact remaining delta seconds to hit the precise user configuration.
		try:
			from app.services.timezone import get_current_timezone
			import pytz
			tz_str = await get_current_timezone()
			tz = pytz.timezone(tz_str)
			now = datetime.datetime.now(tz)
			
			async with AsyncSessionLocal() as session:
				res = await session.execute(select(Person).where(Person.circle_type == "identity"))
				me = res.scalar_one_or_none()
				if me and me.briefing_time:
					parts = me.briefing_time.split(":")
					if len(parts) == 2:
						target = now.replace(hour=int(parts[0]), minute=int(parts[1]), second=0, microsecond=0)
						delta = (target - now).total_seconds()
						if 0 < delta < 1800: # Max 30 min sleep
							logger.info("morning_briefing — Pre-compilation finished in %.1fs. Precision SLEEP for %.1fs until exact delivery time.", (now.timestamp() - _t1) if '_t1' in locals() else 0, delta)
							await asyncio.sleep(delta)
		except Exception as e:
			logger.warning("morning_briefing — Precision SLEEP failed, falling back to immediate delivery: %s", e)

		# 6. Send text notification to Telegram immediately (does not wait for TTS)
		from app.services.notifier import send_notification, send_voice_message, get_nav_footer
		lang = "en"
		async with AsyncSessionLocal() as session:
			res = await session.execute(select(Person).where(Person.circle_type == "identity"))
			ident = res.scalar_one_or_none()
			if ident and ident.language:
				lang = ident.language
		t = get_translations(lang)
		greeting_text = t.get("morning_greeting", "Good Morning!")

		await send_notification(
			f"---\n{content}",
			nav_footer=get_nav_footer(t)
		)

		# 6b. Persist to global_messages NOW — after delivery so dashboard and
		# Telegram show the briefing at the same time (not 15 min early).
		await save_global_message("telegram", "z", content, model=last_model_used.get())

		# 5b. Wait for TTS to finish and send voice (with generous timeout — non-blocking for text above)
		try:
			audio_briefing = await asyncio.wait_for(tts_task, timeout=90.0)
			if audio_briefing:
				caption_text = t.get("audio_briefing_caption", "🎙️ Audio Briefing")
				await send_voice_message(audio_briefing, caption=caption_text)
		except (asyncio.TimeoutError, Exception) as e:
			logger.warning("TTS briefing skipped: %s", e)

		return content

	except Exception as e:
		logger.error("CRITICAL: Morning Briefing failed: %s", e, exc_info=True)
		return None
