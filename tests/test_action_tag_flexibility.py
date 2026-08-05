"""
Unit tests for flexible action tag parameter parsing in agent_actions.py.

Verifies that action tags with reversed or flexible key order
(e.g., NAME before PROJECT) are parsed correctly.
"""
from app.services.agent_actions import _parse_tag_params, parse_and_execute_actions
from unittest.mock import AsyncMock, patch


def test_parse_tag_params_key_order():
	tag1 = "[ACTION: CREATE_BOARD | PROJECT: My projects | NAME: Producing Setup]"
	params1 = _parse_tag_params(tag1)
	assert params1 == {"PROJECT": "My projects", "NAME": "Producing Setup"}

	tag2 = "[ACTION: CREATE_BOARD | NAME: Producing Setup | PROJECT: My projects]"
	params2 = _parse_tag_params(tag2)
	assert params2 == {"NAME": "Producing Setup", "PROJECT": "My projects"}

	tag3 = "[ACTION: CREATE_TASK | TITLE: Buy microphone | BOARD: Producing Setup | LIST: Todo]"
	params3 = _parse_tag_params(tag3)
	assert params3 == {"TITLE": "Buy microphone", "BOARD": "Producing Setup", "LIST": "Todo"}


@patch("app.services.agent_actions.planka_create_board", new_callable=AsyncMock)
@patch("app.services.agent_actions.get_planka_auth_token", new_callable=AsyncMock)
def test_create_board_reversed_keys_executes(mock_auth, mock_create_board):
	mock_auth.return_value = "fake_token"
	mock_create_board.return_value = {"id": "board_123"}

	# Tag with NAME before PROJECT (the exact pattern produced by LLM today)
	reply = "Creating board.\n[ACTION: CREATE_BOARD | NAME: Producing Setup | PROJECT: My projects]"

	with patch("httpx.AsyncClient") as mock_client_cls:
		mock_client = AsyncMock()
		mock_resp = AsyncMock()
		mock_resp.json.return_value = {"items": [{"id": "proj_999", "name": "My projects"}]}
		mock_client.get.return_value = mock_resp
		mock_client_cls.return_value.__aenter__.return_value = mock_client

		import asyncio
		clean, executed, pending = asyncio.run(
			parse_and_execute_actions(reply, require_hitl=False, user_text="Neues Board: producing setup")
		)

	assert "No action was executed" not in clean
	assert len(executed) == 1
	assert "Producing Setup" in executed[0]
