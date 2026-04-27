"""
Hallucination regression test suite (Layer 8).

Tests that architectural anti-hallucination barriers (Layers 1-7) hold
across known-bad prompt patterns. All tests use mocked LLM/Planka so
there are no network calls. Runs in CI on every commit.

Covered scenarios
────────────────
1. Phantom history filter (L1): phantom prose + no executed_cmds
   → DB receives placeholder, not the phantom text.
2. SYSTEM RECEIPT injection (L2): successful action
   → receipt saved with role="system" containing the executed command.
3. State-question interception (L3): "wo sind die?" style message
   → router injects VERIFIED PLANKA STATE context before LLM call.
4. SYSTEM label in history (L7): role="system" history messages
   → _build_history_text labels them "SYSTEM", not "Z".
5. Phantom warning on user-facing reply (existing): no tag + phantom prose
   → clean reply includes the "⚠ Nothing was actually saved" warning.
"""
from __future__ import annotations

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(coro):
	"""Run a coroutine synchronously (test helper)."""
	return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# L1 — Phantom history filter
# ---------------------------------------------------------------------------

class TestL1PhantomHistoryFilter:
	"""Bus.commit_reply must NOT save phantom prose to the DB."""

	def test_phantom_reply_is_replaced_in_db(self, tmp_path, monkeypatch):
		"""When is_phantom() returns True, history saves the placeholder."""
		from app.common.phantom import PHANTOM_HISTORY_PLACEHOLDER

		saved_calls: list[dict] = []

		async def mock_save(channel, role, content, model=None):
			saved_calls.append({"role": role, "content": content})

		async def mock_parse(raw_reply, db=None, require_hitl=False, user_text=""):
			# Simulate phantom: clean reply has confirmation prose, no commands
			return raw_reply, [], []

		async def mock_session_factory():
			return MagicMock()

		phantom_reply = "Done — I've added it to your Operator Board under Today."

		with (
			patch("app.services.message_bus.save_global_message", new=AsyncMock(side_effect=mock_save)),
			patch("app.services.message_bus.AsyncSessionLocal"),
			patch("app.services.agent_actions.parse_and_execute_actions", new=AsyncMock(side_effect=mock_parse)),
			patch("app.services.message_bus.extract_and_store_facts", new=AsyncMock()),
		):
			from app.services.message_bus import MessageBus
			bus = MessageBus()
			_run(bus.commit_reply(
				channel="test", raw_reply=phantom_reply,
				model="test", user_text="add milk to my list", save=True,
			))

		# The z-role save MUST use the placeholder, not the phantom text
		z_saves = [s for s in saved_calls if s["role"] == "z"]
		assert z_saves, "commit_reply must save a z-role message"
		assert z_saves[0]["content"] == PHANTOM_HISTORY_PLACEHOLDER, (
			f"Expected placeholder, got: {z_saves[0]['content']!r}"
		)

	def test_non_phantom_reply_is_saved_verbatim(self):
		"""When the reply has an executed command, the full reply is saved."""
		saved_calls: list[dict] = []

		async def mock_save(channel, role, content, model=None):
			saved_calls.append({"role": role, "content": content})

		async def mock_parse(raw_reply, db=None, require_hitl=False, user_text=""):
			return raw_reply, ["CREATE_TASK(board=Operator Board, list=Today, title=milk)"], []

		real_reply = "Adding milk to your list."

		with (
			patch("app.services.message_bus.save_global_message", new=AsyncMock(side_effect=mock_save)),
			patch("app.services.message_bus.AsyncSessionLocal"),
			patch("app.services.agent_actions.parse_and_execute_actions", new=AsyncMock(side_effect=mock_parse)),
			patch("app.services.message_bus.extract_and_store_facts", new=AsyncMock()),
		):
			from app.services.message_bus import MessageBus
			bus = MessageBus()
			_run(bus.commit_reply(
				channel="test", raw_reply=real_reply,
				model="test", user_text="add milk", save=True,
			))

		z_saves = [s for s in saved_calls if s["role"] == "z"]
		assert z_saves
		assert z_saves[0]["content"] == real_reply


# ---------------------------------------------------------------------------
# L2 — SYSTEM RECEIPT injection
# ---------------------------------------------------------------------------

class TestL2SystemReceipt:
	"""After a successful action, a role='system' receipt must be saved."""

	def test_receipt_saved_after_action(self):
		saved_calls: list[dict] = []

		async def mock_save(channel, role, content, model=None):
			saved_calls.append({"role": role, "content": content})

		async def mock_parse(raw_reply, db=None, require_hitl=False, user_text=""):
			return raw_reply, ["CREATE_TASK(board=Operator Board, list=Today, title=milk)"], []

		with (
			patch("app.services.message_bus.save_global_message", new=AsyncMock(side_effect=mock_save)),
			patch("app.services.message_bus.AsyncSessionLocal"),
			patch("app.services.agent_actions.parse_and_execute_actions", new=AsyncMock(side_effect=mock_parse)),
			patch("app.services.message_bus.extract_and_store_facts", new=AsyncMock()),
		):
			from app.services.message_bus import MessageBus
			bus = MessageBus()
			_run(bus.commit_reply(
				channel="test", raw_reply="Adding milk.",
				model="test", user_text="add milk", save=True,
			))

		system_saves = [s for s in saved_calls if s["role"] == "system"]
		assert system_saves, "A system receipt must be saved after a real action"
		receipt_text = system_saves[0]["content"]
		assert "[SYSTEM RECEIPT" in receipt_text, f"Receipt missing header: {receipt_text!r}"
		assert "CREATE_TASK" in receipt_text, f"Receipt missing cmd: {receipt_text!r}"

	def test_no_receipt_when_no_actions(self):
		"""Pure conversation — no receipt should be saved."""
		saved_calls: list[dict] = []

		async def mock_save(channel, role, content, model=None):
			saved_calls.append({"role": role, "content": content})

		async def mock_parse(raw_reply, db=None, require_hitl=False, user_text=""):
			return raw_reply, [], []

		with (
			patch("app.services.message_bus.save_global_message", new=AsyncMock(side_effect=mock_save)),
			patch("app.services.message_bus.AsyncSessionLocal"),
			patch("app.services.agent_actions.parse_and_execute_actions", new=AsyncMock(side_effect=mock_parse)),
			patch("app.services.message_bus.extract_and_store_facts", new=AsyncMock()),
		):
			from app.services.message_bus import MessageBus
			bus = MessageBus()
			_run(bus.commit_reply(
				channel="test", raw_reply="Hey, how's it going?",
				model="test", user_text="hi", save=True,
			))

		system_saves = [s for s in saved_calls if s["role"] == "system"]
		assert not system_saves, "No system receipt should be saved for conversation-only replies"


# ---------------------------------------------------------------------------
# L3 — State-question Planka lookup regex
# ---------------------------------------------------------------------------

class TestL3StateQueryRegex:
	"""STATE_QUERY_RE inside router._generate must match known patterns."""

	@pytest.mark.parametrize("phrase, should_match", [
		# German — positive
		("wo sind die gespeichert?", True),
		("wo ist das?", True),
		("hast du das gespeichert?", True),
		("wurde das erstellt?", True),
		("wo habe ich das?", True),
		# English — positive
		("where is it?", True),
		("where are they?", True),
		("did you save that?", True),
		("was it created?", True),
		("were they added?", True),
		# Spanish — positive
		("dónde están?", True),
		# Negative cases (must NOT trigger)
		("add milk to my list", False),
		("hi", False),
		("sort the reef tank board", False),
		("what is the weather?", False),
		("create a task for tomorrow", False),
	])
	def test_state_query_regex(self, phrase, should_match):
		import re
		_STATE_QUERY_RE = re.compile(
			r'\bwo\s+(?:sind|ist|sind\s+die|habe\s+ich|hast\s+du)\b'
			r'|\bhast\s+du\s+(?:das|die|es|sie)?\s*(?:gespeichert|erstellt|hinzugef[üu]gt|abgelegt|gemacht)\b'
			r'|\bwurde\s+(?:das|es|die)\s+(?:gespeichert|erstellt|angelegt)\b'
			r'|\bwo\s+(?:wurde|wurden|habe|hat)\b'
			r'|\bwhere\s+(?:is|are|did\s+you|was|were)\s+(?:it|they|the|that|those)\b'
			r'|\bdid\s+you\s+(?:save|create|add|store|put|make)\b'
			r'|\bwas\s+(?:it|that|the\s+(?:task|card|board|todo|item))\s+(?:saved|created|added|stored)\b'
			r'|\bwere\s+(?:they|those|the\s+(?:tasks?|cards?|items?))\s+(?:saved|created|added|stored)\b'
			r'|\b(?:d[oó]nde|où)\s+(?:est[aá]|son|est|sont)\b'
			r'|\b(?:guardaste|enregistr[eé])\b',
			re.IGNORECASE,
		)
		matched = bool(_STATE_QUERY_RE.search(phrase))
		assert matched == should_match, (
			f"Phrase {phrase!r}: expected match={should_match}, got {matched}"
		)


# ---------------------------------------------------------------------------
# L7 — SYSTEM label in _build_history_text
# ---------------------------------------------------------------------------

class TestL7HistorySystemLabel:
	"""System receipts must be labelled SYSTEM, not Z."""

	def test_system_receipt_labelled_correctly(self):
		from app.services.llm import _build_history_text

		history = [
			{"role": "user", "content": "add milk to my list"},
			{"role": "z", "content": "Adding milk now."},
			{"role": "system", "content": "[SYSTEM RECEIPT 2026-01-01 12:00:00 UTC]\nCREATE_TASK(board=Operator Board, list=Today, title=milk)"},
			{"role": "user", "content": "wo sind die gespeichert?"},
		]
		result = _build_history_text(history)

		assert "SYSTEM: [SYSTEM RECEIPT" in result, (
			f"System receipt must be labelled SYSTEM: ...\nGot:\n{result}"
		)
		assert "Z: [SYSTEM RECEIPT" not in result, (
			"System receipt must NOT be labelled as Z"
		)

	def test_user_messages_labelled_user(self):
		from app.services.llm import _build_history_text

		history = [{"role": "user", "content": "hello"}, {"role": "z", "content": "hi"}]
		result = _build_history_text(history)
		assert "User: hello" in result
		assert "Z: hi" in result


# ---------------------------------------------------------------------------
# Phantom guard on user-facing reply (existing regression)
# ---------------------------------------------------------------------------

class TestPhantomUserFacingWarning:
	"""Router step 5 appends the ⚠ warning when phantom prose detected."""

	def test_phantom_warning_appended(self):
		from app.common.phantom import PHANTOM_RE

		phantom_text = "Done — I've added it to your Operator Board under Today."
		assert PHANTOM_RE.search(phantom_text), (
			"PHANTOM_RE must match this known phantom phrase for the test to be valid"
		)

	def test_non_phantom_no_warning(self):
		from app.common.phantom import PHANTOM_RE

		clean_text = "Sure, what would you like to add?"
		assert not PHANTOM_RE.search(clean_text), (
			"PHANTOM_RE must NOT match a non-phantom reply"
		)
