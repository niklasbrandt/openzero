"""Shared data models for the Ambient Intelligence engine.

See docs/artifacts/ambient_intelligence.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal


@dataclass
class Signal:
	"""A typed observation emitted by one state adapter after a diff."""

	source: str      # adapter source_id, e.g. "planka"
	kind: str        # e.g. "card_stall_threshold", "calendar_overload"
	severity: float  # 0.0 – 1.0
	detail: dict     # source-specific payload
	timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class Trigger:
	"""An actionable cross-source event produced by the TriggerRuleEngine."""

	rule_id: str
	priority: int        # 1 = critical, 5 = informational
	crews: list[str]     # crew IDs to fire; empty list => direct LLM insight
	context: str         # injected into crew prompt / insight prompt
	cooldown_minutes: int
	delivery: Literal["immediate", "quiet_moment", "next_briefing"] = "quiet_moment"
