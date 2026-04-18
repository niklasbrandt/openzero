"""
One-time script: delete known duplicate cards on the Nutrition board.

Run inside the backend container:
  docker exec -it openzero-backend-1 python /app/scripts/fix_nutrition_duplicates.py

Targets (keep oldest, delete extras):
  - 'spicy chicken wings'       — 3 cards, delete 2
  - 'knusprige mandel-schnitzel' — 2 cards, delete 1
  - 'parmesan-kräuter-schnitzel' — 2 cards, delete 1
"""

import asyncio
import httpx
import os
import sys

PLANKA_BASE_URL = os.environ.get("PLANKA_BASE_URL", "http://planka:1337")
PLANKA_EMAIL = os.environ.get("PLANKA_ADMIN_EMAIL", "")
PLANKA_PASSWORD = os.environ.get("PLANKA_ADMIN_PASSWORD", "")

TARGETS = {
	"spicy chicken wings",
	"knusprige mandel-schnitzel",
	"parmesan-kräuter-schnitzel",
}

async def get_token(client: httpx.AsyncClient) -> str:
	resp = await client.post(
		f"{PLANKA_BASE_URL}/api/access-tokens",
		json={"emailOrUsername": PLANKA_EMAIL, "password": PLANKA_PASSWORD},
	)
	if resp.status_code == 403:
		pending = resp.json().get("pendingToken")
		if pending:
			await client.post(f"{PLANKA_BASE_URL}/api/access-tokens/{pending}/actions/accept")
			resp = await client.post(
				f"{PLANKA_BASE_URL}/api/access-tokens",
				json={"emailOrUsername": PLANKA_EMAIL, "password": PLANKA_PASSWORD},
			)
	resp.raise_for_status()
	return resp.json()["item"]

async def main() -> None:
	async with httpx.AsyncClient(timeout=20.0) as client:
		token = await get_token(client)
		headers = {"Authorization": f"Bearer {token}"}

		# Get all projects
		resp = await client.get(f"{PLANKA_BASE_URL}/api/projects", headers=headers)
		resp.raise_for_status()
		projects = resp.json().get("items", [])

		# Find the Nutrition board
		nutrition_board = None
		for proj in projects:
			det = await client.get(f"{PLANKA_BASE_URL}/api/projects/{proj['id']}", headers=headers)
			det.raise_for_status()
			for board in det.json().get("included", {}).get("boards", []):
				if "nutrition" in board.get("name", "").lower():
					nutrition_board = board
					break
			if nutrition_board:
				break

		if not nutrition_board:
			print("ERROR: Nutrition board not found.")
			sys.exit(1)

		print(f"Found board: {nutrition_board['name']} (id={nutrition_board['id']})")

		# Fetch all cards on the board
		bd = await client.get(
			f"{PLANKA_BASE_URL}/api/boards/{nutrition_board['id']}",
			params={"included": "lists,cards"},
			headers=headers,
		)
		bd.raise_for_status()
		cards = bd.json().get("included", {}).get("cards", [])

		# Group by normalised name
		from collections import defaultdict
		groups: dict[str, list[dict]] = defaultdict(list)
		for card in cards:
			groups[card.get("name", "").lower()].append(card)

		deleted_total = 0
		for target_name in TARGETS:
			group = groups.get(target_name, [])
			if len(group) < 2:
				print(f"  '{target_name}': {len(group)} card(s) — nothing to delete.")
				continue
			# Sort by createdAt asc, keep first
			group.sort(key=lambda c: (c.get("createdAt") or "", c["id"]))
			keep = group[0]
			dupes = group[1:]
			print(f"  '{target_name}': keeping id={keep['id']} (createdAt={keep.get('createdAt')}), deleting {len(dupes)}:")
			for dupe in dupes:
				r = await client.delete(f"{PLANKA_BASE_URL}/api/cards/{dupe['id']}", headers=headers)
				status = "OK" if r.is_success else f"FAIL ({r.status_code})"
				print(f"    DELETE cards/{dupe['id']} -> {status}")
				if r.is_success:
					deleted_total += 1

		print(f"\nDone. Deleted {deleted_total} duplicate card(s).")

asyncio.run(main())
