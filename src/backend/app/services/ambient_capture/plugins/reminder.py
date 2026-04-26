"""ReminderPlugin — routes phrases that contain explicit recurring schedules
or "every X" patterns to the calendar reminder service.

Epoch 3 plugin. Distinguishes from CalendarEventPlugin by targeting recurrence
patterns ("every Monday", "daily", "weekly", etc.) rather than one-off events.

Capabilities:
- can_create_resources: True   (creates recurring calendar entries)
- can_modify_existing: False
- can_delete: False
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from app.services.ambient_capture.plugin import (
	ActionResult,
	CaptureDecision,
	CapturePlugin,
	PluginCapabilities,
	PluginScore,
)

logger = logging.getLogger(__name__)

_RECURRENCE_RE = re.compile(
	r"\b(every|each|daily|weekly|monthly|annually|jede[rns]?|täglich|wöchentlich|"
	r"chaque|quotidien|毎|每|еженедельно)\b",
	re.I | re.UNICODE,
)

_SCHEDULE_RE = re.compile(
	r"\b(every (monday|tuesday|wednesday|thursday|friday|saturday|sunday|day|week|month)|"
	r"at \d{1,2}(:\d{2})?\s*(am|pm)?|"
	r"\d{1,2}(:\d{2})?\s*(am|pm)\b)",
	re.I,
)

_MIN_SCORE = 0.30


def _recurrence_score(phrase: str) -> float:
	hits = (1 if _RECURRENCE_RE.search(phrase) else 0) + (1 if _SCHEDULE_RE.search(phrase) else 0)
	return min(1.0, hits * 0.45)


class ReminderPlugin:
	"""Create a recurring reminder from a phrase."""

	name = "reminder"
	capabilities = PluginCapabilities(
		can_create_resources=True,
		can_modify_existing=False,
		can_delete=False,
		requires_hitl_for=frozenset({"create"}),
		max_capture_size_chars=500,
	)

	async def score_match(self, phrase: str, context: dict) -> Optional[PluginScore]:
		score = _recurrence_score(phrase)
		if score < _MIN_SCORE:
			return None
		return PluginScore(
			score=score,
			destination_id="reminder",
			destination_label="Reminder",
			reasoning={"recurrence_score": score},
		)

	async def execute_capture(self, decision: CaptureDecision) -> ActionResult:
		"""Create recurring calendar entry.  Epoch 3 stub — full integration TBD."""
		try:
			from app.services.calendar import create_recurring_reminder
			result = await create_recurring_reminder(decision.phrase)
			return ActionResult(success=True, message=str(result))
		except Exception as e:
			logger.warning("reminder: execute failed: %s", e)
			return ActionResult(success=False, message=str(e))

	async def explain_routing(self, decision: CaptureDecision, lang: str) -> str:
		return f"Recurrence pattern detected in '{decision.phrase}' → Reminder"
