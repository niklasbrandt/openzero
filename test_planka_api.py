
import httpx
import asyncio
import os
import sys

# Add src to sys.path
sys.path.append(os.path.abspath("src/backend"))

from app.config import settings
from app.services.planka import get_planka_auth_token

async def test_planka():
    print(f"Testing Planka integration at {settings.PLANKA_BASE_URL}")
    try:
        token = await get_planka_auth_token()
        print(f"Auth successful. Token starts with: {token[:10]}...")
        
        headers = {"Authorization": f"Bearer {token}"}
        async with httpx.AsyncClient(base_url=settings.PLANKA_BASE_URL, headers=headers) as client:
            resp = await client.get("/api/projects")
            projects = resp.json().get("items", [])
            print(f"Found {len(projects)} projects:")
            for p in projects:
                print(f"- {p['name']} (ID: {p['id']})")
                
                # Get boards
                detail_resp = await client.get(f"/api/projects/{p['id']}")
                detail = detail_resp.json()
                boards = detail.get("included", {}).get("boards", []) or detail.get("boards", [])
                for b in boards:
                    print(f"  └── Board: {b['name']} (ID: {b['id']})")
                    
                    # Get lists
                    b_detail_resp = await client.get(f"/api/boards/{b['id']}", params={"included": "lists,cards"})
                    b_detail = b_detail_resp.json()
                    lists = b_detail.get("included", {}).get("lists", []) or b_detail.get("lists", [])
                    cards = b_detail.get("included", {}).get("cards", []) or b_detail.get("cards", [])
                    print(f"      - Lists: {[l['name'] for l in lists]}")
                    print(f"      - Cards: {len(cards)}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_planka())
