"""Tests for the deterministic Planka intent router (Phase 1).

Mocks the Planka snapshot fetcher so tests do not hit a live Planka instance.
Covers EN + DE verb classification, conversational hedge suppression, and
unknown-entity rejection.
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.services import intent_router as ir


# Fixed snapshot of projects + boards used by every test in this module.
_SNAPSHOT = [
	{
		"id": "p_my",
		"name": "My Projects",
		"boards": [
			{"id": "b_aq", "name": "Aquarium"},
			{"id": "b_garden", "name": "Garden"},
		],
	},
	{
		"id": "p_ops",
		"name": "Operations",
		"boards": [
			{"id": "b_house", "name": "Household"},
		],
	},
	{
		"id": "p_dump",
		"name": "Inbox",
		"boards": [
			{"id": "b_misc", "name": "Misc"},
		],
	},
]


@pytest.fixture(autouse=True)
def _patch_snapshot(monkeypatch):
	"""Replace the live Planka snapshot fetch with a fixture."""
	async def _fake() -> list[dict]:
		return _SNAPSHOT

	monkeypatch.setattr(ir, "_get_planka_snapshot", _fake)
	# Reset cache between tests so monkeypatched function runs.
	ir._cache["ts"] = 0.0
	ir._cache["projects"] = []
	yield


def _classify(text: str, lang: str = "en"):
	return asyncio.get_event_loop().run_until_complete(
		ir.classify_structural_intent(text, lang)
	)


# ─── EN positive cases ──────────────────────────────────────────────────────

@pytest.mark.parametrize("text", [
	"move aquarium board to my projects",
	"move the aquarium board to my projects",
	"Move aquarium board into my projects",
	"please move the aquarium board to my projects",
	"move board aquarium to my projects",
	"move the garden board into operations",
	"move the household board to inbox",
	"move the aquarium board under my projects",
	"move the aquarium board to My Projects",
	"can you move the aquarium board to my projects",
])
def test_en_move_board_classifies(text):
	intent = _classify(text, "en")
	assert intent is not None, f"failed to classify: {text!r}"
	assert intent.verb == "MOVE_BOARD"
	assert intent.confidence >= 0.85


# ─── DE positive cases ──────────────────────────────────────────────────────

@pytest.mark.parametrize("text", [
	"verschiebe das aquarium board zu my projects",
	"verschiebe das aquarium-board zu my projects",
	"verschiebe das board aquarium zu my projects",
	"verschieb das aquarium board nach my projects",
	"verschiebe das garden board zu operations",
	"verschiebe das aquarium board in my projects",
	"verschiebe das household board zu inbox",
	"verschiebe das aquarium board unter my projects",
	"verschiebe das garden board nach operations",
	"verschieb das aquarium board zu my projects bitte",
])
def test_de_move_board_classifies(text):
	intent = _classify(text, "de")
	assert intent is not None, f"failed to classify: {text!r}"
	assert intent.verb == "MOVE_BOARD"


# ─── Conversational / hedged phrases must NOT classify ─────────────────────

@pytest.mark.parametrize("text", [
	"I was thinking about moving the aquarium board sometime",
	"what does it mean to move a board",
	"how do I move the aquarium board to my projects",
	"should I move the aquarium board to operations",
	"can you explain how moving boards works",
])
def test_hedged_phrases_do_not_classify(text):
	assert _classify(text, "en") is None


# ─── Non-existent boards/projects ──────────────────────────────────────────

@pytest.mark.parametrize("text", [
	"move the unicorn board to my projects",
	"move the aquarium board to nonexistent",
	"move the foobar board to operations",
])
def test_unknown_entity_returns_none(text):
	assert _classify(text, "en") is None


# ─── MARK_DONE + ARCHIVE_CARD smoke tests ──────────────────────────────────

def test_mark_done_classifies():
	intent = _classify("mark the laundry card as done", "en")
	assert intent is not None
	assert intent.verb == "MARK_DONE"
	assert "laundry" in intent.entities["card_fragment"].lower()


def test_archive_card_classifies():
	intent = _classify("archive the laundry card", "en")
	assert intent is not None
	assert intent.verb == "ARCHIVE_CARD"


def test_archive_skips_when_object_is_a_board():
	# "archive the aquarium board" should NOT classify as ARCHIVE_CARD.
	assert _classify("archive the aquarium board", "en") is None


# ─── Unsupported language returns None ─────────────────────────────────────

def test_unsupported_language():
	assert _classify("move the aquarium board to my projects", "fr") is None


# ─── Dispatch returns localised confirmation ───────────────────────────────

def test_dispatch_move_board_calls_executor():
	intent = ir.StructuralIntent(
		verb="MOVE_BOARD",
		entities={
			"board_id": "b_aq", "board_name": "Aquarium",
			"project_id": "p_my", "project_name": "My Projects",
			"raw_board_query": "aquarium", "raw_project_query": "my projects",
		},
		raw_text="move aquarium board to my projects",
		confidence=1.0,
	)
	with patch("app.services.agent_actions.execute_move_board", new=AsyncMock(return_value="Board 'Aquarium' moved to 'My Projects'.")) as m:
		result = asyncio.get_event_loop().run_until_complete(
			ir.dispatch_structural_intent(intent, "en")
		)
		m.assert_awaited_once_with("Aquarium", "My Projects")
	assert "Aquarium" in result and "My Projects" in result
	assert "[AUDIT:move_board:Aquarium" in result


def test_dispatch_move_board_de_localised():
	intent = ir.StructuralIntent(
		verb="MOVE_BOARD",
		entities={
			"board_id": "b_aq", "board_name": "Aquarium",
			"project_id": "p_my", "project_name": "My Projects",
			"raw_board_query": "aquarium", "raw_project_query": "my projects",
		},
		raw_text="verschiebe das aquarium board zu my projects",
		confidence=1.0,
	)
	with patch("app.services.agent_actions.execute_move_board", new=AsyncMock(return_value="Board 'Aquarium' moved to 'My Projects'.")):
		result = asyncio.get_event_loop().run_until_complete(
			ir.dispatch_structural_intent(intent, "de")
		)
	assert "verschoben" in result.lower()


# ─── Project-name fallback (board_q matches a project with one board) ───────


@pytest.mark.parametrize("text,lang,proj_name", [
	("Move aquarium board to my projects", "en", "My projects"),
	("Verschiebe das aquarium-board zu Meine Projekte", "de", "Meine Projekte"),
])
def test_move_board_project_name_fallback(text, lang, proj_name, monkeypatch):
	snapshot = [
		{"id": "p_my", "name": proj_name, "boards": [{"id": "b_garden", "name": "Garden"}]},
		{"id": "p_aq", "name": "Aquarium", "boards": [{"id": "b_reef", "name": "30L nano reef tank"}]},
	]
	async def _fake() -> list[dict]:
		return snapshot
	monkeypatch.setattr(ir, "_get_planka_snapshot", _fake)
	ir._cache["ts"] = 0.0
	ir._cache["projects"] = []
	intent = asyncio.get_event_loop().run_until_complete(
		ir.classify_structural_intent(text, lang)
	)
	assert intent is not None, f"failed to classify: {text!r}"
	assert intent.verb == "MOVE_BOARD"
	assert intent.entities["board_name"] == "30L nano reef tank"
	assert intent.entities["project_name"] == proj_name
