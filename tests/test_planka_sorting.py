"""
Unit tests for Planka board and project tree sorting logic in planka.py.

Verifies that boards and projects are sorted by their latest modification
timestamp descending (latest creation or changes to cards/items inside come first).
"""

import pytest
import httpx
from unittest.mock import patch, AsyncMock, MagicMock

if not hasattr(httpx, "AsyncClient"):
	httpx.AsyncClient = MagicMock  # type: ignore[attr-defined]
from app.services.planka import _extract_latest_timestamp, get_project_tree, _tree_cache


def test_extract_latest_timestamp():
	# Simple strings
	assert _extract_latest_timestamp("2026-08-01T10:00:00Z", "2026-08-05T12:00:00Z") == "2026-08-05T12:00:00Z"

	# Nested dicts with updatedAt / createdAt
	obj1 = {"createdAt": "2026-01-01T00:00:00Z", "updatedAt": "2026-08-06T15:00:00Z"}
	obj2 = {"createdAt": "2026-08-06T18:30:00Z"}
	assert _extract_latest_timestamp(obj1, obj2) == "2026-08-06T18:30:00Z"

	# Nested lists of cards
	cards = [
		{"updatedAt": "2026-08-02T10:00:00Z"},
		{"updatedAt": "2026-08-06T20:00:00Z"},
		{"createdAt": "2026-08-01T10:00:00Z"},
	]
	assert _extract_latest_timestamp(cards) == "2026-08-06T20:00:00Z"


@pytest.mark.asyncio
@patch("app.services.planka.get_planka_auth_token", new_callable=AsyncMock)
async def test_get_project_tree_sorting(mock_auth):
	mock_auth.return_value = "fake_token"
	_tree_cache.clear()

	projects_resp = {
		"items": [
			{"id": "proj_old", "name": "Old Project", "updatedAt": "2026-01-01T00:00:00Z"},
			{"id": "proj_new", "name": "Active Project", "updatedAt": "2026-08-01T00:00:00Z"},
		]
	}

	# Old Project has a board with a very recent change
	proj_old_detail = {
		"included": {
			"boards": [
				{"id": "board_old_1", "name": "Stale Board", "updatedAt": "2026-01-02T00:00:00Z"},
				{"id": "board_old_2", "name": "Hot Board", "updatedAt": "2026-08-06T22:00:00Z"},
			]
		}
	}

	# Active Project has a moderately recent board
	proj_new_detail = {
		"included": {
			"boards": [
				{"id": "board_new_1", "name": "Moderate Board", "updatedAt": "2026-08-05T10:00:00Z"},
			]
		}
	}

	board_old_1_detail = {
		"included": {
			"lists": [{"id": "l1", "name": "Todo"}],
			"cards": [{"id": "c1", "listId": "l1", "name": "Old task", "updatedAt": "2026-01-02T00:00:00Z"}],
		}
	}

	board_old_2_detail = {
		"included": {
			"lists": [{"id": "l2", "name": "Todo"}],
			"cards": [{"id": "c2", "listId": "l2", "name": "Latest task", "updatedAt": "2026-08-06T22:00:00Z"}],
		}
	}

	board_new_1_detail = {
		"included": {
			"lists": [{"id": "l3", "name": "Todo"}],
			"cards": [{"id": "c3", "listId": "l3", "name": "Moderate task", "updatedAt": "2026-08-05T10:00:00Z"}],
		}
	}

	def mock_get(url, **kwargs):
		res = MagicMock()
		res.raise_for_status = lambda: None
		if url == "/api/projects":
			res.json.return_value = projects_resp
		elif url == "/api/projects/proj_old":
			res.json.return_value = proj_old_detail
		elif url == "/api/projects/proj_new":
			res.json.return_value = proj_new_detail
		elif url == "/api/boards/board_old_1":
			res.json.return_value = board_old_1_detail
		elif url == "/api/boards/board_old_2":
			res.json.return_value = board_old_2_detail
		elif url == "/api/boards/board_new_1":
			res.json.return_value = board_new_1_detail
		return res

	with patch("app.services.planka.settings") as mock_settings, patch.object(httpx, "AsyncClient") as mock_client_cls:
		mock_settings.PLANKA_BASE_URL = "http://planka:1337"
		mock_settings.BASE_URL = "http://localhost:8000"
		mock_client = AsyncMock()
		mock_client.get.side_effect = mock_get
		mock_client_cls.return_value.__aenter__.return_value = mock_client

		tree = await get_project_tree(as_html=False)

		# Old Project should come FIRST because its "Hot Board" has the latest modification (2026-08-06T22:00:00Z)
		# Within Old Project, "Hot Board" should come BEFORE "Stale Board"
		pos_old_proj = tree.find("[Old Project]")
		pos_new_proj = tree.find("[Active Project]")
		assert pos_old_proj != -1 and pos_new_proj != -1
		assert pos_old_proj < pos_new_proj, "Project with most recent board modification should appear first"

		pos_hot_board = tree.find("[Hot Board]")
		pos_stale_board = tree.find("[Stale Board]")
		assert pos_hot_board != -1 and pos_stale_board != -1
		assert pos_hot_board < pos_stale_board, "Board with latest modification should appear first within project"
