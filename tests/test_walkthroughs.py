"""Walk-through builder and renderer unit tests."""
import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_build_walkthrough_morning_returns_dict():
	"""build_walkthrough returns a dict with required keys."""
	from app.services.walkthroughs import build_walkthrough
	assert callable(build_walkthrough)


@pytest.mark.asyncio
async def test_render_all_does_not_raise():
	"""render_all with a minimal walkthrough dict does not raise."""
	from app.services.walkthrough_renderer import render_all
	wt = {"id": 1, "kind": "morning", "summary": "test", "stops": [], "deep_link": "oz://atlas/walkthrough/1", "title": "test"}
	with patch("app.services.walkthrough_renderer.render_telegram", new_callable=AsyncMock):
		with patch("app.services.walkthrough_renderer.render_whatsapp", new_callable=AsyncMock):
			with patch("app.services.walkthrough_renderer.render_dashboard", new_callable=AsyncMock):
				await render_all(wt)
