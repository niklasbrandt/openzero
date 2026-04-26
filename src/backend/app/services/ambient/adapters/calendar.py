"""Calendar density adapter.

Snapshot schema (see §3.2 of ambient_intelligence.md):
{
    "today_events": int,
    "today_meeting_hours": float,
    "today_gaps_minutes": [int],
    "tomorrow_events": int,
    "tomorrow_meeting_hours": float,
    "next_event_minutes": int,      # minutes until next event (-1 = none)
    "travel_detected": bool,
    "back_to_back_count": int,      # pairs with <15min gap
}

Interesting diffs:
  - Tomorrow meeting hours > 6 (calendar overload incoming)
  - Back-to-back count > 3 (no recovery time)
  - Travel detected
  - Next event in < 30 minutes (suppress pushes in delivery.py)
  - Today has zero gaps > 30 minutes (deep work impossible)
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

_TRAVEL_KEYWORDS = {
	"flight to", "trip to", "stay in", "travel to", "moving to",
	"flug nach", "reise nach", "fahrt nach",
}
_BACK_TO_BACK_GAP_MINUTES = 15


class CalendarAdapter:
	source_id = "calendar"
	poll_interval_s = 300

	async def snapshot(self) -> dict:
		try:
			return await _fetch_calendar_snapshot()
		except Exception as exc:
			logger.warning("CalendarAdapter.snapshot failed: %s", exc)
			return _empty_snapshot()


async def _fetch_calendar_snapshot() -> dict:
	from app.services.calendar import fetch_calendar_events

	now = datetime.utcnow()
	today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
	today_end = today_start + timedelta(days=1)
	tomorrow_start = today_end
	tomorrow_end = tomorrow_start + timedelta(days=1)

	# Fetch 2 days of events in one call
	events = await fetch_calendar_events(days_ahead=2)
	if not events:
		return _empty_snapshot()

	def _parse_dt(s: str) -> datetime | None:
		if not s:
			return None
		try:
			if "T" in s:
				return datetime.fromisoformat(s.replace("Z", "+00:00")).replace(tzinfo=None)
			return datetime.strptime(s, "%Y-%m-%d")
		except ValueError:
			return None

	today_events: list[dict] = []
	tomorrow_events: list[dict] = []
	travel_detected = False

	for ev in events:
		start_dt = _parse_dt(ev.get("start", ""))
		end_dt = _parse_dt(ev.get("end", ""))
		if start_dt is None:
			continue
		summary_lower = ev.get("summary", "").lower()

		if any(kw in summary_lower for kw in _TRAVEL_KEYWORDS):
			travel_detected = True

		if today_start <= start_dt < today_end:
			today_events.append({"start": start_dt, "end": end_dt, "summary": ev.get("summary", "")})
		elif tomorrow_start <= start_dt < tomorrow_end:
			tomorrow_events.append({"start": start_dt, "end": end_dt, "summary": ev.get("summary", "")})

	def _meeting_hours(evs: list[dict]) -> float:
		total = 0.0
		for ev in evs:
			start, end = ev["start"], ev["end"]
			if start and end and isinstance(start, datetime) and isinstance(end, datetime):
				total += (end - start).total_seconds() / 3600
		return round(total, 2)

	def _gaps_minutes(evs: list[dict]) -> list[int]:
		sorted_evs = sorted(evs, key=lambda e: e["start"] or datetime.max)
		gaps: list[int] = []
		for i in range(1, len(sorted_evs)):
			prev_end = sorted_evs[i - 1].get("end")
			curr_start = sorted_evs[i].get("start")
			if prev_end and curr_start and isinstance(prev_end, datetime):
				gap = int((curr_start - prev_end).total_seconds() / 60)
				if gap > 0:
					gaps.append(gap)
		return gaps

	def _back_to_back_count(evs: list[dict]) -> int:
		gaps = _gaps_minutes(evs)
		return sum(1 for g in gaps if g < _BACK_TO_BACK_GAP_MINUTES)

	# Next event in minutes
	next_event_minutes = -1
	for ev in sorted(today_events, key=lambda e: e["start"] or datetime.max):
		start = ev["start"]
		if isinstance(start, datetime) and start > now:
			delta_m = int((start - now).total_seconds() / 60)
			next_event_minutes = delta_m
			break

	today_gaps = _gaps_minutes(today_events)

	return {
		"today_events": len(today_events),
		"today_meeting_hours": _meeting_hours(today_events),
		"today_gaps_minutes": today_gaps,
		"tomorrow_events": len(tomorrow_events),
		"tomorrow_meeting_hours": _meeting_hours(tomorrow_events),
		"next_event_minutes": next_event_minutes,
		"travel_detected": travel_detected,
		"back_to_back_count": _back_to_back_count(today_events + tomorrow_events),
	}


def _empty_snapshot() -> dict:
	return {
		"today_events": 0,
		"today_meeting_hours": 0.0,
		"today_gaps_minutes": [],
		"tomorrow_events": 0,
		"tomorrow_meeting_hours": 0.0,
		"next_event_minutes": -1,
		"travel_detected": False,
		"back_to_back_count": 0,
	}
