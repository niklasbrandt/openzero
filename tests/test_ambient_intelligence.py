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
