"""
Operator Board Service (Mission Control)
----------------------------------------
This service implements the 'Master Priority' logic for the AI Operating System.
Instead of the user managing dozens of lists across disparate project boards, 
the Operator Board acts as a centralized 'Today' view.

The logic follows a 'High-Signal' pattern:
1. Every mission starts in its respective Project Board (e.g., 'Family', 'Career').
2. High-priority items marked with '!!' are 'lifted' into the 'Today' column of 
   the Operator Board.
3. Items marked with '!' are lifted into 'This Week'.
4. Cards appearing in any 'Inbox' board are automatically staged in the 
   Operator Backlog.

This allows Z to act as a true project manager, preparing the battlefield for 
the user every morning.
"""

import httpx
import logging
from app.config import settings
from app.services.translations import (
	get_planka_entity_names,
	get_all_values,
)

logger = logging.getLogger(__name__)

class OperatorBoardService:
	def __init__(self):
		self._lang = "en"
		self._apply_lang()
		self._token = None
		# Cached IDs so we can rename without searching by name
		self._project_id: str | None = None
		self._board_id: str | None = None
		self._list_ids: dict[str, str] = {}  # logical key -> planka id

	def _apply_lang(self):
		"""Refresh entity names from the translations module."""
		names = get_planka_entity_names(self._lang)
		self.project_name = names["project_name"]
		self.board_name = names["board_name"]
		self.mandatory_lists = [
			names["list_today"],
			names["list_this_week"],
			names["list_backlog"],
			names["list_done"],
		]
		# Map from logical key to current translated name (for sync)
		self._list_key_map = {
			"list_today": names["list_today"],
			"list_this_week": names["list_this_week"],
			"list_backlog": names["list_backlog"],
			"list_done": names["list_done"],
		}

	async def _get_auth_token(self) -> str:
		"""Retrieves or refreshes the authentication token using the central Planka service."""
		from app.services.planka import get_planka_auth_token
		if self._token:
			return self._token
		self._token = await get_planka_auth_token()
		return self._token

	async def _get_client(self):
		"""Returns a configured async client."""
		token = await self._get_auth_token()
		return httpx.AsyncClient(
			base_url=settings.PLANKA_BASE_URL, 
			timeout=10.0,
			headers={"Authorization": f"Bearer {token}"}
		)

	async def initialize_board(self, client: httpx.AsyncClient):
		"""Ensures the Operator Board and its lists exist. Returns (project_id, board_id)."""
		# If we already have cached IDs, verify they still exist
		if self._project_id and self._board_id:
			try:
				proj_resp = await client.get(f"/api/projects/{self._project_id}")
				board_resp = await client.get(f"/api/boards/{self._board_id}")
				if proj_resp.status_code == 200 and board_resp.status_code == 200:
					return self._project_id, self._board_id
				logger.debug("Planka cache stale (proj=%s board=%s), falling through to search",
							proj_resp.status_code, board_resp.status_code)
			except Exception:
				logger.debug("Planka cache validation failed, falling through to search")
			# Cache stale -- clear and fall through to search
			self._project_id = None
			self._board_id = None

		# 1. Get/Create Project -- match against ALL translated project names
		all_project_names = get_all_values("project_name")
		# Also match legacy names that may still exist
		all_project_names.update({"openZero", "Boards"})

		projects_resp = await client.get("/api/projects")
		projects = projects_resp.json().get("items", [])
		project = next(
			(p for p in projects if p["name"] in all_project_names),
			None,
		)
		
		if not project:
			logger.info("Creating project %s", self.project_name)
			try:
				resp = await client.post("/api/projects", json={"name": self.project_name, "type": "private"})
				resp.raise_for_status()
				project = resp.json()["item"]
			except Exception as e:
				logger.warning("Failed to create project with 'type', retrying with 'isPublic': %s", e)
				resp = await client.post("/api/projects", json={"name": self.project_name, "isPublic": False})
				resp.raise_for_status()
				project = resp.json().get("item") or resp.json()
			
		# 2. Get/Create Board
		detail_resp = await client.get(f"/api/projects/{project['id']}")
		detail_resp.raise_for_status()
		detail = detail_resp.json()
		boards = detail.get("included", {}).get("boards", [])
		all_board_names = get_all_values("board_name")
		all_board_names.add("Operator Board")  # legacy
		board = next((b for b in boards if b["name"] in all_board_names), None)
		
		if not board:
			logger.info("Creating board %s", self.board_name)
			resp = await client.post(f"/api/projects/{project['id']}/boards", json={
				"name": self.board_name,
				"position": 65535
			})
			resp.raise_for_status()
			board = resp.json()["item"]
			
		# 3. Get/Create Lists -- match any translated variant
		board_detail_resp = await client.get(f"/api/boards/{board['id']}", params={"included": "lists"})
		board_detail_resp.raise_for_status()
		board_detail = board_detail_resp.json()
		current_lists = board_detail.get("included", {}).get("lists", [])

		# Build sets for each logical list to match any language variant
		list_key_all = {
			"list_today": get_all_values("list_today"),
			"list_this_week": get_all_values("list_this_week"),
			"list_backlog": get_all_values("list_backlog"),
			"list_done": get_all_values("list_done"),
		}
		
		for key, translated_name in self._list_key_map.items():
			existing = next(
				(l for l in current_lists if l["name"] in list_key_all[key]),
				None,
			)
			if not existing:
				logger.info("Creating list %s", translated_name)
				pos = list(self._list_key_map.keys()).index(key)
				try:
					create_resp = await client.post(f"/api/boards/{board['id']}/lists", json={
						"name": translated_name,
						"type": "active",
						"position": (pos + 1) * 65535
					})
					if create_resp.status_code not in (200, 201):
						logger.warning("Failed to create list '%s': HTTP %s %s",
									translated_name, create_resp.status_code, create_resp.text[:200])
					else:
						logger.info("List '%s' created successfully.", translated_name)
				except Exception as _le:
					logger.warning("Exception creating list '%s': %s", translated_name, _le)

		# Cache IDs for fast lookup
		self._project_id = project["id"]
		self._board_id = board["id"]
				
		return project["id"], board["id"]

	async def sync_operator_tasks(self):
		"""
		Consolidates tasks from other boards into the Operator Board.
		"""
		try:
			async with await self._get_client() as client:
				target_project_id, target_board_id = await self.initialize_board(client)
				
				# Get target lists IDs -- build a logical-key lookup
				board_detail = (await client.get(f"/api/boards/{target_board_id}", params={"included": "lists"})).json()
				all_lists = board_detail.get("included", {}).get("lists", [])

				# Map logical key -> list id by matching any translated name
				list_key_all = {
					"list_today": get_all_values("list_today"),
					"list_this_week": get_all_values("list_this_week"),
					"list_backlog": get_all_values("list_backlog"),
					"list_done": get_all_values("list_done"),
				}
				target_list_by_key: dict[str, str] = {}
				for lst in all_lists:
					for key, variants in list_key_all.items():
						if lst["name"] in variants:
							target_list_by_key[key] = lst["id"]
							break

				# Also match inbox names from any language
				all_inbox_names = {name.lower() for name in get_all_values("list_inbox")}
				
				projects_resp = await client.get("/api/projects")
				all_projects = projects_resp.json().get("items", [])
				
				moved_count = 0
				
				for project in all_projects:
					if project["id"] == target_project_id:
						continue 
					
					p_detail = (await client.get(f"/api/projects/{project['id']}")).json()
					boards = p_detail.get("included", {}).get("boards", [])
					
					for board in boards:
						b_detail = (await client.get(f"/api/boards/{board['id']}", params={"included": "cards"})).json()
						cards = b_detail.get("included", {}).get("cards", [])
						
						for card in cards:
							source_board_name = board["name"]
							new_list_id = None
							
							title = card["name"]
							# Priority markers determine target list
							if "!!" in title:
								new_list_id = target_list_by_key.get("list_today")
							elif "!" in title:
								new_list_id = target_list_by_key.get("list_this_week")
							elif any(inbox in source_board_name.lower() for inbox in all_inbox_names):
								new_list_id = target_list_by_key.get("list_backlog")
								
							if new_list_id:
								# Prevent infinite loops by checking if the card is already in the target board
								if card["boardId"] == target_board_id:
									continue
									
								clean_name = title.replace("!!", "").replace("!", "").strip()
								new_name = f"[{source_board_name}] {clean_name}"
								
								logger.info("Moving card %s to Operator Board", title)
								await client.patch(f"/api/cards/{card['id']}", json={
									"boardId": target_board_id,
									"listId": new_list_id,
									"name": new_name
								})
								moved_count += 1
				
				return f"Synchronized {moved_count} tasks to Operator Board."
		except Exception as e:
			logger.error("Sync failed: %s", e)
			return "Sync failed."
	async def rename_planka_entities(self, old_lang: str, new_lang: str) -> str:
		"""Rename the Operations project, Operator Board, and its lists
		from old_lang names to new_lang names via Planka PATCH API."""
		if old_lang == new_lang:
			return "No language change."

		old_names = get_planka_entity_names(old_lang)
		new_names = get_planka_entity_names(new_lang)

		try:
			async with await self._get_client() as client:
				# Ensure board exists (also caches IDs)
				await self.initialize_board(client)

				if not self._project_id or not self._board_id:
					return "Could not find Operator project/board to rename."

				renamed = []

				# Rename project
				if old_names["project_name"] != new_names["project_name"]:
					resp = await client.patch(
						f"/api/projects/{self._project_id}",
						json={"name": new_names["project_name"]},
					)
					if resp.status_code == 200:
						renamed.append(f"Project -> {new_names['project_name']}")

				# Rename board
				if old_names["board_name"] != new_names["board_name"]:
					resp = await client.patch(
						f"/api/boards/{self._board_id}",
						json={"name": new_names["board_name"]},
					)
					if resp.status_code == 200:
						renamed.append(f"Board -> {new_names['board_name']}")

				# Rename lists
				board_detail = (await client.get(
					f"/api/boards/{self._board_id}",
					params={"included": "lists"},
				)).json()
				current_lists = board_detail.get("included", {}).get("lists", [])

				list_key_map = {
					"list_today": None,
					"list_this_week": None,
					"list_backlog": None,
					"list_done": None,
				}

				# Match existing lists by old-lang name OR any known variant
				for lst in current_lists:
					for key in list_key_map:
						all_variants = get_all_values(key)
						if lst["name"] in all_variants:
							list_key_map[key] = lst["id"]
							break

				for key, list_id in list_key_map.items():
					if not list_id:
						continue
					new_name = new_names[key]
					old_name = old_names[key]
					if old_name != new_name:
						resp = await client.patch(
							f"/api/lists/{list_id}",
							json={"name": new_name},
						)
						if resp.status_code == 200:
							renamed.append(f"List -> {new_name}")

				# Update internal language and re-apply names
				self._lang = new_lang
				self._apply_lang()

				# Invalidate tree cache so dashboard picks up new names
				from app.services.planka import _tree_cache
				_tree_cache.clear()

				if renamed:
					return f"Renamed: {', '.join(renamed)}"
				return "No entities needed renaming."
		except Exception as e:
			logger.error("Planka rename failed: %s", e)
			return "Rename failed."

# Singleton
operator_service = OperatorBoardService()
