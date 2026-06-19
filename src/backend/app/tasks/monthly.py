import asyncio
import logging
from app.models.db import AsyncSessionLocal, Briefing

logger = logging.getLogger(__name__)

async def monthly_review():
	"""Generate and store the monthly review."""
	from app.services.llm import chat, last_model_used
	from app.services.planka import get_project_tree, get_activity_report
	from app.services.crew_memory import get_recent_crew_outputs
	logger.info("Monthly Review started...")
	try:
		tree, activity, crew_outputs = await asyncio.gather(
			get_project_tree(as_html=False),
			get_activity_report(days=30),
			get_recent_crew_outputs(hours=720),
		)

		activity_block = activity if activity and not str(activity).strip().startswith("### OPERATIONAL DATA FAILURE") else "[EMPTY — omit the activity/accomplishments section entirely]"
		tree_block = tree if tree and str(tree).strip() else "[EMPTY — omit the project tree section entirely]"

		# Load crew registry and collect insights from all active crews
		crew_insights = []
		try:
			from app.services.crews import crew_registry
			await crew_registry.load()
			active_crews = crew_registry.list_active()
			if active_crews:
				from app.services.crews_native import native_crew_engine
				import re
				_ACTION_STRIP_RE = re.compile(r'\[ACTION:[^\]]*\]', re.IGNORECASE)

				async def _get_crew_insight(crew_config):
					try:
						crew_prompt = (
							f"You are the {crew_config.name} crew. We are preparing the monthly review for the operator.\n"
							f"Here is the month's raw data:\n\n"
							f"ACTIVITY:\n{activity_block}\n\n"
							f"PROJECTS:\n{tree_block}\n\n"
							f"Based on your specialized domain, review this data and generate a single short paragraph (under 40 words) with your top insight, recommendation, or warning for this month. "
							f"Be extremely concise. Write only the paragraph. Do not introduce yourself."
						)
						res = await native_crew_engine.run_crew(crew_config.id, crew_prompt)
						res_clean = _ACTION_STRIP_RE.sub("", res).strip()
						if res_clean:
							return f"**{crew_config.name}**: {res_clean}"
					except Exception as ex:
						logger.warning("Failed to get monthly insight from crew %s: %s", crew_config.id, ex)
					return None

				insights_results = await asyncio.wait_for(
					asyncio.gather(*[_get_crew_insight(c) for c in active_crews]),
					timeout=90.0
				)
				crew_insights = [ins for ins in insights_results if ins]
		except Exception as e:
			logger.warning("Gathering active crew insights for monthly review failed: %s", e)

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

		prompt = (
			"Z, it's been a full month — write the monthly review.\n"
			"Write like a smart colleague giving a frank summary after a month of work. Natural, direct, slightly informal — not a literary essay, not a raw data dump.\n"
			"Short sentences. Plain words. Sections are fine — the language inside should sound like a person, not a report generator.\n"
			"Be specific: name actual boards, cards, and progress mentioned in the data. Don't be vague.\n"
			"Aim for 250-400 words. Use bullets for lists; use short prose for observations and context.\n\n"
			"STRICT OPERATIONAL DATA (THE ONLY TRUTH):\n"
			f"{activity_block}\n\n"
			f"FULL PROJECT TREE:\n{tree_block}\n\n"
			f"{crew_outputs_block}\n\n"
			"HALLUCINATION RULES (never break these):\n"
			"- Only include a section if real data for it was provided in the context above.\n"
			"- If a data block is marked [EMPTY] or contains no items — omit that section entirely. No heading, no placeholder text.\n"
			"- Never invent board cards, calendar events, emails, metrics, or completed tasks.\n"
			"- Never assume what happened during the month if no data confirms it.\n"
			"- The 'What was accomplished' section must only contain items explicitly present in OPERATIONAL DATA or PROJECT TREE above. If no cards moved, state that plainly — do not invent progress.\n"
			"- Proactive goals for next month are allowed but must be clearly framed as suggestions, not as confirmed plans.\n\n"
			"CREW REASONING SECTION:\n"
			"- The CREW REASONING & DOMAIN INSIGHTS section contains domain-specific analysis from scheduled crew runs over this period.\n"
			"- If crew outputs are present, create a dedicated 'Crews' section in the review to explicitly present their feedback, findings, and domain insights. List each crew name (e.g. Scrum, Focus) and summarize what they observed or flagged. Focus on their warnings or project risks. If a section is marked [EMPTY], omit the Crews section entirely.\n\n"
			"RULES:\n"
			"1. Respond ONLY based on the OPERATIONAL DATA, PROJECT TREE, and CREW REASONING & DOMAIN INSIGHTS above.\n"
			"2. If OPERATIONAL DATA is marked [EMPTY], do not list any specific card names or board progress — acknowledge honestly that no activity data is available for this period.\n"
			"3. CRITICAL: Ignore any placeholder or '[e.g., ...]' values from personal/business context.\n"
			"4. Suggest 3 meaningful goals for next month — frame them as suggestions, not scheduled commitments.\n"
			"5. NO metaphors, NO literary prose, NO filler phrases. Write like a human, not an LLM trying to sound reflective.\n"
			"6. NEVER use emoji or unicode decorative symbols.\n"
		)

		try:
			content = await asyncio.wait_for(chat(prompt, _feature="monthly_review", include_health=False), timeout=300.0)
		except asyncio.TimeoutError:
			logger.warning("monthly_review — cloud tier timed out, retrying")
			content = await chat(prompt, _feature="monthly_review", include_health=False)

		from app.services.agent_actions import parse_and_execute_actions
		content, _, _ = await parse_and_execute_actions(content)

		# Store in Database
		async with AsyncSessionLocal() as session:
			briefing = Briefing(type="month", content=content, model=last_model_used.get())
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
		logger.error("CRITICAL: monthly_review failed: %s", e, exc_info=True)
		return None
