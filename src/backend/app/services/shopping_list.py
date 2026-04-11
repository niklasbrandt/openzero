"""Nutrition Shopping List Service
----------------------------------
Maintains weekly shopping list cards in Planka:

  Project:  Crews
  Board:    Nutrition
  List:     Shopping List (positioned right after Conversation)
  Card:     "W{week_num} ({start_date} - {end_date})"
  Description: Accumulated shopping items, appended throughout the week.

When the user discusses meals or recipes, ingredients are automatically
appended to the current week's card. After the week rolls over, a new
card is created.

Public API:
  append_shopping_items(items_text: str)
      Appends ingredient items to the current week's shopping card.
"""
import logging
import re
from datetime import datetime, timedelta, timezone

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

MAX_DESC_CHARS = 8000
LIST_NAME_DEFAULT = "Shopping List"
LIST_I18N_KEY = "crew_shopping_list"


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


def _week_card_name(now: datetime) -> str:
	"""Build a card name like 'W15 (2026.04.07 - 2026.04.13)'."""
	iso_cal = now.isocalendar()
	week_num = iso_cal[1]
	# Monday of this week
	monday = now - timedelta(days=now.weekday())
	sunday = monday + timedelta(days=6)
	return f"W{week_num} ({monday.strftime('%Y.%m.%d')} - {sunday.strftime('%Y.%m.%d')})"


async def _planka_client():
	from app.services.planka_common import get_planka_auth_token
	token = await get_planka_auth_token()
	return httpx.AsyncClient(
		base_url=settings.PLANKA_BASE_URL,
		headers={"Authorization": f"Bearer {token}"},
		timeout=20.0,
	)


async def _find_nutrition_board(client: httpx.AsyncClient) -> tuple[str | None, str | None]:
	"""Return (board_id, shopping_list_id) for the Nutrition board in the Crews project."""
	try:
		from app.services.translations import get_translations, get_user_lang
		lang = await get_user_lang()
		t = get_translations(lang)
		project_name = t.get("crews_project_name", "Crews")
		list_name = t.get(LIST_I18N_KEY, LIST_NAME_DEFAULT)

		resp = await client.get("/api/projects")
		resp.raise_for_status()
		project_id = None
		for p in resp.json().get("items", []):
			if (p.get("name") or "").lower() == project_name.lower():
				project_id = p["id"]
				break
		if not project_id:
			return None, None

		det = await client.get(f"/api/projects/{project_id}")
		det.raise_for_status()
		board_id = None
		for b in det.json().get("included", {}).get("boards", []):
			if (b.get("name") or "").lower() == "nutrition":
				board_id = b["id"]
				break
		if not board_id:
			return None, None

		# Find the Shopping List
		b_detail = await client.get(f"/api/boards/{board_id}", params={"included": "lists"})
		b_detail.raise_for_status()
		lists = b_detail.json().get("included", {}).get("lists", [])
		list_id = None
		for lst in lists:
			if (lst.get("name") or "").lower() == list_name.lower():
				list_id = lst["id"]
				break

		# Auto-create the list if missing, positioned right after Conversation
		if not list_id:
			conv_name = t.get("crew_conversation_list", "Conversation")
			conv_pos = None
			next_pos = None
			sorted_lists = sorted(lists, key=lambda l: l.get("position") or 0)
			for i, lst in enumerate(sorted_lists):
				if (lst.get("name") or "").lower() == conv_name.lower():
					conv_pos = lst.get("position") or 0
					# Find the next list's position to place Shopping List in between
					if i + 1 < len(sorted_lists):
						next_pos = sorted_lists[i + 1].get("position") or 0
					break
			if conv_pos is not None:
				# Place halfway between Conversation and the next list
				pos = conv_pos + ((next_pos - conv_pos) / 2 if next_pos else 65536)
			else:
				pos = 65536  # fallback: end of board
			r = await client.post(f"/api/boards/{board_id}/lists", json={
				"name": list_name,
				"type": "active",
				"position": pos,
			})
			r.raise_for_status()
			list_id = (r.json().get("item") or r.json()).get("id")

		return board_id, list_id
	except Exception as e:
		logger.warning("shopping_list: _find_nutrition_board failed: %s", e)
		return None, None


async def _get_or_create_weekly_card(
	client: httpx.AsyncClient,
	board_id: str,
	list_id: str,
	card_name: str,
) -> tuple[str | None, str]:
	"""Return (card_id, current_description) for the current week's shopping card."""
	try:
		b_detail = await client.get(f"/api/boards/{board_id}", params={"included": "lists,cards"})
		b_detail.raise_for_status()
		cards = b_detail.json().get("included", {}).get("cards", [])
		for c in cards:
			if c.get("listId") == list_id and c.get("name") == card_name:
				return c["id"], c.get("description") or ""
		# Create new weekly card at position 1 (top of list)
		r = await client.post(f"/api/lists/{list_id}/cards", json={
			"name": card_name,
			"type": "project",
			"position": 1,
		})
		r.raise_for_status()
		item = r.json().get("item") or r.json()
		return item.get("id"), ""
	except Exception as e:
		logger.warning("shopping_list: _get_or_create_weekly_card failed: %s", e)
		return None, ""


# Matches a leading quantity like "360g", "120ml", "2x", "5 Stück"
_QTY_PREFIX = re.compile(
	r"^\d[\d.,]*\s*(?:g|kg|ml|l|cl|dl|x|st[üu]ck|pcs?|tbsp?|tsp?|el|tl|bunch|bund)?\s+",
	re.IGNORECASE,
)
# Detects an inline quantity that marks the start of a new item inside a long line
_INLINE_QTY = re.compile(
	r"(?<!\w)(\d[\d.,]*\s*(?:g|kg|ml|l|cl|dl|x|st[üu]ck|pcs?|tbsp?|tsp?|el|tl|bunch|bund)\s+)",
	re.IGNORECASE,
)


def _parse_raw_items(raw: str) -> list[str]:
	"""Normalise any raw items text into a clean list of non-empty item strings."""
	# Strip residual ACTION tag fragments
	text = re.sub(r"\[?ACTION:[^\]]*\]?", "", raw)
	# Replace literal \n sequences with real newlines
	text = text.replace("\\n", "\n")
	# Replace semicolons used as separators
	text = text.replace(";", "\n")

	lines: list[str] = []
	for raw_line in text.splitlines():
		line = raw_line.strip()
		if not line:
			continue
		# Skip timestamp markers and section headers / category labels
		if line.startswith("---") or line.startswith("[...") or line.startswith("Last updated"):
			continue
		# If a single line contains multiple quantity-prefixed items squashed together,
		# split them out (e.g. "1000g chicken 360g starch 60g cornflour")
		parts = _INLINE_QTY.split(line)
		if len(parts) > 2:
			# parts alternates: [leading_text, qty, ingredient, qty, ingredient, ...]
			rebuilt: list[str] = []
			i = 0
			# leading text before the first quantity (usually empty)
			if parts[0].strip():
				rebuilt.append(parts[0].strip())
			i = 1
			while i + 1 < len(parts):
				rebuilt.append((parts[i] + parts[i + 1]).strip())
				i += 2
			lines.extend(rebuilt)
		else:
			lines.append(line)

	return [l for l in lines if l]


def _item_key(item: str) -> str:
	"""Return a normalised dedup key for an item (quantity-agnostic, lowercase)."""
	key = _QTY_PREFIX.sub("", item).lower().strip()
	return key or item.lower().strip()


def _dedup(items: list[str]) -> list[str]:
	"""Deduplicate items, keeping the first occurrence of each ingredient key."""
	seen: dict[str, str] = {}
	for item in items:
		k = _item_key(item)
		if k not in seen:
			seen[k] = item
	return list(seen.values())


def _merge_items(current_desc: str, new_items: str, timestamp: str) -> str:
	"""Consolidate all shopping items into a single deduplicated, clean list."""
	existing = _parse_raw_items(current_desc)
	incoming = _parse_raw_items(new_items)

	if not incoming:
		return current_desc

	merged = _dedup(existing + incoming)

	header = f"Last updated: {timestamp}\n"
	body = "\n".join(merged)
	updated = header + body

	if len(updated) > MAX_DESC_CHARS:
		# Trim oldest items from the top of the body
		lines = merged[:]
		while lines and len(header + "\n".join(lines)) > MAX_DESC_CHARS:
			lines.pop(0)
		updated = header + "[...older items trimmed...]\n" + "\n".join(lines)

	return updated


async def append_shopping_items(items_text: str) -> bool:
	"""Append shopping items to the current week's card on Crews -> Nutrition -> Shopping List.

	Returns True on success, False on failure.
	"""
	if not items_text or not items_text.strip():
		return False

	try:
		tz = await _get_user_timezone()
		now_local = datetime.now(tz)
	except Exception:
		now_local = datetime.now(timezone.utc)

	card_name = _week_card_name(now_local)
	timestamp = now_local.strftime("%Y.%m.%d %H:%M")

	try:
		async with await _planka_client() as client:
			board_id, list_id = await _find_nutrition_board(client)
			if not board_id or not list_id:
				logger.warning("shopping_list: Nutrition board or Shopping List not found")
				return False

			card_id, current_desc = await _get_or_create_weekly_card(
				client, board_id, list_id, card_name
			)
			if not card_id:
				return False

			updated = _merge_items(current_desc, items_text, timestamp)
			r = await client.patch(f"/api/cards/{card_id}", json={"description": updated})
			r.raise_for_status()
			logger.info("shopping_list: appended items to %s", card_name)
			return True
	except Exception as e:
		logger.warning("shopping_list: append_shopping_items failed: %s", e)
		return False
