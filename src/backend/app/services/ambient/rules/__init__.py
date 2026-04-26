"""TriggerRuleEngine — evaluates registered rules against signal lists and
enforces per-rule cooldowns via Redis.

Adding a new rule:
    from app.services.ambient.rules.my_rule import rule_my_thing
    engine.register(rule_my_thing, cooldown_minutes=120)

See docs/artifacts/ambient_intelligence.md §6.
"""

from __future__ import annotations

import logging
from typing import Callable

from app.services.ambient.models import Signal, Trigger

logger = logging.getLogger(__name__)

_COOLDOWN_KEY_PREFIX = "oz:ambient:cooldown:"
RuleFn = Callable[[list[Signal]], "Trigger | None"]


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


class RuleEngine:
	"""Evaluates trigger rules and enforces per-rule cooldowns."""

	def __init__(self) -> None:
		self._rules: list[tuple[RuleFn, int]] = []  # (fn, cooldown_minutes)

	def register(self, rule: RuleFn, cooldown_minutes: int = 60) -> None:
		self._rules.append((rule, cooldown_minutes))

	def _is_on_cooldown(self, rule_id: str) -> bool:
		try:
			r = _get_redis()
			return bool(r.exists(f"{_COOLDOWN_KEY_PREFIX}{rule_id}"))
		except Exception as exc:
			logger.warning("RuleEngine cooldown check failed for %s: %s", rule_id, exc)
			return False  # fail open — allow the rule to fire rather than suppress forever

	def _is_disabled(self, rule_id: str) -> bool:
		try:
			r = _get_redis()
			return bool(r.exists(f"oz:ambient:rule_disabled:{rule_id}"))
		except Exception as exc:
			logger.warning("RuleEngine disable check failed for %s: %s", rule_id, exc)
			return False  # fail open

	def _set_cooldown(self, rule_id: str, cooldown_minutes: int) -> None:
		try:
			r = _get_redis()
			r.set(f"{_COOLDOWN_KEY_PREFIX}{rule_id}", "1", ex=cooldown_minutes * 60)
		except Exception as exc:
			logger.warning("RuleEngine cooldown set failed for %s: %s", rule_id, exc)

	def evaluate(self, signals: list[Signal]) -> list[Trigger]:
		"""Evaluate all registered rules and return triggered (non-cooldown) triggers."""
		triggers: list[Trigger] = []
		for rule_fn, cooldown_minutes in self._rules:
			rule_id = getattr(rule_fn, "__name__", repr(rule_fn))
			try:
				if self._is_on_cooldown(rule_id):
					logger.debug("RuleEngine: '%s' is on cooldown — skipping", rule_id)
					continue
				if self._is_disabled(rule_id):
					logger.debug("RuleEngine: '%s' is disabled — skipping", rule_id)
					continue
				trigger = rule_fn(signals)
				if trigger is None:
					continue
				self._set_cooldown(rule_id, cooldown_minutes)
				triggers.append(trigger)
				logger.info(
					"RuleEngine: trigger fired — rule='%s' priority=%d crews=%s",
					rule_id,
					trigger.priority,
					trigger.crews,
				)
			except Exception as exc:
				logger.warning("RuleEngine: rule '%s' raised an error: %s", rule_id, exc)
		return triggers
