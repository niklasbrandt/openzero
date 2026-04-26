"""Planka board-velocity adapter.

Snapshot schema (see §3.1 of ambient_intelligence.md):
{
    "in_progress": [{"name": str, "board": str, "days_active": int}],
    "stalled":     [{"name": str, "board": str, "last_activity": str}],
    "blocked":     [{"name": str, "board": str}],
    "completed_24h": int,
    "wip_violations": [{"board": str, "list": str, "count": int}],
    "today_count": int,      # cards on Operator Board Today list
    "this_week_count": int,  # cards on Operator Board This Week list
}

"Stalled" = incomplete card not updated for >= 4 days (stall threshold from §6.1).
The threshold is intentionally lower than get_activity_report's 7-day threshold
so that rule_card_stall has room for early warning.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

_STALL_DAYS = 4
_IP_KEYWORDS = {"in progress", "doing", "active", "today", "im gang", "en curso"}
_WIP_LIMIT = 3


class PlankaAdapter:
	source_id = "planka"
	poll_interval_s = 300  # 5 minutes

	async def snapshot(self) -> dict:
		try:
			return await _fetch_planka_snapshot()
		except Exception as exc:
			logger.warning("PlankaAdapter.snapshot failed: %s", exc)
			return {
				"in_progress": [],
				"stalled": [],
				"blocked": [],
				"completed_24h": 0,
				"wip_violations": [],
				"today_count": 0,
				"this_week_count": 0,
				"error": str(exc),
			}


async def _fetch_planka_snapshot() -> dict:
	import httpx
	from app.config import settings
	from app.services.planka_common import get_planka_auth_token
	from app.services.translations import get_done_keywords

	cutoff_24h = datetime.now() - timedelta(hours=24)
	stall_threshold = datetime.now() - timedelta(days=_STALL_DAYS)
	done_kw = get_done_keywords()

	token = await get_planka_auth_token()
	headers = {"Authorization": f"Bearer {token}"}

	in_progress: list[dict] = []
	stalled: list[dict] = []
	blocked: list[dict] = []
	wip_violations: list[dict] = []
	completed_24h = 0
	today_count = 0
	this_week_count = 0

	async with httpx.AsyncClient(
		base_url=settings.PLANKA_BASE_URL, timeout=20.0, headers=headers
	) as client:
		resp = await client.get("/api/projects")
		resp.raise_for_status()
		projects = resp.json().get("items", [])

		if not projects:
			return _empty_snapshot()

		project_resps = await asyncio.gather(
			*[client.get(f"/api/projects/{p['id']}") for p in projects],
			return_exceptions=True,
		)

		board_tasks = []
		board_names: list[str] = []
		for r in project_resps:
			if isinstance(r, Exception):
				continue
			boards = r.json().get("included", {}).get("boards", [])
			for b in boards:
				board_tasks.append(
					client.get(
						f"/api/boards/{b['id']}",
						params={"included": "lists,cards,labels,cardLabels"},
					)
				)
				board_names.append(b["name"])

		board_resps = await asyncio.gather(*board_tasks, return_exceptions=True)

	for b_idx, b_resp in enumerate(board_resps):
		if isinstance(b_resp, Exception):
			continue
		b_name = board_names[b_idx]
		b_data = b_resp.json()
		lists = b_data.get("included", {}).get("lists", []) or []
		cards = b_data.get("included", {}).get("cards", []) or []
		labels = b_data.get("included", {}).get("labels", []) or []
		card_labels_raw = b_data.get("included", {}).get("cardLabels", []) or []

		label_map = {lbl["id"]: lbl for lbl in labels}
		card_to_labels: dict[str, list] = {}
		for cl in card_labels_raw:
			cid, lid = cl["cardId"], cl["labelId"]
			card_to_labels.setdefault(cid, [])
			if lid in label_map:
				card_to_labels[cid].append(label_map[lid])

		done_list_ids = {
			lst["id"] for lst in lists
			if lst.get("name") and lst["name"].lower() in done_kw
		}
		ip_list_ids = {
			lst["id"] for lst in lists
			if lst.get("name") and lst["name"].lower() in _IP_KEYWORDS
		}
		today_list_ids = {
			lst["id"] for lst in lists
			if lst.get("name") and lst["name"].lower() == "today"
		}
		week_list_ids = {
			lst["id"] for lst in lists
			if lst.get("name") and lst["name"].lower() in {"this week", "week"}
		}

		for lst in lists:
			lst_cards = [c for c in cards if c["listId"] == lst["id"]]
			if lst["id"] in ip_list_ids and len(lst_cards) > _WIP_LIMIT:
				wip_violations.append({
					"board": b_name,
					"list": lst["name"],
					"count": len(lst_cards),
				})

		for card in cards:
			try:
				updated_raw = card.get("updatedAt") or card.get("createdAt", "")
				updated = datetime.fromisoformat(updated_raw.replace("Z", ""))
			except (ValueError, AttributeError):
				updated = datetime.now()

			c_name = card["name"]
			c_labels = card_to_labels.get(card["id"], [])
			c_label_names = {lbl["name"].lower() for lbl in c_labels}
			is_done = card["listId"] in done_list_ids
			is_ip = card["listId"] in ip_list_ids
			is_blocked = "blocked" in c_label_names or "block" in c_name.lower()

			if is_done:
				if updated > cutoff_24h:
					completed_24h += 1
			elif is_blocked:
				blocked.append({"name": c_name, "board": b_name})
			elif is_ip:
				days_active = (datetime.now() - updated).days
				in_progress.append({"name": c_name, "board": b_name, "days_active": days_active})
			elif updated < stall_threshold:
				stalled.append({
					"name": c_name,
					"board": b_name,
					"last_activity": updated.strftime("%Y-%m-%d"),
				})

			if card["listId"] in today_list_ids:
				today_count += 1
			if card["listId"] in week_list_ids:
				this_week_count += 1

	return {
		"in_progress": in_progress,
		"stalled": stalled,
		"blocked": blocked,
		"completed_24h": completed_24h,
		"wip_violations": wip_violations,
		"today_count": today_count,
		"this_week_count": this_week_count,
	}


def _empty_snapshot() -> dict:
	return {
		"in_progress": [],
		"stalled": [],
		"blocked": [],
		"completed_24h": 0,
		"wip_violations": [],
		"today_count": 0,
		"this_week_count": 0,
	}
