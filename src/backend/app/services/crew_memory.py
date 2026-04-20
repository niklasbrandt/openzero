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


# All known historical names for the conversation list across all languages and legacy variants.
# Used for name-based dedup when no persisted ID is available.
_CONVERSATION_LIST_LEGACY_NAMES: set[str] = {
	# EN
	"Conversation", "Conversations",
	# DE
	"Gespr\u00e4ch", "Konversation", "Unterhaltung",
	# ES
	"Conversaci\u00f3n",
	# FR (same as EN)
	# AR
	"\u0645\u062d\u0627\u062f\u062b\u0629",
	# JA
	"\u4f1a\u8a71",
	# ZH
	"\u5bf9\u8bdd",
	# HI
	"\u0935\u093e\u0930\u094d\u0924\u093e\u0932\u093e\u092a", "\u092c\u093e\u0924\u091a\u0940\u0924",
	# PT
	"Conversa",
	# KO
	"\ub300\ud654",
	# RU
	"\u0420\u0430\u0437\u0433\u043e\u0432\u043e\u0440",
}


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


async def _load_crew_list_id(crew_id: str, purpose: str) -> str | None:
	"""Load a persisted Planka list ID from the Preference table."""
	try:
		from app.models.db import AsyncSessionLocal, Preference
		from sqlalchemy import select
		key = f"crew_list_{crew_id}_{purpose}"
		async with AsyncSessionLocal() as session:
			res = await session.execute(select(Preference).where(Preference.key == key))
			pref = res.scalar_one_or_none()
			return pref.value if pref else None
	except Exception as e:
		logger.warning("crew_memory: could not load list ID for %s/%s: %s", crew_id, purpose, e)
		return None


async def _save_crew_list_id(crew_id: str, purpose: str, list_id: str) -> None:
	"""Persist a Planka list ID to the Preference table."""
	try:
		from app.models.db import AsyncSessionLocal, Preference
		from sqlalchemy import select
		key = f"crew_list_{crew_id}_{purpose}"
		async with AsyncSessionLocal() as session:
			res = await session.execute(select(Preference).where(Preference.key == key))
			pref = res.scalar_one_or_none()
			if pref:
				pref.value = list_id
			else:
				session.add(Preference(key=key, value=list_id))
			await session.commit()
		logger.info("crew_memory: persisted list ID crew_id=%s purpose=%s id=%s", crew_id, purpose, list_id)
	except Exception as e:
		logger.warning("crew_memory: could not persist list ID for %s/%s: %s", crew_id, purpose, e)


async def _get_or_create_conversation_list(
	client: httpx.AsyncClient,
	board_id: str,
	list_name: str,
	crew_id: str,
) -> str | None:
	"""Return list_id for the Conversation list on the board.

	Lookup strategy (mirrors OperatorBoardService list ID persistence):
	1. DB-persisted ID: validate against live board lists by ID.
	   If valid, rename to current-language name if it has drifted.
	2. Name-based dedup across all known language variants + legacy names.
	   Pick the list with the most cards (winner), delete empty duplicates,
	   rename winner to current language, persist winner's ID.
	3. Create a new list if nothing found, persist its ID.
	"""
	try:
		from app.services.translations import get_all_values
		all_conv_names: set[str] = get_all_values("crew_conversation_list") | _CONVERSATION_LIST_LEGACY_NAMES

		# Fetch lists + cards in one request (reused by all strategies)
		b_detail = await client.get(f"/api/boards/{board_id}", params={"included": "lists,cards"})
		b_detail.raise_for_status()
		b_data = b_detail.json()
		lists = b_data.get("included", {}).get("lists", []) or b_data.get("lists", [])
		cards = b_data.get("included", {}).get("cards", []) or []

		def _card_count(lst_id: str) -> int:
			return sum(1 for c in cards if c.get("listId") == lst_id)

		# --- Strategy 1: persisted ID ---
		persisted_id = await _load_crew_list_id(crew_id, "conversation")
		if persisted_id:
			matched = next((lst for lst in lists if lst["id"] == persisted_id), None)
			if matched:
				if matched.get("name") != list_name:
					r = await client.patch(f"/api/lists/{persisted_id}", json={"name": list_name})
					if r.status_code == 200:
						logger.info("crew_memory: renamed conversation list '%s' -> '%s' for crew '%s'",
									matched.get("name"), list_name, crew_id)
				return persisted_id
			logger.warning("crew_memory: persisted list ID %s not found on board %s — falling back to name search",
						   persisted_id, board_id)

		# --- Strategy 2: name-based dedup across all language variants ---
		candidates = [lst for lst in lists if (lst.get("name") or "") in all_conv_names]
		if candidates:
			winner = max(candidates, key=lambda lst: _card_count(lst["id"]))
			# Delete empty duplicates
			for lst in candidates:
				if lst["id"] == winner["id"]:
					continue
				if _card_count(lst["id"]) == 0:
					r = await client.delete(f"/api/lists/{lst['id']}")
					logger.info("crew_memory: deleted empty duplicate conversation list '%s' (id=%s) on board %s",
								lst.get("name"), lst["id"], board_id)
				else:
					logger.warning("crew_memory: non-empty duplicate conversation list '%s' (id=%s) — not auto-deleting",
								   lst.get("name"), lst["id"])
			# Rename winner to current language if needed
			if winner.get("name") != list_name:
				r = await client.patch(f"/api/lists/{winner['id']}", json={"name": list_name})
				if r.status_code == 200:
					logger.info("crew_memory: renamed conversation list '%s' -> '%s' for crew '%s'",
								winner.get("name"), list_name, crew_id)
			await _save_crew_list_id(crew_id, "conversation", winner["id"])
			return winner["id"]

		# --- Strategy 3: create new list ---
		r = await client.post(f"/api/boards/{board_id}/lists", json={
			"name": list_name,
			"type": "active",
			"position": 65535,
		})
		r.raise_for_status()
		data = r.json()
		item = data.get("item") or data
		new_id = item.get("id")
		if new_id:
			await _save_crew_list_id(crew_id, "conversation", new_id)
		return new_id
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
			list_id = await _get_or_create_conversation_list(client, board_id, list_name, crew_id)
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


MAX_BOARD_CONTEXT_CHARS = 2000


async def get_crew_board_work_context(crew_id: str) -> str:
	"""
	Read all non-Conversation lists from the crew's Planka board and return a
	formatted summary of their card names and descriptions.

	This is the primary reference for follow-up questions like "describe your
	last suggestion" or "what did we decide?" — the crew consults its own board
	history rather than the general Telegram conversation thread.

	Returns empty string if the board does not exist or on any error.
	"""
	try:
		from app.services.translations import get_translations, get_user_lang
		lang = await get_user_lang()
		t = get_translations(lang)
		project_name: str = t.get("crews_project_name", "Crews")
		conversation_list_name: str = t.get("crew_conversation_list", "Conversation")
		board_name = _crew_board_name(crew_id)

		async with await _planka_client() as client:
			resp = await client.get("/api/projects")
			resp.raise_for_status()
			project_id = next(
				(p["id"] for p in resp.json().get("items", [])
				 if (p.get("name") or "").lower() == project_name.lower()),
				None,
			)
			if not project_id:
				return ""

			det = await client.get(f"/api/projects/{project_id}")
			det.raise_for_status()
			boards = det.json().get("included", {}).get("boards", [])
			board_id = next(
				(b["id"] for b in boards if (b.get("name") or "").lower() == board_name.lower()),
				None,
			)
			if not board_id:
				return ""

			bd = await client.get(f"/api/boards/{board_id}", params={"included": "lists,cards"})
			bd.raise_for_status()
			bd_data = bd.json()
			lists = bd_data.get("included", {}).get("lists", []) or []
			cards = bd_data.get("included", {}).get("cards", []) or []

		from app.services.translations import get_all_values
		all_conv_names_lower = {n.lower() for n in (get_all_values("crew_conversation_list") | _CONVERSATION_LIST_LEGACY_NAMES)}
		work_lists = [
			lst for lst in lists
			if (lst.get("name") or "").lower() not in all_conv_names_lower
		]
		if not work_lists:
			return ""

		work_lists.sort(key=lambda x: x.get("position", 0))

		lines: list[str] = [
			f"CREW BOARD HISTORY — {board_name} "
			"(primary reference for past work, suggestions, and decisions — "
			"use this when the user asks about previous ideas or last suggestions):"
		]
		found_any = False
		for lst in work_lists:
			lst_cards = [c for c in cards if c.get("listId") == lst["id"]]
			if not lst_cards:
				continue
			found_any = True
			lst_cards.sort(key=lambda x: x.get("position", 0))
			lines.append(f"\n[{lst['name']}]")
			for c in lst_cards:
				card_line = f"  - {c['name']}"
				desc = (c.get("description") or "").strip()
				if desc:
					short_desc = desc[:300] + ("..." if len(desc) > 300 else "")
					card_line += f": {short_desc}"
				lines.append(card_line)

		if not found_any:
			return ""

		full = "\n".join(lines)
		if len(full) > MAX_BOARD_CONTEXT_CHARS:
			full = "[...earlier board entries omitted...]\n" + full[-MAX_BOARD_CONTEXT_CHARS:]
		return full
	except Exception as e:
		logger.warning("crew_memory: get_crew_board_work_context failed: %s", e)
		return ""


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

		from app.services.translations import get_all_values
		all_conv_names = get_all_values("crew_conversation_list") | _CONVERSATION_LIST_LEGACY_NAMES

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

			# Fetch board lists + cards in one request
			bd = await client.get(f"/api/boards/{board_id}", params={"included": "lists,cards"})
			bd.raise_for_status()
			bd_data = bd.json()
			all_lists = bd_data.get("included", {}).get("lists", []) or bd_data.get("lists", [])
			all_cards = bd_data.get("included", {}).get("cards", []) or bd_data.get("cards", [])

			# Locate conversation list: persisted ID first, then name-based across all variants
			list_id = await _load_crew_list_id(crew_id, "conversation")
			if list_id:
				if not any(lst["id"] == list_id for lst in all_lists):
					logger.warning("crew_memory: persisted list ID %s not found in board lists — falling back to name search", list_id)
					list_id = None
			if not list_id:
				matched = next((lst for lst in all_lists if (lst.get("name") or "") in all_conv_names), None)
				if matched:
					list_id = matched["id"]
			if not list_id:
				return ""

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
