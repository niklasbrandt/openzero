import pytest
from unittest.mock import AsyncMock, patch
from app.services.crews import is_system_action_or_operational_query


@pytest.mark.anyio
async def test_is_system_action_or_operational_query_positive():
	# Test that YES response from LLM resolves to True
	with patch("app.services.llm.chat", new=AsyncMock(return_value=" YES \n")) as mock_chat:
		result = await is_system_action_or_operational_query("pon la receta en la lista de chef")
		assert result is True
		mock_chat.assert_called_once()
		assert "multilingual intent classifier" in mock_chat.call_args[1]["system_override"]


@pytest.mark.anyio
async def test_is_system_action_or_operational_query_negative():
	# Test that NO response from LLM resolves to False
	with patch("app.services.llm.chat", new=AsyncMock(return_value=" NO ")) as mock_chat:
		result = await is_system_action_or_operational_query("explain the Fermi paradox")
		assert result is False
		mock_chat.assert_called_once()


@pytest.mark.anyio
async def test_is_system_action_or_operational_query_failure_fallback():
	# Test that exceptions in LLM call fall back to False
	with patch("app.services.llm.chat", new=AsyncMock(side_effect=RuntimeError("LLM down"))) as mock_chat:
		result = await is_system_action_or_operational_query("move board")
		assert result is False
		mock_chat.assert_called_once()
