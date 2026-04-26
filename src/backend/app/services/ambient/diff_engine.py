"""Signal computation layer.

Each DiffEngine instance holds a registry of SignalRule callables.  After every
snapshot cycle the engine is called with the latest history per source and
returns the combined list of Signal objects.

A SignalRule is any callable with signature:
    (current: dict, previous: dict | None) -> list[Signal]

See docs/artifacts/ambient_intelligence.md §5.
"""

from __future__ import annotations

import logging
from typing import Callable

from app.services.ambient.models import Signal

logger = logging.getLogger(__name__)

# Type alias
SignalRule = Callable[[dict, "dict | None"], list[Signal]]


class DiffEngine:
	"""Evaluates registered signal rules against snapshot histories."""

	def __init__(self) -> None:
		self._rules: list[tuple[str, SignalRule]] = []  # (source_id, rule_fn)

	def register(self, source_id: str, rule: SignalRule) -> None:
		"""Register a rule that applies to snapshots from *source_id*."""
		self._rules.append((source_id, rule))

	def evaluate(self, snapshots: dict[str, list[dict]]) -> list[Signal]:
		"""Run all rules.  *snapshots* maps source_id -> [newest, ..., oldest]."""
		signals: list[Signal] = []
		for source_id, rule in self._rules:
			history = snapshots.get(source_id, [])
			if not history:
				continue
			current = history[0]
			previous = history[1] if len(history) > 1 else None
			try:
				emitted = rule(current, previous)
				signals.extend(emitted)
			except Exception as exc:
				logger.warning(
					"DiffEngine: rule '%s' raised an error for source '%s': %s",
					getattr(rule, "__name__", repr(rule)),
					source_id,
					exc,
				)
		return signals
