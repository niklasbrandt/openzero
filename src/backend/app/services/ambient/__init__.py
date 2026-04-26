"""Ambient Intelligence engine — State-Diff Engine.

See docs/artifacts/ambient_intelligence.md.

This package is the state-diff engine that reacts to *observed state changes*
and fires crews proactively.  It is separate from the ambient_capture/ package
(which routes inbound user messages).

Entry points:
    ambient_loop()  — called by the scheduler at AMBIENT_POLL_INTERVAL_S
    init_ambient()  — called once at startup to validate config

Both are no-ops unless settings.AMBIENT_ENABLED is True.
"""

from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Global rate-limit key
# ---------------------------------------------------------------------------
_RATE_KEY = "oz:ambient:hourly_trigger_count"
_RATE_WINDOW_S = 3600


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


def _under_rate_limit(max_per_hour: int) -> bool:
	"""Return True if we are below the global trigger rate cap."""
	try:
		r = _get_redis()
		current = r.get(_RATE_KEY)
		if current is None:
			return True
		return int(current) < max_per_hour
	except Exception as exc:
		logger.warning("ambient: rate-limit check failed: %s", exc)
		return True  # fail open


def _increment_rate() -> None:
	try:
		r = _get_redis()
		pipe = r.pipeline()
		pipe.incr(_RATE_KEY)
		pipe.expire(_RATE_KEY, _RATE_WINDOW_S)
		pipe.execute()
	except Exception as exc:
		logger.warning("ambient: rate-limit increment failed: %s", exc)


# ---------------------------------------------------------------------------
# Engine singleton (lazy-initialised)
# ---------------------------------------------------------------------------
_engine_ready = False
_store = None
_diff_engine = None
_rule_engine = None
_adapters: list = []


def _build_engine():
	global _store, _diff_engine, _rule_engine, _adapters, _engine_ready

	from app.services.ambient.state_store import StateStore
	from app.services.ambient.diff_engine import DiffEngine
	from app.services.ambient.rules import RuleEngine
	from app.services.ambient.adapters.planka import PlankaAdapter
	from app.services.ambient.rules.stall import detect_card_stalls, rule_card_stall

	_store = StateStore()
	_diff_engine = DiffEngine()
	_rule_engine = RuleEngine()
	_adapters = [PlankaAdapter()]

	# Register diff rules (source_id -> signal rule)
	_diff_engine.register("planka", detect_card_stalls)

	# Register trigger rules
	_rule_engine.register(rule_card_stall, cooldown_minutes=360)

	_engine_ready = True
	logger.info("ambient_intelligence: engine initialised with %d adapter(s)", len(_adapters))


def init_ambient() -> None:
	"""Called at startup. Validates config and pre-builds the engine if enabled."""
	from app.config import settings
	if not getattr(settings, "AMBIENT_ENABLED", False):
		logger.debug("ambient_intelligence: disabled (AMBIENT_ENABLED=false) — skipping init")
		return
	_build_engine()


async def ambient_loop() -> None:
	"""Single iteration of the ambient state-diff cycle.

	Orchestrates: snapshot adapters → push to store → diff → evaluate rules
	             → apply rate limit → deliver triggers.
	"""
	from app.config import settings

	if not getattr(settings, "AMBIENT_ENABLED", False):
		return

	global _engine_ready
	if not _engine_ready:
		_build_engine()

	max_triggers = getattr(settings, "AMBIENT_MAX_TRIGGERS_PER_HOUR", 3)

	# 1. Snapshot all adapters
	snapshots: dict[str, list[dict]] = {}
	for adapter in _adapters:
		try:
			snap = await adapter.snapshot()
			_store.push(adapter.source_id, snap)
			snapshots[adapter.source_id] = _store.latest(adapter.source_id, n=2)
		except Exception as exc:
			logger.warning("ambient_loop: adapter '%s' failed: %s", adapter.source_id, exc)

	# 2. Compute signals
	signals = _diff_engine.evaluate(snapshots)
	if not signals:
		logger.debug("ambient_loop: no signals emitted")
		return

	# 3. Evaluate trigger rules
	triggers = _rule_engine.evaluate(signals)
	if not triggers:
		logger.debug("ambient_loop: no triggers fired")
		return

	# 4. Dispatch with global rate cap
	from app.services.ambient.delivery import deliver
	for trigger in triggers:
		if not _under_rate_limit(max_triggers):
			logger.warning(
				"ambient_loop: global rate limit reached (%d/hour) — suppressing trigger '%s'",
				max_triggers, trigger.rule_id,
			)
			break
		_increment_rate()
		await deliver(trigger)
