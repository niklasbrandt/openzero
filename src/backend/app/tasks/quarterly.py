import asyncio
import logging
from app.models.db import AsyncSessionLocal, Briefing

logger = logging.getLogger(__name__)

async def quarterly_review():
	"""Generate and store the quarterly strategic review."""
	from app.services.llm import chat, last_model_used
	from app.services.planka import (
		get_project_tree,
		get_activity_report,
		get_board_walkthrough,
		get_crew_board_snapshot,
		get_stale_cards,
	)
	from app.services.crew_memory import get_recent_crew_outputs
	logger.info("Quarterly Review started...")
	try:
		(
			tree,
			activity,
			crew_outputs,
			board_walkthrough,
			crew_snapshot,
			stale_cards,
		) = await asyncio.gather(
			get_project_tree(as_html=False),
			get_activity_report(days=90),
			get_recent_crew_outputs(hours=2160),
			get_board_walkthrough(min_stale_days=30),
			get_crew_board_snapshot(),
			get_stale_cards(min_days=60),
		)

		activity_block = (
			activity
			if activity and not str(activity).strip().startswith("### OPERATIONAL DATA FAILURE")
			else "[EMPTY — omit the activity/accomplishments section entirely]"
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
		stale_block = (
			stale_cards
			if stale_cards and stale_cards != "[NO STALE ITEMS]" and not stale_cards.startswith("### STALE")
			else "[NO STALE ITEMS — all active cards have been touched recently]"
		)

		# Quarterly relies on scheduled crew run outputs only.
		# get_recent_crew_outputs(hours=2160) covers 90 days of crew analysis;
		# per-crew dynamic insight calls would be redundant and costly at this cadence.
		crew_outputs_block = ""
		if crew_outputs:
			parts = [f"--- {cid} (scheduled run) ---\n{text}" for cid, text in crew_outputs.items()]
			crew_outputs_block = "CREW REASONING & DOMAIN INSIGHTS:\n" + "\n\n".join(parts)
		else:
			crew_outputs_block = "[EMPTY — no recent crew outputs]"

		prompt = (
			"Z, three months have passed — write the quarterly review.\n"
			"Write like a smart colleague summing up a quarter: natural, direct, slightly informal — not a literary reflection, not a bullet dump.\n"
			"Short sentences. Plain words. Sections are fine — the language inside should sound human, not generated.\n"
			"What actually moved, what stalled, and what matters going forward — based only on the data provided. Be specific.\n"
			"Aim for 350-500 words. Over 750 words is a failure.\n\n"
			"OPERATIONAL DATA (PAST 90 DAYS ACTIVITY):\n"
			f"{activity_block}\n\n"
			f"FULL PROJECT TREE:\n{tree_block}\n\n"
			f"BOARD WALKTHROUGH (per-board active + stale detail):\n{board_walkthrough_block}\n\n"
			f"CREW BOARD SNAPSHOT (top active items per crew board):\n{crew_snapshot_block}\n\n"
			f"STALE / NO MOVEMENT (60+ DAYS):\n{stale_block}\n\n"
			f"{crew_outputs_block}\n\n"
			"HALLUCINATION RULES (never break these):\n"
			"- Only include a section if real data for it was provided in the context above.\n"
			"- If a data block is marked [EMPTY] or contains no items — omit that section entirely. No heading, no placeholder text.\n"
			"- Never invent board cards, calendar events, emails, metrics, or completed tasks.\n"
			"- Never assume what happened during the quarter if no data confirms it.\n"
			"- The 'What was accomplished' section must only contain items explicitly present in OPERATIONAL DATA or PROJECT TREE above. If no cards moved, state that plainly — do not invent progress.\n"
			"- Proactive suggestions for the next quarter are allowed but must be clearly framed as suggestions, not as confirmed facts.\n\n"
			"CREW REASONING SECTION:\n"
			"- The CREW REASONING & DOMAIN INSIGHTS section contains domain-specific analysis from scheduled crew runs over this period.\n"
			"- If crew outputs are present, create a dedicated 'Crews' section in the review to explicitly present their feedback, findings, and domain insights. List each crew name (e.g. Scrum, Focus) and summarize what they observed or flagged. Focus on their warnings or project risks. If a section is marked [EMPTY], omit the Crews section entirely.\n\n"
			"RULES:\n"
			"1. Analyze the past 90 days based ONLY on the data above.\n"
			"2. If OPERATIONAL DATA is marked [EMPTY], do not list any specific card names or board progress — acknowledge honestly that no activity data is available for this period.\n"
			"3. Focus on what actually moved in the data and what the longer arc looks like from here.\n"
			"4. CRITICAL: Ignore any placeholder or '[e.g., ...]' values in your personal context.\n"
			"5. NO metaphors, NO literary prose, NO filler phrases. Write like a human, not an LLM trying to sound thoughtful.\n"
			"6. NEVER use emoji or unicode decorative symbols.\n"
		)

		try:
			content = await asyncio.wait_for(chat(prompt, _feature="quarterly_review", include_health=False), timeout=300.0)
		except asyncio.TimeoutError:
			logger.warning("quarterly_review — cloud tier timed out, retrying")
			content = await chat(prompt, _feature="quarterly_review", include_health=False)

		from app.services.agent_actions import parse_and_execute_actions
		content, _, _ = await parse_and_execute_actions(content)

		# Store in Database
		async with AsyncSessionLocal() as session:
			briefing = Briefing(type="quarter", content=content, model=last_model_used.get())
			session.add(briefing)
			await session.commit()

		# Send Telegram Notification
		from app.services.notifier import send_notification
		from app.config import settings
		await send_notification(f"---\n{content}\n\n[Dashboard]({settings.BASE_URL}/dashboard)")

		from app.models.db import save_global_message
		await save_global_message("telegram", "z", content, model=last_model_used.get())

		return content

	except Exception as e:
		logger.error("CRITICAL: quarterly_review failed: %s", e, exc_info=True)
		return None
