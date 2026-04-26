"""Email urgency adapter.

Reads EmailSummary rows from the database.

Snapshot schema (see §3.3 of ambient_intelligence.md):
{
    "unread_count": int,
    "priority_count": int,           # badge in ('priority', 'action-required')
    "unread_age_hours_max": float,   # oldest unread
    "new_since_last": int,           # delta from previous snapshot (set by diff engine)
    "priority_sender_repeat": int,   # senders with 3+ emails in 2 hours
}

Interesting diffs:
  - priority_count crossed threshold (0 -> 1+)
  - Unread count growing faster than processing
  - Oldest unread > 24h and badged
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

_PRIORITY_BADGES = {"priority", "action-required"}
_SENDER_REPEAT_WINDOW_HOURS = 2
_SENDER_REPEAT_THRESHOLD = 3


class EmailAdapter:
	source_id = "email"
	poll_interval_s = 600  # piggyback on the 10-min email poll cycle

	async def snapshot(self) -> dict:
		try:
			return await _fetch_email_snapshot()
		except Exception as exc:
			logger.warning("EmailAdapter.snapshot failed: %s", exc)
			return _empty_snapshot()


async def _fetch_email_snapshot() -> dict:
	from sqlalchemy import select
	from app.models.db import AsyncSessionLocal, EmailSummary

	now = datetime.utcnow()
	repeat_cutoff = now - timedelta(hours=_SENDER_REPEAT_WINDOW_HOURS)

	async with AsyncSessionLocal() as session:
		res = await session.execute(
			select(EmailSummary).where(EmailSummary.included_in_briefing.is_(False))
		)
		unread: list[EmailSummary] = list(res.scalars().all())

	if not unread:
		return _empty_snapshot()

	priority_count = sum(
		1 for e in unread
		if (e.badge or "").lower() in _PRIORITY_BADGES or e.is_urgent
	)

	oldest_age_hours = 0.0
	for e in unread:
		if e.processed_at:
			age_h = (now - e.processed_at).total_seconds() / 3600
			oldest_age_hours = max(oldest_age_hours, age_h)

	# Count senders who sent >= threshold emails within the repeat window
	recent = [e for e in unread if e.processed_at and e.processed_at > repeat_cutoff]
	sender_counts: dict[str, int] = {}
	for e in recent:
		sender_counts[e.sender] = sender_counts.get(e.sender, 0) + 1
	priority_sender_repeat = sum(
		1 for cnt in sender_counts.values() if cnt >= _SENDER_REPEAT_THRESHOLD
	)

	return {
		"unread_count": len(unread),
		"priority_count": priority_count,
		"unread_age_hours_max": round(oldest_age_hours, 1),
		"new_since_last": 0,  # set by DiffEngine via detect_email_surge
		"priority_sender_repeat": priority_sender_repeat,
	}


def _empty_snapshot() -> dict:
	return {
		"unread_count": 0,
		"priority_count": 0,
		"unread_age_hours_max": 0.0,
		"new_since_last": 0,
		"priority_sender_repeat": 0,
	}
