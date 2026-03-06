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

async def get_planka_auth_token() -> str:
	"""Authenticates with Planka and returns an access token. Handles ToS acceptance."""
	login_url = f"{settings.PLANKA_BASE_URL}/api/access-tokens"
	payload = {
		"emailOrUsername": settings.PLANKA_ADMIN_EMAIL,
		"password": settings.PLANKA_ADMIN_PASSWORD
	}
	logger.debug("Attempting Planka auth at %s", login_url)
	async with httpx.AsyncClient(timeout=10.0) as client:
		try:
			resp = await client.post(login_url, json=payload)
			
			# Handle pending ToS acceptance (common on first login)
			if resp.status_code == 403:
				data = resp.json()
				pending_token = data.get("pendingToken")
				if pending_token:
					logger.debug("Planka requires ToS acceptance (pendingToken found). Accepting...")
					accept_url = f"{settings.PLANKA_BASE_URL}/api/access-tokens/{pending_token}/actions/accept"
					accept_resp = await client.post(accept_url)
					accept_resp.raise_for_status()
					# After accepting, retry the login to get the real token
					resp = await client.post(login_url, json=payload)
				else:
					resp.raise_for_status()  # 403 without pendingToken is a real error

			resp.raise_for_status()
			token = resp.json().get("item")
			if token:
				logger.debug("Planka auth successful.")
			else:
				raise ValueError("Auth token is empty — check Planka credentials.")
			return token
		except Exception as e:
			logger.debug("Planka auth exception: %s", e)
			raise

import asyncio
import time

_tree_cache: dict[str, tuple[float, str]] = {} # cache_key -> (timestamp, data)

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
		logger.error(f"Planka project tree error: {e}")
		return f"Planka connection issue: {str(e)}"

async def create_task(board_name: str, list_name: str, title: str, description: str = "") -> bool:
	"""Creates a card on the specified board and list."""
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

	logger.debug("create_task requested -> Board: %s, List: %s, Title: %s", board_name, list_name, title)
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
				logger.debug("Board '%s' not found. Defaulting to Operator Board.", board_name)
				_, b_id = await operator_service.initialize_board(client)
				target_board = {"id": b_id, "name": "Operator Board"}

			# 2. Find List
			board_id = target_board["id"]
			b_detail_resp = await client.get(f"/api/boards/{board_id}", params={"included": "lists"})
			b_detail = b_detail_resp.json()
			lists = b_detail.get("included", {}).get("lists", []) or b_detail.get("lists", [])
			target_list = next((l for l in lists if l["name"].lower() == list_name.lower()), None)
			
			if not target_list:
				if lists:
					target_list = lists[0]
				else:
					l_resp = await client.post(f"/api/boards/{board_id}/lists", json={"name": "Inbox", "position": 65535})
					target_list = l_resp.json().get("item")

			# 3. Create Card
			res = await client.post(f"/api/boards/{board_id}/cards", json={
				"boardId": board_id,
				"listId": target_list["id"],
				"name": title,
				"description": description,
				"position": 65535
			})
			res.raise_for_status()
			logger.debug("Card created successfully in %s -> %s", target_board['name'], target_list['name'])
			return True
	except Exception as e:
		logger.debug("create_task failed: %s", e)
		return False

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
