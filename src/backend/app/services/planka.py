"""
Planka Integration Service
--------------------------
This service provides the low-level bridge between the OpenZero backend and the 
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
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(login_url, json=payload)
        resp.raise_for_status()
        return resp.json().get("item")

async def get_project_tree(as_html: bool = True) -> str:
    """Recursively build a semantic text tree of all projects, boards, and progress stats from Planka."""
    try:
        token = await get_planka_auth_token()
        headers = {"Authorization": f"Bearer {token}"}
        
        async with httpx.AsyncClient(base_url=settings.PLANKA_BASE_URL, timeout=15.0, headers=headers) as client:
            resp = await client.get("/api/projects")
            resp.raise_for_status()
            projects = resp.json().get("items", [])
            
            if not projects:
                return "No projects found. Use Planka to create your first mission."
                
            tree_lines = []
            for project in projects:
                # Fetch detailed project to get boards
                detail_resp = await client.get(f"/api/projects/{project['id']}")
                detail_resp.raise_for_status()
                detail = detail_resp.json()
                boards = detail.get("included", {}).get("boards", [])
                
                project_name = f"<b>{project['name']}</b>" if as_html else f"[{project['name']}]"
                tree_lines.append(project_name)
                
                for board in boards:
                    board_id = board['id']
                    board_name = board['name']
                    
                    # Fetch board detail to get lists and card counts
                    try:
                        b_resp = await client.get(f"/api/boards/{board_id}", params={"included": "lists,cards"})
                        b_detail = b_resp.json()
                        lists = b_detail.get("included", {}).get("lists", [])
                        cards = b_detail.get("included", {}).get("cards", [])
                        
                        total_cards = len(cards)
                        done_cards = 0
                        
                        # Identify 'Done' lists
                        done_list_ids = [l['id'] for l in lists if l.get('name') and any(kw in l['name'].lower() for kw in ['done', 'complete', 'finish'])]
                        done_cards = len([c for c in cards if c['listId'] in done_list_ids])
                        
                        progress_pct = int((done_cards / total_cards) * 100) if total_cards > 0 else 0
                        
                        if as_html:
                            progress_str = f" <span style='color: #4ade80; font-size: 0.8rem;'>({progress_pct}%)</span>" if total_cards > 0 else ""
                            line = f"  └── <a href='/api/dashboard/planka-redirect?target_board_id={board_id}' target='_blank' style='color: inherit; text-decoration: none;'>{board_name}</a>{progress_str}"
                        else:
                            progress_str = f" ({progress_pct}%)" if total_cards > 0 else ""
                            line = f"  └── {board_name}{progress_str}"
                            
                        tree_lines.append(line)
                    except Exception as be:
                        logger.error(f"Error fetching stats for board {board_name}: {be}")
                        tree_lines.append(f"  └── {board_name} (Stats offline)")
                        
                tree_lines.append("") # Spacer
                    
            return "\n".join(tree_lines)
    except Exception as e:
        logger.error(f"Planka project tree error: {e}")
        return f"Planka connection issue: {str(e)}"
    except Exception as e:
        logger.error(f"Planka project tree error: {e}")
        return f"Planka connection issue: {str(e)}"

async def create_task(board_name: str, list_name: str, title: str) -> bool:
    """ Creates a task on a specific board and list. Returns True if successful. """
    try:
        token = await get_planka_auth_token()
        headers = {"Authorization": f"Bearer {token}"}
        
        async with httpx.AsyncClient(base_url=settings.PLANKA_BASE_URL, timeout=10.0, headers=headers) as client:
            # 1. Find the project/board
            proj_resp = await client.get("/api/projects")
            projects = proj_resp.json().get("items", [])
            
            for project in projects:
                detail_resp = await client.get(f"/api/projects/{project['id']}")
                detail = detail_resp.json()
                boards = detail.get("included", {}).get("boards", [])
                
                for board in boards:
                    if board["name"] == board_name:
                        # 2. Find the list
                        board_detail = (await client.get(f"/api/boards/{board['id']}")).json()
                        lists = board_detail.get("included", {}).get("lists", [])
                        
                        target_list = next((l for l in lists if l["name"] == list_name), None)
                        if target_list:
                            # 3. Create the card
                            await client.post(f"/api/boards/{board['id']}/cards", json={
                                "listId": target_list["id"],
                                "name": title,
                                "position": 65535
                            })
                            return True
        return False
    except Exception as e:
        logger.error(f"Task creation failed: {e}")
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
            "position": 65535
        })
        
        return board
