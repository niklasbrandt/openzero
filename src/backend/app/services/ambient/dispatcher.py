"""Crew dispatch + direct-insight delivery for ambient triggers.

For crew triggers:  calls execute_crew_programmatically() for each crew.
For crewless triggers:  generates a short LLM insight from the trigger context.

Ambient outputs are saved to GlobalMessage with channel="ambient" so they
are queryable but don't pollute the user channels.

See docs/artifacts/ambient_intelligence.md §7.
"""

from __future__ import annotations

import logging

from app.services.ambient.models import Trigger

logger = logging.getLogger(__name__)

_PREFIX = "[Ambient]"


async def dispatch(trigger: Trigger) -> None:
	"""Dispatch a trigger: fire crews or generate a direct insight."""
	if trigger.crews:
		await _fire_crews(trigger)
	else:
		await _direct_insight(trigger)


async def _fire_crews(trigger: Trigger) -> None:
	try:
		from app.services.agent_actions import execute_crew_programmatically
		for crew_id in trigger.crews:
			logger.info(
				"AmbientDispatcher: firing crew '%s' for trigger '%s'",
				crew_id, trigger.rule_id,
			)
			await execute_crew_programmatically(crew_id, trigger.context)
	except Exception as exc:
		logger.error("AmbientDispatcher._fire_crews failed for '%s': %s", trigger.rule_id, exc)


async def _direct_insight(trigger: Trigger) -> None:
	"""Generate a concise LLM insight and push it to all channels."""
	try:
		from app.services.llm import chat as llm_chat
		from app.services.message_bus import bus

		prompt = (
			f"{trigger.context}\n\n"
			"Respond with a brief, actionable insight (2-4 sentences). "
			"Do not ask follow-up questions. Be direct."
		)
		insight = await llm_chat(prompt, system_override=None)
		if not insight:
			return

		message = f"{_PREFIX} {insight}"
		await bus.push_all(message)
		logger.info(
			"AmbientDispatcher: direct insight delivered for trigger '%s'",
			trigger.rule_id,
		)
	except Exception as exc:
		logger.error(
			"AmbientDispatcher._direct_insight failed for '%s': %s",
			trigger.rule_id, exc,
		)
