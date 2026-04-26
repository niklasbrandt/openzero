"""Unit tests for the Ambient Intelligence engine (P0).

Tests:
  - StateStore push/latest (in-memory mock, no real Redis)
  - DiffEngine: no signals on first snapshot and on identical snapshots
  - DiffEngine: detect_card_stalls emits signal for new stalls
  - RuleEngine: cooldown suppression (mock Redis)
  - rule_card_stall: returns Trigger for stall signals; None when no stalls
  - ambient_loop: no-op when AMBIENT_ENABLED=False

See docs/artifacts/ambient_intelligence.md §12 (P0 unit tests).
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Path bootstrap — backend must be on sys.path for static imports
# ---------------------------------------------------------------------------
_BACKEND_SRC = os.path.abspath(
	os.path.join(os.path.dirname(__file__), "..", "src", "backend")
)
if _BACKEND_SRC not in sys.path:
	sys.path.insert(0, _BACKEND_SRC)

# Stub out heavy backend deps before any 'from app...' import
_STUBS: dict[str, Any] = {}
for _mod in [
	"app.config",
	"redis",
	"httpx",
	"sqlalchemy",
	"sqlalchemy.ext.asyncio",
]:
	if _mod not in sys.modules:
		_STUBS[_mod] = MagicMock()
		sys.modules[_mod] = _STUBS[_mod]

# Provide minimal settings stub
_settings_stub = MagicMock()
_settings_stub.REDIS_HOST = "localhost"
_settings_stub.REDIS_PORT = 6379
_settings_stub.REDIS_PASSWORD = None
_settings_stub.AMBIENT_ENABLED = False
_settings_stub.AMBIENT_POLL_INTERVAL_S = 300
_settings_stub.AMBIENT_QUIET_MOMENT_WINDOW_M = 15
_settings_stub.AMBIENT_MAX_TRIGGERS_PER_HOUR = 3
sys.modules["app.config"].settings = _settings_stub


# ---------------------------------------------------------------------------
# StateStore
# ---------------------------------------------------------------------------

class _FakeRedis:
	"""Minimal in-memory Redis stub for testing."""

	def __init__(self):
		self._data: dict[str, list[str]] = {}
		self._ttls: dict[str, int] = {}

	def pipeline(self):
		return _FakePipeline(self)

	def lrange(self, key: str, start: int, end: int) -> list[str]:
		items = self._data.get(key, [])
		# Redis lrange end is inclusive; -1 means last
		if end == -1:
			return items[start:]
		return items[start: end + 1]

	def exists(self, key: str) -> bool:
		return key in self._data and bool(self._data[key])

	def get(self, key: str):
		return self._data.get(key, None)

	def set(self, key: str, value: Any, ex: int | None = None):
		self._data[key] = value
		if ex is not None:
			self._ttls[key] = ex

	def incr(self, key: str) -> int:
		cur = int(self._data.get(key) or 0) + 1
		self._data[key] = str(cur)
		return cur

	def expire(self, key: str, seconds: int):
		self._ttls[key] = seconds


class _FakePipeline:
	def __init__(self, r: _FakeRedis):
		self._r = r
		self._cmds: list[tuple] = []

	def lpush(self, key: str, value: Any):
		self._cmds.append(("lpush", key, value))
		return self

	def ltrim(self, key: str, start: int, end: int):
		self._cmds.append(("ltrim", key, start, end))
		return self

	def expire(self, key: str, seconds: int):
		self._cmds.append(("expire", key, seconds))
		return self

	def execute(self):
		for cmd in self._cmds:
			if cmd[0] == "lpush":
				self._r._data.setdefault(cmd[1], []).insert(0, cmd[2])
			elif cmd[0] == "ltrim":
				key, start, end = cmd[1], cmd[2], cmd[3]
				self._r._data[key] = (self._r._data.get(key) or [])[start: end + 1]
			elif cmd[0] == "expire":
				self._r._ttls[cmd[1]] = cmd[2]
		self._cmds.clear()


def _make_store(fake_redis: _FakeRedis):
	from app.services.ambient.state_store import StateStore
	store = StateStore(max_snapshots=5)
	with patch("app.services.ambient.state_store._get_redis", return_value=fake_redis):
		yield store


@pytest.fixture()
def fake_redis():
	return _FakeRedis()


@pytest.fixture()
def store(fake_redis):
	from app.services.ambient.state_store import StateStore
	s = StateStore(max_snapshots=5)
	with patch("app.services.ambient.state_store._get_redis", return_value=fake_redis):
		yield s


class TestStateStore:
	def test_push_and_latest_single(self, store, fake_redis):
		with patch("app.services.ambient.state_store._get_redis", return_value=fake_redis):
			snap = {"stalled": [], "in_progress": []}
			store.push("planka", snap)
			result = store.latest("planka", n=1)
		assert len(result) == 1
		assert result[0]["stalled"] == []

	def test_push_keeps_newest_first(self, store, fake_redis):
		with patch("app.services.ambient.state_store._get_redis", return_value=fake_redis):
			store.push("planka", {"seq": 1})
			store.push("planka", {"seq": 2})
			result = store.latest("planka", n=2)
		assert result[0]["seq"] == 2
		assert result[1]["seq"] == 1

	def test_latest_empty_returns_empty(self, store, fake_redis):
		with patch("app.services.ambient.state_store._get_redis", return_value=fake_redis):
			result = store.latest("nonexistent", n=2)
		assert result == []

	def test_max_snapshots_enforced(self, store, fake_redis):
		with patch("app.services.ambient.state_store._get_redis", return_value=fake_redis):
			for i in range(10):
				store.push("planka", {"seq": i})
			result = store.latest("planka", n=10)
		assert len(result) <= 5  # max_snapshots=5


# ---------------------------------------------------------------------------
# DiffEngine + detect_card_stalls signal rule
# ---------------------------------------------------------------------------

class TestDiffEngine:
	def test_no_rules_returns_empty(self):
		from app.services.ambient.diff_engine import DiffEngine
		engine = DiffEngine()
		signals = engine.evaluate({"planka": [{"stalled": []}]})
		assert signals == []

	def test_no_snapshots_returns_empty(self):
		from app.services.ambient.diff_engine import DiffEngine
		from app.services.ambient.rules.stall import detect_card_stalls
		engine = DiffEngine()
		engine.register("planka", detect_card_stalls)
		signals = engine.evaluate({})
		assert signals == []

	def test_identical_snapshots_no_signal(self):
		from app.services.ambient.diff_engine import DiffEngine
		from app.services.ambient.rules.stall import detect_card_stalls
		engine = DiffEngine()
		engine.register("planka", detect_card_stalls)
		snap = {
			"stalled": [{"name": "Card A", "board": "Work", "last_activity": "2026-04-20"}],
			"in_progress": [],
		}
		signals = engine.evaluate({"planka": [snap, snap]})
		# Same stall in both snapshots -> no NEW stalls -> no signal
		assert signals == []

	def test_new_stall_emits_signal(self):
		from app.services.ambient.diff_engine import DiffEngine
		from app.services.ambient.rules.stall import detect_card_stalls
		engine = DiffEngine()
		engine.register("planka", detect_card_stalls)
		prev = {"stalled": [], "in_progress": []}
		curr = {
			"stalled": [
				{"name": "Emperor Angel Care", "board": "Reef Tank", "last_activity": "2026-04-20"}
			],
			"in_progress": [],
		}
		signals = engine.evaluate({"planka": [curr, prev]})
		assert len(signals) == 1
		assert signals[0].kind == "card_stall_threshold"
		assert signals[0].source == "planka"
		assert signals[0].severity > 0

	def test_first_snapshot_surfaces_existing_stalls(self):
		from app.services.ambient.diff_engine import DiffEngine
		from app.services.ambient.rules.stall import detect_card_stalls
		engine = DiffEngine()
		engine.register("planka", detect_card_stalls)
		curr = {
			"stalled": [
				{"name": "Stale Todo", "board": "Personal", "last_activity": "2026-04-01"}
			],
		}
		# No previous snapshot
		signals = engine.evaluate({"planka": [curr]})
		assert len(signals) == 1

	def test_rule_exception_does_not_propagate(self):
		from app.services.ambient.diff_engine import DiffEngine
		from app.services.ambient.models import Signal

		def bad_rule(current, previous):
			raise RuntimeError("simulated failure")

		engine = DiffEngine()
		engine.register("planka", bad_rule)
		# Should not raise
		signals = engine.evaluate({"planka": [{"stalled": []}]})
		assert signals == []


# ---------------------------------------------------------------------------
# rule_card_stall trigger rule
# ---------------------------------------------------------------------------

class TestRuleCardStall:
	def test_no_signals_returns_none(self):
		from app.services.ambient.rules.stall import rule_card_stall
		assert rule_card_stall([]) is None

	def test_wrong_kind_returns_none(self):
		from app.services.ambient.rules.stall import rule_card_stall
		from app.services.ambient.models import Signal
		sig = Signal(source="planka", kind="calendar_overload", severity=0.5, detail={})
		assert rule_card_stall([sig]) is None

	def test_stall_signal_produces_trigger(self):
		from app.services.ambient.rules.stall import rule_card_stall
		from app.services.ambient.models import Signal
		sig = Signal(
			source="planka",
			kind="card_stall_threshold",
			severity=0.4,
			detail={"stalled_cards": [
				{"name": "Reef Tank", "board": "Hobbies", "last_activity": "2026-04-20"}
			]},
		)
		trigger = rule_card_stall([sig])
		assert trigger is not None
		assert trigger.rule_id == "card_stall"
		assert "flow" in trigger.crews
		assert trigger.cooldown_minutes == 360
		assert "AMBIENT_TRIGGER" in trigger.context

	def test_trigger_caps_card_list_at_five(self):
		from app.services.ambient.rules.stall import rule_card_stall
		from app.services.ambient.models import Signal
		cards = [
			{"name": f"Card {i}", "board": "Work", "last_activity": "2026-04-15"}
			for i in range(10)
		]
		sig = Signal(
			source="planka",
			kind="card_stall_threshold",
			severity=1.0,
			detail={"stalled_cards": cards},
		)
		trigger = rule_card_stall([sig])
		assert trigger is not None
		# "and 5 more" should appear in context
		assert "more" in trigger.context


# ---------------------------------------------------------------------------
# RuleEngine cooldown
# ---------------------------------------------------------------------------

class TestRuleEngineCooldown:
	def test_rule_fires_when_no_cooldown(self, fake_redis):
		from app.services.ambient.rules import RuleEngine
		from app.services.ambient.models import Signal, Trigger

		def _rule(signals):
			return Trigger(
				rule_id="_rule",
				priority=3,
				crews=["flow"],
				context="test",
				cooldown_minutes=60,
			)

		engine = RuleEngine()
		engine.register(_rule, cooldown_minutes=60)

		# No cooldown key present
		fake_redis._data.pop("oz:ambient:cooldown:_rule", None)

		with patch("app.services.ambient.rules._get_redis", return_value=fake_redis):
			triggers = engine.evaluate([])

		assert len(triggers) == 1
		# Cooldown should now be set
		assert "oz:ambient:cooldown:_rule" in fake_redis._data

	def test_rule_suppressed_on_cooldown(self, fake_redis):
		from app.services.ambient.rules import RuleEngine
		from app.services.ambient.models import Trigger

		def _rule(signals):
			return Trigger(
				rule_id="_rule",
				priority=3,
				crews=["flow"],
				context="test",
				cooldown_minutes=60,
			)

		engine = RuleEngine()
		engine.register(_rule, cooldown_minutes=60)

		# Pre-set cooldown key (simulate it was set)
		fake_redis._data["oz:ambient:cooldown:_rule"] = "1"

		with patch("app.services.ambient.rules._get_redis", return_value=fake_redis):
			triggers = engine.evaluate([])

		assert triggers == []


# ---------------------------------------------------------------------------
# ambient_loop: no-op when disabled
# ---------------------------------------------------------------------------

def test_ambient_loop_noop_when_disabled():
	"""ambient_loop must be a true no-op when AMBIENT_ENABLED=False."""
	import asyncio

	async def _run():
		from app.services.ambient import ambient_loop
		_settings_stub.AMBIENT_ENABLED = False
		await ambient_loop()

	asyncio.run(_run())


# ---------------------------------------------------------------------------
# P1 — Calendar signal rules
# ---------------------------------------------------------------------------

class TestCalendarSignalRules:
	def test_overload_no_signal_below_threshold(self):
		from app.services.ambient.rules.calendar import detect_calendar_overload
		snap = {"tomorrow_meeting_hours": 4.0, "back_to_back_count": 0}
		signals = detect_calendar_overload(snap, None)
		assert signals == []

	def test_overload_emits_on_first_crossing(self):
		from app.services.ambient.rules.calendar import detect_calendar_overload
		curr = {"tomorrow_meeting_hours": 7.5, "back_to_back_count": 0}
		prev = {"tomorrow_meeting_hours": 3.0}
		signals = detect_calendar_overload(curr, prev)
		assert len(signals) == 1
		assert signals[0].kind == "calendar_overload"
		assert signals[0].source == "calendar"
		assert signals[0].severity > 0

	def test_overload_no_second_signal_if_already_critical(self):
		from app.services.ambient.rules.calendar import detect_calendar_overload
		curr = {"tomorrow_meeting_hours": 8.0}
		prev = {"tomorrow_meeting_hours": 7.0}  # also above threshold
		signals = detect_calendar_overload(curr, prev)
		assert signals == []

	def test_back_to_back_emits_when_count_high(self):
		from app.services.ambient.rules.calendar import detect_back_to_back
		curr = {"back_to_back_count": 5}
		prev = {"back_to_back_count": 1}
		signals = detect_back_to_back(curr, prev)
		assert len(signals) == 1
		assert signals[0].kind == "back_to_back_day"

	def test_back_to_back_no_signal_at_threshold(self):
		from app.services.ambient.rules.calendar import detect_back_to_back
		curr = {"back_to_back_count": 2}
		signals = detect_back_to_back(curr, None)
		assert signals == []

	def test_calendar_advisory_trigger_fires_on_overload_signal(self):
		from app.services.ambient.rules.calendar import rule_calendar_advisory
		from app.services.ambient.models import Signal
		sig = Signal(
			source="calendar", kind="calendar_overload",
			severity=0.5, detail={"tomorrow_meeting_hours": 7.5},
		)
		trigger = rule_calendar_advisory([sig])
		assert trigger is not None
		assert trigger.rule_id == "rule_calendar_advisory"
		assert trigger.priority == 3
		assert trigger.crews == []

	def test_calendar_advisory_returns_none_for_unrelated_signals(self):
		from app.services.ambient.rules.calendar import rule_calendar_advisory
		from app.services.ambient.models import Signal
		sig = Signal(
			source="email", kind="priority_spike", severity=0.3, detail={},
		)
		assert rule_calendar_advisory([sig]) is None


# ---------------------------------------------------------------------------
# P1 — Email signal rules
# ---------------------------------------------------------------------------

class TestEmailSignalRules:
	def test_priority_spike_no_signal_when_zero(self):
		from app.services.ambient.rules.email import detect_priority_spike
		snap = {"priority_count": 0, "priority_sender_repeat": 0}
		assert detect_priority_spike(snap, None) == []

	def test_priority_spike_emits_on_increase(self):
		from app.services.ambient.rules.email import detect_priority_spike
		curr = {"priority_count": 3, "priority_sender_repeat": 0, "unread_age_hours_max": 1.0}
		prev = {"priority_count": 0}
		signals = detect_priority_spike(curr, prev)
		assert len(signals) == 1
		assert signals[0].kind == "priority_spike"
		assert signals[0].detail["priority_count"] == 3

	def test_priority_spike_no_signal_when_count_unchanged(self):
		from app.services.ambient.rules.email import detect_priority_spike
		curr = {"priority_count": 3}
		prev = {"priority_count": 3}
		assert detect_priority_spike(curr, prev) == []

	def test_inbox_surge_emits_on_rapid_growth(self):
		from app.services.ambient.rules.email import detect_inbox_surge
		curr = {"unread_count": 15}
		prev = {"unread_count": 10}
		signals = detect_inbox_surge(curr, prev)
		assert len(signals) == 1
		assert signals[0].kind == "inbox_surge"
		assert signals[0].detail["delta"] == 5

	def test_inbox_surge_no_signal_below_threshold(self):
		from app.services.ambient.rules.email import detect_inbox_surge
		curr = {"unread_count": 11}
		prev = {"unread_count": 10}
		assert detect_inbox_surge(curr, prev) == []

	def test_inbox_overwhelm_trigger_fires(self):
		from app.services.ambient.rules.email import rule_inbox_overwhelm
		from app.services.ambient.models import Signal
		sig = Signal(
			source="email", kind="priority_spike", severity=0.4,
			detail={"priority_count": 2, "priority_sender_repeat": 0, "unread_age_hours_max": 2.0},
		)
		trigger = rule_inbox_overwhelm([sig])
		assert trigger is not None
		assert "priority" in trigger.context.lower() or "2" in trigger.context

	def test_inbox_overwhelm_returns_none_for_non_email_signals(self):
		from app.services.ambient.rules.email import rule_inbox_overwhelm
		from app.services.ambient.models import Signal
		sig = Signal(source="hardware", kind="disk_critical", severity=0.8, detail={})
		assert rule_inbox_overwhelm([sig]) is None


# ---------------------------------------------------------------------------
# P1 — Hardware signal rules
# ---------------------------------------------------------------------------

class TestHardwareSignalRules:
	def test_disk_critical_no_signal_below_threshold(self):
		from app.services.ambient.rules.hardware import detect_disk_critical
		snap = {"disk_percent": 70.0}
		assert detect_disk_critical(snap, None) == []

	def test_disk_critical_emits_on_first_crossing(self):
		from app.services.ambient.rules.hardware import detect_disk_critical
		curr = {"disk_percent": 87.0}
		prev = {"disk_percent": 80.0}
		signals = detect_disk_critical(curr, prev)
		assert len(signals) == 1
		assert signals[0].kind == "disk_critical"
		assert signals[0].detail["disk_percent"] == 87.0

	def test_disk_critical_no_re_fire_if_already_above(self):
		from app.services.ambient.rules.hardware import detect_disk_critical
		curr = {"disk_percent": 90.0}
		prev = {"disk_percent": 88.0}
		assert detect_disk_critical(curr, prev) == []

	def test_memory_critical_emits_on_crossing(self):
		from app.services.ambient.rules.hardware import detect_memory_critical
		curr = {"memory_percent": 92.0}
		prev = {"memory_percent": 85.0}
		signals = detect_memory_critical(curr, prev)
		assert len(signals) == 1
		assert signals[0].kind == "memory_critical"

	def test_container_failure_emits_only_new_failures(self):
		from app.services.ambient.rules.hardware import detect_container_failure
		curr = {"container_unhealthy": ["backend", "llm"]}
		prev = {"container_unhealthy": ["backend"]}  # backend already known
		signals = detect_container_failure(curr, prev)
		assert len(signals) == 1
		assert "llm" in signals[0].detail["new_unhealthy"]

	def test_container_failure_no_signal_when_unchanged(self):
		from app.services.ambient.rules.hardware import detect_container_failure
		curr = {"container_unhealthy": ["backend"]}
		prev = {"container_unhealthy": ["backend"]}
		assert detect_container_failure(curr, prev) == []

	def test_infra_critical_trigger_immediate_delivery(self):
		from app.services.ambient.rules.hardware import rule_infra_critical
		from app.services.ambient.models import Signal
		sig = Signal(
			source="hardware", kind="disk_critical", severity=0.8,
			detail={"disk_percent": 87.0, "threshold": 85.0},
		)
		trigger = rule_infra_critical([sig])
		assert trigger is not None
		assert trigger.priority == 1
		assert trigger.delivery == "immediate"
		assert "[INFRA]" in trigger.context

	def test_infra_critical_returns_none_for_non_hw_signals(self):
		from app.services.ambient.rules.hardware import rule_infra_critical
		from app.services.ambient.models import Signal
		sig = Signal(source="calendar", kind="calendar_overload", severity=0.3, detail={})
		assert rule_infra_critical([sig]) is None
