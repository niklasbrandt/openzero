from app.services.llm import chat, last_model_used
from app.services.planka import get_project_tree, get_activity_report
from app.models.db import AsyncSessionLocal, Briefing
import asyncio
import datetime

async def weekly_review():
	"""Generate and store the weekly review based on live Planka activity."""
	import logging
	logger = logging.getLogger(__name__)
	logger.info("Weekly Review started...")
	
	try:
		tree = await get_project_tree(as_html=False)
		activity = await get_activity_report(days=7)

		activity_block = activity if activity and not str(activity).strip().startswith("### OPERATIONAL DATA FAILURE") else "[EMPTY — omit the activity/accomplishments section entirely]"
		tree_block = tree if tree and str(tree).strip() else "[EMPTY — omit the project tree section entirely]"

		prompt = (
			"Z, it's the end of the week — write the weekly review.\n"
			"Write like a smart colleague summing up the week in a message. Natural, direct, slightly informal — not a literary reflection, not a bullet dump.\n"
			"Short sentences. Plain words. Sections with headers are fine — the language inside should sound like a person, not a report generator.\n"
			"Be specific: name actual boards, cards, and progress mentioned in the data. Don't be vague.\n"
			"Aim for 200-350 words. Over 500 words is a failure regardless of data volume. Use bullets for lists of items; use short prose for observations and context.\n\n"
			"OPERATIONAL DATA (7-DAY ACTIVITY):\n"
			f"{activity_block}\n\n"
			f"PROJECT TREE:\n{tree_block}\n\n"
			"HALLUCINATION RULES (never break these):\n"
			"- Only include a section if real data for it was provided in the context above.\n"
			"- If a data block is marked [EMPTY] or contains no items — omit that section entirely. No heading, no placeholder text.\n"
			"- Never invent board cards, calendar events, emails, metrics, or completed tasks.\n"
			"- Never assume what happened during the week if no data confirms it.\n"
			"- The 'What was accomplished' section must only contain items explicitly present in OPERATIONAL DATA or PROJECT TREE above. If no cards moved, state that plainly — do not invent progress.\n"
			"- Proactive suggestions for next week are allowed but must be clearly framed as suggestions, not as confirmed facts.\n\n"
			"RULES:\n"
			"- Base your message ONLY on the OPERATIONAL DATA and PROJECT TREE provided above.\n"
			"- If OPERATIONAL DATA is marked [EMPTY], do not list any specific card names or board progress — acknowledge honestly that no activity data is available for this period.\n"
			"- Do not mention placeholder examples from personal files (like Acme Studio).\n"
			"- NO metaphors, NO literary prose, NO filler ('honestly?', 'that screams', etc.). Write like a human, not an LLM trying to sound thoughtful.\n"
			"- NEVER use emoji or unicode decorative symbols.\n\n"
			"PRIORITIZATION & NEXT STEPS (include as a labelled section 'Next Week:' before the board audit, only if PROJECT TREE is not [EMPTY]):\n"
			"As a kanban expert, read all cards across all boards and produce an opinionated priority ranking for the coming week:\n"
			"- Pick the top 3-5 cards or work items that should move next week, ranked by impact and urgency.\n"
			"- For each: one line naming the card and its board, plus the single next physical action that would advance it (e.g. 'write the first draft', 'run the test suite', 'send the email', 'book the appointment').\n"
			"- If a card is blocking other cards downstream, flag it explicitly — it should be at the top.\n"
			"- If any board has no active work this week, include a pull recommendation: name the best card to start.\n"
			"- Do NOT suggest vague actions like 'continue work on X' or 'make progress on Y'. Every step must be physically executable.\n"
			"- This is a recommendation, not a directive — frame it as: 'Vorschlag für nächste Woche:' (or equivalent in the user's language).\n\n"
			"BOARD STRUCTURE AUDIT (include as a labelled section 'Board Setup:' after 'Next Week:', only if PROJECT TREE is not [EMPTY]):\n"
			"For each board in the project tree:\n"
			"- Read its actual list names from the tree.\n"
			"- As a kanban expert, assess whether the current list structure supports clear flow for that board's purpose.\n"
			"- If the structure looks healthy, say so briefly in one line.\n"
			"- If a board has no lists, or has redundant/unclear lists, or is missing a stage that would clearly help (e.g. a review gate, a blocked column), name the specific improvement and ask if the user wants it set up.\n"
			"- Keep it one bullet per board. Do not over-explain. Concrete, opinionated.\n"
			"- End with: 'Soll ich bei einem dieser Boards die Listen anpassen?' (or equivalent in the user's language).\n"
			"'Board Setup:' must be the last section."
		)
		
		try:
			content = await asyncio.wait_for(chat(prompt, _feature="weekly_review", include_health=False), timeout=300.0)
		except asyncio.TimeoutError:
			logger.warning("weekly_review — cloud tier timed out, retrying")
			content = await chat(prompt, _feature="weekly_review", include_health=False)

		from app.services.agent_actions import parse_and_execute_actions
		content, _, _ = await parse_and_execute_actions(content)

		# Store in Database
		async with AsyncSessionLocal() as session:
			briefing = Briefing(type="week", content=content, model=last_model_used.get())
			session.add(briefing)
			await session.commit()
			
		# Precision Delivery SLEEP logic
		try:
			from app.services.timezone import get_current_timezone
			import pytz
			tz_str = await get_current_timezone()
			tz = pytz.timezone(tz_str)
			now = datetime.datetime.now(tz)
			target = now.replace(hour=10, minute=0, second=0, microsecond=0)
			delta = (target - now).total_seconds()
			if 0 < delta < 1800:
				logger.info("weekly_review — Precision SLEEP for %.1fs.", delta)
				await asyncio.sleep(delta)
		except Exception as e:
			logger.warning("weekly_review — Precision SLEEP failed: %s", e)
		
		# Send Telegram Notification
		from app.services.notifier import send_notification
		from app.config import settings
		await send_notification(f"---\n{content}\n\n[Dashboard]({settings.BASE_URL}/dashboard)")

		from app.models.db import save_global_message
		await save_global_message("telegram", "z", content, model=last_model_used.get())

		return content

	except Exception as e:
		logger.error("CRITICAL: Weekly Review failed: %s", e, exc_info=True)
		return None
