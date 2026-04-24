"""
Planka Integration Service
--------------------------
This service provides the low-level bridge between the openZero backend and the
Planka Kanban instance. It handles API communication for project tree fetching
and task creation.

Key Responsibilities:
- Fetching board/project hierarchies for the Dashboard UI.
- Creating tasks (cards) in response to LLM or user actions.
- Ensuring robust connection handling across different environments.
"""

import html as _html
import httpx
import logging
import re
from datetime import datetime, timedelta
from typing import Optional, Any
from app.config import settings

logger = logging.getLogger(__name__)

from app.services.planka_common import get_planka_auth_token, _tree_cache
import asyncio
import time

def _sanitize_for_log(text: Any) -> str:
	"""Built-in sanitizer for CodeQL Log Injection (CWE-117)."""
	val = str(text)[:255]
	# re.escape is a built-in sanitizer that escapes all special characters
	return re.escape(val)

async def get_project_tree(as_html: bool = True) -> str:
	"""Recursively build a semantic text tree. Uses parallel requests and caching for speed."""
	cache_key = f"tree_{as_html}"
	if cache_key in _tree_cache:
		timestamp, data = _tree_cache[cache_key]
		if time.time() - timestamp < 60: # 1 minute TTL
			return data

	try:
		token = await get_planka_auth_token()
		headers = {"Authorization": f"Bearer {token}"}

		async with httpx.AsyncClient(base_url=settings.PLANKA_BASE_URL, timeout=15.0, headers=headers) as client:
			resp = await client.get("/api/projects")
			resp.raise_for_status()
			projects = resp.json().get("items", [])

			if not projects:
				return "No active projects found."

			# Fetch all project details in parallel
			project_tasks = [client.get(f"/api/projects/{p['id']}") for p in projects]
			project_resps = await asyncio.gather(*project_tasks)

			tree_lines = []
			board_tasks = []
			board_metadata = [] # Keep track of which board task belongs to which project/name

			for i, p_resp in enumerate(project_resps):
				p_resp.raise_for_status()
				detail = p_resp.json()
				boards = detail.get("included", {}).get("boards", [])

				project = projects[i]
				project_id = project['id']

				project_name = project['name']

				# Make project names clickable
				if as_html:
					p_display = f"<b><a href='/api/dashboard/planka-redirect?target_project_id={project_id}' target='_blank' style='color: inherit; text-decoration: none;'>{_html.escape(project_name)}</a></b>"
				else:
					# Use version without underscores for Telegram Markdown
					p_display = f"**[{project_name}]({settings.BASE_URL}/api/dashboard/planka-redirect?targetprojectid={project_id})**"

				tree_lines.append((i, "project", p_display))

				for board in boards:
					# Include labels and cardLabels for class-of-service/blocker detection
					task = client.get(f"/api/boards/{board['id']}", params={"included": "lists,cards,labels,cardLabels"})
					board_tasks.append(task)
					board_metadata.append({"project_idx": i, "name": board['name'], "id": board['id']})

			# Fetch all board details in parallel
			board_resps = await asyncio.gather(*board_tasks, return_exceptions=True)

			# Map board responses back to their projects
			project_boards: dict[int, list[str]] = {i: [] for i in range(len(projects))}
			for meta, b_resp in zip(board_metadata, board_resps):
				if isinstance(b_resp, BaseException):
					project_boards[meta["project_idx"]].append(f"  └── {meta['name']} (Stats offline)")
					continue

				b_detail = b_resp.json()
				lists = b_detail.get("included", {}).get("lists", [])
				cards = b_detail.get("included", {}).get("cards", [])

				total_cards = len(cards)
				from app.services.translations import get_done_keywords
				_done_kw = get_done_keywords()
				done_list_ids = [l['id'] for l in lists if l.get('name') and l['name'].lower() in _done_kw]
				done_cards = len([c for c in cards if c['listId'] in done_list_ids])

				progress_pct = int((done_cards / total_cards) * 100) if total_cards > 0 else 0
				board_id = meta["id"]
				board_name = meta["name"]

				if as_html:
					progress_str = f" <span style='color: #4ade80; font-size: 0.8rem;'>({progress_pct}%)</span>" if total_cards > 0 else ""
					line = f"  └── <a href='/api/dashboard/planka-redirect?target_board_id={board_id}' target='_blank' style='color: inherit; text-decoration: none;'>{_html.escape(board_name)}</a>{progress_str}"
				else:
					progress_str = f" ({progress_pct}%)" if total_cards > 0 else ""
					# Use version without underscores for Telegram Markdown
					line = f" • [{board_name}]({settings.BASE_URL}/api/dashboard/planka-redirect?targetboardid={board_id}){progress_str}"

				project_boards[meta["project_idx"]].append(line)

			# Assemble final tree
			final_lines = []
			for i, p_type, p_name in tree_lines:
				final_lines.append(p_name)
				final_lines.extend(project_boards[i])
				final_lines.append("")

			result = "\n".join(final_lines)
			_tree_cache[cache_key] = (time.time(), result)
			return result
	except Exception as e:
		logger.error("Planka project tree error: %s", _sanitize_for_log(e))
		return "Planka connection issue."

async def create_task(board_name: str, list_name: str, title: str, description: str = "") -> Optional[str]:
	"""Creates a card on the specified board and list.

	Returns the human-readable path "ProjectName → BoardName → ListName" on success,
	or None on failure, so callers can surface WHERE the card landed.
	"""
	# Clean LLM inputs (sometimes they pass literal quotes like '"Test Board"')
	board_name = (board_name or "Operator Board").strip().strip('"\'')
	list_name = (list_name or "Inbox").strip().strip('"\'')
	title = (title or "New Task").strip().strip('"\'')

	# Detect PII-sanitization token leakage (e.g. board_name='[ORG_1] Board' when the
	# cloud sanitizer mangled the operator board directive before it reached the LLM).
	# Any board name that still contains a [CATEGORY_N] placeholder is unrehydrated;
	# fall back to Operator Board rather than creating a card on the wrong board.
	if re.search(r'\[[A-Z]+_\d+\]', board_name):
		logger.warning(
			"create_task: board_name '%s' contains a sanitization token — defaulting to Operator Board",
			board_name,
		)
		board_name = "Operator Board"

	# Normalize any translated project/board name variant to operator board
	from app.services.translations import get_all_values
	all_project_names = get_all_values("project_name")
	all_project_names.update({"openZero", "Boards"})  # legacy names
	all_board_names = get_all_values("board_name")
	all_board_names.add("Operator Board")

	if board_name in all_project_names or board_name.lower() in {n.lower() for n in all_project_names}:
		board_name = "Operator Board"
	if board_name.lower() in {n.lower() for n in all_board_names}:
		board_name = "Operator Board"

		logger.info("create_task requested -> Board: %s, List: %s, Title: %s", _sanitize_for_log(board_name), _sanitize_for_log(list_name), _sanitize_for_log(title))
	try:
		from app.services.operator_board import operator_service
		token = await get_planka_auth_token()
		headers = {"Authorization": f"Bearer {token}"}

		async with httpx.AsyncClient(base_url=settings.PLANKA_BASE_URL, timeout=10.0, headers=headers) as client:
			# 1. SPECIAL CASE: Operator Board
			target_board = None
			if board_name.lower() == "operator board":
				logger.info("Targeting Operator Board, ensuring initialization...")
				_, b_id = await operator_service.initialize_board(client)
				target_board = {"id": b_id, "name": "Operator Board"}
			else:
				# General Search across all projects
				projects_resp = await client.get("/api/projects")
				projects = projects_resp.json().get("items", [])
				for p in projects:
					p_det_resp = await client.get(f"/api/projects/{p['id']}")
					p_det = p_det_resp.json()
					# Boards might be in 'included' or 'boards' key depending on version/sideloading
					boards = p_det.get("included", {}).get("boards", []) or p_det.get("boards", [])
					match = next((b for b in boards if (b.get("name") or "").lower() == board_name.lower()), None)
					if match:
						target_board = match
						break

			if not target_board:
				logger.debug("Board %s not found. Defaulting to Operator Board.", _sanitize_for_log(board_name))
				_, b_id = await operator_service.initialize_board(client)
				target_board = {"id": b_id, "name": "Operator Board"}

			# 2. Find List
			board_id = target_board["id"]
			b_detail_resp = await client.get(f"/api/boards/{board_id}", params={"included": "lists"})
			b_detail_resp.raise_for_status()
			b_detail = b_detail_resp.json()
			lists = b_detail.get("included", {}).get("lists", []) or b_detail.get("lists", [])
			target_list = next((l for l in lists if (l.get("name") or "").lower() == list_name.lower()), None)

			if not target_list:
				# Fall back to first active named list — never use archive/trash lists (cards would be invisible).
				active_lists = [l for l in lists if l.get("type") == "active" and (l.get("name") or "").strip()]
				if active_lists:
					target_list = active_lists[0]
					logger.info("create_task: list '%s' not found on board '%s', falling back to '%s'", _sanitize_for_log(list_name), _sanitize_for_log(target_board["name"]), _sanitize_for_log(target_list.get("name")))
				else:
					l_resp = await client.post(f"/api/boards/{board_id}/lists", json={"name": "Inbox", "type": "active", "position": 65535})
					l_resp.raise_for_status()
					target_list = l_resp.json().get("item")

			if not target_list:
				raise ValueError(f"List '{list_name}' not found and could not be created on board '{target_board['name']}'")

			# 3. Create Card
			# Planka v2: "type" is required (whitelist: project, story).
			# Empty description is rejected — omit the field when blank.
			card_payload: dict = {"name": title, "type": "project", "position": 65535}
			if description:
				card_payload["description"] = description
			res = await client.post(f"/api/lists/{target_list['id']}/cards", json=card_payload)
			res.raise_for_status()
			# Resolve the project name for the path string
			project_name = "Operations"
			try:
				from app.services.operator_board import operator_service
				project_name = operator_service.project_name
			except Exception:
				logger.debug("create_task: operator_service not ready, using default project name")
			path = f"{project_name} → {target_board['name']} → {target_list['name']}"
			logger.info("Card created successfully: %s", path)
			return path
	except Exception as e:
		logger.warning("create_task failed: %s", _sanitize_for_log(e))
		return None

async def archive_card(card_title_fragment: str, board_name: str = "") -> bool:
	"""Move a Planka card to the 'Archive' list instead of deleting it.
	Creates the Archive list on the board if it does not already exist.
	"""
	try:
		token = await get_planka_auth_token()
		headers = {"Authorization": f"Bearer {token}"}
		async with httpx.AsyncClient(base_url=settings.PLANKA_BASE_URL, headers=headers, timeout=15.0) as client:
			projects_resp = await client.get("/api/projects")
			projects_resp.raise_for_status()
			projects = projects_resp.json().get("items", [])

			for p in projects:
				det = await client.get(f"/api/projects/{p['id']}")
				boards = det.json().get("included", {}).get("boards", [])
				for b in boards:
					if board_name and b["name"].lower() != board_name.lower():
						continue
					bd = await client.get(f"/api/boards/{b['id']}", params={"included": "lists,cards"})
					bdata = bd.json()
					cards = bdata.get("included", {}).get("cards", [])
					lists = bdata.get("included", {}).get("lists", [])
					card = next(
						(c for c in cards if card_title_fragment.lower() in (c.get("name") or "").lower()),
						None,
					)
					if not card:
						continue
					# Find or create Archive list
					archive_list = next((l for l in lists if l.get("name", "").lower() == "archive"), None)
					if not archive_list:
						max_pos = max((l.get("position", 0) for l in lists), default=0)
						r = await client.post(
							f"/api/boards/{b['id']}/lists",
							json={"name": "Archive", "type": "closed", "position": max_pos + 65535},
						)
						r.raise_for_status()
						archive_list = r.json().get("item")
					if not archive_list:
						return False
					# Move card to Archive list
					move_resp = await client.patch(
						f"/api/cards/{card['id']}",
						json={"listId": archive_list["id"], "position": 65535},
					)
					if move_resp.status_code == 200:
						logger.debug("archive_card: moved '%s' to Archive on board '%s'", card_title_fragment, b["name"])
						return True
			return False
	except Exception as e:
		logger.warning("archive_card failed: %s", _sanitize_for_log(e))
		return False


async def create_project(name: str, description: str = "") -> dict:
	"""Create a new project in Planka. Returns existing project if name matches (idempotent)."""
	token = await get_planka_auth_token()
	headers = {"Authorization": f"Bearer {token}"}
	async with httpx.AsyncClient(base_url=settings.PLANKA_BASE_URL, headers=headers) as client:
		# Dedup: return existing project if one with the same name already exists
		try:
			resp = await client.get("/api/projects")
			resp.raise_for_status()
			for p in resp.json().get("items", []):
				if (p.get("name") or "").lower() == name.lower():
					logger.debug("create_project: '%s' already exists (id=%s), returning existing", _sanitize_for_log(name), p["id"])
					return p
		except Exception as e:
			logger.debug("create_project dedup check failed: %s", _sanitize_for_log(e))

		# Try with 'type' first, then 'isPublic' if it fails
		try:
			resp = await client.post("/api/projects", json={
				"name": name,
				"description": description,
				"type": "private"
			})
			resp.raise_for_status()
			data = resp.json()
			return data.get("item") or data
		except Exception as e:
			logger.debug("create_project failed with 'type', retrying with 'isPublic': %s", _sanitize_for_log(e))
			try:
				resp = await client.post("/api/projects", json={
					"name": name,
					"description": description,
					"isPublic": False
				})
				resp.raise_for_status()
				data = resp.json()
				return data.get("item") or data
			except Exception as e2:
				logger.debug("create_project retry also failed: %s", _sanitize_for_log(e2))
				return None

async def delete_project(project_id: str) -> bool:
	"""Cascade-delete a Planka project: cards → lists → boards → project."""
	token = await get_planka_auth_token()
	headers = {"Authorization": f"Bearer {token}"}
	async with httpx.AsyncClient(base_url=settings.PLANKA_BASE_URL, headers=headers, timeout=30.0) as client:
		try:
			# Get project details with boards
			det = await client.get(f"/api/projects/{project_id}")
			det.raise_for_status()
			boards = det.json().get("included", {}).get("boards", [])

			for board in boards:
				bid = board["id"]
				# Get board contents
				bd = await client.get(f"/api/boards/{bid}")
				if bd.status_code == 200:
					bd_data = bd.json()
					cards = bd_data.get("included", {}).get("cards", [])
					lists = bd_data.get("included", {}).get("lists", [])
					for c in cards:
						await client.delete(f"/api/cards/{c['id']}")
					for l in lists:
						await client.delete(f"/api/lists/{l['id']}")
				await client.delete(f"/api/boards/{bid}")

			# Now delete the empty project
			resp = await client.delete(f"/api/projects/{project_id}")
			resp.raise_for_status()
			logger.debug("Deleted Planka project %s", project_id)
			return True
		except Exception as e:
			logger.error("delete_project failed for %s: %s", _sanitize_for_log(project_id), _sanitize_for_log(e))
			return False

async def find_and_delete_projects_by_prefix(prefix: str) -> list:
	"""Find and cascade-delete all Planka projects whose name starts with a given prefix."""
	token = await get_planka_auth_token()
	headers = {"Authorization": f"Bearer {token}"}
	deleted = []
	async with httpx.AsyncClient(base_url=settings.PLANKA_BASE_URL, headers=headers, timeout=15.0) as client:
		resp = await client.get("/api/projects")
		resp.raise_for_status()
		projects = resp.json().get("items", [])

	for p in projects:
		if p.get("name", "").startswith(prefix):
			if await delete_project(p["id"]):
				deleted.append(p["name"])
	return deleted

async def create_board(project_id: str, name: str) -> dict:
	"""Create a new board in a project. Returns existing board if name matches (idempotent)."""
	token = await get_planka_auth_token()
	headers = {"Authorization": f"Bearer {token}"}
	async with httpx.AsyncClient(base_url=settings.PLANKA_BASE_URL, headers=headers) as client:
		# Dedup: return existing board if one with the same name already exists
		try:
			det = await client.get(f"/api/projects/{project_id}")
			det.raise_for_status()
			for b in det.json().get("included", {}).get("boards", []):
				if (b.get("name") or "").lower() == name.lower():
					logger.debug("create_board: '%s' already exists in project %s (id=%s), returning existing", _sanitize_for_log(name), _sanitize_for_log(project_id), b["id"])
					return b
		except Exception as e:
			logger.debug("create_board dedup check failed: %s", _sanitize_for_log(e))

		try:
			resp = await client.post(f"/api/projects/{project_id}/boards", json={
				"name": name,
				"position": 65535
			})
			resp.raise_for_status()
			data = resp.json()
			board = data.get("item") or data
		except Exception as e:
			logger.debug("create_board failed for project %s: %s", _sanitize_for_log(project_id), _sanitize_for_log(e))
			return None

		return board

async def _move_board_via_db(board_id: str, new_project_id: str) -> bool:
	"""Direct DB fallback for moving a board between projects.

	Planka v2's REST API (`PATCH /api/boards/:id`) does NOT accept `projectId`
	as a writable field — boards are immutably scoped to their parent project.
	We share Planka's postgres database so we can UPDATE the foreign key
	directly. This is safe because:
	  - the `board.project_id` column has no DB-level constraints beyond the
	    FK to `project.id`, and we verify the target project exists first;
	  - Planka's UI re-fetches board lists on page navigation, so the change
	    becomes visible without restarting the container.
	"""
	from sqlalchemy import text
	from app.models.db import engine
	try:
		async with engine.begin() as conn:
			# Ensure target project exists to avoid a stranded board.
			row = (await conn.execute(
				text("SELECT 1 FROM project WHERE id = :pid"),
				{"pid": int(new_project_id)},
			)).first()
			if not row:
				logger.error("move_board DB fallback: target project %s not found", _sanitize_for_log(new_project_id))
				return False
			result = await conn.execute(
				text("UPDATE board SET project_id = :pid, updated_at = NOW() WHERE id = :bid"),
				{"pid": int(new_project_id), "bid": int(board_id)},
			)
			if result.rowcount == 0:
				logger.error("move_board DB fallback: board %s not found", _sanitize_for_log(board_id))
				return False
		logger.info("move_board DB fallback: board %s moved to project %s via SQL", _sanitize_for_log(board_id), _sanitize_for_log(new_project_id))
		return True
	except Exception as e:
		logger.error("move_board DB fallback failed: %s", _sanitize_for_log(e))
		return False


async def move_board(board_id: str, new_project_id: str) -> bool:
	"""Move a board to a different project.

	Planka v2's REST API does not support changing a board's parent project
	(the `projectId` field is read-only on `PATCH /api/boards/:id`), so we
	fall back to a direct SQL UPDATE on the shared postgres database after
	confirming via re-GET that the PATCH was ignored.
	"""
	try:
		token = await get_planka_auth_token()
		headers = {"Authorization": f"Bearer {token}"}
		async with httpx.AsyncClient(base_url=settings.PLANKA_BASE_URL, headers=headers, timeout=30.0) as client:
			# Step 1: PATCH (will be silently ignored for projectId on Planka v2).
			try:
				resp = await client.patch(f"/api/boards/{board_id}", json={"projectId": new_project_id})
				resp.raise_for_status()
				logger.info("move_board PATCH response: %s", _sanitize_for_log(str(resp.json())[:400]))
			except Exception as patch_err:
				logger.info("move_board: PATCH attempt failed (expected on Planka v2): %s", _sanitize_for_log(patch_err))

			# Step 2: re-GET to see if PATCH actually moved the board.
			await asyncio.sleep(0.3)
			verify_resp = await client.get(f"/api/boards/{board_id}")
			verify_resp.raise_for_status()
			verify_item = verify_resp.json().get("item") or verify_resp.json()
			actual_project_id = str(verify_item.get("projectId", ""))
			if actual_project_id == str(new_project_id):
				logger.info("move_board: confirmed via API — board %s is now in project %s", _sanitize_for_log(board_id), _sanitize_for_log(new_project_id))
				return True

			logger.info(
				"move_board: API path did not move board (got %s, want %s) — falling back to direct DB update",
				_sanitize_for_log(actual_project_id), _sanitize_for_log(new_project_id),
			)

		# Step 3: DB fallback.
		ok = await _move_board_via_db(board_id, new_project_id)
		if not ok:
			return False

		# Step 4: re-GET once more to confirm Planka's API now reports the new project.
		try:
			async with httpx.AsyncClient(base_url=settings.PLANKA_BASE_URL, headers=headers, timeout=10.0) as client:
				await asyncio.sleep(0.3)
				verify_resp = await client.get(f"/api/boards/{board_id}")
				verify_resp.raise_for_status()
				verify_item = verify_resp.json().get("item") or verify_resp.json()
				actual_project_id = str(verify_item.get("projectId", ""))
				if actual_project_id == str(new_project_id):
					logger.info("move_board: confirmed via DB fallback — board %s is now in project %s", _sanitize_for_log(board_id), _sanitize_for_log(new_project_id))
					return True
				logger.warning(
					"move_board: DB UPDATE succeeded but API still reports projectId=%s (expected %s) — change persisted; client may need refresh",
					_sanitize_for_log(actual_project_id), _sanitize_for_log(new_project_id),
				)
		except Exception as ge:
			logger.warning("move_board: post-DB verify GET failed: %s — DB UPDATE already committed, treating as success", _sanitize_for_log(ge))
		return True
	except Exception as e:
		logger.error("move_board failed: %s", _sanitize_for_log(e))
		return False

async def move_card(card_title_fragment: str, destination_list: str, board_name: str = "") -> bool:
	"""Find a card by name fragment (case-insensitive) and move it to the target list column.

	Searches all projects/boards unless board_name is specified. Returns True on success.
	"""
	card_title_fragment = card_title_fragment.strip().strip('"\'').lower()
	destination_list = destination_list.strip().strip('"\'')
	board_name = board_name.strip().strip('"\'')
	logger.debug("move_card: fragment=%s, dest=%s, board=%s", _sanitize_for_log(card_title_fragment), _sanitize_for_log(destination_list), _sanitize_for_log(board_name))
	try:
		token = await get_planka_auth_token()
		headers = {"Authorization": f"Bearer {token}"}
		async with httpx.AsyncClient(base_url=settings.PLANKA_BASE_URL, timeout=10.0, headers=headers) as client:
			projects_resp = await client.get("/api/projects")
			projects_resp.raise_for_status()
			projects = projects_resp.json().get("items", [])

			found_card = None
			dest_list_id = None

			for p in projects:
				p_det = await client.get(f"/api/projects/{p['id']}")
				boards = p_det.json().get("included", {}).get("boards", [])
				for b in boards:
					if board_name and b["name"].lower() != board_name.lower():
						continue
					b_det = await client.get(f"/api/boards/{b['id']}", params={"included": "lists,cards"})
					b_data = b_det.json()
					lists = b_data.get("included", {}).get("lists", [])
					cards = b_data.get("included", {}).get("cards", [])
					for c in cards:
						if card_title_fragment in c["name"].lower():
							found_card = c
							dest_list = next(
								(l for l in lists if l["name"].lower() == destination_list.lower()), None
							)
							if dest_list:
								dest_list_id = dest_list["id"]
							break
					if found_card:
						break
				if found_card:
					break

			if not found_card:
				logger.debug("move_card: no card matching %r found", card_title_fragment)
				return False
			if not dest_list_id:
				logger.debug("move_card: list %r not found on the card's board", destination_list)
				return False

			patch_resp = await client.patch(f"/api/cards/{found_card['id']}", json={
				"listId": dest_list_id,
				"position": 65535
			})
			patch_resp.raise_for_status()
			logger.debug("move_card: %r moved to %r", found_card["name"], destination_list)
			return True
	except Exception as e:
		logger.debug("move_card failed: %s", e)
		return False

async def rename_card(card_title_fragment: str, new_name: str, board_name: str = "") -> bool:
	"""Find a card by name fragment and rename it. Returns True on success."""
	card_title_fragment = card_title_fragment.strip().strip('"\'').lower()
	new_name = new_name.strip().strip('"\'')
	board_name = board_name.strip().strip('"\'')
	if not new_name:
		logger.warning("rename_card: refusing to rename to empty string")
		return False
	logger.debug("rename_card: fragment=%s, new_name=%s, board=%s", _sanitize_for_log(card_title_fragment), _sanitize_for_log(new_name), _sanitize_for_log(board_name))
	try:
		token = await get_planka_auth_token()
		headers = {"Authorization": f"Bearer {token}"}
		async with httpx.AsyncClient(base_url=settings.PLANKA_BASE_URL, timeout=10.0, headers=headers) as client:
			projects_resp = await client.get("/api/projects")
			projects_resp.raise_for_status()
			projects = projects_resp.json().get("items", [])

			found_card = None
			for p in projects:
				p_det = await client.get(f"/api/projects/{p['id']}")
				boards = p_det.json().get("included", {}).get("boards", [])
				for b in boards:
					if board_name and b["name"].lower() != board_name.lower():
						continue
					b_det = await client.get(f"/api/boards/{b['id']}", params={"included": "cards"})
					cards = b_det.json().get("included", {}).get("cards", [])
					for c in cards:
						if card_title_fragment in c["name"].lower():
							found_card = c
							break
					if found_card:
						break
				if found_card:
					break

			if not found_card:
				logger.debug("rename_card: no card matching %r found", card_title_fragment)
				return False

			patch_resp = await client.patch(f"/api/cards/{found_card['id']}", json={"name": new_name})
			patch_resp.raise_for_status()
			logger.debug("rename_card: %r renamed to %r", found_card["name"], new_name)
			return True
	except Exception as e:
		logger.debug("rename_card failed: %s", e)
		return False

async def rename_list(list_name_fragment: str, new_name: str, board_name: str = "") -> bool:
	"""Find a list (column) by name fragment and rename it. Returns True on success."""
	list_name_fragment = list_name_fragment.strip().strip('"\'').lower()
	new_name = new_name.strip().strip('"\'')
	board_name = board_name.strip().strip('"\'')
	if not new_name:
		logger.warning("rename_list: refusing to rename to empty string")
		return False
	logger.debug("rename_list: fragment=%s, new_name=%s, board=%s", _sanitize_for_log(list_name_fragment), _sanitize_for_log(new_name), _sanitize_for_log(board_name))
	try:
		token = await get_planka_auth_token()
		headers = {"Authorization": f"Bearer {token}"}
		async with httpx.AsyncClient(base_url=settings.PLANKA_BASE_URL, timeout=10.0, headers=headers) as client:
			projects_resp = await client.get("/api/projects")
			projects_resp.raise_for_status()
			projects = projects_resp.json().get("items", [])

			found_list = None
			for p in projects:
				p_det = await client.get(f"/api/projects/{p['id']}")
				boards = p_det.json().get("included", {}).get("boards", [])
				for b in boards:
					if board_name and b["name"].lower() != board_name.lower():
						continue
					b_det = await client.get(f"/api/boards/{b['id']}", params={"included": "lists"})
					lists = b_det.json().get("included", {}).get("lists", [])
					for lst in lists:
						if list_name_fragment in lst["name"].lower():
							found_list = lst
							break
					if found_list:
						break
				if found_list:
					break

			if not found_list:
				logger.debug("rename_list: no list matching %r found", list_name_fragment)
				return False

			patch_resp = await client.patch(f"/api/lists/{found_list['id']}", json={"name": new_name})
			patch_resp.raise_for_status()
			logger.debug("rename_list: %r renamed to %r", found_list["name"], new_name)
			return True
	except Exception as e:
		logger.debug("rename_list failed: %s", e)
		return False

async def create_list(board_name: str, list_name: str, project_name: Optional[str] = None) -> Optional[dict]:
	"""Create a new list (column) in a board. Returns existing list if name matches (idempotent)."""
	if not list_name or not list_name.strip():
		logger.warning("create_list: refusing to create list with empty name on board '%s'", _sanitize_for_log(board_name))
		return None
	token = await get_planka_auth_token()
	headers = {"Authorization": f"Bearer {token}"}
	async with httpx.AsyncClient(base_url=settings.PLANKA_BASE_URL, headers=headers) as client:
		# Find board by name
		resp = await client.get("/api/projects", headers=headers)
		resp.raise_for_status()
		projects = resp.json().get("items", [])

		board_id = None
		existing_lists = []
		for proj in projects:
			if project_name and proj["name"].lower() != project_name.lower():
				continue
			det = await client.get(f"/api/projects/{proj['id']}")
			det.raise_for_status()
			det_data = det.json()
			boards = det_data.get("included", {}).get("boards", []) or det_data.get("boards", [])
			for b in boards:
				if b["name"].lower() == board_name.lower():
					board_id = b["id"]
					break
			if board_id:
				break

		if not board_id:
			logger.debug("create_list - board '%s' not found", _sanitize_for_log(board_name))
			return None

		# Dedup: check if a list with the same name already exists on this board
		try:
			b_detail = await client.get(f"/api/boards/{board_id}", params={"included": "lists"})
			b_detail.raise_for_status()
			existing_lists = b_detail.json().get("included", {}).get("lists", [])
			for lst in existing_lists:
				if lst.get("type") in ("archive", "trash"):
					continue
				if (lst.get("name") or "").lower() == list_name.lower():
					logger.debug("create_list: '%s' already exists on board '%s' (id=%s), returning existing", _sanitize_for_log(list_name), _sanitize_for_log(board_name), lst["id"])
					return lst
		except Exception as e:
			logger.debug("create_list dedup check failed: %s", _sanitize_for_log(e))

		try:
			resp = await client.post(f"/api/boards/{board_id}/lists", json={
				"name": list_name,
				"type": "active",
				"position": 65535
			})
			resp.raise_for_status()
			data = resp.json()
			return data.get("item") or data
		except Exception as e:
			logger.debug("create_list failed: %s", _sanitize_for_log(e))
			return None

async def get_board_summary(board_name: str = "Operator Board") -> str:
	"""Fetches a structured text summary of all active cards and lists on a specific board.
	Used to inject live operational context into tactical Dify crews.
	"""
	# get_planka_auth_token imported from planka_common at module level
	token = await get_planka_auth_token()
	headers = {"Authorization": f"Bearer {token}"}
	
	try:
		async with httpx.AsyncClient(base_url=settings.PLANKA_BASE_URL, timeout=10.0, headers=headers) as client:
			# 1. Resolve Board ID
			projects_resp = await client.get("/api/projects")
			projects = projects_resp.json().get("items", [])
			board_id = None
			
			for p in projects:
				p_det = await client.get(f"/api/projects/{p['id']}")
				boards = p_det.json().get("included", {}).get("boards", [])
				match = next((b for b in boards if b["name"].lower() == board_name.lower()), None)
				if match:
					board_id = match["id"]
					break

			
			if not board_id:
				return f"Board '{board_name}' not found."
				
			# 2. Fetch Lists and Cards
			b_detail_resp = await client.get(f"/api/boards/{board_id}", params={"included": "lists,cards"})
			b_detail = b_detail_resp.json()
			lists = b_detail.get("included", {}).get("lists", [])
			cards = b_detail.get("included", {}).get("cards", [])
			
			# Sort by position
			lists.sort(key=lambda x: x.get("position", 0))
			
			summary_lines = [f"### Planka Board: {board_name} Summary ###"]
			for lst in lists:
				lst_cards = [c for c in cards if c["listId"] == lst["id"]]
				lst_cards.sort(key=lambda x: x.get("position", 0))
				summary_lines.append(f"\n[List: {lst['name']}]")
				if not lst_cards:
					summary_lines.append("  (Empty)")
				for c in lst_cards:
					summary_lines.append(f"  - {c['name']}")
			
			return "\n".join(summary_lines)
	except Exception as e:
		logger.warning("get_board_summary error: %s", e)
		return "Planka context unavailable."

async def find_item_in_planka(title_fragment: str) -> bool:
	"""Check whether title_fragment (case-insensitive substring) exists as a board name
	or as a card name on the Operator Board.  Used by the recall-history intercept to
	provide ground-truth verification instead of trusting Z's reply text.

	Strategy (fast — 3 round-trips):
	  1. GET /api/projects
	  2. GET /api/projects/{id} in parallel → board names
	  3. GET /api/boards/{operator_board_id} with cards included → card names
	"""
	if not title_fragment or len(title_fragment.strip()) < 3:
		return False
	fragment = title_fragment.lower().strip()
	try:
		token = await get_planka_auth_token()
		headers = {"Authorization": f"Bearer {token}"}
		async with httpx.AsyncClient(base_url=settings.PLANKA_BASE_URL, timeout=12.0, headers=headers) as client:
			proj_resp = await client.get("/api/projects")
			projects = proj_resp.json().get("items", [])
			if not projects:
				return False

			proj_details = await asyncio.gather(
				*[client.get(f"/api/projects/{p['id']}") for p in projects],
				return_exceptions=True,
			)

			operator_board_id: Optional[str] = None
			for det in proj_details:
				if isinstance(det, BaseException):
					continue
				boards = det.json().get("included", {}).get("boards", [])
				for b in boards:
					if fragment in b["name"].lower():
						return True
					if b["name"].lower() == "operator board" and operator_board_id is None:
						operator_board_id = b["id"]

			if operator_board_id:
				ob_resp = await client.get(
					f"/api/boards/{operator_board_id}", params={"included": "cards"}
				)
				cards = ob_resp.json().get("included", {}).get("cards", [])
				if any(fragment in c["name"].lower() for c in cards):
					return True
	except Exception as e:
		logger.warning("find_item_in_planka: %s", _sanitize_for_log(e))
	return False

async def get_activity_report(days: int = 30) -> str:
	"""Fetch a detailed record of cards finished vs. cards stalled vs. WIP state.
	This is the 'truth' used by the Review tasks to prevent hallucinations.
	"""
	cutoff = datetime.now() - timedelta(days=days)

	try:
		token = await get_planka_auth_token()
		headers = {"Authorization": f"Bearer {token}"}

		async with httpx.AsyncClient(base_url=settings.PLANKA_BASE_URL, timeout=20.0, headers=headers) as client:
			resp = await client.get("/api/projects")
			projects = resp.json().get("items", [])
			if not projects:
				return "### OPERATIONAL DATA EMPTY ###\nNo active project boards or missions found in the legal database. System is standing by."

			all_details_tasks = [client.get(f"/api/projects/{p['id']}") for p in projects]
			all_details_resps = await asyncio.gather(*all_details_tasks)
			
			board_tasks = []
			board_names = []
			for r in all_details_resps:
				d = r.json()
				boards = d.get("included", {}).get("boards", []) or d.get("boards", [])
				for b in boards:
					board_tasks.append(client.get(f"/api/boards/{b['id']}", params={"included": "lists,cards,labels,cardLabels"}))
					board_names.append(b["name"])
			
			board_details = await asyncio.gather(*board_tasks)
			
			from app.services.translations import get_done_keywords
			_done_kw = get_done_keywords()
			
			# Categories
			completed_cards = []
			in_progress_cards = []
			blocked_cards = []
			stalled_cards = [] # Incomplete and not updated for 7+ days
			
			wip_violations = [] # List of (board, list, count)
			
			for b_idx, b_resp in enumerate(board_details):
				b_data = b_resp.json()
				b_name = board_names[b_idx]
				lists = b_data.get("included", {}).get("lists", [])
				cards = b_data.get("included", {}).get("cards", [])
				labels = b_data.get("included", {}).get("labels", [])
				card_labels = b_data.get("included", {}).get("cardLabels", [])
				
				# Map labels for lookups
				label_map = {l["id"]: l for l in labels}
				card_to_labels: dict[str, list] = {}
				for cl in card_labels:
					cid = cl["cardId"]
					lid = cl["labelId"]
					if cid not in card_to_labels: card_to_labels[cid] = []
					if lid in label_map: card_to_labels[cid].append(label_map[lid])

				done_list_ids = {l['id'] for l in lists if l.get('name') and l['name'].lower() in _done_kw}
				
				# Define "In Progress" lists (e.g. "Doing", "In Progress", "Today")
				in_progress_kw = {"in progress", "doing", "active", "today", "im gang", "en curso"}
				ip_list_ids = {l['id'] for l in lists if l.get('name') and l['name'].lower() in in_progress_kw}
				
				for lst in lists:
					lst_cards = [c for c in cards if c["listId"] == lst["id"]]
					if lst["id"] in ip_list_ids and len(lst_cards) > 3:
						wip_violations.append(f"{b_name} → {lst['name']} ({len(lst_cards)} cards, limit 3)")
				
				for card in cards:
					c_name = card["name"]
					c_updated = datetime.fromisoformat(card["updatedAt"].replace('Z', ''))
					c_labels = card_to_labels.get(card["id"], [])
					c_label_names = [l["name"].lower() for l in c_labels]
					
					is_done = card["listId"] in done_list_ids
					is_ip = card["listId"] in ip_list_ids
					is_blocked = "blocked" in c_label_names or "block" in c_name.lower()
					
					# Class of Service detection
					is_expedite = "expedite" in c_label_names or "!!" in c_name
					is_fixed_date = "fixed date" in c_label_names or "!" in c_name
					cos_tag = ""
					if is_expedite: cos_tag = " [EXPEDITE]"
					elif is_fixed_date: cos_tag = " [FIXED DATE]"
					
					if is_done:
						if c_updated > cutoff:
							completed_cards.append(f"- {c_name}{cos_tag} ({b_name})")
					else:
						if is_blocked:
							blocked_cards.append(f"- {c_name}{cos_tag} ({b_name})")
						elif is_ip:
							age = (datetime.now() - c_updated).days
							in_progress_cards.append(f"- {c_name}{cos_tag} ({b_name}, {age} days active)")
						elif c_updated < (datetime.now() - timedelta(days=7)):
							stalled_cards.append(f"- {c_name}{cos_tag} ({b_name}, last activity {c_updated.strftime('%Y-%m-%d')})")

			report = "### 30-DAY OPERATIONAL ACTIVITY REPORT ###\n\n"
			
			report += "COMPLETED IN LAST 30 DAYS:\n"
			if completed_cards:
				report += "\n".join(completed_cards[:30]) # Cap at 30
				if len(completed_cards) > 30: report += f"\n...and {len(completed_cards)-30} more."
			else:
				report += "(None found in Done lists)"
			
			report += "\n\nCURRENTLY IN PROGRESS:\n"
			if in_progress_cards:
				report += "\n".join(in_progress_cards)
			else:
				report += "(No tasks in active columns)"
				
			report += "\n\nBLOCKED / STALLED INITIATIVES:\n"
			if blocked_cards or stalled_cards:
				if blocked_cards:
					report += "BLOCKED:\n" + "\n".join(blocked_cards) + "\n"
				if stalled_cards:
					report += "STALLED (>7 days inactive):\n" + "\n".join(stalled_cards[:15])
			else:
				report += "(None detected)"
				
			if wip_violations:
				report += "\n\nWIP LIMIT VIOLATIONS (Limit=3):\n"
				report += "\n".join(wip_violations)

			return report
	except Exception:
		logger.exception("get_activity_report failed")
		return "### OPERATIONAL DATA FAILURE ###\n⚠️ Connection to Planka disrupted. Mission status is UNVERIFIED. DO NOT SIMULATE LIVE STATE."
