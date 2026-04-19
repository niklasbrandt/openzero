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
from typing import Optional
from app.config import settings
from app.services.translations import (
	get_planka_entity_names,
	get_all_values,
)

logger = logging.getLogger(__name__)

class OperatorBoardService:
	def __init__(self) -> None:
		self._lang = "en"
		self._apply_lang()
		self._token: Optional[str] = None
		# Cached IDs so we can rename without searching by name
		self._project_id: str | None = None
		self._board_id: str | None = None
		self._list_ids: dict[str, str] = {}  # logical key -> planka id
		# Guard: only load from DB once per process lifetime
		self._db_ids_loaded: bool = False

	def _apply_lang(self) -> None:
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
		from app.services.planka_common import get_planka_auth_token
		if self._token:
			return self._token
		self._token = await get_planka_auth_token()
		return self._token

	async def _get_client(self) -> httpx.AsyncClient:
		"""Returns a configured async client."""
		token = await self._get_auth_token()
		return httpx.AsyncClient(
			base_url=settings.PLANKA_BASE_URL, 
			timeout=10.0,
			headers={"Authorization": f"Bearer {token}"}
		)

	async def _load_persisted_ids(self) -> None:
		"""Load operator project/board IDs from the Preference table into memory."""
		try:
			from app.models.db import AsyncSessionLocal, Preference
			from sqlalchemy import select
			async with AsyncSessionLocal() as session:
				res = await session.execute(
					select(Preference).where(Preference.key.in_(["operator_project_id", "operator_board_id"]))
				)
				rows = {r.key: r.value for r in res.scalars().all()}
				self._project_id = rows.get("operator_project_id")
				self._board_id = rows.get("operator_board_id")
				if self._project_id and self._board_id:
					logger.info("Loaded persisted operator board IDs from DB (proj=%s board=%s)",
								self._project_id, self._board_id)
		except Exception as e:
			logger.warning("Could not load persisted operator IDs from DB: %s", e)

	async def _save_persisted_ids(self, project_id: str, board_id: str) -> None:
		"""Upsert operator project/board IDs into the Preference table."""
		try:
			from app.models.db import AsyncSessionLocal, Preference
			from sqlalchemy import select
			async with AsyncSessionLocal() as session:
				for key, value in [("operator_project_id", project_id), ("operator_board_id", board_id)]:
					res = await session.execute(select(Preference).where(Preference.key == key))
					pref = res.scalar_one_or_none()
					if pref:
						pref.value = value
					else:
						session.add(Preference(key=key, value=value))
				await session.commit()
				logger.info("Persisted operator board IDs to DB (proj=%s board=%s)", project_id, board_id)
		except Exception as e:
			logger.warning("Could not persist operator IDs to DB: %s", e)

	async def initialize_board(self, client: httpx.AsyncClient):
		"""Ensures the Operator Board and its lists exist. Returns (project_id, board_id).

		Lookup strategy (in order of precedence):
		  1. In-memory cache (fastest path, cleared on stale).
		  2. DB-persisted IDs — loaded on first call. Verified against Planka by ID.
		     If IDs are valid, rename project/board to the current language rather than
		     creating new entities. This prevents duplicates on language change.
		  3. Name-based search across all translated variants (fallback for first run or
		     after an entity is manually deleted in Planka). New IDs are persisted to DB.
		"""
		# 0. One-time DB load — also refreshes in-memory language from identity profile
		if not self._db_ids_loaded:
			await self._load_persisted_ids()
			from app.services.translations import get_user_lang
			lang = await get_user_lang()
			if lang != self._lang:
				self._lang = lang
				self._apply_lang()
			self._db_ids_loaded = True

		# 1. If we have IDs (from DB or in-memory cache), validate + rename in Planka
		if self._project_id and self._board_id:
			try:
				proj_resp = await client.get(f"/api/projects/{self._project_id}")
				board_resp = await client.get(f"/api/boards/{self._board_id}")
				if proj_resp.status_code == 200 and board_resp.status_code == 200:
					# Rename to current language names if Planka has a stale/different name
					proj_data = proj_resp.json().get("item", {})
					board_data = board_resp.json().get("item", {})
					if proj_data.get("name") != self.project_name:
						r = await client.patch(
							f"/api/projects/{self._project_id}",
							json={"name": self.project_name},
						)
						if r.status_code == 200:
							logger.info("Renamed operator project '%s' -> '%s'",
										proj_data.get("name"), self.project_name)
					if board_data.get("name") != self.board_name:
						r = await client.patch(
							f"/api/boards/{self._board_id}",
							json={"name": self.board_name},
						)
						if r.status_code == 200:
							logger.info("Renamed operator board '%s' -> '%s'",
										board_data.get("name"), self.board_name)
					# Ensure all required lists exist (creates missing ones, does not rename)
					await self._ensure_lists(client)
					return self._project_id, self._board_id
				logger.warning(
					"Persisted operator IDs no longer valid in Planka (proj=%s board=%s) — "
					"falling back to name search",
					proj_resp.status_code, board_resp.status_code,
				)
			except Exception as e:
				logger.warning("Planka ID validation failed (%s) — falling back to name search", e)
			# Stale — clear and fall through to name search + creation
			self._project_id = None
			self._board_id = None

		# 2. Name-based fallback: search ALL translated variants to avoid creating duplicates
		# 2a. Get/Create Project
		all_project_names = get_all_values("project_name")
		# Legacy/placeholder names that have ever been used in Planka (including bad-translation artifacts)
		all_project_names.update({
			# English
			"Operations", "openZero", "Boards",
			# German
			"Projektname", "Operationen",
			# Spanish
			"Operaciones",
			# French
			"Opérations",
			# Arabic
			"العمليات",
			# Japanese
			"オペレーション",
			# Chinese
			"运营",
			# Hindi
			"संचालन",
			# Portuguese
			"Operações",
			# Korean
			"운영",
			# Russian
			"Операции",
		})

		projects_resp = await client.get("/api/projects")
		projects = projects_resp.json().get("items", [])
		matching_projects = [p for p in projects if p["name"] in all_project_names]

		if len(matching_projects) > 1:
			# One-time startup cleanup: multiple operator projects found — keep the one with real content
			project = await self._resolve_duplicate_projects(client, matching_projects)
		elif matching_projects:
			project = matching_projects[0]
		else:
			project = None

		# Rename to current language immediately — don't wait for next startup cycle
		if project and project["name"] != self.project_name:
			r = await client.patch(
				f"/api/projects/{project['id']}",
				json={"name": self.project_name},
			)
			if r.status_code == 200:
				logger.info("Renamed operator project '%s' -> '%s'",
							project["name"], self.project_name)
				project = r.json().get("item", project)

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
			
		# 2b. Get/Create Board
		detail_resp = await client.get(f"/api/projects/{project['id']}")
		detail_resp.raise_for_status()
		detail = detail_resp.json()
		boards = detail.get("included", {}).get("boards", [])
		all_board_names = get_all_values("board_name")
		all_board_names.update({  # legacy + placeholder artifacts across all languages
			# English
			"Operator Board", "Operations",
			# German
			"Boardname", "Operator-Board",
			# Spanish
			"Tablero de Operaciones",
			# French
			"Tableau de Bord",
			# Arabic
			"لوحة العمليات",
			# Japanese
			"オペレーターボード",
			# Chinese
			"操作员看板",
			# Hindi
			"ऑपरेटर बोर्ड",
			# Portuguese
			"Painel de Operações",
			# Korean
			"운영자 보드",
			# Russian
			"Доска оператора",
		})
		board = next((b for b in boards if b["name"] in all_board_names), None)

		# Rename to current language immediately
		if board and board["name"] != self.board_name:
			r = await client.patch(
				f"/api/boards/{board['id']}",
				json={"name": self.board_name},
			)
			if r.status_code == 200:
				logger.info("Renamed operator board '%s' -> '%s'",
							board["name"], self.board_name)
				board = r.json().get("item", board)

		if not board:
			logger.info("Creating board %s", self.board_name)
			resp = await client.post(f"/api/projects/{project['id']}/boards", json={
				"name": self.board_name,
				"position": 65535
			})
			resp.raise_for_status()
			board = resp.json()["item"]

		# 2c. Ensure all required lists exist
		self._project_id = project["id"]
		self._board_id = board["id"]
		await self._ensure_lists(client)

		# Persist IDs to DB so future restarts do not need name-based lookup
		await self._save_persisted_ids(project["id"], board["id"])

		return project["id"], board["id"]

	async def _resolve_duplicate_projects(
		self, client: httpx.AsyncClient, candidates: list[dict]
	) -> dict:
		"""Called when multiple Planka projects match a known operator project name.

		Counts total cards in each candidate.  Deletes any project with zero cards.
		Keeps and returns the project with the most content.  If two projects share
		the same non-zero card count, logs a warning and keeps the first one found.
		"""
		async def _count_cards(proj: dict) -> int:
			try:
				detail = (await client.get(f"/api/projects/{proj['id']}")).json()
				boards = detail.get("included", {}).get("boards", [])
				total = 0
				for board in boards:
					b_detail = (
						await client.get(
							f"/api/boards/{board['id']}",
							params={"included": "cards"},
						)
					).json()
					total += len(b_detail.get("included", {}).get("cards", []))
				return total
			except Exception as _ce:
				logger.warning("Could not count cards for project %s: %s", proj["id"], _ce)
				return 0

		card_counts = {p["id"]: await _count_cards(p) for p in candidates}
		for p in candidates:
			logger.info(
				"Operator project candidate '%s' (id=%s): %d cards",
				p["name"], p["id"], card_counts[p["id"]],
			)

		best = max(candidates, key=lambda p: card_counts[p["id"]])
		best_count = card_counts[best["id"]]

		# Warn if multiple candidates tie on content
		ties = [p for p in candidates if card_counts[p["id"]] == best_count and p["id"] != best["id"]]
		if ties:
			logger.warning(
				"Multiple operator project candidates share the highest card count (%d). "
				"Keeping '%s' (id=%s). Manual review may be needed.",
				best_count, best["name"], best["id"],
			)

		# Delete empty duplicates; leave non-empty ones for manual review
		for p in candidates:
			if p["id"] == best["id"]:
				continue
			if card_counts[p["id"]] == 0:
				try:
					# Planka requires all boards to be deleted before a project can be deleted (HTTP 422 otherwise)
					proj_detail = (await client.get(f"/api/projects/{p['id']}")).json()
					for board in proj_detail.get("included", {}).get("boards", []):
						br = await client.delete(f"/api/boards/{board['id']}")
						logger.info("Deleted board '%s' (id=%s) from duplicate project", board.get("name"), board["id"])
					r = await client.delete(f"/api/projects/{p['id']}")
					if r.status_code in (200, 204):
						logger.info(
							"Deleted empty duplicate operator project '%s' (id=%s)",
							p["name"], p["id"],
						)
					else:
						logger.warning(
							"Could not delete duplicate operator project '%s' (id=%s): HTTP %s",
							p["name"], p["id"], r.status_code,
						)
				except Exception as _de:
					logger.warning(
						"Exception deleting duplicate operator project '%s': %s",
						p["name"], _de,
					)
			else:
				logger.warning(
					"Duplicate operator project '%s' (id=%s) has %d cards — NOT auto-deleting. "
					"Manual cleanup required.",
					p["name"], p["id"], card_counts[p["id"]],
				)

		return best

	async def _ensure_lists(self, client: httpx.AsyncClient) -> None:
		"""Create any missing Operator Board lists. Does not rename existing lists."""
		board_detail_resp = await client.get(f"/api/boards/{self._board_id}", params={"included": "lists"})
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
				(lst for lst in current_lists if lst["name"] in list_key_all[key]),
				None,
			)
			if not existing:
				logger.info("Creating list %s", translated_name)
				pos = list(self._list_key_map.keys()).index(key)
				try:
					create_resp = await client.post(f"/api/boards/{self._board_id}/lists", json={
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

	async def sync_operator_tasks(self) -> str:
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
				from app.services.planka_common import clear_tree_cache
				clear_tree_cache()

				if renamed:
					return f"Renamed: {', '.join(renamed)}"
				return "No entities needed renaming."
		except Exception as e:
			logger.error("Planka rename failed: %s", e)
			return "Rename failed."

# Singleton
operator_service = OperatorBoardService()
