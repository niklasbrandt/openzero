from app.models.db import AsyncSessionLocal, Briefing, Preference
from app.config import settings
from sqlalchemy import select
import asyncio
import datetime
import logging

logger = logging.getLogger(__name__)


def build_briefing_skeleton(
	weather: str,
	calendar_events: list,
	project_tree: str,
	recent_activity: str,
	stale_cards: str,
	crew_snapshot: str,
	email_summary: str = "",
	board_walkthrough: str = "",
	activity_days: int = 7,
) -> str:
	"""Build a pre-formatted briefing draft from real data. The LLM only adds voice/tone."""
	lines: list[str] = []

	lines.append(f"Weather: {weather}")
	lines.append("")

	if calendar_events:
		lines.append("Calendar today:")
		for ev in calendar_events:
			time_str = ""
			start = ev.get("start", "")
			if "T" in start:
				t = start.split("T")[1][:5]
				if t != "00:00":
					time_str = f"{t} "
			lines.append(f"  - {time_str}{ev.get('summary', '?')}")
		lines.append("")

	if project_tree and "Planka connection issue" not in project_tree and "[NO DATA]" not in project_tree:
		lines.append("All active boards (current state):")
		lines.append(project_tree)
		lines.append("")

	if board_walkthrough and "UNAVAILABLE" not in board_walkthrough and "no projects" not in board_walkthrough:
		lines.append("Board walkthrough (active + stale per board):")
		lines.append(board_walkthrough)
		lines.append("")

	if recent_activity and "NO ACTIVITY" not in recent_activity and "UNAVAILABLE" not in recent_activity:
		lines.append(f"Recent changes (last {activity_days}d):")
		lines.append(recent_activity)
		lines.append("")

	if stale_cards and "NO STALE" not in stale_cards and "UNAVAILABLE" not in stale_cards:
		lines.append("No movement in 5+ days (may need attention):")
		lines.append(stale_cards)
		lines.append("")

	if crew_snapshot and "UNAVAILABLE" not in crew_snapshot and "no crew boards found" not in crew_snapshot:
		lines.append("Crew boards:")
		lines.append(crew_snapshot)
		lines.append("")

	if email_summary and not email_summary.startswith("[NO DATA"):
		lines.append("Email (unread):")
		lines.append(email_summary)
		lines.append("")

	lines.append("=== DAY STRUCTURE ===")
	lines.append("[PLANNER: structure today based on the cards and activity above — suggest AM/PM blocks, flag any urgent cards or stale items that need attention today. Keep it concise. Do NOT invent tasks. Only reference what is in the skeleton above.]")
	lines.append("")

	lines.append("=== END OF VERIFIED DATA ===")
	lines.append("Everything above this line is verified system data from live APIs.")
	lines.append("Do NOT add status notes, parenthetical remarks, or hypothetical scenarios to items above.")
	lines.append("Report card names and task titles EXACTLY as written — no renaming, no merging, no editorialising.")
	lines.append("")

	return "\n".join(lines)


async def morning_briefing():
	"""Generate and store the daily morning briefing."""
	logger.info("Morning Briefing initialization started (T-15m offset applied).")
	try:
		from app.services.crews import crew_registry
		
		# 1. Native Pre-Compilation Yield: Await active /day crews (if any were started in background)
		# While true 'active' tracking for native is lightweight, we sync with the registry loader.
		await crew_registry.load()

		from app.services.llm import chat, last_model_used
		from app.services.planka import get_project_tree
		from app.services.gmail import fetch_unread_emails
		from app.services.calendar import fetch_calendar_events
		from app.services.weather import get_weather_forecast
		from app.services.tts import generate_speech
		from app.services.translations import get_translations

		# 2.2 Batch 1 — calendar fetch
		logger.debug("morning_briefing — starting batch-1 (calendar)")
		_t1 = asyncio.get_event_loop().time()

		async def _fetch_calendar_safe():
			try:
				return await fetch_calendar_events(days_ahead=0)
			except Exception as ce:
				logger.debug("Calendar fetch during briefing skipped: %s", ce)
				return []

		calendar_events = await _fetch_calendar_safe()
		logger.debug("morning_briefing — batch-1 done in %.1fs", asyncio.get_event_loop().time() - _t1)

		calendar_summary_parts = []
		for e in calendar_events:
			time_str = e['start'].split('T')[1][:5] if 'T' in e['start'] else None
			if time_str == "00:00": time_str = None
			item = f"- {e['summary']}"
			if time_str: item += f" ({time_str})"
			calendar_summary_parts.append(item)
		calendar_summary = "\n".join(calendar_summary_parts) if calendar_summary_parts else "[NO DATA — zero events exist. The Calendar section MUST be absent from the briefing. Do NOT invent or infer any events, meetings, or times.]"

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

		# Read configurable preferences before batch-2 (activity_hours is needed in the gather)
		max_obs = 3
		activity_days = 4
		try:
			async with AsyncSessionLocal() as _obs_session:
				_obs_res = await _obs_session.execute(select(Preference).where(Preference.key == "briefing_max_observations"))
				_obs_pref = _obs_res.scalar_one_or_none()
				if _obs_pref and _obs_pref.value:
					max_obs = int(_obs_pref.value)
		except Exception as _obs_err:
			logger.debug("morning_briefing: could not read briefing_max_observations, defaulting to 3: %s", _obs_err)
		try:
			async with AsyncSessionLocal() as _days_session:
				_days_res = await _days_session.execute(select(Preference).where(Preference.key == "briefing_activity_days"))
				_days_pref = _days_res.scalar_one_or_none()
				if _days_pref and _days_pref.value:
					activity_days = int(_days_pref.value)
		except Exception as _days_err:
			logger.debug("morning_briefing: could not read briefing_activity_days, defaulting to 7: %s", _days_err)
		activity_hours = activity_days * 24

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
			return "\n".join([f"- {e['from']}: {e['subject']}" for e in emails]) if emails else "[NO DATA — email is not connected or inbox is empty. The Email section MUST be absent from the briefing. Do NOT invent senders, subjects, or message content.]"

		from app.services.planka import get_activity_report, get_recent_activity, get_stale_cards, get_crew_board_snapshot, get_board_walkthrough
		from app.services.translations import get_user_lang
		from app.services.crew_memory import get_recent_crew_outputs
		(
			weather_report,
			tree,
			email_summary,
			activity,
			recent_activity,
			stale_cards,
			crew_snapshot,
			board_walkthrough,
			user_language,
			crew_outputs,
		) = await asyncio.gather(
			get_weather_forecast(detected_location),
			get_project_tree(as_html=False),
			_get_email_summary(),
			get_activity_report(days=1),
			get_recent_activity(hours=activity_hours),
			get_stale_cards(min_days=5),
			get_crew_board_snapshot(),
			get_board_walkthrough(),
			get_user_lang(),
			get_recent_crew_outputs(hours=24),
		)
		logger.debug("morning_briefing — batch-2 done in %.1fs", asyncio.get_event_loop().time() - _t2)

		# NOTE: Previous briefing injection REMOVED (Change 7).
		# Injecting yesterday's LLM-generated prose created a hallucination echo chamber:
		# fabricated status notes from yesterday were read as facts today and elaborated.
		# The skeleton's recent_activity and stale_cards data already cover delta detection.

		# Detect Planka unavailability — prevent LLM hallucination when all board data fails
		_planka_unavailable_warning = ""
		if "Planka connection issue" in tree or "OPERATIONAL DATA FAILURE" in activity:
			_planka_unavailable_warning = (
				"\nIMPORTANT: All board data is currently unavailable. Do NOT attempt to generate board content "
				"from memory or inference. Simply say that board data could not be loaded and ask the user to "
				"check Planka connectivity.\n"
			)
			logger.warning("morning_briefing: Planka data unavailable — injecting hallucination guard into prompt")

		# 2. Get Recent Memories for context — handle failure gracefully
		try:
			recent_memories = await get_recent_memories(hours=24)
			memory_review = "\n".join([f"• {m['text']}" for m in recent_memories])
		except Exception as e:
			logger.warning("Optional memory retrieval skipped for briefing: %s", e)
			memory_review = "" 

		# 2.5 Build crew context — summarise which crews are active and what they cover
		crew_context = ""
		active_crews = []
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

		skeleton = build_briefing_skeleton(
			weather=weather_report,
			calendar_events=calendar_events,
			project_tree=tree,
			recent_activity=recent_activity,
			stale_cards=stale_cards,
			crew_snapshot=crew_snapshot,
			email_summary=email_summary,
			board_walkthrough=board_walkthrough,
			activity_days=activity_days,
		)

		# Coordinate active crews to check in and generate domain-specific insights
		dynamic_insights = {}
		if active_crews:
			from app.services.crews_native import native_crew_engine
			import re
			_ACTION_STRIP_RE = re.compile(r'\[ACTION:[^\]]*\]', re.IGNORECASE)

			async def _get_crew_insight(crew_config):
				try:
					crew_prompt = (
						f"You are the {crew_config.name} crew. We are preparing the daily morning briefing for the operator.\n"
						f"Here is the day's raw data:\n\n{skeleton}\n\n"
						f"Based on your specialized domain, review this data and generate a single short paragraph (under 40 words) with your top insight, recommendation, or warning for today. "
						f"STRICT: Do NOT invent background details, hypothetical scenarios, or context not present in the raw data (e.g. do not invent status notes or user habits like cooking rice). "
						f"Be extremely concise. Write only the paragraph. Do not introduce yourself, and do not say 'Here is my insight'."
					)
					res = await native_crew_engine.run_crew(crew_config.id, crew_prompt)
					res_clean = _ACTION_STRIP_RE.sub("", res).strip()
					if res_clean:
						return crew_config.id, res_clean
				except Exception as ex:
					logger.warning("Failed to get briefing insight from crew %s: %s", crew_config.id, ex)
				return crew_config.id, None

			try:
				insights_results = await asyncio.wait_for(
					asyncio.gather(*[_get_crew_insight(c) for c in active_crews]),
					timeout=90.0
				)
				for cid, ins in insights_results:
					if ins:
						dynamic_insights[cid] = ins
			except Exception as e:
				logger.warning("Gathering active crew insights for morning briefing failed/timed out: %s", e)

		# Build unified Crew Reasoning block
		crew_blocks = []
		for c in active_crews:
			cid = c.id
			name = c.name
			
			has_insight = cid in dynamic_insights
			has_output = crew_outputs and cid in crew_outputs
			if not has_insight and not has_output:
				continue
				
			crew_block = f"--- Crew: {name} ({cid}) ---\n"
			if has_insight:
				crew_block += f"Daily Insight: {dynamic_insights[cid]}\n"
			if has_output:
				log_text = crew_outputs[cid]
				if cid == "life" and len(log_text) > 300:
					log_text = log_text[:300] + "..."
				elif len(log_text) > 1500:
					log_text = log_text[:1500] + "..."
				crew_block += f"Detailed Log/Context:\n{log_text}\n"
			crew_blocks.append(crew_block)

		if crew_blocks:
			skeleton += "\n\nCREW REASONING & DOMAIN INSIGHTS:\n" + "\n\n".join(crew_blocks)

		# Build crew prompt block conditionally — only when actual crew data exists
		_crew_prompt_block = ""
		if crew_blocks:
			_crew_prompt_block = (
				"4. CREWS: Include a 'Crews' section listing every crew present in the CREW REASONING section of the draft. "
				"For each crew, summarize their 'Daily Insight' and 'Detailed Log/Context' in Z's voice. "
				"For the 'life (private reflection)' crew output: if present, summarize as a warm 1-2 sentence note in a 'Life' section. Do not skip any crew.\n"
			)
		else:
			_crew_prompt_block = (
				"4. CREWS: No crew data is available today. Do NOT generate a Crews section. "
				"Do NOT invent crew insights, meal plans, fitness plans, or any domain-specific content.\n"
			)

		full_prompt = (
			f"You are Z, a personal AI assistant. Write the following briefing in a direct, uplifting tone — "
			f"no preamble, no 'Here is your briefing' opener, no robotic recap. Begin immediately with the most relevant information. "
			f"Tone: {settings.PERSONA_TONE}. Only use humor when it is clearly appropriate and actually funny.\n\n"
			"The BRIEFING DRAFT below contains ALL the facts for today's briefing. Your role is as follows:\n"
			"Begin the response with a compact table of contents — one line listing only the sections that have real content (skip empty or [NO DATA] sections). Format example: '1. Boards  2. Stale  3. Meta  4. Calibration'\n"
			"1. VOICE: Present the data clearly and concisely in Z's voice (warm, direct, no corporate language, no emoji). Prefer bullet points and short lines over full sentences. Headers should be 1-2 words. Get to the point.\n"
			f"2. KANBAN ANALYST: Add up to {max_obs} observations about board health — stale cards, stuck items, WIP violations, boards with nothing active.\n"
			"3. PROACTIVE THINKER: For 1-2 boards or projects, add a brief meta question that sparks strategic thinking. Must reference specific card names from the data.\n"
			f"{_crew_prompt_block}"
			"5. End with 'Irgendwas Neues fuer heute?' (or equivalent in the user's language)\n\n"
			"=== HARD RULES (violation = failure) ===\n"
			"- STRICT LENGTH: Target 150-250 words. Over 400 words is a hard failure. If the skeleton has few active items, a 100-word briefing is ideal.\n"
			"- DO NOT invent board names, card titles, or project names. Only reference what appears in the skeleton.\n"
			"- DO NOT add parenthetical status annotations to card names (e.g. '(verschoben von gestern?)', '(HRV im Stressbereich)', '(Vermieter wartet)'). Report card names EXACTLY as written in the skeleton — verbatim, no additions.\n"
			"- DO NOT merge separate cards into one entry (e.g. do not combine 'edible machen' and 'Intel Depth camera' into one line).\n"
			"- DO NOT invent shopping lists, ingredient lists, meal plans, biometric data (HRV, heart rate, sleep hours), or exercise routines unless they appear VERBATIM in the CREW REASONING section.\n"
			"- DO NOT add any information not present in the BRIEFING DRAFT.\n"
			"- DO NOT invent events, cards, emails, people, or project names.\n"
			"- If a section is absent from the draft, it does not exist today — do not mention it. Do NOT generate content for empty sections.\n"
			"- Cards from different boards/projects must stay in their respective sections. Do not cross-attribute cards.\n"
			"You may emit action tags silently (they are stripped before delivery): "
			"[ACTION: MOVE_CARD | CARD: <fragment> | LIST: <list>], [ACTION: MARK_DONE | CARD: <fragment>], [ACTION: LEARN | TEXT: <fact>]. "
			"Only for cards/boards named verbatim in the draft.\n\n"
			f"BRIEFING DRAFT:\n{skeleton}\n\n"
			f"Write the final briefing now, in {user_language}. Write only as much as the data warrants."
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
				 "Be specific — not 'my kids' but 'the way my child laughed at breakfast yesterday.' "
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
				res = await session.execute(select(Preference).where(Preference.key == "briefing_time"))
				bt_pref = res.scalar_one_or_none()
				if bt_pref and bt_pref.value:
					parts = bt_pref.value.split(":")
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
		from app.services.translations import get_user_lang
		from telegram import InlineKeyboardButton, InlineKeyboardMarkup

		lang = await get_user_lang()
		t = get_translations(lang)

		btn_text = t.get("checkin_btn_guided", "Geführtes Check-in")
		keyboard = InlineKeyboardMarkup([
			[InlineKeyboardButton(f"▶ {btn_text}", callback_data="checkin_start")]
		])

		await send_notification(
			f"---\n{content}",
			reply_markup=keyboard,
			nav_footer=get_nav_footer(t)
		)

		# 6b. Persist to global_messages NOW — after delivery so dashboard and
		# Telegram show the briefing at the same time (not 15 min early).
		await save_global_message("telegram", "z", content, model=last_model_used.get())
		# Record that a briefing was delivered this week for coach earning tracking
		from app.services.coach_earning import record_briefing_sent
		await record_briefing_sent()

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
