from app.services.llm import chat, last_model_used
from app.services.planka import (
	get_project_tree,
	get_recent_activity,
	get_stale_cards,
	get_board_walkthrough,
	get_crew_board_snapshot,
)
from app.models.db import AsyncSessionLocal, Briefing
import asyncio
import datetime

async def weekly_review():
	"""Generate and store the weekly review based on live Planka activity."""
	import logging
	logger = logging.getLogger(__name__)
	logger.info("Weekly Review started...")

	try:
		from app.services.crew_memory import get_recent_crew_outputs
		(
			tree,
			recent_activity,
			stale_cards,
			crew_outputs,
			board_walkthrough,
			crew_snapshot,
		) = await asyncio.gather(
			get_project_tree(as_html=False),
			get_recent_activity(hours=336),
			get_stale_cards(min_days=14),
			get_recent_crew_outputs(hours=168),
			get_board_walkthrough(min_stale_days=7),
			get_crew_board_snapshot(),
		)

		activity_block = (
			recent_activity
			if recent_activity and not recent_activity.startswith("### RECENT ACTIVITY FETCH FAILED")
			else "[EMPTY — omit the activity/accomplishments section entirely]"
		)
		stale_block = (
			stale_cards
			if stale_cards and stale_cards != "[NO STALE ITEMS]" and not stale_cards.startswith("### STALE")
			else "[NO STALE ITEMS — all active cards have been touched recently]"
		)
		tree_block = tree if tree and str(tree).strip() else "[EMPTY — omit the project tree section entirely]"
		board_walkthrough_block = (
			board_walkthrough
			if board_walkthrough and "UNAVAILABLE" not in board_walkthrough and "no boards" not in board_walkthrough
			else "[EMPTY — board walkthrough unavailable]"
		)
		crew_snapshot_block = (
			crew_snapshot
			if crew_snapshot and "UNAVAILABLE" not in crew_snapshot and "no crew boards" not in crew_snapshot
			else "[EMPTY — crew snapshot unavailable]"
		)

		# Batch all active crew insights in a SINGLE inference call instead of N separate calls.
		# This replaces the previous asyncio.gather(*[run_crew(c) for c in active_crews]) pattern.
		crew_insights = []
		try:
			from app.services.crews import crew_registry
			await crew_registry.load()
			active_crews = crew_registry.list_active()
			if active_crews:
				import re
				_ACTION_STRIP_RE = re.compile(r'\[ACTION:[^\]]*\]', re.IGNORECASE)
				crew_list = "\n".join(
					f"- {c.id} ({c.name}): {c.description}" for c in active_crews
				)
				batch_prompt = (
					"The following specialist crews are reviewing the week's data.\n"
					"For each crew, write one paragraph (under 40 words) grounded strictly in their domain.\n"
					"Output EXACTLY one line per crew in this format: '<crew_id>: <paragraph>'\n\n"
					f"Crews:\n{crew_list}\n\n"
					f"Weekly data:\nACTIVITY:\n{activity_block}\n\nPROJECTS:\n{tree_block}\n\n"
					"Rules: base each paragraph only on the data above. "
					"No intros. Do not say 'Here is my insight'. Do not invent data."
				)
				try:
					batch_result = await asyncio.wait_for(
						chat(batch_prompt, _feature="weekly_crew_batch_insights", include_health=False),
						timeout=60.0,
					)
					batch_result = _ACTION_STRIP_RE.sub("", batch_result)
					for line in batch_result.strip().splitlines():
						if ":" in line:
							cid, _, paragraph = line.partition(":")
							cid = cid.strip()
							paragraph = paragraph.strip()
							if paragraph:
								crew_name = next((c.name for c in active_crews if c.id == cid), cid)
								crew_insights.append(f"**{crew_name}**: {paragraph}")
				except Exception as batch_err:
					logger.warning("Batch crew insights for weekly review failed: %s", batch_err)
		except Exception as e:
			logger.warning("Crew registry load for weekly review failed: %s", e)

		crew_outputs_block = ""
		if crew_outputs or crew_insights:
			parts = []
			if crew_outputs:
				for cid, text in crew_outputs.items():
					parts.append(f"--- {cid} (scheduled run) ---\n{text}")
			if crew_insights:
				parts.append("--- Active Crew Insights ---\n" + "\n".join(crew_insights))
			crew_outputs_block = "CREW REASONING & DOMAIN INSIGHTS:\n" + "\n\n".join(parts)
		else:
			crew_outputs_block = "[EMPTY — no recent crew outputs]"

		now = datetime.datetime.now()
		start_dt = now - datetime.timedelta(days=7)
		date_range_str = f"{start_dt.strftime('%d.%m.%Y')} – {now.strftime('%d.%m.%Y')}"

		prompt = (
			"ABSOLUTE RULE — FABRICATION IS FORBIDDEN:\n"
			"Every statement in this review must reference data from one of the sections below.\n"
			"If a section is marked [EMPTY] or [NO STALE ITEMS], do not mention that topic.\n"
			"Do not generate project guesses, suggestions, or next-week plans from your own knowledge.\n\n"
			f"Z, write the weekly review covering the 7-day period: {date_range_str}.\n"
			"Tone: Direct, grounded, objective, professional yet conversational. Natural, clear, concise — not a literary reflection, not a snarky commentary, not a bullet dump.\n"
			"Short sentences. Plain words. Use standard markdown headings on their own lines (e.g. '## Erledigt', '## In Arbeit / Offen', '## Stillstand / Bottlenecks', '## Crews & Insights', '## Vorschlag für nächste Woche', '## Board Setup').\n"
			f"IMPORTANT TITLE & FORMATTING RULES:\n"
			f"- The very first line MUST be a standard Markdown H1 title: '# Wochenrückblick ({date_range_str})' followed by a blank line.\n"
			f"- NEVER wrap the title in square brackets like '[Wochenrückblick – ...]'.\n"
			f"- NO cringy, folksy, or cynical metaphors/similes (e.g. absolutely NO 'wie Wäsche...', 'wie ein langer Sonntag', 'wie ein Haufen ungeladener Gäste').\n"
			f"- NO sarcastic or patronizing parenthetical commentary on tasks. Report completed items straightforwardly.\n"
			f"- NO whimsical, metaphorical, or sarcastic section headings. Use plain, clear headings.\n"
			f"- NO cynical remarks about lack of progress. State facts objectively.\n"
			"Be specific: name actual boards, cards, and progress mentioned in the data. Don't be vague.\n"
			"Aim for 450-700 words. Provide thorough, well-elaborated analysis across all sections — dive into what moved, why stalled items are blocked, and what the strategic focus for next week should be. Use bullets for lists of items; use short prose for observations and context.\n\n"
			f"REVIEW PERIOD: {date_range_str} (covers the past 7 days)\n\n"
			f"RECENCY NOTE: Activity covers the last 14 days. Focus your analysis on the most recent 7 days; treat the prior 7 days as comparison context only.\n\n"
			f"RECENT ACTIVITY (LAST 14 DAYS):\n{activity_block}\n\n"
			f"STALE / NO MOVEMENT (14+ DAYS):\n{stale_block}\n\n"
			f"PROJECT TREE:\n{tree_block}\n\n"
			f"BOARD WALKTHROUGH (per-board active + stale detail):\n{board_walkthrough_block}\n\n"
			f"CREW BOARD SNAPSHOT (top active items per crew board):\n{crew_snapshot_block}\n\n"
			f"{crew_outputs_block}\n\n"
			"HALLUCINATION RULES (never break these):\n"
			"- Only include a section if real data for it was provided in the context above.\n"
			"- If a data block is marked [EMPTY] or contains no items — omit that section entirely. No heading, no placeholder text.\n"
			"- Never invent board cards, calendar events, emails, metrics, or completed tasks.\n"
			"- Never assume what happened during the week if no data confirms it.\n"
			"- The 'What was accomplished' section must only contain items explicitly present in RECENT ACTIVITY or PROJECT TREE above. If no cards moved, state that plainly — do not invent progress.\n"
			"- Never treat stale or aged WIP cards (cards in 'In Progress' without recent completion) as accomplishments or positive progress — they are stalled bottlenecks.\n"
			"- NO SELF-REFERENTIAL BIAS: Do not highlight or give special prominence/praise to the 'openZero' board, openZero tasks, or system self-development unless actual tangible cards moved to Done in the data. Treat openZero identically to every other project board.\n"
			"- Every bullet must trace back to a card name, board name, or list name that appears verbatim in the data above.\n\n"
			"CREW REASONING SECTION:\n"
			"- The CREW REASONING & DOMAIN INSIGHTS section contains domain-specific analysis from scheduled crew runs over this period.\n"
			"- If crew outputs are present, create a dedicated 'Crews' section in the review to explicitly present their feedback, findings, and domain insights. List each crew name (e.g. Scrum, Focus) and summarize what they observed or flagged. Focus on their warnings or project risks. If a section is marked [EMPTY], omit the Crews section entirely.\n\n"
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
			content = await asyncio.wait_for(chat(prompt, tier="cloud", _feature="weekly_review", max_tokens=2000, include_health=False), timeout=300.0)
		except asyncio.TimeoutError:
			logger.warning("weekly_review — cloud tier timed out, retrying")
			content = await chat(prompt, tier="cloud", _feature="weekly_review", max_tokens=2000, include_health=False)

		from app.services.agent_actions import parse_and_execute_actions
		from app.tasks.review_utils import format_review_markdown
		content, _, _ = await parse_and_execute_actions(content)
		content = format_review_markdown(content, "Wochenrückblick", date_range_str)

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
