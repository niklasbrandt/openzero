"""Crew Conversation Memory Service
-----------------------------------
Maintains a per-crew conversation log in Planka:

  Project:  <crews_project_name>      (i18n, default "Crews")
  Board:    <crew display name>        (e.g. "Nutrition", "Fitness")
  List:     <crew_conversation_list>   (i18n, default "Conversation") — always first
  Card:     <date_str>                 (e.g. "2026.04.04", format from user setting)
  Description: Rolling log of today's exchange — user + crew turns, re-summarised on each append.
               Truncated to MAX_DESC_CHARS with a "[...]" prefix when it grows too long.

Public API:
  append_crew_exchange(crew_id, user_msg, crew_response)
      Called after every crew response. Creates/updates today's card.

  get_crew_memory_context(crew_id) -> str
      Returns recent conversation history formatted for injection into system prompt.
"""
import logging
from datetime import datetime, timedelta, timezone

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# Maximum characters kept in the card description before truncation
MAX_DESC_CHARS = 4000
# How many past days to load for context injection
CONTEXT_DAYS = 7
# Max chars of history to inject into the crew prompt
MAX_CONTEXT_CHARS = 2000

_DATE_FORMAT_MAP = {
	"iso": "%Y.%m.%d",
	"us": "%m/%d/%Y",
	"eu": "%d.%m.%Y",
	"cn": "%Y\u5e74%m\u6708%d\u65e5",
}
_DEFAULT_DATE_FORMAT_KEY = "iso"


async def _get_user_date_format() -> str:
	"""Return the strftime format string for the user's preferred date format."""
	try:
		from app.models.db import AsyncSessionLocal, Person
		from sqlalchemy import select
		async with AsyncSessionLocal() as session:
			res = await session.execute(select(Person).where(Person.circle_type == "identity"))
			ident = res.scalar_one_or_none()
			fmt_key = (ident.date_format if ident and ident.date_format else _DEFAULT_DATE_FORMAT_KEY)
			return _DATE_FORMAT_MAP.get(fmt_key, _DATE_FORMAT_MAP[_DEFAULT_DATE_FORMAT_KEY])
	except Exception:
		return _DATE_FORMAT_MAP[_DEFAULT_DATE_FORMAT_KEY]


async def _get_user_timezone():
	"""Return the user's timezone or UTC."""
	try:
		import pytz
		from app.models.db import AsyncSessionLocal, Person
		from sqlalchemy import select
		async with AsyncSessionLocal() as session:
			res = await session.execute(select(Person).where(Person.circle_type == "identity"))
			ident = res.scalar_one_or_none()
			tz_str = ident.timezone if ident and ident.timezone else "UTC"
			return pytz.timezone(tz_str)
	except Exception:
		return timezone.utc


def _crew_board_name(crew_id: str) -> str:
	"""Convert crew_id to a human-readable board name. e.g. 'market-intel' -> 'Market Intel'"""
	return crew_id.replace("-", " ").title()


async def _planka_client():
	"""Return an authenticated httpx.AsyncClient for Planka."""
	from app.services.planka_common import get_planka_auth_token
	token = await get_planka_auth_token()
	return httpx.AsyncClient(
		base_url=settings.PLANKA_BASE_URL,
		headers={"Authorization": f"Bearer {token}"},
		timeout=20.0,
	)


async def _get_or_create_crews_project(client: httpx.AsyncClient, project_name: str) -> str | None:
	"""Return project_id for the Crews project, creating it if absent."""
	try:
		resp = await client.get("/api/projects")
		resp.raise_for_status()
		for p in resp.json().get("items", []):
			if (p.get("name") or "").lower() == project_name.lower():
				return p["id"]
		# Create it
		r = await client.post("/api/projects", json={"name": project_name, "type": "private"})
		if r.status_code >= 400:
			r = await client.post("/api/projects", json={"name": project_name, "isPublic": False})
		r.raise_for_status()
		return (r.json().get("item") or r.json())["id"]
	except Exception as e:
		logger.warning("crew_memory: _get_or_create_crews_project failed: %s", e)
		return None


async def _get_or_create_crew_board(
	client: httpx.AsyncClient,
	project_id: str,
	board_name: str,
) -> str | None:
	"""Return board_id for the crew's named board inside the Crews project."""
	try:
		det = await client.get(f"/api/projects/{project_id}")
		det.raise_for_status()
		boards = det.json().get("included", {}).get("boards", [])
		for b in boards:
			if (b.get("name") or "").lower() == board_name.lower():
				return b["id"]
		# Create board directly on this client (same auth session)
		r = await client.post(f"/api/projects/{project_id}/boards", json={
			"name": board_name,
			"position": 65535,
		})
		r.raise_for_status()
		data = r.json()
		board = data.get("item") or data
		board_id = board.get("id")
		if not board_id:
			logger.warning("crew_memory: board creation returned no id for '%s'", board_name.replace('\n', ' ').replace('\r', ' '))
			return None
		return board_id
	except Exception as e:
		logger.warning("crew_memory: _get_or_create_crew_board failed: %s", e)
		return None


async def _get_or_create_conversation_list(
	client: httpx.AsyncClient,
	board_id: str,
	list_name: str,
) -> str | None:
	"""Return list_id for the Conversation list on the board."""
	try:
		b_detail = await client.get(f"/api/boards/{board_id}", params={"included": "lists"})
		b_detail.raise_for_status()
		b_data = b_detail.json()
		lists = b_data.get("included", {}).get("lists", []) or b_data.get("lists", [])
		for lst in lists:
			if (lst.get("name") or "").lower() == list_name.lower():
				return lst["id"]
		# Create conversation list
		r = await client.post(f"/api/boards/{board_id}/lists", json={
			"name": list_name,
			"type": "active",
			"position": 65535,
		})
		r.raise_for_status()
		data = r.json()
		item = data.get("item") or data
		return item.get("id")
	except Exception as e:
		logger.warning("crew_memory: _get_or_create_conversation_list failed: %s", e)
		return None


async def _get_or_create_today_card(
	client: httpx.AsyncClient,
	board_id: str,
	list_id: str,
	date_str: str,
) -> tuple[str | None, str]:
	"""Return (card_id, current_description) for today's conversation card."""
	try:
		# Planka has no GET /api/lists/{id}/cards — fetch cards via board detail
		b_detail = await client.get(f"/api/boards/{board_id}", params={"included": "lists,cards"})
		b_detail.raise_for_status()
		b_data = b_detail.json()
		cards = b_data.get("included", {}).get("cards", []) or b_data.get("cards", [])
		for c in cards:
			if c.get("listId") == list_id and c.get("name") == date_str:
				return c["id"], c.get("description") or ""
		# Create today's card at position 1 so it appears at the top of the list
		# Planka v2: "type" is required; omit empty description (rejected with 400).
		r = await client.post(f"/api/lists/{list_id}/cards", json={
			"name": date_str,
			"type": "project",
			"position": 1,
		})
		r.raise_for_status()
		data = r.json()
		item = data.get("item") or data
		return item.get("id"), ""
	except Exception as e:
		logger.warning("crew_memory: _get_or_create_today_card failed: %s", e)
		return None, ""


async def _patch_card_description(client: httpx.AsyncClient, card_id: str, description: str) -> None:
	"""Update a card's description field."""
	try:
		r = await client.patch(f"/api/cards/{card_id}", json={"description": description})
		r.raise_for_status()
	except Exception as e:
		logger.warning("crew_memory: _patch_card_description failed for %s: %s", card_id, e)


def _build_updated_description(current: str, user_msg: str, crew_response: str, now_str: str) -> str:
	"""Append the new exchange to the current description, truncating if needed."""
	# Strip action tags from crew response before storing
	import re
	clean_response = re.sub(r"\[?ACTION:[^\]]+\]?", "", crew_response).strip()
	clean_response = re.sub(r"\n{3,}", "\n\n", clean_response)

	new_entry = (
		f"[{now_str}] User: {user_msg.strip()}\n"
		f"[{now_str}] Crew: {clean_response[:800]}\n"
		"---\n"
	)
	updated = current + new_entry if current else new_entry

	if len(updated) > MAX_DESC_CHARS:
		truncated = updated[-MAX_DESC_CHARS:]
		# Cut to nearest newline boundary
		nl = truncated.find("\n")
		if nl > 0:
			truncated = truncated[nl + 1:]
		updated = "[...earlier conversation omitted...]\n" + truncated

	return updated


async def append_crew_exchange(crew_id: str, user_msg: str, crew_response: str) -> None:
	"""Create or update today's conversation card for the given crew."""
	try:
		from app.services.translations import get_translations, get_user_lang
		lang = await get_user_lang()
		t = get_translations(lang)
		project_name: str = t.get("crews_project_name", "Crews")
		list_name: str = t.get("crew_conversation_list", "Conversation")

		date_fmt = await _get_user_date_format()
		try:
			tz = await _get_user_timezone()
			now_local = datetime.now(tz)
		except Exception:
			now_local = datetime.now(timezone.utc)

		date_str = now_local.strftime(date_fmt)
		time_str = now_local.strftime("%H:%M")
		board_name = _crew_board_name(crew_id)

		async with await _planka_client() as client:
			project_id = await _get_or_create_crews_project(client, project_name)
			if not project_id:
				return
			board_id = await _get_or_create_crew_board(client, project_id, board_name)
			if not board_id:
				return
			list_id = await _get_or_create_conversation_list(client, board_id, list_name)
			if not list_id:
				return
			card_id, current_desc = await _get_or_create_today_card(client, board_id, list_id, date_str)
			if not card_id:
				return
			updated_desc = _build_updated_description(current_desc, user_msg, crew_response, time_str)
			await _patch_card_description(client, card_id, updated_desc)
			logger.info("crew_memory: updated conversation card for crew '%s' (%s)", crew_id.replace('\n', ' ').replace('\r', ' '), date_str)
	except Exception as e:
		logger.warning("crew_memory: append_crew_exchange failed: %s", e)


async def get_crew_memory_context(crew_id: str) -> str:
	"""
	Load the last CONTEXT_DAYS days of conversation cards for this crew and
	return a formatted string for injection into the crew system prompt.
	Returns empty string if nothing found or on error.
	"""
	try:
		from app.services.translations import get_translations, get_user_lang
		lang = await get_user_lang()
		t = get_translations(lang)
		project_name: str = t.get("crews_project_name", "Crews")
		list_name: str = t.get("crew_conversation_list", "Conversation")
		board_name = _crew_board_name(crew_id)

		date_fmt = await _get_user_date_format()
		try:
			tz = await _get_user_timezone()
			now_local = datetime.now(tz)
		except Exception:
			now_local = datetime.now(timezone.utc)

		# Build set of expected date strings for the last CONTEXT_DAYS days
		expected_dates = {
			(now_local - timedelta(days=i)).strftime(date_fmt)
			for i in range(CONTEXT_DAYS)
		}

		async with await _planka_client() as client:
			# Locate project
			resp = await client.get("/api/projects")
			resp.raise_for_status()
			project_id = next(
				(p["id"] for p in resp.json().get("items", [])
				 if (p.get("name") or "").lower() == project_name.lower()),
				None,
			)
			if not project_id:
				return ""

			# Locate board
			det = await client.get(f"/api/projects/{project_id}")
			det.raise_for_status()
			boards = det.json().get("included", {}).get("boards", [])
			board_id = next(
				(b["id"] for b in boards if (b.get("name") or "").lower() == board_name.lower()),
				None,
			)
			if not board_id:
				return ""

			# Locate conversation list
			bl = await client.get(f"/api/boards/{board_id}", params={"included": "lists"})
			bl.raise_for_status()
			lists = bl.json().get("included", {}).get("lists", []) or bl.json().get("lists", [])
			list_id = next(
				(lst["id"] for lst in lists if (lst.get("name") or "").lower() == list_name.lower()),
				None,
			)
			if not list_id:
				return ""

			# Fetch cards from board detail (Planka has no GET /api/lists/{id}/cards)
			bd = await client.get(f"/api/boards/{board_id}", params={"included": "lists,cards"})
			bd.raise_for_status()
			bd_data = bd.json()
			all_cards = bd_data.get("included", {}).get("cards", []) or bd_data.get("cards", [])
			cards = [c for c in all_cards if c.get("listId") == list_id]

		matching = [
			(c["name"], c.get("description", ""))
			for c in cards
			if c.get("name") in expected_dates and c.get("description", "").strip()
		]
		if not matching:
			return ""

		# Sort ascending so oldest is first (most recent last)
		matching.sort(key=lambda x: x[0])

		parts = [f"[{date}]\n{desc.strip()}" for date, desc in matching]
		full = "\n\n".join(parts)

		# Cap total context to MAX_CONTEXT_CHARS
		if len(full) > MAX_CONTEXT_CHARS:
			full = "[...older history omitted...]\n" + full[-MAX_CONTEXT_CHARS:]

		return f"CREW CONVERSATION HISTORY (last {CONTEXT_DAYS} days):\n{full}"
	except Exception as e:
		logger.warning("crew_memory: get_crew_memory_context failed: %s", e)
		return ""
