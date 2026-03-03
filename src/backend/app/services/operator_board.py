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
from app.services.planka import get_planka_auth_token
from app.services.translations import (
	get_planka_entity_names,
	get_all_values,
	get_done_keywords,
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
				resp = await client.get(f"/api/projects/{self._project_id}")
				if resp.status_code == 200:
					return self._project_id, self._board_id
			except Exception:
				pass
			# Cache stale -- fall through to search

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
			logger.info(f"Creating project {self.project_name}")
			try:
				resp = await client.post("/api/projects", json={"name": self.project_name, "type": "private"})
				resp.raise_for_status()
				project = resp.json()["item"]
			except Exception as e:
				logger.warning(f"Failed to create project with 'type', retrying with 'isPublic': {e}")
				resp = await client.post("/api/projects", json={"name": self.project_name, "isPublic": False})
				resp.raise_for_status()
				project = resp.json().get("item") or resp.json()
			
		# 2. Get/Create Board
		detail_resp = await client.get(f"/api/projects/{project['id']}")
		detail_resp.raise_for_status()
		detail = detail_resp.json()
		boards = detail.get("included", {}).get("boards", [])
		board = next((b for b in boards if b["name"] == self.board_name), None)
		
		if not board:
			logger.info(f"Creating board {self.board_name}")
			resp = await client.post(f"/api/projects/{project['id']}/boards", json={
				"name": self.board_name,
				"position": 65535
			})
			resp.raise_for_status()
			board = resp.json()["item"]
			
		# 3. Get/Create Lists
		board_detail_resp = await client.get(f"/api/boards/{board['id']}", params={"included": "lists"})
		board_detail_resp.raise_for_status()
		board_detail = board_detail_resp.json()
		current_lists = board_detail.get("included", {}).get("lists", [])
		list_names = [l["name"] for l in current_lists]
		
		for i, lname in enumerate(self.mandatory_lists):
			if lname not in list_names:
				logger.info(f"Creating list {lname}")
				await client.post(f"/api/boards/{board['id']}/lists", json={
					"name": lname,
					"type": "active",
					"position": (i + 1) * 65535
				})
				
		return project["id"], board["id"]

	async def sync_operator_tasks(self):
		"""
		Consolidates tasks from other boards into the Operator Board.
		"""
		try:
			async with await self._get_client() as client:
				target_project_id, target_board_id = await self.initialize_board(client)
				
				# Get target lists IDs
				board_detail = (await client.get(f"/api/boards/{target_board_id}", params={"included": "lists"})).json()
				target_lists = {l["name"]: l["id"] for l in board_detail.get("included", {}).get("lists", [])}
				
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
							# Only sync if not already synced or if we want to update (logic: simplified for now)
							# We check if it has the priority markers
							if "!!" in title:
								new_list_id = target_lists.get("Today")
							elif "!" in title:
								new_list_id = target_lists.get("This Week")
							elif "Inbox" in source_board_name:
								new_list_id = target_lists.get("Backlog")
								
							if new_list_id:
								# Prevent infinite loops by checking if the card is already in the target board
								if card["boardId"] == target_board_id:
									continue
									
								clean_name = title.replace("!!", "").replace("!", "").strip()
								new_name = f"[{source_board_name}] {clean_name}"
								
								logger.info(f"Moving card {title} to Operator Board")
								await client.patch(f"/api/cards/{card['id']}", json={
									"boardId": target_board_id,
									"listId": new_list_id,
									"name": new_name
								})
								moved_count += 1
				
				return f"Synchronized {moved_count} tasks to Operator Board."
		except Exception as e:
			logger.error(f"Sync failed: {e}")
			return f"Sync failed: {str(e)}"

# Singleton
operator_service = OperatorBoardService()
