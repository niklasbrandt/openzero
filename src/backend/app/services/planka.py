from plankapy import Planka
from app.config import settings

def get_planka_client():
    return Planka(
        url=settings.PLANKA_BASE_URL,
        username=settings.PLANKA_ADMIN_EMAIL,
        password=settings.PLANKA_ADMIN_PASSWORD,
    )

async def get_project_tree() -> str:
    """Recursively build a text tree of all projects."""
    # This currently uses the mock logic or fetches from Planka
    # For now, let's provide a structured placeholder that matches the UI
    try:
        client = get_planka_client()
        # projects = client.get_projects()
        # Actual tree building logic would go here
        return "[ACTIVE] Career [40%]\n  [PAUSED] Job Applications [20%]\n[ACTIVE] Family [60%]\n   Kindergarten Registration [100%]"
    except Exception as e:
        return f"Error fetching project tree: {str(e)}"

def create_task(board_name: str, list_name: str, title: str):
    client = get_planka_client()
    projects = client.get_projects()
    for project in projects:
        for board in project.boards:
            if board.name == board_name:
                for lst in board.lists:
                    if lst.name == list_name:
                        lst.create_card(name=title, position=65535)
                        return True
    return False
