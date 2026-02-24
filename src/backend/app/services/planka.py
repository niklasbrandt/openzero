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

import httpx
import logging
from app.config import settings

logger = logging.getLogger(__name__)

async def get_planka_auth_token() -> str:
    """Authenticates with Planka and returns an access token."""
    login_url = f"{settings.PLANKA_BASE_URL}/api/access-tokens"
    payload = {
        "emailOrUsername": settings.PLANKA_ADMIN_EMAIL,
        "password": settings.PLANKA_ADMIN_PASSWORD
    }
    print(f"DEBUG: Attempting Planka auth at {login_url} for {settings.PLANKA_ADMIN_EMAIL}")
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(login_url, json=payload)
            if resp.status_code != 200:
                print(f"DEBUG: Planka auth failed with status {resp.status_code}: {resp.text}")
                resp.raise_for_status()
            token = resp.json().get("item")
            if token:
                 print("DEBUG: Planka auth successful.")
            return token
        except Exception as e:
            print(f"DEBUG: Planka auth exception: {e}")
            raise

import asyncio
import time

_tree_cache = {} # cache_key -> (timestamp, data)

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
                return "No projects found. Use Planka to create your first mission."

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
                
                # Make project names clickable
                if as_html:
                    project_name = f"<b><a href='/api/dashboard/planka-redirect?target_project_id={project_id}' target='_blank' style='color: inherit; text-decoration: none;'>{project['name']}</a></b>"
                else:
                    project_name = f"*[{project['name']}]({settings.BASE_URL}/api/dashboard/planka-redirect?target_project_id={project_id})*"
                
                tree_lines.append((i, "project", project_name))
                
                for board in boards:
                    task = client.get(f"/api/boards/{board['id']}", params={"included": "lists,cards"})
                    board_tasks.append(task)
                    board_metadata.append({"project_idx": i, "name": board['name'], "id": board['id']})

            # Fetch all board details in parallel
            board_resps = await asyncio.gather(*board_tasks, return_exceptions=True)
            
            # Map board responses back to their projects
            project_boards = {i: [] for i in range(len(projects))}
            for meta, b_resp in zip(board_metadata, board_resps):
                if isinstance(b_resp, Exception):
                    project_boards[meta["project_idx"]].append(f"  └── {meta['name']} (Stats offline)")
                    continue

                b_detail = b_resp.json()
                lists = b_detail.get("included", {}).get("lists", [])
                cards = b_detail.get("included", {}).get("cards", [])
                
                total_cards = len(cards)
                done_list_ids = [l['id'] for l in lists if l.get('name') and any(kw in l['name'].lower() for kw in ['done', 'complete', 'finish'])]
                done_cards = len([c for c in cards if c['listId'] in done_list_ids])
                
                progress_pct = int((done_cards / total_cards) * 100) if total_cards > 0 else 0
                board_id = meta["id"]
                board_name = meta["name"]

                if as_html:
                    progress_str = f" <span style='color: #4ade80; font-size: 0.8rem;'>({progress_pct}%)</span>" if total_cards > 0 else ""
                    line = f"  └── <a href='/api/dashboard/planka-redirect?target_board_id={board_id}' target='_blank' style='color: inherit; text-decoration: none;'>{board_name}</a>{progress_str}"
                else:
                    progress_str = f" ({progress_pct}%)" if total_cards > 0 else ""
                    # Use a simpler bullet for Telegram to avoid breaking Markdown links
                    line = f" • _[{board_name}]({settings.BASE_URL}/api/dashboard/planka-redirect?target_board_id={board_id})_{progress_str}"
                
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

async def create_task(board_name: str, list_name: str, title: str) -> bool:
    """Creates a card on the specified board and list."""
    print(f"DEBUG: create_task requested -> Board: {board_name}, List: {list_name}, Title: {title}")
    try:
        from app.services.operator_board import operator_service
        token = await get_planka_auth_token()
        headers = {"Authorization": f"Bearer {token}"}
        
        async with httpx.AsyncClient(base_url=settings.PLANKA_BASE_URL, timeout=10.0, headers=headers) as client:
            # 1. SPECIAL CASE: Operator Board
            target_board = None
            if board_name.lower() == "operator board":
                print("DEBUG: Targeting Operator Board, ensuring initialization...")
                _, b_id = await operator_service.initialize_board(client)
                target_board = {"id": b_id, "name": "Operator Board"}
            else:
                # General Search
                projects_resp = await client.get("/api/projects")
                projects = projects_resp.json().get("items", [])
                for p in projects:
                    p_det = (await client.get(f"/api/projects/{p['id']}")).json()
                    match = next((b for b in p_det.get("included", {}).get("boards", []) if b["name"].lower() == board_name.lower()), None)
                    if match:
                        target_board = match
                        break
            
            if not target_board:
                print(f"DEBUG: Board '{board_name}' not found. Defaulting to Operator Board.")
                _, b_id = await operator_service.initialize_board(client)
                target_board = {"id": b_id, "name": "Operator Board"}

            # 2. Find List
            board_id = target_board["id"]
            b_detail = (await client.get(f"/api/boards/{board_id}", params={"included": "lists"})).json()
            lists = b_detail.get("included", {}).get("lists", [])
            target_list = next((l for l in lists if l["name"].lower() == list_name.lower()), None)
            
            if not target_list:
                if lists:
                    target_list = lists[0]
                else:
                    l_resp = await client.post(f"/api/boards/{board_id}/lists", json={"name": "Inbox", "position": 65535})
                    target_list = l_resp.json()["item"]

            # 3. Create Card
            res = await client.post(f"/api/boards/{board_id}/cards", json={
                "boardId": board_id,
                "listId": target_list["id"],
                "name": title,
                "position": 65535
            })
            res.raise_for_status()
            print(f"DEBUG: Card created successfully in {target_board['name']} -> {target_list['name']}")
            return True
    except Exception as e:
        print(f"DEBUG: create_task failed: {e}")
        return False

async def create_project(name: str, description: str = "") -> dict:
    """Create a new project in Planka."""
    token = await get_planka_auth_token()
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(base_url=settings.PLANKA_BASE_URL, headers=headers) as client:
        resp = await client.post("/api/projects", json={
            "name": name, 
            "description": description,
            "type": "private"
        })
        resp.raise_for_status()
        return resp.json().get("item")

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
        
        # Also create a default 'Inbox' list
        board = resp.json().get("item")
        await client.post(f"/api/boards/{board['id']}/lists", json={
            "name": "Inbox",
            "type": "active",
            "position": 65535
        })
        
        return board
