"""Delivery scheduler for ambient triggers.

P0 implementation: immediate delivery only (priority 1) and quiet-moment
delivery for priority 2-3.  Priority 4-5 inserts into the briefing queue
(`oz:ambient:briefing_queue`) for morning.py to consume.

Quiet moment conditions (P0 — simple checks):
  - No calendar event starting within AMBIENT_QUIET_MOMENT_WINDOW_M minutes.
  - Current time is within active hours (respects Person.quiet_hours_* if
    available; falls back to 07:00-22:00).

See docs/artifacts/ambient_intelligence.md §8.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from app.services.ambient.models import Trigger

logger = logging.getLogger(__name__)

_BRIEFING_QUEUE_KEY = "oz:ambient:briefing_queue"
_BRIEFING_QUEUE_TTL_S = 86400  # 24 hours — stale entries evict automatically


def _get_redis():
	import redis
	from app.config import settings
	return redis.Redis(
		host=settings.REDIS_HOST,
		port=settings.REDIS_PORT,
		password=settings.REDIS_PASSWORD or None,
		decode_responses=True,
		socket_timeout=2.0,
	)


async def deliver(trigger: Trigger) -> None:
	"""Route a trigger to the correct delivery path."""
	from app.config import settings
	from app.services.ambient.dispatcher import dispatch

	if trigger.priority == 1 or trigger.delivery == "immediate":
		logger.info(
			"AmbientDelivery: immediate delivery for trigger '%s' (priority=%d)",
			trigger.rule_id, trigger.priority,
		)
		await dispatch(trigger)
		return

	if trigger.priority in (4, 5) or trigger.delivery == "next_briefing":
		_enqueue_for_briefing(trigger)
		return

	# Priority 2-3 / quiet_moment
	if await _is_quiet_moment(settings):
		logger.info(
			"AmbientDelivery: quiet moment detected — delivering trigger '%s'",
			trigger.rule_id,
		)
		await dispatch(trigger)
	else:
		# Queue for briefing rather than holding in memory (P0 simplification).
		# P2 will implement a proper in-memory delivery queue with re-check.
		logger.info(
			"AmbientDelivery: not a quiet moment — queuing trigger '%s' for briefing",
			trigger.rule_id,
		)
		_enqueue_for_briefing(trigger)


def _enqueue_for_briefing(trigger: Trigger) -> None:
	try:
		r = _get_redis()
		payload = json.dumps({
			"rule_id": trigger.rule_id,
			"priority": trigger.priority,
			"crews": trigger.crews,
			"context": trigger.context,
			"queued_at": datetime.now(tz=timezone.utc).isoformat(),
		})
		r.rpush(_BRIEFING_QUEUE_KEY, payload)
		r.expire(_BRIEFING_QUEUE_KEY, _BRIEFING_QUEUE_TTL_S)
		logger.debug("AmbientDelivery: queued trigger '%s' for briefing", trigger.rule_id)
	except Exception as exc:
		logger.warning("AmbientDelivery._enqueue_for_briefing failed: %s", exc)


async def _is_quiet_moment(settings) -> bool:  # noqa: ANN001
	"""Return True when conditions favour a non-intrusive push."""
	try:
		from datetime import time as dt_time
		now = datetime.now()
		quiet_window_m = getattr(settings, "AMBIENT_QUIET_MOMENT_WINDOW_M", 15)

		# Active hours check — fall back to 07:00-22:00 if Person row unavailable
		active_start = dt_time(7, 0)
		active_end = dt_time(22, 0)
		try:
			from sqlalchemy import select
			from app.models.db import AsyncSessionLocal, Person
			async with AsyncSessionLocal() as session:
				res = await session.execute(
					select(Person).where(Person.circle_type == "identity")
				)
				me = res.scalar_one_or_none()
				if me and me.quiet_hours_enabled and me.quiet_hours_start and me.quiet_hours_end:
					qh_start = dt_time(*[int(x) for x in me.quiet_hours_start.split(":")])
					qh_end = dt_time(*[int(x) for x in me.quiet_hours_end.split(":")])
					# Active hours are outside the quiet window
					if qh_end < qh_start:
						# spans midnight: active between qh_end and qh_start
						if not (qh_end <= now.time() < qh_start):
							return False
					else:
						if qh_start <= now.time() < qh_end:
							return False
		except Exception as db_exc:
			logger.debug("AmbientDelivery: Could not load quiet hours, using defaults: %s", db_exc)

		if not (active_start <= now.time() < active_end):
			return False

		# Calendar check — is there an event starting soon?
		try:
			from app.services.calendar import fetch_calendar_events
			events = await fetch_calendar_events(days_ahead=0)
			for event in events:
				start_str = event.get("start", "")
				if "T" not in start_str:
					continue
				try:
					event_dt = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
					# Convert to local time for comparison
					event_local = event_dt.replace(tzinfo=None)
					delta_m = (event_local - now).total_seconds() / 60
					if 0 <= delta_m <= quiet_window_m:
						return False  # event starting soon
				except ValueError:
					pass
		except Exception as cal_exc:
			logger.debug("AmbientDelivery: calendar check failed, assuming quiet: %s", cal_exc)

		return True

	except Exception as exc:
		logger.warning("AmbientDelivery._is_quiet_moment error: %s", exc)
		return False  # fail safe — do not deliver if check raises
