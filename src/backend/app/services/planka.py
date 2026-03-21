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

from typing import Optional
import httpx
import logging
from app.config import settings

logger = logging.getLogger(__name__)

from app.services.planka_common import get_planka_auth_token, _tree_cache
import asyncio
import time

def _log_safe(text: str) -> str:
	"""Sanitize input for logging to prevent CRLF injection (CWE-117)."""
	if not isinstance(text, str):
		return str(text)
	# Completely remove newlines and carriage returns to satisfy CodeQL
	return text.replace("\n", "").replace("\r", "")[:255]

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
					p_display = f"<b><a href='/api/dashboard/planka-redirect?target_project_id={project_id}' target='_blank' style='color: inherit; text-decoration: none;'>{project_name}</a></b>"
				else:
					# Use version without underscores for Telegram Markdown
					p_display = f"**[{project_name}]({settings.BASE_URL}/api/dashboard/planka-redirect?targetprojectid={project_id})**"

				tree_lines.append((i, "project", p_display))

				for board in boards:
					task = client.get(f"/api/boards/{board['id']}", params={"included": "lists,cards"})
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
					line = f"  └── <a href='/api/dashboard/planka-redirect?target_board_id={board_id}' target='_blank' style='color: inherit; text-decoration: none;'>{board_name}</a>{progress_str}"
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
		logger.error("Planka project tree error: %s", e)
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

	logger.debug("create_task requested -> Board: %r, List: %r, Title: %r", _log_safe(board_name), _log_safe(list_name), _log_safe(title))
	try:
		from app.services.operator_board import operator_service
		token = await get_planka_auth_token()
		headers = {"Authorization": f"Bearer {token}"}

		async with httpx.AsyncClient(base_url=settings.PLANKA_BASE_URL, timeout=10.0, headers=headers) as client:
			# 1. SPECIAL CASE: Operator Board
			target_board = None
			if board_name.lower() == "operator board":
				logger.debug("Targeting Operator Board, ensuring initialization...")
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
					match = next((b for b in boards if b["name"].lower() == board_name.lower()), None)
					if match:
						target_board = match
						break

			if not target_board:
				logger.debug("Board %r not found. Defaulting to Operator Board.", _log_safe(board_name))
				_, b_id = await operator_service.initialize_board(client)
				target_board = {"id": b_id, "name": "Operator Board"}

			# 2. Find List
			board_id = target_board["id"]
			b_detail_resp = await client.get(f"/api/boards/{board_id}", params={"included": "lists"})
			b_detail_resp.raise_for_status()
			b_detail = b_detail_resp.json()
			lists = b_detail.get("included", {}).get("lists", []) or b_detail.get("lists", [])
			target_list = next((l for l in lists if l["name"].lower() == list_name.lower()), None)

			if not target_list:
				# Fall back to first available list, or create 'Inbox' if board is empty
				if lists:
					target_list = lists[0]
				else:
					l_resp = await client.post(f"/api/boards/{board_id}/lists", json={"name": "Inbox", "position": 65535})
					l_resp.raise_for_status()
					target_list = l_resp.json().get("item")

			if not target_list:
				raise ValueError(f"List '{list_name}' not found and could not be created on board '{target_board['name']}'")

			# 3. Create Card
			res = await client.post(f"/api/boards/{board_id}/cards", json={
				"boardId": board_id,
				"listId": target_list["id"],
				"name": title,
				"description": description,
				"position": 65535
			})
			res.raise_for_status()
			# Resolve the project name for the path string
			project_name = "Operations"
			try:
				from app.services.operator_board import operator_service
				project_name = operator_service.project_name
			except Exception:
				logger.debug("create_task: operator_service not ready, using default project name")
			path = f"{project_name} → {target_board['name']} → {target_list['name']}"
			logger.debug("Card created successfully: %s", path)
			return path
	except Exception as e:
		logger.warning("create_task failed: %s", e)
		return None

async def create_project(name: str, description: str = "") -> dict:
	"""Create a new project in Planka."""
	token = await get_planka_auth_token()
	headers = {"Authorization": f"Bearer {token}"}
	async with httpx.AsyncClient(base_url=settings.PLANKA_BASE_URL, headers=headers) as client:
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
			logger.debug("create_project failed with 'type', retrying with 'isPublic': %s", e)
			resp = await client.post("/api/projects", json={
				"name": name,
				"description": description,
				"isPublic": False
			})
			resp.raise_for_status()
			data = resp.json()
			return data.get("item") or data

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
			logger.error("delete_project failed for %s: %s", project_id, e)
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
	"""Create a new board in a project."""
	token = await get_planka_auth_token()
	headers = {"Authorization": f"Bearer {token}"}
	async with httpx.AsyncClient(base_url=settings.PLANKA_BASE_URL, headers=headers) as client:
		resp = await client.post(f"/api/projects/{project_id}/boards", json={
			"name": name,
			"position": 65535
		})
		resp.raise_for_status()
		data = resp.json()
		board = data.get("item") or data

		# Also create a default 'Inbox' list
		try:
			await client.post(f"/api/boards/{board['id']}/lists", json={
				"name": "Inbox",
				"type": "active",
				"position": 65535
			})
		except Exception as e:
			logger.debug("Failed to create default Inbox list with type, retrying without: %s", e)
			try:
				await client.post(f"/api/boards/{board['id']}/lists", json={
					"name": "Inbox",
					"position": 65535
				})
			except Exception as e2:
				logger.debug("Failed to create default Inbox list: %s", e2)

		return board

async def move_card(card_title_fragment: str, destination_list: str, board_name: str = "") -> bool:
	"""Find a card by name fragment (case-insensitive) and move it to the target list column.

	Searches all projects/boards unless board_name is specified. Returns True on success.
	"""
	card_title_fragment = card_title_fragment.strip().strip('"\'').lower()
	destination_list = destination_list.strip().strip('"\'')
	board_name = board_name.strip().strip('"\'')
	logger.debug("move_card: fragment=%s, dest=%s, board=%s", card_title_fragment, destination_list, board_name)
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

async def create_list(board_name: str, list_name: str, project_name: Optional[str] = None) -> Optional[dict]:
	"""Create a new list (column) in a board."""
	token = await get_planka_auth_token()
	headers = {"Authorization": f"Bearer {token}"}
	async with httpx.AsyncClient(base_url=settings.PLANKA_BASE_URL, headers=headers) as client:
		# Find board by name
		resp = await client.get("/api/projects", headers=headers)
		resp.raise_for_status()
		projects = resp.json().get("items", [])

		board_id = None
		for proj in projects:
			if project_name and proj["name"].lower() != project_name.lower():
				continue
			det = await client.get(f"/api/projects/{proj['id']}")
			det.raise_for_status()
			boards = det.json().get("included", {}).get("boards", [])
			for b in boards:
				if b["name"].lower() == board_name.lower():
					board_id = b["id"]
					break
			if board_id:
				break

		if not board_id:
			logger.debug("create_list - board '%s' not found", board_name)
			return None

		try:
			resp = await client.post(f"/api/boards/{board_id}/lists", json={
				"name": list_name,
				"position": 65535
			})
			resp.raise_for_status()
			data = resp.json()
			return data.get("item") or data
		except Exception as e:
			logger.debug("create_list failed: %s", e)
			return None
