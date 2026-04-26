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
		# Queue the trigger in Redis for the delivery_checker job to retry.
		# Priority-2 triggers are held for up to 30 minutes; priority-3 for 2 hours.
		# After that, they fall into the briefing queue (staleness prevention).
		_enqueue_pending(trigger)


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


# Pending delivery key format: oz:ambient:pending:{rule_id}
# Value: JSON with priority, context, crews, queued_at
_PENDING_KEY_PREFIX = "oz:ambient:pending:"
# Max hold before escalating to briefing queue
_PRIORITY_2_MAX_HOLD_M = 30
_PRIORITY_3_MAX_HOLD_M = 120


def _enqueue_pending(trigger: Trigger) -> None:
	"""Store a trigger in Redis for retry by process_pending_triggers()."""
	try:
		r = _get_redis()
		key = f"{_PENDING_KEY_PREFIX}{trigger.rule_id}"
		# Don't overwrite a pending entry with a newer one (cooldown handles dedup)
		if r.exists(key):
			return
		max_hold_m = _PRIORITY_2_MAX_HOLD_M if trigger.priority <= 2 else _PRIORITY_3_MAX_HOLD_M
		payload = json.dumps({
			"rule_id": trigger.rule_id,
			"priority": trigger.priority,
			"crews": trigger.crews,
			"context": trigger.context,
			"delivery": trigger.delivery,
			"queued_at": datetime.now(tz=timezone.utc).isoformat(),
			"max_hold_minutes": max_hold_m,
		})
		ttl_s = max_hold_m * 60 + 60  # a bit of slack
		r.set(key, payload, ex=ttl_s)
		logger.info(
			"AmbientDelivery: queued trigger '%s' (priority=%d, max_hold=%dm)",
			trigger.rule_id, trigger.priority, max_hold_m,
		)
	except Exception as exc:
		logger.warning("AmbientDelivery._enqueue_pending failed: %s", exc)


async def process_pending_triggers() -> None:
	"""Called by the scheduler every 5 minutes.

	For each pending trigger:
	  - If a quiet moment is now available, deliver immediately.
	  - If the trigger has been held past its max_hold time, escalate to
	    the briefing queue (staleness prevention).
	"""
	from app.config import settings
	from app.services.ambient.dispatcher import dispatch

	try:
		r = _get_redis()
		keys = r.keys(f"{_PENDING_KEY_PREFIX}*")
	except Exception as exc:
		logger.warning("process_pending_triggers: Redis scan failed: %s", exc)
		return

	if not keys:
		return

	quiet = await _is_quiet_moment(settings)
	now = datetime.now(tz=timezone.utc)

	for key in keys:
		try:
			raw = r.get(key)
			if not raw:
				continue
			data = json.loads(raw)
			queued_at = datetime.fromisoformat(data["queued_at"])
			held_minutes = (now - queued_at).total_seconds() / 60
			max_hold = data.get("max_hold_minutes", _PRIORITY_3_MAX_HOLD_M)

			# Reconstruct minimal Trigger (only fields delivery needs)
			trigger = Trigger(
				rule_id=data["rule_id"],
				priority=data["priority"],
				crews=data.get("crews", []),
				context=data.get("context", ""),
				cooldown_minutes=0,  # cooldown already set when first queued
				delivery=data.get("delivery", "quiet_moment"),
			)

			if quiet:
				logger.info(
					"process_pending_triggers: quiet moment — delivering '%s' (held %.1fm)",
					trigger.rule_id, held_minutes,
				)
				r.delete(key)
				await dispatch(trigger)
			elif held_minutes >= max_hold:
				logger.info(
					"process_pending_triggers: '%s' exceeded max hold (%dm) — moving to briefing queue",
					trigger.rule_id, max_hold,
				)
				r.delete(key)
				_enqueue_for_briefing(trigger)
		except Exception as exc:
			logger.warning("process_pending_triggers: error processing key '%s': %s", key, exc)


def drain_briefing_queue() -> list[dict]:
	"""Read and clear the briefing queue. Called by morning.py at briefing time.

	Returns a list of payload dicts sorted by priority (ascending = highest first).
	"""
	try:
		r = _get_redis()
		raw_items = r.lrange(_BRIEFING_QUEUE_KEY, 0, -1)
		if not raw_items:
			return []
		r.delete(_BRIEFING_QUEUE_KEY)
		items = [json.loads(x) for x in raw_items]
		items.sort(key=lambda i: i.get("priority", 99))
		logger.info("drain_briefing_queue: drained %d ambient insight(s)", len(items))
		return items
	except Exception as exc:
		logger.warning("drain_briefing_queue failed: %s", exc)
		return []


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
