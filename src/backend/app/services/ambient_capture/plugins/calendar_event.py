"""CalendarEventPlugin — routes date-bearing phrases to the calendar service.

Epoch 3 plugin. Scores phrases that contain a date/time pattern or event
keyword, then creates a calendar event via the existing calendar service.

Scoring is self-contained: no Planka profile builder needed.

Capabilities:
- can_create_resources: True   (creates calendar events)
- can_modify_existing: False   (Epoch 3 v1 — create only)
- can_delete: False            (ambient routing never deletes)
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

# Simple date/time anchor patterns for cheap Tier A scoring.
_DATE_PATTERNS = [
	re.compile(r"\b\d{1,2}[./\-]\d{1,2}([./\-]\d{2,4})?\b"),     # 12/05 or 12.05.2024
	re.compile(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\b", re.I),
	re.compile(r"\b(january|february|march|april|june|july|august|september|october|november|december)\b", re.I),
	re.compile(r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", re.I),
	re.compile(r"\b\d{4}\b"),  # bare year
	re.compile(r"\b(at|on|every|next|this)\s+\w+", re.I),
]

_EVENT_KEYWORDS = frozenset({
	"meeting", "appointment", "call", "session", "visit", "conference",
	"flight", "train", "marathon", "race", "birthday", "anniversary",
	"deadline", "reminder", "event", "lunch", "dinner", "breakfast",
	"termin",  # DE
	"cita",    # ES/PT
})

# Minimum score to report a non-None PluginScore.
_MIN_SCORE = 0.20


def _date_score(phrase: str) -> float:
	"""Cheap Tier A: fraction of date patterns matched, capped at 0.60."""
	hits = sum(1 for p in _DATE_PATTERNS if p.search(phrase))
	return min(0.60, hits * 0.12)


def _keyword_score(phrase: str) -> float:
	"""Cheap Tier A: event-keyword presence, capped at 0.40."""
	words = set(phrase.lower().split())
	hits = len(words & _EVENT_KEYWORDS)
	return min(0.40, hits * 0.20)


class CalendarEventPlugin:
	"""Route a phrase to a new calendar event."""

	name = "calendar_event"
	capabilities = PluginCapabilities(
		can_create_resources=True,
		can_modify_existing=False,
		can_delete=False,
		requires_hitl_for=frozenset({"create"}),
		max_capture_size_chars=500,
	)

	async def score_match(self, phrase: str, context: dict) -> Optional[PluginScore]:
		date_s = _date_score(phrase)
		kw_s = _keyword_score(phrase)
		score = min(1.0, date_s + kw_s)
		if score < _MIN_SCORE:
			return None
		return PluginScore(
			score=score,
			destination_id="calendar",
			destination_label="Calendar",
			reasoning={"date_score": date_s, "keyword_score": kw_s},
		)

	async def execute_capture(self, decision: CaptureDecision) -> ActionResult:
		"""Create a calendar event.  Epoch 3 stub — full integration in follow-up."""
		try:
			from app.services.calendar import create_event_from_phrase
			result = await create_event_from_phrase(decision.phrase)
			return ActionResult(success=True, message=result.get("message", ""), resource_id=result.get("id"))
		except Exception as e:
			logger.warning("calendar_event: execute failed: %s", e)
			return ActionResult(success=False, message=str(e))

	async def explain_routing(self, decision: CaptureDecision, lang: str) -> str:
		return f"Date or event keyword detected in '{decision.phrase}' → Calendar"
