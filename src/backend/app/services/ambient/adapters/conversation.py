"""Conversational signals meta-adapter.

Scans GlobalMessage for meta-level conversation signals WITHOUT storing
any message content. Reports counts and ages only.

Snapshot schema (see §3.6 of ambient_intelligence.md):
{
    "messages_last_hour": int,
    "last_user_message_age_minutes": int,   # -1 = no recent messages
    "active_tracking_sessions": int,
    "sentiment_keywords": [str],            # keyword names only, never message text
    "unanswered_count": int,
}

Interesting diffs:
  - User silent for 4+ hours during active hours (check-in opportunity)
  - Rapid burst (user is stressed or excited)
  - Unanswered messages appeared
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

_POSITIVE_KEYWORDS = {"amazing", "great", "fantastic", "love", "excited", "happy"}
_NEGATIVE_KEYWORDS = {"angry", "frustrated", "hate", "horrible", "terrible", "worst"}


class ConversationAdapter:
	source_id = "conversation"
	poll_interval_s = 300

	async def snapshot(self) -> dict:
		try:
			return await _fetch_conversation_snapshot()
		except Exception as exc:
			logger.warning("ConversationAdapter.snapshot failed: %s", exc)
			return _empty_snapshot()


async def _fetch_conversation_snapshot() -> dict:
	from sqlalchemy import select, func
	from app.models.db import AsyncSessionLocal, GlobalMessage

	now = datetime.utcnow()
	cutoff_1h = now - timedelta(hours=1)
	cutoff_4h = now - timedelta(hours=4)

	snap = _empty_snapshot()

	async with AsyncSessionLocal() as session:
		# Count user messages in last hour
		res = await session.execute(
			select(func.count(GlobalMessage.id))
			.where(GlobalMessage.role == "user")
			.where(GlobalMessage.created_at >= cutoff_1h)
		)
		snap["messages_last_hour"] = res.scalar_one() or 0

		# Most recent user message timestamp
		res2 = await session.execute(
			select(GlobalMessage.created_at)
			.where(GlobalMessage.role == "user")
			.order_by(GlobalMessage.created_at.desc())
			.limit(1)
		)
		latest_ts = res2.scalar_one_or_none()
		if latest_ts:
			snap["last_user_message_age_minutes"] = int(
				(now - latest_ts).total_seconds() / 60
			)

		# Scan last hour for sentiment keywords (count occurrences, never store text)
		res3 = await session.execute(
			select(GlobalMessage.content)
			.where(GlobalMessage.role == "user")
			.where(GlobalMessage.created_at >= cutoff_1h)
		)
		detected_kw: list[str] = []
		for (content,) in res3.all():
			if not content:
				continue
			lower = content.lower()
			for kw in _POSITIVE_KEYWORDS:
				if kw in lower and kw not in detected_kw:
					detected_kw.append(kw)
			for kw in _NEGATIVE_KEYWORDS:
				if kw in lower and kw not in detected_kw:
					detected_kw.append(kw)
		snap["sentiment_keywords"] = detected_kw

		# Unanswered user messages: user messages with no Z response after them
		res4 = await session.execute(
			select(GlobalMessage.created_at, GlobalMessage.role)
			.where(GlobalMessage.created_at >= cutoff_4h)
			.order_by(GlobalMessage.created_at.asc())
		)
		rows = list(res4.all())
		unanswered = 0
		last_role: str | None = None
		for ts, role in rows:
			if role == "user" and last_role != "z":
				unanswered += 1
			elif role == "z":
				unanswered = 0  # reset on Z reply
			last_role = role
		snap["unanswered_count"] = unanswered

	# Active tracking sessions from follow_up service (sync, non-blocking)
	try:
		from app.services.follow_up import _nudge_state
		snap["active_tracking_sessions"] = len(_nudge_state)
	except Exception:
		pass

	return snap


def _empty_snapshot() -> dict:
	return {
		"messages_last_hour": 0,
		"last_user_message_age_minutes": -1,
		"active_tracking_sessions": 0,
		"sentiment_keywords": [],
		"unanswered_count": 0,
	}
