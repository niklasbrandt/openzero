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


# ─── Unsupported / cross-language fallback ─────────────────────────────────

def test_english_command_from_other_locale_still_classifies():
	# Multilingual fallback: an English command issued from a French UI
	# should still classify (English patterns are tried as universal fallback).
	intent = _classify("move the aquarium board to my projects", "fr")
	assert intent is not None
	assert intent.verb == "MOVE_BOARD"


def test_gibberish_in_unsupported_locale_returns_none():
	assert _classify("xyzzy plugh frobnitz", "xx") is None


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


# ─── Multilingual MOVE_BOARD coverage (es/fr/pt/ru/ja/zh/ko/hi/ar) ──────────


@pytest.mark.parametrize("text,lang", [
	# Spanish
	("mueve el tablero aquarium a my projects", "es"),
	("mueve el aquarium tablero a my projects", "es"),
	# French
	("déplace le tableau aquarium vers my projects", "fr"),
	("deplace le tableau aquarium vers my projects", "fr"),
	# Portuguese
	("mova o quadro aquarium para my projects", "pt"),
	# Russian
	("перемести доску aquarium в my projects", "ru"),
	("перенеси доску aquarium на my projects", "ru"),
	# Japanese
	("aquariumボードをmy projectsに移動して", "ja"),
	# Chinese
	("把aquarium看板移动到my projects", "zh"),
	("将aquarium面板移到my projects", "zh"),
	# Korean
	("aquarium 보드를 my projects로 이동", "ko"),
	# Hindi
	("aquarium बोर्ड को my projects में ले जाएं", "hi"),
	# Arabic
	("انقل اللوحة aquarium إلى my projects", "ar"),
])
def test_multilingual_move_board_classifies(text, lang):
	intent = _classify(text, lang)
	assert intent is not None, f"failed to classify ({lang}): {text!r}"
	assert intent.verb == "MOVE_BOARD"
	assert intent.entities["board_name"].lower() == "aquarium"
	assert intent.entities["project_name"].lower() == "my projects"


# ─── Multilingual hedge suppression ─────────────────────────────────────────


@pytest.mark.parametrize("text,lang", [
	("vielleicht sollte ich das aquarium board zu my projects verschieben", "de"),
	("tal vez deba mover el tablero aquarium a my projects", "es"),
	("peut-être devrais-je déplacer le tableau aquarium vers my projects", "fr"),
	("talvez eu deva mover o quadro aquarium para my projects", "pt"),
	("может быть стоит переместить доску aquarium в my projects", "ru"),
])
def test_multilingual_hedges_do_not_classify(text, lang):
	assert _classify(text, lang) is None


# ─── Localised dispatch confirmation per language ───────────────────────────


@pytest.mark.parametrize("lang,needle", [
	("es", "movido"),
	("fr", "déplacé"),
	("pt", "movido"),
	("ru", "перемещена"),
	("ja", "移動"),
	("zh", "移动"),
	("ko", "이동"),
	("hi", "स्थानांतरित"),
	("ar", "نقل"),
])
def test_dispatch_move_board_localised(lang, needle):
	intent = ir.StructuralIntent(
		verb="MOVE_BOARD",
		entities={
			"board_id": "b_aq", "board_name": "Aquarium",
			"project_id": "p_my", "project_name": "My Projects",
			"raw_board_query": "aquarium", "raw_project_query": "my projects",
		},
		raw_text="...",
		confidence=1.0,
	)
	with patch("app.services.agent_actions.execute_move_board", new=AsyncMock(return_value="Board 'Aquarium' moved to 'My Projects'.")):
		result = asyncio.get_event_loop().run_until_complete(
			ir.dispatch_structural_intent(intent, lang)
		)
	assert needle in result, f"{lang}: missing {needle!r} in {result!r}"


# ── CREATE_CARD tests ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("text,lang", [
	("add a card buy groceries to Inbox", "en"),
	("create task meeting prep on Work", "en"),
	("new card dentist appointment", "en"),
	("erstelle eine Karte Zahnarzttermin", "de"),
	("füge hinzu eine Aufgabe Einkaufen in Inbox", "de"),
	("agrega una tarjeta comprar leche en lista", "es"),
	("ajouter une carte réunion à Inbox", "fr"),
	("adicionar um cartão médico em Inbox", "pt"),
	("добавь карточку купить молоко в список", "ru"),
])
def test_create_card_pattern_classifies(text, lang):
	"""CREATE_CARD verb is detected from basic input in each supported language."""
	result = asyncio.get_event_loop().run_until_complete(
		ir.classify_structural_intent(text, lang)
	)
	assert result is not None, f"[{lang}] classified as None for: {text!r}"
	assert result.verb == "CREATE_CARD", f"[{lang}] expected CREATE_CARD, got {result.verb!r}"
	assert result.entities.get("title"), f"[{lang}] title entity missing"


def test_create_card_dispatch_calls_executor():
	"""dispatch_structural_intent with CREATE_CARD calls execute_create_card and returns localised result."""
	from app.services.intent_router import StructuralIntent, dispatch_structural_intent
	intent = StructuralIntent(
		verb="CREATE_CARD",
		entities={"title": "buy groceries", "destination": "Inbox"},
		raw_text="add a card buy groceries to Inbox",
		confidence=0.85,
	)
	with patch("app.services.agent_actions.execute_create_card", new=AsyncMock(return_value="Card 'buy groceries' added to 'Inbox'.")):
		result = asyncio.get_event_loop().run_until_complete(
			dispatch_structural_intent(intent, "en")
		)
	assert "buy groceries" in result
	assert "[AUDIT:create_card:" in result


def test_create_card_dispatch_returns_warning_on_failure():
	"""dispatch returns the warning string from execute_create_card when it fails."""
	from app.services.intent_router import StructuralIntent, dispatch_structural_intent
	intent = StructuralIntent(
		verb="CREATE_CARD",
		entities={"title": "buy groceries", "destination": "BadList"},
		raw_text="add a card buy groceries to BadList",
		confidence=0.85,
	)
	with patch("app.services.agent_actions.execute_create_card", new=AsyncMock(return_value="⚠ Could not create card 'buy groceries'.")):
		result = asyncio.get_event_loop().run_until_complete(
			dispatch_structural_intent(intent, "en")
		)
	assert result.startswith("⚠")


# ── CREATE_LIST tests ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("text,lang", [
	("create a list called Waiting on Work board", "en"),
	("add a new list In Progress to Garden", "en"),
	("erstelle eine Liste Wartend auf Garden board", "de"),
	("füge eine Liste Fertig zum Garden board hinzu", "de"),
	("crea una lista Esperando en Garden", "es"),
	("créer une liste En attente sur Garden", "fr"),
	("criar uma lista Aguardando em Garden", "pt"),
	("создай список Ожидание на доске Garden", "ru"),
])
def test_create_list_pattern_classifies(text, lang):
	"""CREATE_LIST verb is detected from basic input across languages."""
	result = asyncio.get_event_loop().run_until_complete(
		ir.classify_structural_intent(text, lang)
	)
	assert result is not None, f"[{lang}] classified as None for: {text!r}"
	assert result.verb == "CREATE_LIST", f"[{lang}] expected CREATE_LIST, got {result.verb!r}"
	assert result.entities.get("list_name"), f"[{lang}] list_name entity missing"


def test_create_list_dispatch_calls_executor():
	"""dispatch_structural_intent with CREATE_LIST calls execute_create_list and returns localised result."""
	from app.services.intent_router import StructuralIntent, dispatch_structural_intent
	intent = StructuralIntent(
		verb="CREATE_LIST",
		entities={"list_name": "Waiting", "board_name": "Work"},
		raw_text="create a list called Waiting on Work board",
		confidence=0.85,
	)
	with patch("app.services.agent_actions.execute_create_list", new=AsyncMock(return_value="List 'Waiting' created on 'Work'.")):
		result = asyncio.get_event_loop().run_until_complete(
			dispatch_structural_intent(intent, "en")
		)
	assert "Waiting" in result
	assert "[AUDIT:create_list:" in result


# ── RENAME_CARD tests ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("text,lang", [
	("rename the Buy Milk card to Buy Oat Milk", "en"),
	("rename Fix login to Fix SSO login", "en"),
	("umbenennen Milch kaufen in Hafermilch kaufen", "de"),
	("benenne die Karte Milch kaufen in Hafermilch um", "de"),
	("renombrar la tarjeta Comprar leche a Comprar avena", "es"),
	("renommer la carte Acheter lait en Acheter avoine", "fr"),
	("renomear o cartão Comprar leite para Comprar aveia", "pt"),
	("переименовать карточку Купить молоко в Купить овсяное молоко", "ru"),
])
def test_rename_card_pattern_classifies(text, lang):
	"""RENAME_CARD verb is detected from basic input across languages."""
	result = asyncio.get_event_loop().run_until_complete(
		ir.classify_structural_intent(text, lang)
	)
	assert result is not None, f"[{lang}] classified as None for: {text!r}"
	assert result.verb == "RENAME_CARD", f"[{lang}] expected RENAME_CARD, got {result.verb!r}"
	assert result.entities.get("card_fragment"), f"[{lang}] card_fragment entity missing"
	assert result.entities.get("new_name"), f"[{lang}] new_name entity missing"


def test_rename_card_dispatch_calls_executor():
	"""dispatch_structural_intent with RENAME_CARD calls execute_rename_card and returns localised result."""
	from app.services.intent_router import StructuralIntent, dispatch_structural_intent
	intent = StructuralIntent(
		verb="RENAME_CARD",
		entities={"card_fragment": "Buy Milk", "new_name": "Buy Oat Milk"},
		raw_text="rename the Buy Milk card to Buy Oat Milk",
		confidence=0.85,
	)
	with patch("app.services.agent_actions.execute_rename_card", new=AsyncMock(return_value="Card 'Buy Milk' renamed to 'Buy Oat Milk'.")):
		result = asyncio.get_event_loop().run_until_complete(
			dispatch_structural_intent(intent, "en")
		)
	assert "Buy Milk" in result
	assert "[AUDIT:rename_card:" in result


def test_rename_card_dispatch_returns_warning_on_failure():
	"""dispatch returns warning string when executor signals failure."""
	from app.services.intent_router import StructuralIntent, dispatch_structural_intent
	intent = StructuralIntent(
		verb="RENAME_CARD",
		entities={"card_fragment": "nonexistent card", "new_name": "New Name"},
		raw_text="rename nonexistent card to New Name",
		confidence=0.85,
	)
	with patch("app.services.agent_actions.execute_rename_card", new=AsyncMock(return_value="\u26a0 Could not rename card 'nonexistent card' \u2014 card not found.")):
		result = asyncio.get_event_loop().run_until_complete(
			dispatch_structural_intent(intent, "en")
		)
	assert result.startswith("\u26a0")


# ── RENAME_LIST ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text,lang", [
	("rename the list In Progress to Doing", "en"),
	("rename the column Backlog to Todo", "en"),
	("change the list name In Progress to Doing", "en"),
	("update the list In Progress to Doing", "en"),
	("umbenennen die Liste In Bearbeitung in Erledigt", "de"),
	("benenne die Liste Wartend in Erledigt um", "de"),
	("renombrar la lista En progreso a Haciendo", "es"),
	("renommer la liste En cours en Fait", "fr"),
	("renomear a lista Em progresso para Fazendo", "pt"),
	("переименовать список В работе в Готово", "ru"),
])
def test_rename_list_pattern_classifies(text, lang):
	result = asyncio.get_event_loop().run_until_complete(ir.classify_structural_intent(text, lang))
	assert result is not None, f"[{lang}] classified as None for: {text!r}"
	assert result.verb == "RENAME_LIST", f"[{lang}] expected RENAME_LIST, got {result.verb!r}"
	assert result.entities.get("list_fragment"), f"[{lang}] list_fragment entity missing"
	assert result.entities.get("new_name"), f"[{lang}] new_name entity missing"


def test_rename_list_dispatch_calls_executor():
	"""dispatch_structural_intent routes RENAME_LIST and returns AUDIT tag."""
	from app.services.intent_router import StructuralIntent, dispatch_structural_intent
	intent = StructuralIntent(
		verb="RENAME_LIST",
		entities={"list_fragment": "In Progress", "new_name": "Doing"},
		raw_text="rename the list In Progress to Doing",
		confidence=0.85,
	)
	with patch("app.services.agent_actions.execute_rename_list", new=AsyncMock(return_value="List 'In Progress' renamed to 'Doing'.")):
		result = asyncio.get_event_loop().run_until_complete(
			dispatch_structural_intent(intent, "en")
		)
	assert "In Progress" in result
	assert "[AUDIT:rename_list:" in result


def test_rename_list_dispatch_returns_warning_on_failure():
	"""dispatch returns warning string when executor signals failure."""
	from app.services.intent_router import StructuralIntent, dispatch_structural_intent
	intent = StructuralIntent(
		verb="RENAME_LIST",
		entities={"list_fragment": "nonexistent list", "new_name": "New Name"},
		raw_text="rename the list nonexistent list to New Name",
		confidence=0.85,
	)
	with patch("app.services.agent_actions.execute_rename_list", new=AsyncMock(return_value="\u26a0 Could not rename list 'nonexistent list' \u2014 list not found.")):
		result = asyncio.get_event_loop().run_until_complete(
			dispatch_structural_intent(intent, "en")
		)
	assert result.startswith("\u26a0")


# ---------------------------------------------------------------------------
# SET_CARD_DESC
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text,lang", [
	("set description of Buy groceries to Monthly shopping list", "en"),
	("update description of Meeting notes to Quarterly review", "en"),
	("change the description of Sprint card to Fix bug 42", "en"),
])
def test_set_card_desc_pattern_classifies(text, lang):
	"""SET_CARD_DESC verb is classified from natural-language inputs."""
	result = asyncio.get_event_loop().run_until_complete(ir.classify_structural_intent(text, lang))
	assert result is not None, f"[{lang}] classified as None for: {text!r}"
	assert result.verb == "SET_CARD_DESC", f"[{lang}] expected SET_CARD_DESC, got {result.verb!r}"


def test_set_card_desc_dispatch_calls_executor():
	"""dispatch_structural_intent routes SET_CARD_DESC correctly."""
	from app.services.intent_router import StructuralIntent, dispatch_structural_intent
	intent = StructuralIntent(
		verb="SET_CARD_DESC",
		entities={"card_fragment": "Buy groceries", "description": "Monthly shopping list"},
		raw_text="set description of Buy groceries to Monthly shopping list",
		confidence=0.85,
	)
	with patch("app.services.agent_actions.execute_set_card_desc", new=AsyncMock(return_value="Description of 'Buy groceries' updated.")):
		result = asyncio.get_event_loop().run_until_complete(
			dispatch_structural_intent(intent, "en")
		)
	assert "Buy groceries" in result
	assert "[AUDIT:set_card_desc:" in result


def test_set_card_desc_dispatch_returns_warning_on_failure():
	"""dispatch returns warning string when SET_CARD_DESC executor signals failure."""
	from app.services.intent_router import StructuralIntent, dispatch_structural_intent
	intent = StructuralIntent(
		verb="SET_CARD_DESC",
		entities={"card_fragment": "nonexistent", "description": "some text"},
		raw_text="set description of nonexistent to some text",
		confidence=0.85,
	)
	with patch("app.services.agent_actions.execute_set_card_desc", new=AsyncMock(return_value="\u26a0 Could not update description of 'nonexistent' \u2014 card not found.")):
		result = asyncio.get_event_loop().run_until_complete(
			dispatch_structural_intent(intent, "en")
		)
	assert result.startswith("\u26a0")


# ---------------------------------------------------------------------------
# ADD_CARD_TASK
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text,lang", [
	("add task Buy milk to card Shopping", "en"),
	("add a task Call dentist to card Health", "en"),
	("create task Write report in card Work", "en"),
])
def test_add_card_task_pattern_classifies(text, lang):
	"""ADD_CARD_TASK verb is classified from natural-language inputs."""
	result = asyncio.get_event_loop().run_until_complete(ir.classify_structural_intent(text, lang))
	assert result is not None, f"[{lang}] classified as None for: {text!r}"
	assert result.verb == "ADD_CARD_TASK", f"[{lang}] expected ADD_CARD_TASK, got {result.verb!r}"


def test_add_card_task_dispatch_calls_executor():
	"""dispatch_structural_intent routes ADD_CARD_TASK correctly."""
	from app.services.intent_router import StructuralIntent, dispatch_structural_intent
	intent = StructuralIntent(
		verb="ADD_CARD_TASK",
		entities={"card_fragment": "Shopping", "task_name": "Buy milk"},
		raw_text="add task Buy milk to card Shopping",
		confidence=0.85,
	)
	with patch("app.services.agent_actions.execute_add_card_task", new=AsyncMock(return_value="Task 'Buy milk' added to card 'Shopping'.")):
		result = asyncio.get_event_loop().run_until_complete(
			dispatch_structural_intent(intent, "en")
		)
	assert "Shopping" in result
	assert "[AUDIT:add_card_task:" in result


def test_add_card_task_dispatch_returns_warning_on_failure():
	"""dispatch returns warning string when ADD_CARD_TASK executor signals failure."""
	from app.services.intent_router import StructuralIntent, dispatch_structural_intent
	intent = StructuralIntent(
		verb="ADD_CARD_TASK",
		entities={"card_fragment": "nonexistent", "task_name": "Buy milk"},
		raw_text="add task Buy milk to card nonexistent",
		confidence=0.85,
	)
	with patch("app.services.agent_actions.execute_add_card_task", new=AsyncMock(return_value="\u26a0 Could not add task to 'nonexistent' \u2014 card not found.")):
		result = asyncio.get_event_loop().run_until_complete(
			dispatch_structural_intent(intent, "en")
		)
	assert result.startswith("\u26a0")


# ---------------------------------------------------------------------------
# CHECK_CARD_TASK
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text,lang", [
	("check off task Buy milk in card Shopping", "en"),
	("mark task Buy milk in card Shopping as done", "en"),
	("complete task Write report in card Work", "en"),
])
def test_check_card_task_pattern_classifies(text, lang):
	"""CHECK_CARD_TASK verb is classified from natural-language inputs."""
	result = asyncio.get_event_loop().run_until_complete(ir.classify_structural_intent(text, lang))
	assert result is not None, f"[{lang}] classified as None for: {text!r}"
	assert result.verb == "CHECK_CARD_TASK", f"[{lang}] expected CHECK_CARD_TASK, got {result.verb!r}"


def test_check_card_task_dispatch_calls_executor():
	"""dispatch_structural_intent routes CHECK_CARD_TASK correctly."""
	from app.services.intent_router import StructuralIntent, dispatch_structural_intent
	intent = StructuralIntent(
		verb="CHECK_CARD_TASK",
		entities={"card_fragment": "Shopping", "task_fragment": "Buy milk"},
		raw_text="check off task Buy milk in card Shopping",
		confidence=0.85,
	)
	with patch("app.services.agent_actions.execute_check_card_task", new=AsyncMock(return_value="Task 'Buy milk' in card 'Shopping' marked as done.")):
		result = asyncio.get_event_loop().run_until_complete(
			dispatch_structural_intent(intent, "en")
		)
	assert "Shopping" in result
	assert "[AUDIT:check_card_task:" in result


def test_check_card_task_dispatch_returns_warning_on_failure():
	"""dispatch returns warning string when CHECK_CARD_TASK executor signals failure."""
	from app.services.intent_router import StructuralIntent, dispatch_structural_intent
	intent = StructuralIntent(
		verb="CHECK_CARD_TASK",
		entities={"card_fragment": "Shopping", "task_fragment": "nonexistent task"},
		raw_text="check off task nonexistent task in card Shopping",
		confidence=0.85,
	)
	with patch("app.services.agent_actions.execute_check_card_task", new=AsyncMock(return_value="\u26a0 Could not check off task 'nonexistent task' in card 'Shopping' \u2014 not found.")):
		result = asyncio.get_event_loop().run_until_complete(
			dispatch_structural_intent(intent, "en")
		)
	assert result.startswith("\u26a0")


# ---------------------------------------------------------------------------
# UNCHECK_CARD_TASK
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text,lang", [
	("uncheck task Buy milk in card Shopping", "en"),
	("mark task Buy milk in card Shopping as not done", "en"),
	("reopen task Write report in card Work", "en"),
])
def test_uncheck_card_task_pattern_classifies(text, lang):
	"""UNCHECK_CARD_TASK verb is classified from natural-language inputs."""
	result = asyncio.get_event_loop().run_until_complete(ir.classify_structural_intent(text, lang))
	assert result is not None, f"[{lang}] classified as None for: {text!r}"
	assert result.verb == "UNCHECK_CARD_TASK", f"[{lang}] expected UNCHECK_CARD_TASK, got {result.verb!r}"


def test_uncheck_card_task_dispatch_calls_executor():
	"""dispatch_structural_intent routes UNCHECK_CARD_TASK correctly."""
	from app.services.intent_router import StructuralIntent, dispatch_structural_intent
	intent = StructuralIntent(
		verb="UNCHECK_CARD_TASK",
		entities={"card_fragment": "Shopping", "task_fragment": "Buy milk"},
		raw_text="uncheck task Buy milk in card Shopping",
		confidence=0.85,
	)
	with patch("app.services.agent_actions.execute_uncheck_card_task", new=AsyncMock(return_value="Task 'Buy milk' in card 'Shopping' marked as not done.")):
		result = asyncio.get_event_loop().run_until_complete(
			dispatch_structural_intent(intent, "en")
		)
	assert "Shopping" in result
	assert "[AUDIT:uncheck_card_task:" in result


def test_uncheck_card_task_dispatch_returns_warning_on_failure():
	"""dispatch returns warning string when UNCHECK_CARD_TASK executor signals failure."""
	from app.services.intent_router import StructuralIntent, dispatch_structural_intent
	intent = StructuralIntent(
		verb="UNCHECK_CARD_TASK",
		entities={"card_fragment": "Shopping", "task_fragment": "nonexistent task"},
		raw_text="uncheck task nonexistent task in card Shopping",
		confidence=0.85,
	)
	with patch("app.services.agent_actions.execute_uncheck_card_task", new=AsyncMock(return_value="\u26a0 Could not uncheck task 'nonexistent task' in card 'Shopping' \u2014 not found.")):
		result = asyncio.get_event_loop().run_until_complete(
			dispatch_structural_intent(intent, "en")
		)
	assert result.startswith("\u26a0")


# ---------------------------------------------------------------------------
# RENAME_CARD_TASK
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text,lang", [
	("rename task Buy milk in card Shopping to Buy oat milk", "en"),
	("rename task Write report in card Work to Finalize report", "en"),
])
def test_rename_card_task_pattern_classifies(text, lang):
	"""RENAME_CARD_TASK verb is classified from natural-language inputs."""
	result = asyncio.get_event_loop().run_until_complete(ir.classify_structural_intent(text, lang))
	assert result is not None, f"[{lang}] classified as None for: {text!r}"
	assert result.verb == "RENAME_CARD_TASK", f"[{lang}] expected RENAME_CARD_TASK, got {result.verb!r}"


def test_rename_card_task_dispatch_calls_executor():
	"""dispatch_structural_intent routes RENAME_CARD_TASK correctly."""
	from app.services.intent_router import StructuralIntent, dispatch_structural_intent
	intent = StructuralIntent(
		verb="RENAME_CARD_TASK",
		entities={"card_fragment": "Shopping", "task_fragment": "Buy milk", "new_name": "Buy oat milk"},
		raw_text="rename task Buy milk in card Shopping to Buy oat milk",
		confidence=0.85,
	)
	with patch("app.services.agent_actions.execute_rename_card_task", new=AsyncMock(return_value="Task 'Buy milk' in card 'Shopping' renamed to 'Buy oat milk'.")):
		result = asyncio.get_event_loop().run_until_complete(
			dispatch_structural_intent(intent, "en")
		)
	assert "Shopping" in result
	assert "[AUDIT:rename_card_task:" in result


def test_rename_card_task_dispatch_returns_warning_on_failure():
	"""dispatch returns warning string when RENAME_CARD_TASK executor signals failure."""
	from app.services.intent_router import StructuralIntent, dispatch_structural_intent
	intent = StructuralIntent(
		verb="RENAME_CARD_TASK",
		entities={"card_fragment": "Shopping", "task_fragment": "nonexistent", "new_name": "Buy oat milk"},
		raw_text="rename task nonexistent in card Shopping to Buy oat milk",
		confidence=0.85,
	)
	with patch("app.services.agent_actions.execute_rename_card_task", new=AsyncMock(return_value="\u26a0 Could not rename task 'nonexistent' in card 'Shopping' \u2014 not found.")):
		result = asyncio.get_event_loop().run_until_complete(
			dispatch_structural_intent(intent, "en")
		)
	assert result.startswith("\u26a0")


# ---------------------------------------------------------------------------
# DELETE_CARD
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text,lang", [
        ("delete card Shopping", "en"),
        ("remove card Meeting notes", "en"),
])
def test_delete_card_pattern_classifies(text, lang):
        """DELETE_CARD verb is classified from natural-language inputs."""
        result = asyncio.get_event_loop().run_until_complete(ir.classify_structural_intent(text, lang))
        assert result is not None, f"[{lang}] classified as None for: {text!r}"
        assert result.verb == "DELETE_CARD", f"[{lang}] expected DELETE_CARD, got {result.verb!r}"


def test_delete_card_dispatch_calls_executor():
        """dispatch_structural_intent routes DELETE_CARD correctly."""
        from app.services.intent_router import StructuralIntent, dispatch_structural_intent
        intent = StructuralIntent(
                verb="DELETE_CARD",
                entities={"card_fragment": "Shopping"},
                raw_text="delete card Shopping",
                confidence=0.85,
        )
        with patch("app.services.agent_actions.execute_delete_card", new=AsyncMock(return_value="Card 'Shopping' deleted.")):
                result = asyncio.get_event_loop().run_until_complete(
                        dispatch_structural_intent(intent, "en")
                )
        assert "Shopping" in result
        assert "[AUDIT:delete_card:" in result


def test_delete_card_dispatch_returns_warning_on_failure():
        """dispatch returns warning string when DELETE_CARD executor signals failure."""
        from app.services.intent_router import StructuralIntent, dispatch_structural_intent
        intent = StructuralIntent(
                verb="DELETE_CARD",
                entities={"card_fragment": "Nonexistent"},
                raw_text="delete card Nonexistent",
                confidence=0.85,
        )
        with patch("app.services.agent_actions.execute_delete_card", new=AsyncMock(return_value="\u26a0 Could not delete card 'Nonexistent' \u2014 card not found.")):
                result = asyncio.get_event_loop().run_until_complete(
                        dispatch_structural_intent(intent, "en")
                )
        assert result.startswith("\u26a0")


# ---------------------------------------------------------------------------
# DELETE_LIST
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text,lang", [
        ("delete list Backlog", "en"),
        ("remove column In Progress", "en"),
])
def test_delete_list_pattern_classifies(text, lang):
        """DELETE_LIST verb is classified from natural-language inputs."""
        result = asyncio.get_event_loop().run_until_complete(ir.classify_structural_intent(text, lang))
        assert result is not None, f"[{lang}] classified as None for: {text!r}"
        assert result.verb == "DELETE_LIST", f"[{lang}] expected DELETE_LIST, got {result.verb!r}"


def test_delete_list_dispatch_calls_executor():
        """dispatch_structural_intent routes DELETE_LIST correctly."""
        from app.services.intent_router import StructuralIntent, dispatch_structural_intent
        intent = StructuralIntent(
                verb="DELETE_LIST",
                entities={"list_fragment": "Backlog"},
                raw_text="delete list Backlog",
                confidence=0.85,
        )
        with patch("app.services.agent_actions.execute_delete_list", new=AsyncMock(return_value="List 'Backlog' deleted.")):
                result = asyncio.get_event_loop().run_until_complete(
                        dispatch_structural_intent(intent, "en")
                )
        assert "Backlog" in result
        assert "[AUDIT:delete_list:" in result


def test_delete_list_dispatch_returns_warning_on_failure():
        """dispatch returns warning string when DELETE_LIST executor signals failure."""
        from app.services.intent_router import StructuralIntent, dispatch_structural_intent
        intent = StructuralIntent(
                verb="DELETE_LIST",
                entities={"list_fragment": "Nonexistent"},
                raw_text="delete list Nonexistent",
                confidence=0.85,
        )
        with patch("app.services.agent_actions.execute_delete_list", new=AsyncMock(return_value="\u26a0 Could not delete list 'Nonexistent' \u2014 list not found.")):
                result = asyncio.get_event_loop().run_until_complete(
                        dispatch_structural_intent(intent, "en")
                )
        assert result.startswith("\u26a0")


# ---------------------------------------------------------------------------
# DELETE_CARD_TASK
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text,lang", [
        ("remove task Buy milk from card Shopping", "en"),
        ("delete task Write report from card Work", "en"),
])
def test_delete_card_task_pattern_classifies(text, lang):
        """DELETE_CARD_TASK verb is classified from natural-language inputs."""
        result = asyncio.get_event_loop().run_until_complete(ir.classify_structural_intent(text, lang))
        assert result is not None, f"[{lang}] classified as None for: {text!r}"
        assert result.verb == "DELETE_CARD_TASK", f"[{lang}] expected DELETE_CARD_TASK, got {result.verb!r}"


def test_delete_card_task_dispatch_calls_executor():
        """dispatch_structural_intent routes DELETE_CARD_TASK correctly."""
        from app.services.intent_router import StructuralIntent, dispatch_structural_intent
        intent = StructuralIntent(
                verb="DELETE_CARD_TASK",
                entities={"card_fragment": "Shopping", "task_fragment": "Buy milk"},
                raw_text="remove task Buy milk from card Shopping",
                confidence=0.85,
        )
        with patch("app.services.agent_actions.execute_delete_card_task", new=AsyncMock(return_value="Task 'Buy milk' removed from card 'Shopping'.")):
                result = asyncio.get_event_loop().run_until_complete(
                        dispatch_structural_intent(intent, "en")
                )
        assert "Shopping" in result
        assert "[AUDIT:delete_card_task:" in result


def test_delete_card_task_dispatch_returns_warning_on_failure():
        """dispatch returns warning string when DELETE_CARD_TASK executor signals failure."""
        from app.services.intent_router import StructuralIntent, dispatch_structural_intent
        intent = StructuralIntent(
                verb="DELETE_CARD_TASK",
                entities={"card_fragment": "Shopping", "task_fragment": "nonexistent"},
                raw_text="remove task nonexistent from card Shopping",
                confidence=0.85,
        )
        with patch("app.services.agent_actions.execute_delete_card_task", new=AsyncMock(return_value="\u26a0 Could not remove task 'nonexistent' from card 'Shopping' \u2014 not found.")):
                result = asyncio.get_event_loop().run_until_complete(
                        dispatch_structural_intent(intent, "en")
                )
        assert result.startswith("\u26a0")


# ---------------------------------------------------------------------------
# CREATE_BOARD
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text,lang", [
	("create board Finance in My Projects", "en"),
	("add board Shopping", "en"),
	("new board Roadmap in Work", "en"),
])
def test_create_board_pattern_classifies(text, lang):
	"""CREATE_BOARD verb is classified from natural-language inputs."""
	result = asyncio.get_event_loop().run_until_complete(ir.classify_structural_intent(text, lang))
	assert result is not None, f"[{lang}] classified as None for: {text!r}"
	assert result.verb == "CREATE_BOARD", f"[{lang}] expected CREATE_BOARD, got {result.verb!r}"


def test_create_board_dispatch_calls_executor():
	"""dispatch_structural_intent routes CREATE_BOARD correctly."""
	from app.services.intent_router import StructuralIntent, dispatch_structural_intent
	intent = StructuralIntent(
		verb="CREATE_BOARD",
		entities={"board_name": "Finance", "project_fragment": "My Projects"},
		raw_text="create board Finance in My Projects",
		confidence=0.85,
	)
	with patch("app.services.agent_actions.execute_create_board", new=AsyncMock(return_value="Board 'Finance' created.")):
		result = asyncio.get_event_loop().run_until_complete(
			dispatch_structural_intent(intent, "en")
		)
	assert "Finance" in result
	assert "[AUDIT:create_board:" in result


def test_create_board_dispatch_returns_warning_on_failure():
	"""dispatch returns warning string when CREATE_BOARD executor signals failure."""
	from app.services.intent_router import StructuralIntent, dispatch_structural_intent
	intent = StructuralIntent(
		verb="CREATE_BOARD",
		entities={"board_name": "Finance", "project_fragment": "nonexistent"},
		raw_text="create board Finance in nonexistent",
		confidence=0.85,
	)
	with patch("app.services.agent_actions.execute_create_board", new=AsyncMock(return_value="\u26a0 Could not create board 'Finance' \u2014 project not found.")):
		result = asyncio.get_event_loop().run_until_complete(
			dispatch_structural_intent(intent, "en")
		)
	assert result.startswith("\u26a0")


# ---------------------------------------------------------------------------
# RENAME_BOARD
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text,lang", [
	("rename board Finance to Investments", "en"),
	("change board name Shopping to Groceries", "en"),
])
def test_rename_board_pattern_classifies(text, lang):
	"""RENAME_BOARD verb is classified from natural-language inputs."""
	result = asyncio.get_event_loop().run_until_complete(ir.classify_structural_intent(text, lang))
	assert result is not None, f"[{lang}] classified as None for: {text!r}"
	assert result.verb == "RENAME_BOARD", f"[{lang}] expected RENAME_BOARD, got {result.verb!r}"


def test_rename_board_dispatch_calls_executor():
	"""dispatch_structural_intent routes RENAME_BOARD correctly."""
	from app.services.intent_router import StructuralIntent, dispatch_structural_intent
	intent = StructuralIntent(
		verb="RENAME_BOARD",
		entities={"board_fragment": "Finance", "new_name": "Investments"},
		raw_text="rename board Finance to Investments",
		confidence=0.85,
	)
	with patch("app.services.agent_actions.execute_rename_board", new=AsyncMock(return_value="Board 'Finance' renamed to 'Investments'.")):
		result = asyncio.get_event_loop().run_until_complete(
			dispatch_structural_intent(intent, "en")
		)
	assert "Finance" in result
	assert "[AUDIT:rename_board:" in result


def test_rename_board_dispatch_returns_warning_on_failure():
	"""dispatch returns warning string when RENAME_BOARD executor signals failure."""
	from app.services.intent_router import StructuralIntent, dispatch_structural_intent
	intent = StructuralIntent(
		verb="RENAME_BOARD",
		entities={"board_fragment": "nonexistent", "new_name": "New Name"},
		raw_text="rename board nonexistent to New Name",
		confidence=0.85,
	)
	with patch("app.services.agent_actions.execute_rename_board", new=AsyncMock(return_value="\u26a0 Could not rename board 'nonexistent' \u2014 board not found.")):
		result = asyncio.get_event_loop().run_until_complete(
			dispatch_structural_intent(intent, "en")
		)
	assert result.startswith("\u26a0")


# ---------------------------------------------------------------------------
# DELETE_BOARD
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text,lang", [
	("delete board Finance", "en"),
	("remove board Shopping", "en"),
])
def test_delete_board_pattern_classifies(text, lang):
	"""DELETE_BOARD verb is classified from natural-language inputs."""
	result = asyncio.get_event_loop().run_until_complete(ir.classify_structural_intent(text, lang))
	assert result is not None, f"[{lang}] classified as None for: {text!r}"
	assert result.verb == "DELETE_BOARD", f"[{lang}] expected DELETE_BOARD, got {result.verb!r}"


def test_delete_board_dispatch_calls_executor():
	"""dispatch_structural_intent routes DELETE_BOARD correctly."""
	from app.services.intent_router import StructuralIntent, dispatch_structural_intent
	intent = StructuralIntent(
		verb="DELETE_BOARD",
		entities={"board_fragment": "Finance"},
		raw_text="delete board Finance",
		confidence=0.85,
	)
	with patch("app.services.agent_actions.execute_delete_board", new=AsyncMock(return_value="Board 'Finance' deleted.")):
		result = asyncio.get_event_loop().run_until_complete(
			dispatch_structural_intent(intent, "en")
		)
	assert "Finance" in result
	assert "[AUDIT:delete_board:" in result


def test_delete_board_dispatch_returns_warning_on_failure():
	"""dispatch returns warning string when DELETE_BOARD executor signals failure."""
	from app.services.intent_router import StructuralIntent, dispatch_structural_intent
	intent = StructuralIntent(
		verb="DELETE_BOARD",
		entities={"board_fragment": "nonexistent"},
		raw_text="delete board nonexistent",
		confidence=0.85,
	)
	with patch("app.services.agent_actions.execute_delete_board", new=AsyncMock(return_value="\u26a0 Could not delete board 'nonexistent' \u2014 board not found.")):
		result = asyncio.get_event_loop().run_until_complete(
			dispatch_structural_intent(intent, "en")
		)
	assert result.startswith("\u26a0")


# ---------------------------------------------------------------------------
# CREATE_PROJECT
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text,lang", [
	("create a project called Alpha", "en"),
	("erstelle ein Projekt namens Alpha", "de"),
	("crea un proyecto llamado Alpha", "es"),
])
def test_create_project_pattern_classifies(text, lang):
	"""CREATE_PROJECT verb is classified from natural-language inputs."""
	result = asyncio.get_event_loop().run_until_complete(ir.classify_structural_intent(text, lang))
	assert result is not None, f"[{lang}] classified as None for: {text!r}"
	assert result.verb == "CREATE_PROJECT", f"[{lang}] expected CREATE_PROJECT, got {result.verb!r}"


def test_create_project_dispatch_success():
	"""dispatch_structural_intent routes CREATE_PROJECT correctly on success."""
	from app.services.intent_router import StructuralIntent, dispatch_structural_intent
	intent = StructuralIntent(
		verb="CREATE_PROJECT",
		entities={"project_name": "Alpha"},
		raw_text="create a project called Alpha",
		confidence=0.85,
	)
	with patch("app.services.agent_actions.execute_create_project", new=AsyncMock(return_value="Project 'Alpha' created.")):
		result = asyncio.get_event_loop().run_until_complete(
			dispatch_structural_intent(intent, "en")
		)
	assert "created" in result
	assert "[AUDIT:create_project:Alpha]" in result


def test_create_project_dispatch_duplicate():
	"""dispatch returns duplicate message when CREATE_PROJECT executor signals existing project."""
	from app.services.intent_router import StructuralIntent, dispatch_structural_intent
	intent = StructuralIntent(
		verb="CREATE_PROJECT",
		entities={"project_name": "Alpha"},
		raw_text="create a project called Alpha",
		confidence=0.85,
	)
	with patch("app.services.agent_actions.execute_create_project", new=AsyncMock(return_value="⚠duplicate:Alpha")):
		result = asyncio.get_event_loop().run_until_complete(
			dispatch_structural_intent(intent, "en")
		)
	assert "already exists" in result
	assert "AUDIT" not in result


# ---------------------------------------------------------------------------
# RENAME_PROJECT
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text,lang", [
	("rename project Alpha to Beta", "en"),
])
def test_rename_project_pattern_classifies(text, lang):
	"""RENAME_PROJECT verb is classified from natural-language inputs."""
	result = asyncio.get_event_loop().run_until_complete(ir.classify_structural_intent(text, lang))
	assert result is not None, f"[{lang}] classified as None for: {text!r}"
	assert result.verb == "RENAME_PROJECT", f"[{lang}] expected RENAME_PROJECT, got {result.verb!r}"
	assert result.entities.get("project_fragment") == "Alpha"
	assert result.entities.get("new_name") == "Beta"


def test_rename_project_dispatch_success():
	"""dispatch_structural_intent routes RENAME_PROJECT correctly on success."""
	from app.services.intent_router import StructuralIntent, dispatch_structural_intent
	intent = StructuralIntent(
		verb="RENAME_PROJECT",
		entities={"project_fragment": "Alpha", "new_name": "Beta"},
		raw_text="rename project Alpha to Beta",
		confidence=0.85,
	)
	with patch("app.services.agent_actions.execute_rename_project", new=AsyncMock(return_value="Project 'Alpha' renamed to 'Beta'.")):
		result = asyncio.get_event_loop().run_until_complete(
			dispatch_structural_intent(intent, "en")
		)
	assert "renamed" in result
	assert "[AUDIT:rename_project:Alpha->Beta]" in result


def test_rename_project_dispatch_not_found():
	"""dispatch returns not-found message when RENAME_PROJECT executor cannot locate project."""
	from app.services.intent_router import StructuralIntent, dispatch_structural_intent
	intent = StructuralIntent(
		verb="RENAME_PROJECT",
		entities={"project_fragment": "Alpha", "new_name": "Beta"},
		raw_text="rename project Alpha to Beta",
		confidence=0.85,
	)
	with patch("app.services.agent_actions.execute_rename_project", new=AsyncMock(return_value="⚠notfound:Alpha")):
		result = asyncio.get_event_loop().run_until_complete(
			dispatch_structural_intent(intent, "en")
		)
	assert "not found" in result
	assert "AUDIT" not in result


# ---------------------------------------------------------------------------
# DELETE_PROJECT
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text,lang", [
	("delete project Alpha", "en"),
	("lösche das Projekt Alpha", "de"),
])
def test_delete_project_pattern_classifies(text, lang):
	"""DELETE_PROJECT verb is classified from natural-language inputs."""
	result = asyncio.get_event_loop().run_until_complete(ir.classify_structural_intent(text, lang))
	assert result is not None, f"[{lang}] classified as None for: {text!r}"
	assert result.verb == "DELETE_PROJECT", f"[{lang}] expected DELETE_PROJECT, got {result.verb!r}"


def test_delete_project_dispatch_success():
	"""dispatch_structural_intent routes DELETE_PROJECT correctly on success."""
	from app.services.intent_router import StructuralIntent, dispatch_structural_intent
	intent = StructuralIntent(
		verb="DELETE_PROJECT",
		entities={"project_fragment": "Alpha"},
		raw_text="delete project Alpha",
		confidence=0.85,
	)
	with patch("app.services.agent_actions.execute_delete_project", new=AsyncMock(return_value="Project 'Alpha' deleted.")):
		result = asyncio.get_event_loop().run_until_complete(
			dispatch_structural_intent(intent, "en")
		)
	assert "deleted" in result
	assert "[AUDIT:delete_project:Alpha]" in result


def test_delete_project_dispatch_not_found():
	"""dispatch returns not-found message when DELETE_PROJECT executor cannot locate project."""
	from app.services.intent_router import StructuralIntent, dispatch_structural_intent
	intent = StructuralIntent(
		verb="DELETE_PROJECT",
		entities={"project_fragment": "nonexistent"},
		raw_text="delete project nonexistent",
		confidence=0.85,
	)
	with patch("app.services.agent_actions.execute_delete_project", new=AsyncMock(return_value="⚠notfound:nonexistent")):
		result = asyncio.get_event_loop().run_until_complete(
			dispatch_structural_intent(intent, "en")
		)
	assert "not found" in result
	assert "AUDIT" not in result
