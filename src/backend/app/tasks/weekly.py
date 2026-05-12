from app.services.llm import chat, last_model_used
from app.services.planka import get_project_tree, get_recent_activity, get_stale_cards
from app.models.db import AsyncSessionLocal, Briefing
import asyncio
import datetime

async def weekly_review():
	"""Generate and store the weekly review based on live Planka activity."""
	import logging
	logger = logging.getLogger(__name__)
	logger.info("Weekly Review started...")
	
	try:
		tree, recent_activity, stale_cards = await asyncio.gather(
			get_project_tree(as_html=False),
			get_recent_activity(hours=336),
			get_stale_cards(min_days=14),
		)

		activity_block = recent_activity if recent_activity and not recent_activity.startswith("### RECENT ACTIVITY FETCH FAILED") else "[EMPTY — omit the activity/accomplishments section entirely]"
		stale_block = stale_cards if stale_cards and stale_cards != "[NO STALE ITEMS]" and not stale_cards.startswith("### STALE") else "[NO STALE ITEMS — all active cards have been touched recently]"
		tree_block = tree if tree and str(tree).strip() else "[EMPTY — omit the project tree section entirely]"

		prompt = (
			"ABSOLUTE RULE — FABRICATION IS FORBIDDEN:\n"
			"Every statement in this review must reference data from one of the sections below.\n"
			"If a section is marked [EMPTY] or [NO STALE ITEMS], do not mention that topic.\n"
			"Do not generate project guesses, suggestions, or next-week plans from your own knowledge.\n\n"
			"Z, it's the end of the week — write the weekly review.\n"
			"Write like a smart colleague summing up the week in a message. Natural, direct, slightly informal — not a literary reflection, not a bullet dump.\n"
			"Short sentences. Plain words. Sections with headers are fine — the language inside should sound like a person, not a report generator.\n"
			"Be specific: name actual boards, cards, and progress mentioned in the data. Don't be vague.\n"
			"Write only as much as the data warrants. If activity is light, a short focused review is better than a padded one. If there is a lot happening, up to ~600 words is fine. Never pad. Use bullets for lists of items; use short prose for observations and context.\n\n"
			f"RECENCY NOTE: Activity covers the last 14 days. Focus your analysis on the most recent 7 days; treat the prior 7 days as comparison context only.\n\n"
			f"RECENT ACTIVITY (LAST 14 DAYS):\n{activity_block}\n\n"
			f"STALE / NO MOVEMENT (14+ DAYS):\n{stale_block}\n\n"
			f"PROJECT TREE:\n{tree_block}\n\n"
			"HALLUCINATION RULES (never break these):\n"
			"- Only include a section if real data for it was provided in the context above.\n"
			"- If a data block is marked [EMPTY] or contains no items — omit that section entirely. No heading, no placeholder text.\n"
			"- Never invent board cards, calendar events, emails, metrics, or completed tasks.\n"
			"- Never assume what happened during the week if no data confirms it.\n"
			"- The 'What was accomplished' section must only contain items explicitly present in RECENT ACTIVITY or PROJECT TREE above. If no cards moved, state that plainly — do not invent progress.\n"
			"- Every bullet must trace back to a card name, board name, or list name that appears verbatim in the data above.\n\n"
			"RULES:\n"
			"- Base your message ONLY on the data sections provided above.\n"
			"- If RECENT ACTIVITY is marked [EMPTY], do not list any specific card names or board progress — acknowledge honestly that no activity data is available for this period.\n"
			"- Ignore any placeholder or '[e.g., ...]' values in personal context files — treat them as absent.\n"
			"- NO metaphors, NO literary prose, NO filler ('honestly?', 'that screams', etc.). Write like a human, not an LLM trying to sound thoughtful.\n"
			"- NEVER use emoji or unicode decorative symbols.\n\n"
			"STALE ITEMS SECTION (only if STALE / NO MOVEMENT has real entries):\n"
			"- Name each stale card and its board verbatim from the STALE section.\n"
			"- State how many days it has been inactive.\n"
			"- Suggest the one concrete action that would unblock or close it — only if that action is inferable from the card name and board context.\n\n"
			"PRIORITIZATION & NEXT STEPS (section 'Next Week:', before board audit, only if PROJECT TREE not [EMPTY]):\n"
			"- Pick 3-5 cards ranked by impact/urgency from PROJECT TREE or RECENT ACTIVITY. One line per card: name + board + single next physical action.\n"
			"- Blocking cards go first. Boards with no active work: name one card to pull.\n"
			"- No vague actions ('continue work on X'). Every step must be executable.\n"
			"- Frame as: 'Vorschlag für nächste Woche:' (or equivalent in user's language).\n\n"
			"BOARD STRUCTURE AUDIT (section 'Board Setup:', after 'Next Week:', only if PROJECT TREE not [EMPTY]):\n"
			"- One bullet per board: assess whether list structure supports clear flow. Healthy = one line.\n"
			"- Name specific improvements for any board missing a stage or with redundant/unclear lists.\n"
			"- End with: 'Soll ich bei einem dieser Boards die Listen anpassen?' (or equivalent).\n"
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

		# Phase W: build and deliver as walk-through
		try:
			from app.services.walkthroughs import build_walkthrough
			from app.services.walkthrough_renderer import render_all
			wt = await build_walkthrough(kind="weekly")
			await render_all(wt)
		except Exception as _wt_err:
			logger.warning("weekly_review: walk-through build failed (non-fatal): %s", _wt_err)

		return content

	except Exception as e:
		logger.error("CRITICAL: Weekly Review failed: %s", e, exc_info=True)
		return None
