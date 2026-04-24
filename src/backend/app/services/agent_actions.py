import re
import logging
from datetime import datetime, timedelta
from langchain_core.tools import tool
from typing import Optional

logger = logging.getLogger(__name__)

@tool
async def create_task(title: str, description: str = "", board_name: str = "Operator Board", list_name: str = "Today") -> str:
	"""Create a task in a specific board and list."""
	from app.services.planka import create_task as planka_create_task
	path = await planka_create_task(
		board_name=board_name,
		list_name=list_name,
		title=title,
		description=description
	)
	if path:
		return f"Task '{title}' created in {path}."
	return f"Failed to create task '{title}'. Check Planka connection."

@tool
async def create_project(name: str, description: str = "") -> str:
	"""Create a new project."""
	from app.services.planka import create_project as planka_create_project
	try:
		result = await planka_create_project(name=name, description=description)
		if result:
			return f"Project '{name}' created."
		return f"Failed to create project '{name}'."
	except Exception as _e:
		logger.error("create_project tool failed: %s", _e)
		return f"Failed to create project '{name}'."

@tool
async def create_event(title: str, start_time: str, end_time: Optional[str] = None) -> str:
	"""Create a new calendar event."""
	from app.models.db import LocalEvent, AsyncSessionLocal
	from app.services.calendar import create_caldav_event
	
	# Validate and parse start datetime (M-A1)
	try:
		start_dt = datetime.fromisoformat(start_time.replace('Z', ''))
	except ValueError:
		return f"Error: invalid start date '{start_time}'. Use YYYY-MM-DDThh:mm or YYYY-MM-DD HH:MM format."
	try:
		end_dt = datetime.fromisoformat(end_time.replace('Z', '')) if end_time else start_dt + timedelta(hours=1)
	except ValueError:
		return f"Error: invalid end date '{end_time}'. Use YYYY-MM-DDThh:mm or YYYY-MM-DD HH:MM format."
	
	# 1. Sync to Private CalDAV if available
	await create_caldav_event(title, start_dt, end_dt)

	# 2. Local fallback/audit write
	async with AsyncSessionLocal() as db:
		event = LocalEvent(
			summary=title,
			start_time=start_dt,
			end_time=end_dt
		)
		db.add(event)
		await db.commit()
	return f"Calendar event '{title}' created."

@tool
async def learn_memory(text: str) -> str:
	"""Learn a new memory fact."""
	from app.services.memory import store_memory
	await store_memory(text)
	return "Memory stored."

@tool
async def schedule_reminder(message: str, interval_minutes: int, duration_hours: Optional[int] = None) -> str:
	"""Schedule a periodic reminder. Interval in minutes, duration in hours."""
	# --- Input validation (H-A1) ---
	if not (1 <= interval_minutes <= 10080):
		return "Error: interval_minutes must be between 1 and 10080 (max 1 week)."
	if duration_hours is not None and not (1 <= duration_hours <= 168):
		return "Error: duration_hours must be between 1 and 168 (max 1 week)."
	message = message[:500]

	from app.common.scheduler_instance import scheduler
	from app.services.notifier import send_notification
	from apscheduler.triggers.interval import IntervalTrigger
	import pytz
	from app.services.timezone import get_current_timezone
	import uuid

	tz_str = await get_current_timezone()
	tz = pytz.timezone(tz_str)
	
	async def send_reminder_task():
		await send_notification(f"🔔 {message}")

	end_date = None
	if duration_hours:
		end_date = datetime.now(tz) + timedelta(hours=duration_hours)
	
	reminder_id = f"reminder_{uuid.uuid4().hex[:8]}"
	
	scheduler.add_job(
		send_reminder_task,
		IntervalTrigger(minutes=interval_minutes, end_date=end_date, timezone=tz),
		id=reminder_id,
		replace_existing=True
	)
	
	return f"Reminder set: '{message}' every {interval_minutes}m for {duration_hours}h. (ID: {reminder_id})"

@tool
async def schedule_persistent_custom(name: str, message: str, job_type: str, spec: str) -> str:
	"""Create a persistent scheduled task. job_type='cron' or 'interval'. spec is standard cron or 'minutes=N'."""
	# --- Input validation (H3) ---
	job_type = job_type.strip().lower()
	if job_type not in {"cron", "interval"}:
		return f"Error: job_type must be 'cron' or 'interval', got '{job_type}'."

	if job_type == "cron":
		fields = spec.strip().split()
		if len(fields) != 5 or not all(re.match(r'^[\d*/,\-]+$', f) for f in fields):
			return "Error: cron spec must be exactly 5 fields (e.g. '0 12 * * 1') using only digits, *, /, ,, -."
	elif job_type == "interval":
		allowed_keys = {"minutes", "hours", "days"}
		for part in spec.split(","):
			if "=" not in part:
				return f"Error: interval spec must be 'key=N' pairs (e.g. 'minutes=30'), got '{part.strip()}'."
			k, v = part.split("=", 1)
			if k.strip() not in allowed_keys:
				return f"Error: interval key must be one of {sorted(allowed_keys)}, got '{k.strip()}'."
			try:
				if int(v.strip()) < 1:
					raise ValueError
			except ValueError:
				return f"Error: interval value must be a positive integer, got '{v.strip()}'."

	from app.models.db import AsyncSessionLocal, CustomTask
	from sqlalchemy import select, func as sa_func
	async with AsyncSessionLocal() as session:
		count_result = await session.execute(
			select(sa_func.count()).select_from(CustomTask).where(CustomTask.is_active.is_(True))
		)
		if count_result.scalar() >= 20:
			return "Error: maximum of 20 active custom tasks reached. Deactivate an existing task first."
		task = CustomTask(name=name[:100], message=message[:500], job_type=job_type, spec=spec)
		session.add(task)
		await session.commit()
	from app.tasks.scheduler import load_custom_tasks
	await load_custom_tasks()
	return f"Persistent custom task '{name}' created and scheduled."

@tool
async def move_card(card_title_fragment: str, destination_list: str, board_name: str = "") -> str:
	"""Move a Planka card to a different list/column by searching for it by name fragment."""
	from app.services.planka import move_card as planka_move_card
	success = await planka_move_card(
		card_title_fragment=card_title_fragment,
		destination_list=destination_list,
		board_name=board_name
	)
	if success:
		return f"Card '{card_title_fragment}' moved to '{destination_list}'."
	return f"Failed to find card matching '{card_title_fragment}' on board '{board_name}'."

@tool
async def run_crew(crew_id: str, user_input: str = "Execute autonomous cycle") -> str:
	"""Trigger a specialized autonomous native crew or workflow by ID.
	Example: crew_id='nutrition'
	"""
	from app.services.crews import crew_registry
	from app.services.crews_native import native_crew_engine
	
	config = crew_registry.get(crew_id)
	if not config or not config.enabled:
		return f"Error: Crew '{crew_id}' is not defined or is disabled."

	try:
		# Strictly Native Direct-LLM Engine (Elegant, Zero-Maintenance)
		ans = await native_crew_engine.run_crew(crew_id, user_input)
		return f"Crew '{crew_id}' mission complete: {ans}"

	except Exception as e:
		if "timeout" in str(e).lower():
			logger.warning("Crew '%s' exceeded the massive budget (1h).", crew_id)
			return f"⚠ Crew '{crew_id}' exceeded massive reasoning budget (1h) and was skipped."
		import traceback
		logger.error("Crew '{crew_id}' total runtime failure: %s\n%s", e, traceback.format_exc())
		return f"Error: Communication failure with crew '{crew_id}'."

from app.services.web_search import web_search

AVAILABLE_TOOLS = [create_task, create_project, create_event, learn_memory, schedule_reminder, schedule_persistent_custom, move_card, run_crew, web_search]

SENSITIVE_ACTIONS = {"SCHEDULE_CUSTOM", "LEARN", "CREATE_PROJECT", "ADD_PERSON", "CREATE_BOARD", "CREATE_LIST", "MOVE_BOARD", "PROXIMITY_TRACK", "RUN_CREW", "SCHEDULE_CREW"}


# ─── Module-level executors for Planka mutations ─────────────────────────────
# These were previously inner closures inside parse_and_execute_actions; lifted
# so the deterministic intent_router can invoke them directly without going
# through the LLM tag parser. Behaviour is identical — the inner-closure
# wrappers call these and return the same strings.

async def execute_move_board(board_name: str, target_project: str) -> str:
	"""Move a Planka board to a different project. Returns a result string."""
	from app.services.planka import move_board as planka_move_board
	from app.config import settings as _cfg
	from app.services.planka_common import get_planka_auth_token as _gat
	import httpx as _httpx
	try:
		token = await _gat()
		async with _httpx.AsyncClient(base_url=_cfg.PLANKA_BASE_URL, timeout=15.0, headers={"Authorization": f"Bearer {token}"}) as client:
			pr = await client.get("/api/projects")
			pr.raise_for_status()
			projects = pr.json().get("items", [])
			# 1. Exact case-insensitive project match
			target_proj = next((p for p in projects if p["name"].lower() == target_project.lower()), None)
			if not target_proj:
				# 2. Substring fallback (forward direction only)
				proj_candidates = [p for p in projects if target_project.lower() in p["name"].lower()]
				if proj_candidates:
					target_proj = min(proj_candidates, key=lambda p: abs(len(p["name"]) - len(target_project)))
					logger.info("MOVE_BOARD: fuzzy-matched project '%s' -> '%s'", target_project, target_proj["name"])
			if not target_proj:
				return f"\u26a0 Project '{target_project}' not found. Check the project name in Planka."
			board_id = None
			matched_board_name = None
			for p in projects:
				p_det = await client.get(f"/api/projects/{p['id']}")
				p_det.raise_for_status()
				p_det_json = p_det.json()
				boards = p_det_json.get("included", {}).get("boards", []) or p_det_json.get("boards", [])
				match_b = next((b for b in boards if (b.get("name") or "").lower() == board_name.lower()), None)
				if not match_b:
					b_candidates = [b for b in boards if board_name.lower() in (b.get("name") or "").lower()]
					if b_candidates:
						match_b = min(b_candidates, key=lambda b: abs(len(b.get("name") or "") - len(board_name)))
						logger.info("MOVE_BOARD: fuzzy-matched board '%s' -> '%s'", board_name, match_b.get("name"))
				if match_b:
					board_id = match_b["id"]
					matched_board_name = match_b.get("name", board_name)
					logger.info("MOVE_BOARD: using board id=%s name='%s'", board_id, matched_board_name)
					break
			if not board_id:
				return f"\u26a0 Board '{board_name}' not found. Check the board name in Planka."
			success = await planka_move_board(board_id=board_id, new_project_id=target_proj["id"])
			if success:
				return f"Board '{matched_board_name}' moved to '{target_proj['name']}'."
			return f"\u26a0 Failed to move board '{matched_board_name}' to '{target_proj['name']}'. Check Planka."
	except Exception as _e:
		logger.error("execute_move_board failed: %s", _e)
		return f"\u26a0 Failed to move board '{board_name}'. System error."


async def execute_move_card(card_fragment: str, dest_list: str, board_name: str = "") -> str:
	"""Move a Planka card to a different list. Returns a result string."""
	from app.services.planka import move_card as planka_move_card
	success = await planka_move_card(card_title_fragment=card_fragment, destination_list=dest_list, board_name=board_name)
	if success:
		return f"Card '{card_fragment}' moved to '{dest_list}'."
	return f"\u26a0 Could not find card matching '{card_fragment}'. Check Planka board."


async def execute_archive_card(card_fragment: str, board_name: str = "") -> str:
	"""Archive a Planka card (move it to the Archive list). Returns a result string."""
	from app.services.planka import archive_card as planka_archive_card
	success = await planka_archive_card(card_title_fragment=card_fragment, board_name=board_name)
	if success:
		return f"Card '{card_fragment}' archived (moved to Archive list)."
	return f"\u26a0 Could not archive card '{card_fragment}'. Check Planka board."


async def execute_mark_done(card_fragment: str) -> str:
	"""Mark a Planka card as done by moving it to the Done list."""
	from app.services.planka import move_card as planka_move_card
	success = await planka_move_card(card_title_fragment=card_fragment, destination_list="Done", board_name="")
	if success:
		return f"Card '{card_fragment}' marked done."
	return f"\u26a0 Could not find card matching '{card_fragment}'. Check Planka board."

async def parse_and_execute_actions(reply: str, db=None, require_hitl: bool = False):
	"""
	Parses Semantic Action Tags from the AI reply and executes them.
	If require_hitl is True, sensitive actions are queued for approval instead of executed.
	Returns: (clean_reply, executed_cmds, pending_actions)
	"""
	from app.services.planka import create_task as planka_create_task
	from app.services.planka import create_project as planka_create_project
	from app.services.planka import create_board as planka_create_board
	from app.services.planka import create_list as planka_create_list
	from app.models.db import store_pending_thought
	import json
	
	executed_cmds = []
	pending_actions = []
	clean_reply = reply
	# Dedup: small local models often repeat identical action tags multiple times.
	# Track raw tag strings; skip any tag we have already processed in this response.
	seen_raw_tags: set[str] = set()
	# Detect whether the raw reply contained mutating ACTION tags (language-agnostic phantom guard).
	_MUTATING_TAG_RE = re.compile(r'\[?ACTION:\s*(?:CREATE_TASK|CREATE_BOARD|CREATE_LIST|CREATE_PROJECT|MOVE_BOARD|MOVE_CARD|MARK_DONE|ARCHIVE_CARD|APPEND_SHOPPING|DELETE_BOARD|DELETE_CARD|DELETE_LIST|DELETE_PROJECT)\b', re.IGNORECASE)
	_reply_had_mutating_tags = bool(_MUTATING_TAG_RE.search(reply))

	# helper to clean tag from reply
	def strip_tag(text, tag_match):
		return text.replace(tag_match, "").strip()

	async def handle_action(action_type, raw_tag, executor_coro, description, dedup_key=None):
		_key = dedup_key if dedup_key is not None else raw_tag
		if _key in seen_raw_tags:
			return True
		seen_raw_tags.add(_key)
		if require_hitl and action_type in SENSITIVE_ACTIONS:
			# Store in pending queue
			action_id = await store_pending_thought(f"ACTION:{action_type}", json.dumps({
				"tag": raw_tag,
				"description": description
			}))
			pending_actions.append({
				"id": action_id,
				"type": action_type,
				"description": description,
				"tag": raw_tag
			})
			return True
		else:
			# Execute immediately
			res = await executor_coro()
			if res:
				if isinstance(res, str):
					executed_cmds.append(res)
					# Surface ⚠ errors to the user so Z never falsely confirms a failed action
					if res.startswith("\u26a0"):
						nonlocal clean_reply
						clean_reply = clean_reply.rstrip() + "\n\n" + res
				else:
					executed_cmds.append(f"{action_type} executed.")
			return True

	# ── Scaffolding tags run FIRST so CREATE_TASK can land on the right board ──

	# newly_created_projects: project_name.lower() -> project_id
	newly_created_projects: dict[str, str] = {}
	# newly_created_boards: board_name.lower() -> board_id
	newly_created_boards: dict[str, str] = {}

	# 1. Create Project Tag — DESCRIPTION is optional (LLM may omit it).
	# IMPORTANT: use greedy [^\|\]]+ (NOT lazy +?) — lazy combined with optional \]?
	# causes the group to match only the first character of the project name.
	# Bounded quantifiers prevent polynomial backtracking on uncontrolled input (CWE-1333).
	proj_pattern = r"\[?ACTION: CREATE_PROJECT \| NAME: ([^\|\]]{1,500})(?:\s{0,20}\|\s{0,20}DESCRIPTION:\s{0,20}([^\|\]]{1,2000}))?\]?"
	for match in re.finditer(proj_pattern, reply):
		raw_tag = match.group(0)
		name = match.group(1).strip().strip('"\'')
		desc = (match.group(2) or "").strip().strip('"\'')

		async def _exec_project(name=name, desc=desc):
			try:
				from app.config import settings as _cfg
				from app.services.translations import get_all_values as _gav
				from app.services.planka_common import get_planka_auth_token as _gat
				import httpx as _httpx
				# System projects (Crews in every language) must stay as root-level Planka
				# projects because crew boards are nested directly inside them.
				_all_crew_names = _gav("crews_project_name")
				_parent_name = _cfg.AUDIT_MY_PROJECTS_PARENT
				_is_system = (
					name.lower() in {n.lower() for n in _all_crew_names}
					or name.lower() == _parent_name.lower()
				)
				if _is_system:
					result = await planka_create_project(name=name, description=desc)
					if result:
						proj_id = result.get("id") if isinstance(result, dict) else None
						if proj_id:
							newly_created_projects[name.lower()] = proj_id
						return f"Project '{name}' created."
					return f"\u26a0 Failed to create project '{name}'. Check Planka connection."
				# User-initiated project: create a board inside the parent project
				# (default "My Projects") rather than a new root-level project.
				_tok = await _gat()
				async with _httpx.AsyncClient(
					base_url=_cfg.PLANKA_BASE_URL, timeout=15.0,
					headers={"Authorization": f"Bearer {_tok}"},
				) as _client:
					_pr = await _client.get("/api/projects")
					_pr.raise_for_status()
					_parent = next(
						(p for p in _pr.json().get("items", []) if p["name"].lower() == _parent_name.lower()),
						None,
					)
					if not _parent:
						# Create the parent project on first use
						_cp = await _client.post("/api/projects", json={"name": _parent_name, "type": "private"})
						if _cp.status_code >= 400:
							_cp = await _client.post("/api/projects", json={"name": _parent_name, "isPublic": False})
						_cp.raise_for_status()
						_parent = _cp.json().get("item") or _cp.json()
					_parent_id = _parent["id"]
					_board = await planka_create_board(project_id=_parent_id, name=name)
					if _board and _board.get("id"):
						newly_created_boards[name.lower()] = _board["id"]
						return f"Project '{name}' created as a board in '{_parent_name}'."
					return f"\u26a0 Failed to create project '{name}' in '{_parent_name}'. Check Planka connection."
			except Exception as _e:
				logger.error("CREATE_PROJECT failed: %s", _e)
				return f"\u26a0 Failed to create project '{name}'. System error."

		_dedup_proj = f"CREATE_PROJECT:{name.strip().lower()}"
		await handle_action("CREATE_PROJECT", raw_tag, _exec_project, f"Create project '{name}'", dedup_key=_dedup_proj)
		clean_reply = strip_tag(clean_reply, raw_tag)

	# 2. Create Board Tag — uses newly_created_projects as a fast path.
	board_pattern = r"\[?ACTION: CREATE_BOARD \| PROJECT: ([^\|\]]+) \| NAME: ([^\|\]]+)\]?"
	for match in re.finditer(board_pattern, reply):
		raw_tag = match.group(0)
		proj_name, board_name = match.groups()
		proj_name = proj_name.strip().strip('"\'')
		board_name = board_name.strip().strip('"\'')

		async def _exec_board(proj_name=proj_name, board_name=board_name):
			try:
				# If CREATE_PROJECT was redirected to a board inside "My Projects",
				# there is no Planka project with proj_name to nest a second board into.
				# The project-as-board is already in newly_created_boards — skip.
				if proj_name.lower() in newly_created_boards:
					return f"Board '{proj_name}' already created in 'My Projects' — skipping nested board '{board_name}'."
				from app.services.planka import get_planka_auth_token
				import httpx
				from app.config import settings
				token = await get_planka_auth_token()
				async with httpx.AsyncClient(timeout=30.0, base_url=settings.PLANKA_BASE_URL, headers={"Authorization": f"Bearer {token}"}) as client:
					# Fast path: project just created in this same response
					proj_id = newly_created_projects.get(proj_name.lower())
					if not proj_id:
						resp = await client.get("/api/projects")
						projects = resp.json().get("items", [])
						for p in projects:
							if p["name"].lower() == proj_name.lower():
								proj_id = p["id"]
								break
					if not proj_id:
						return f"\u26a0 Project '{proj_name}' not found. Board not created."
					board_result = await planka_create_board(project_id=proj_id, name=board_name)
					if board_result and board_result.get("id"):
						newly_created_boards[board_name.lower()] = board_result["id"]
						return f"Board '{board_name}' created in '{proj_name}'."
					return f"\u26a0 Failed to create board '{board_name}'. Check Planka."
			except Exception as _e:
				logger.error("CREATE_BOARD failed: %s", _e)
				return f"\u26a0 Failed to create board '{board_name}'. System error."

		_dedup_board = f"CREATE_BOARD:{proj_name.strip().lower()}:{board_name.strip().lower()}"
		await handle_action("CREATE_BOARD", raw_tag, _exec_board, f"Create board '{board_name}' in project '{proj_name}'", dedup_key=_dedup_board)
		clean_reply = strip_tag(clean_reply, raw_tag)

	# 3. Create List (Column) Tag — with auto-board-creation fallback.
	# LLMs often skip CREATE_BOARD and reference the project name as the board name.
	# If the board is not found, we try to auto-create it inside the project.
	list_pattern = r"\[?ACTION: CREATE_LIST \| BOARD: ([^\|\]]+) \| NAME: ([^\|\]]+)\]?"
	for match in re.finditer(list_pattern, reply):
		raw_tag = match.group(0)
		board_name, list_name = match.groups()
		board_name = board_name.strip().strip('"\'')
		list_name = list_name.strip().strip('"\'')

		if not list_name:
			logger.warning("CREATE_LIST: skipping tag with empty list name (board='%s')", board_name)
			clean_reply = strip_tag(clean_reply, raw_tag)
			continue

		async def _exec_list(board_name=board_name, list_name=list_name):
			try:
				from app.services.planka_common import get_planka_auth_token
				import httpx
				from app.config import settings

				async def _post_list_on_board(bid: str) -> str:
					token = await get_planka_auth_token()
					async with httpx.AsyncClient(base_url=settings.PLANKA_BASE_URL, timeout=15.0, headers={"Authorization": f"Bearer {token}"}) as client:
						# Dedup: check if list already exists on this board
						try:
							b_det = await client.get(f"/api/boards/{bid}", params={"included": "lists"})
							b_det.raise_for_status()
							for lst in b_det.json().get("included", {}).get("lists", []):
								if (lst.get("name") or "").lower() == list_name.lower():
									return f"List '{list_name}' already exists in '{board_name}'."
						except Exception as _de:
							logger.debug("board detail fetch failed for bid=%s: %s", bid, _de)
						try:
							resp = await client.post(f"/api/boards/{bid}/lists", json={"name": list_name, "type": "active", "position": 65535})
							resp.raise_for_status()
							return f"List '{list_name}' created in '{board_name}'."
						except Exception as _le:
							logger.error("_post_list_on_board failed for bid=%s list=%s: %s", bid, list_name, _le)
							return None

				# Fast path A: board was just created in this response
				board_id = newly_created_boards.get(board_name.lower())
				if not board_id and len(newly_created_boards) == 1:
					# LLM used a different name for the same board — use the only one created
					board_id = next(iter(newly_created_boards.values()))
				if board_id:
					_r = await _post_list_on_board(board_id)
					if _r:
						return _r

				# Fast path B: board pre-existed — global search
				result = await planka_create_list(board_name=board_name, list_name=list_name)
				if result:
					return f"List '{list_name}' created in '{board_name}'."

				# Fallback C1: board_name matches a project created this response
				proj_id: str | None = newly_created_projects.get(board_name.lower())
				if not proj_id and len(newly_created_projects) == 1:
					proj_id = next(iter(newly_created_projects.values()))
				if proj_id:
					board_result = await planka_create_board(project_id=proj_id, name=board_name)
					if board_result and board_result.get("id"):
						bid = board_result["id"]
						newly_created_boards[board_name.lower()] = bid
						_r1 = await _post_list_on_board(bid)
						if _r1:
							return _r1

				# Fallback C2: search existing Planka projects by name
				_tok2 = await get_planka_auth_token()
				async with httpx.AsyncClient(base_url=settings.PLANKA_BASE_URL, timeout=30.0, headers={"Authorization": f"Bearer {_tok2}"}) as _c2:
					_pr = await _c2.get("/api/projects")
					_pr.raise_for_status()
					_live = _pr.json().get("items", [])
				live_proj_id: str | None = None
				for _lp in _live:
					if _lp["name"].lower() == board_name.lower():
						live_proj_id = _lp["id"]
						break
				if not live_proj_id and len(_live) == 1:
					live_proj_id = _live[0]["id"]
				if live_proj_id:
					_br = await planka_create_board(project_id=live_proj_id, name=board_name)
					if _br and _br.get("id"):
						_bid = _br["id"]
						newly_created_boards[board_name.lower()] = _bid
						_r2 = await _post_list_on_board(_bid)
						if _r2:
							return _r2

				# Fallback C3: no matching project — auto-create project + board + list
				_np = await planka_create_project(name=board_name, description="")
				if _np:
					_npid = _np.get("id") if isinstance(_np, dict) else None
					if _npid:
						newly_created_projects[board_name.lower()] = _npid
						_br2 = await planka_create_board(project_id=_npid, name=board_name)
						if _br2 and _br2.get("id"):
							_bid2 = _br2["id"]
							newly_created_boards[board_name.lower()] = _bid2
							_r3 = await _post_list_on_board(_bid2)
							if _r3:
								return _r3

				return f"\u26a0 Failed to create list '{list_name}' \u2014 board '{board_name}' not found."
			except Exception as _e:
				logger.error("CREATE_LIST failed: %s", _e)
				return f"\u26a0 Failed to create list '{list_name}'. System error."

		_dedup_list = f"CREATE_LIST:{board_name.strip().lower()}:{list_name.strip().lower()}"
		await handle_action("CREATE_LIST", raw_tag, _exec_list, f"Create list '{list_name}' on board '{board_name}'", dedup_key=_dedup_list)
		clean_reply = strip_tag(clean_reply, raw_tag)

	# 4. Create Task Tag — runs AFTER scaffolding so the board/list already exists.
	# DESCRIPTION is optional — captured when present, defaults to empty string.
	# Pattern allows ] inside description content via a bounded capture group.
	# Input is capped before iteration to prevent polynomial backtracking (CWE-1333).
	task_pattern = r"\[?ACTION: CREATE_TASK \| BOARD: ([^\|\]]{1,500}) \| LIST: ([^\|\]]{1,500}) \| TITLE: ([^\|\]]{1,500})(?:\s*\|\s*DESCRIPTION:\s*([\s\S]{0,20000}?))?\]"
	for match in re.finditer(task_pattern, reply[:200_000]):
		raw_tag = match.group(0)
		board, llist, title, desc = match.groups()
		board = board.strip().strip('"\'')
		llist = llist.strip().strip('"\'')
		title = title.strip().strip('"\'')
		desc = (desc or "").strip()

		async def _exec_task(board=board, llist=llist, title=title, desc=desc):
			path = await planka_create_task(board_name=board, list_name=llist, title=title, description=desc)
			if path:
				return f"Task '{title}' created in {path}."
			return f"\u26a0 Failed to create task '{title}'. Check Planka connection."

		_dedup_task = f"CREATE_TASK:{board.strip().lower()}:{llist.strip().lower()}:{title.strip().lower()}"
		await handle_action("CREATE_TASK", raw_tag, _exec_task, f"Create task '{title}' on {board}", dedup_key=_dedup_task)
		clean_reply = strip_tag(clean_reply, raw_tag)

	# 3. Create Event Tag
	event_pattern = r"\[?ACTION: CREATE_EVENT \| TITLE: ([^\|\]]+) \| START: ([^\|\]]+) \| END: ([^\|\]]+)\]?"
	for match in re.finditer(event_pattern, reply):
		raw_tag = match.group(0)
		title, start, end = match.groups()
		# Clean potential quotes from model output
		title = title.strip().strip('"').strip("'")
		# Skip events where the LLM emitted a format placeholder (e.g. YYYY-MM-DD HH:MM)
		if re.search(r'YYYY|MM-DD|HH:MM', start.strip()):
			clean_reply = strip_tag(clean_reply, raw_tag)
			continue

		async def _exec_event(title=title, start=start, end=end):
			try:
				event_result = await create_event.ainvoke({"title": title, "start_time": start.strip(), "end_time": end.strip()})
				# The tool returns an error string starting with "Error:" on failure
				if isinstance(event_result, str) and event_result.lower().startswith("error"):
					return f"\u26a0 Event '{title}' not created: {event_result}"
				return f"Event '{title}' scheduled."
			except Exception as _e:
				logger.error("CREATE_EVENT failed: %s", _e)
				return f"\u26a0 Failed to create event '{title}'. Calendar sync error."

		await handle_action("CREATE_EVENT", raw_tag, _exec_event, f"Schedule event: {title} ({start.strip()})")
		clean_reply = strip_tag(clean_reply, raw_tag)

	# 5. Remind Tag
	remind_pattern = r"\[?ACTION: REMIND \| MESSAGE: ([^\|\]]+) \| INTERVAL: ([^\|\]]+) \| DURATION: ([^\|\]]+)\]?"
	for match in re.finditer(remind_pattern, reply):
		raw_tag = match.group(0)
		message, interval, duration = match.groups()
		message = message.strip()
		
		async def _exec_remind(message=message, interval=interval, duration=duration):
			try:
				res = await schedule_reminder.ainvoke({
					"message": message,
					"interval_minutes": int(interval.strip()),
					"duration_hours": int(duration.strip())
				})
				if isinstance(res, str) and res.lower().startswith("error"):
					return f"\u26a0 Reminder not set: {res}"
				return res
			except Exception as _e:
				logger.error("REMIND failed: %s", _e)
				return f"\u26a0 Failed to schedule reminder '{message[:60]}'. Check scheduler."

		await handle_action("REMIND", raw_tag, _exec_remind, f"Set reminder: {message} every {interval.strip()}m")
		clean_reply = strip_tag(clean_reply, raw_tag)

	# 6. Persistent Custom Tag
	custom_pattern = r"\[?ACTION: SCHEDULE_CUSTOM \| NAME: ([^\|\]]+) \| MESSAGE: ([^\|\]]+) \| TYPE: ([^\|\]]+) \| SPEC: ([^\|\]]+)\]?"
	for match in re.finditer(custom_pattern, reply):
		raw_tag = match.group(0)
		name, msg, ttype, spec = match.groups()
		name, msg, ttype, spec = name.strip(), msg.strip(), ttype.strip().lower(), spec.strip()

		async def _exec_custom(name=name, msg=msg, ttype=ttype, spec=spec):
			try:
				res = await schedule_persistent_custom.ainvoke({
					"name": name,
					"message": msg,
					"job_type": ttype,
					"spec": spec
				})
				if isinstance(res, str) and res.lower().startswith("error"):
					return f"\u26a0 Custom task not scheduled: {res}"
				return res
			except Exception as _e:
				logger.error("SCHEDULE_CUSTOM failed: %s", _e)
				return f"\u26a0 Failed to schedule custom task '{name[:60]}'. Check scheduler."

		await handle_action("SCHEDULE_CUSTOM", raw_tag, _exec_custom, f"Schedule persistent task '{name}' ({spec})")
		clean_reply = strip_tag(clean_reply, raw_tag)

	# 7. Add Person Tag
	person_pattern = r"\[?ACTION: ADD_PERSON \| NAME: ([^\|\]]+) \| RELATIONSHIP: ([^\|\]]+) \| CONTEXT: ([^\|\]]+) \| CIRCLE: ([^\|\]]+)\]?"
	for match in re.finditer(person_pattern, reply):
		raw_tag = match.group(0)
		name, rel, ctx, circle = match.groups()
		name, rel, ctx, circle = name.strip(), rel.strip(), ctx.strip(), circle.strip()

		async def _exec_person(name=name, rel=rel, ctx=ctx, circle=circle):
			try:
				from app.models.db import Person, AsyncSessionLocal
				# --- Input validation (M-A2) ---
				circle_clean = circle.lower()
				if circle_clean not in {"inner", "close", "outer", "identity"}:
					circle_clean = "outer"
				async with AsyncSessionLocal() as session:
					p = Person(name=name[:100], relationship=rel[:100], context=ctx[:1000], circle_type=circle_clean)
					session.add(p)
					await session.commit()
				return f"Added {name} to your circle."
			except Exception as _e:
				logger.error("ADD_PERSON failed: %s", _e)
				return f"\u26a0 Failed to add '{name}' to circle. Check database."

		await handle_action("ADD_PERSON", raw_tag, _exec_person, f"Add {name} ({rel}) to circle")
		clean_reply = strip_tag(clean_reply, raw_tag)

	# 5. Learn Memory Tag
	learn_pattern = r"\[?ACTION: LEARN \| TEXT: ([^\]]+)\]?"
	for match in re.finditer(learn_pattern, reply):
		raw_tag = match.group(0)
		text = match.group(1).strip()

		async def _exec_learn(text=text):
			try:
				from app.services.memory import store_memory
				await store_memory(text)
				# store_memory returns None; it only raises on Qdrant/embed failure
				# (noise-filtered inputs are silently dropped — that is expected behaviour)
				return "Memory updated."
			except Exception as _e:
				logger.error("LEARN failed: %s", _e)
				return "\u26a0 Failed to store memory. Check Qdrant connection."

		await handle_action("LEARN", raw_tag, _exec_learn, f"Learn: {text}")
		clean_reply = strip_tag(clean_reply, raw_tag)

	# 6. Proximity Track Tag
	prox_pattern = r"\[?ACTION: PROXIMITY_TRACK \| TASKS: ([^\|\]]+) \| BREAKDOWN: ([^\|\]]+) \| END: ([^\|\]]+)\]?"
	for match in re.finditer(prox_pattern, reply):
		raw_tag = match.group(0)
		tasks, breakdown, end_val = match.groups()
		tasks, breakdown, end_val = tasks.strip(), breakdown.strip(), end_val.strip()

		async def _exec_track(tasks=tasks, breakdown=breakdown, end_val=end_val):
			try:
				from app.models.db import TrackingSession, AsyncSessionLocal
				import json
				async with AsyncSessionLocal() as session:
					# 1. Parse milestones
					milestones = []
					now = datetime.now()

					# Simple splitter for "task name [ends HH:MM]"
					items = [it.strip() for it in breakdown.split(';') if it.strip()]
					for it in items:
						try:
							# Extract "task name" and "HH:MM"
							parts = re.split(r'\s*\[ends\s+([^\]]+)\]', it)
							if len(parts) >= 2:
								task_name, due_val = parts[0], parts[1]
								# Fix up HH:MM to absolute
								h, m = map(int, due_val.strip().split(':'))
								due_dt = now.replace(hour=h, minute=m, second=0, microsecond=0)
								# Handle next-day rollover if needed (rare for short tracks)
								if due_dt < now: due_dt += timedelta(days=1)
								milestones.append({"task": task_name.strip(), "due_at": due_dt.isoformat(), "sent": False})
						except (ValueError, AttributeError): continue  # malformed HH:MM -- skip milestone

					try:
						# Handle YYYY-MM-DD HH:MM for overall END
						end_dt = datetime.strptime(end_val, "%Y-%m-%d %H:%M")
					except ValueError:
						# Fallback
						end_dt = datetime.now() + timedelta(hours=2)

					session.add(TrackingSession(
						tasks=tasks,
						milestones_json=json.dumps(milestones),
						end_time=end_dt
					))
					await session.commit()
				return "Precision Tracking initiated."
			except Exception as _e:
				logger.error("PROXIMITY_TRACK failed: %s", _e)
				return "\u26a0 Failed to initiate Precision Tracking. Check database."

		await handle_action("PROXIMITY_TRACK", raw_tag, _exec_track, f"Initiate tracking: {tasks}")
		clean_reply = strip_tag(clean_reply, raw_tag)

	# 10. Run Crew Tag
	# Alert #379/380: Avoid polynomial backtracking (ReDoS) by simplifying whitespace
	crew_run_pattern = r"\[?ACTION: RUN_CREW \| CREW: ([^\|\]]+) \| INPUT: ([^\]]+)\]?"
	for match in re.finditer(crew_run_pattern, reply):
		raw_tag = match.group(0)
		crew_id, user_inputs = match.groups()
		crew_id = crew_id.strip()
		user_inputs = user_inputs.strip()

		async def _exec_run_crew(crew_id=crew_id, user_inputs=user_inputs):
			from app.services.crews import crew_registry
			from app.services.crews_native import native_crew_engine
			
			# Recursive vulnerability protection
			if re.search(r'\[ACTION:', user_inputs, flags=re.IGNORECASE):
				logger.warning("Recursive agentic execution prevented in RUN_CREW: %s", user_inputs)
				return "\u26a0 Error: Nested ACTION tags are strictly prohibited."
				
			config = crew_registry.get(crew_id)
			if not config or not config.enabled:
				return f"\u26a0 Error: Crew '{crew_id}' is not defined or is disabled."
				
			try:
				ans = await native_crew_engine.run_crew(crew_id, user_inputs)
				executed_cmds.append(f"__CREW_RUN__:{config.id}")
				return ans
			except Exception as e:
				logger.error("RUN_CREW failed for '%s': %s", crew_id, e)
				return f"\u26a0 Error: Execution failure for crew '{crew_id}'."

		await handle_action("RUN_CREW", raw_tag, _exec_run_crew, f"Run Crew: {crew_id}")
		clean_reply = strip_tag(clean_reply, raw_tag)

	# 11. Schedule Crew Tag
	# Alert #380: Similar fix for SCHEDULE_CREW
	crew_sched_pattern = r"\[?ACTION: SCHEDULE_CREW \| CREW: ([^\|\]]+) \| CRON: ([^\|\]]+) \| INPUT: ([^\]]+)\]?"
	for match in re.finditer(crew_sched_pattern, reply):
		raw_tag = match.group(0)
		crew_id, cron_spec, user_inputs = match.groups()
		crew_id, cron_spec, user_inputs = crew_id.strip(), cron_spec.strip(), user_inputs.strip()

		async def _exec_schedule_crew(crew_id=crew_id, cron_spec=cron_spec, user_inputs=user_inputs):
			from app.common.scheduler_instance import scheduler
			from apscheduler.triggers.cron import CronTrigger
			from app.services.timezone import get_current_timezone
			from app.services.crews import crew_registry
			from app.services.crews_native import native_crew_engine
			import pytz
			
			config = crew_registry.get(crew_id)
			if not config or not config.enabled:
				return f"\u26a0 Error: Crew '{crew_id}' is not found or is disabled."
				
			fields = cron_spec.split()
			if len(fields) != 5 or not all(re.match(r'^[\d*/,\-]+$', f) for f in fields):
				return "\u26a0 Error: CRON spec must be exactly 5 fields using only digits, *, /, ,, - (e.g. '0 12 * * 1')."
			
			tz_str = await get_current_timezone()
			tz = pytz.timezone(tz_str)
			
			try:
				trigger = CronTrigger(minute=fields[0], hour=fields[1], day=fields[2], month=fields[3], day_of_week=fields[4], timezone=tz)
				
				async def run_scheduled_crew():
					logger.info("Executing scheduled crew %s", crew_id)
					try:
						await native_crew_engine.run_crew(crew_id, user_inputs)
					except Exception as e:
						logger.error("Scheduled CREW execution failed: %s", e)
				
				job_id = f"custom_crew_{crew_id}"
				scheduler.add_job(
					run_scheduled_crew,
					trigger,
					id=job_id,
					replace_existing=True
				)
				return f"Scheduled crew '{crew_id}' with cron '{cron_spec}'."
			except Exception as e:
				logger.error("SCHEDULE_CREW failed for '%s': %s", crew_id, e)
				return f"\u26a0 Error: Scheduling failure for crew '{crew_id}'."

		await handle_action("SCHEDULE_CREW", raw_tag, _exec_schedule_crew, f"Schedule Crew {crew_id} at {cron_spec}")
		clean_reply = strip_tag(clean_reply, raw_tag)

	# 9. Move Card Tag
	move_card_pattern = r"\[?ACTION: MOVE_CARD \| CARD: ([^\|\]]+) \| LIST: ([^\|\]]+)(?: \| BOARD: ([^\|\]]+))?\]?"
	for match in re.finditer(move_card_pattern, reply):
		raw_tag = match.group(0)
		card_frag = match.group(1).strip()
		dest_list = match.group(2).strip()
		board = (match.group(3) or "").strip()
		
		async def _exec_move(card_frag=card_frag, dest_list=dest_list, board=board):
			return await execute_move_card(card_frag, dest_list, board)

		await handle_action("MOVE_CARD", raw_tag, _exec_move, f"Move card '{card_frag}' to '{dest_list}'")
		clean_reply = strip_tag(clean_reply, raw_tag)

	# 10. Mark Done Tag (shortcut: moves card to Done list)
	mark_done_pattern = r"\[?ACTION: MARK_DONE \| CARD: ([^\|\]]+)\]?"
	for match in re.finditer(mark_done_pattern, reply):
		raw_tag = match.group(0)
		card_frag = match.group(1).strip()

		async def _exec_done(card_frag=card_frag):
			return await execute_mark_done(card_frag)

		await handle_action("MARK_DONE", raw_tag, _exec_done, f"Mark card '{card_frag}' as done")
		clean_reply = strip_tag(clean_reply, raw_tag)

	# 8. Set Nudge Interval Tag
	nudge_interval_pattern = r"\[?ACTION: SET_NUDGE_INTERVAL \| TASK: ([^\|\]]+) \| INTERVAL: ([^\|\]]+)\]?"
	for match in re.finditer(nudge_interval_pattern, reply):
		raw_tag = match.group(0)
		task_f, interval_raw = match.groups()
		task_f = task_f.strip()

		async def _exec_nudge(task_f=task_f, interval_raw=interval_raw):
			try:
				minutes = int(interval_raw.strip())
				if minutes < 1:
					raise ValueError("interval must be >= 1")
				from app.services.follow_up import set_nudge_override
				set_nudge_override(task_f, minutes)
				return f"Nudge interval for '{task_f}' set to {minutes} min."
			except ValueError as _ve:
				logger.warning("SET_NUDGE_INTERVAL parse error: %s", _ve)
				return f"\u26a0 Could not set nudge interval for '{task_f}'. Invalid interval value."
			except Exception as _e:
				logger.error("SET_NUDGE_INTERVAL failed: %s", _e)
				return f"\u26a0 Failed to set nudge interval for '{task_f}'. Check scheduler."

		await handle_action("SET_NUDGE_INTERVAL", raw_tag, _exec_nudge, f"Set nudge interval for '{task_f}' to {interval_raw.strip()}m")
		clean_reply = strip_tag(clean_reply, raw_tag)

	# 12. Append Shopping List Tag — appends items to the weekly shopping card.
	shopping_pattern = r"\[?ACTION: APPEND_SHOPPING \| ITEMS: ([^\]]{1,4000})\]?"
	for match in re.finditer(shopping_pattern, reply):
		raw_tag = match.group(0)
		items_text = match.group(1).strip()

		async def _exec_shopping(items_text=items_text):
			try:
				from app.services.shopping_list import append_shopping_items
				ok = await append_shopping_items(items_text)
				if ok:
					return "Shopping list updated."
				return "\u26a0 Failed to update shopping list. Nutrition board not found."
			except Exception as _e:
				logger.error("APPEND_SHOPPING failed: %s", _e)
				return "\u26a0 Failed to update shopping list."

		await handle_action("APPEND_SHOPPING", raw_tag, _exec_shopping, "Append items to weekly shopping list")
		clean_reply = strip_tag(clean_reply, raw_tag)

	# Archive Card Tag — moves card to the "Archive" list instead of deleting.
	# Deletion of projects/boards is intentionally NOT available as an agent action.
	# Agents can only archive (reversible). Hard deletion is a manual user action in Planka.
	archive_card_pattern = r"\[?ACTION: ARCHIVE_CARD \| CARD: ([^\|\]]+)(?: \| BOARD: ([^\|\]]+))?\]?"
	for match in re.finditer(archive_card_pattern, reply):
		raw_tag = match.group(0)
		card_frag = match.group(1).strip()
		board = (match.group(2) or "").strip()

		async def _exec_archive_card(card_frag=card_frag, board=board):
			return await execute_archive_card(card_frag, board)

		await handle_action("ARCHIVE_CARD", raw_tag, _exec_archive_card, f"Archive card '{card_frag}'")
		clean_reply = strip_tag(clean_reply, raw_tag)

	# Move Board Tag — patches a board's projectId to move it to a different project.
	move_board_pattern = r"\[?ACTION: MOVE_BOARD \| BOARD: ([^\|\]]+) \| TO_PROJECT: ([^\|\]]+)\]?"
	for match in re.finditer(move_board_pattern, reply):
		raw_tag = match.group(0)
		mb_board_name = match.group(1).strip().strip('"\'')
		mb_target_project = match.group(2).strip().strip('"\'"')

		async def _exec_move_board(mb_board_name=mb_board_name, mb_target_project=mb_target_project):
			return await execute_move_board(mb_board_name, mb_target_project)

		_dedup_mb = f"MOVE_BOARD:{mb_board_name.strip().lower()}:{mb_target_project.strip().lower()}"
		await handle_action("MOVE_BOARD", raw_tag, _exec_move_board, f"Move board '{mb_board_name}' to project '{mb_target_project}'", dedup_key=_dedup_mb)
		clean_reply = strip_tag(clean_reply, raw_tag)

	# --- FINAL AGGRESSIVE HYGIENE ---
	# This prevents 'leaking' of internal agent thoughts or malformed tags to the user.
	
	# 1. First Pass: Strip known bracketed action tags
	# Use [^\]] to avoid polynomial backtracking on adversarial input.
	clean_reply = re.sub(r'\[?ACTION:[^\]]*\]?', '', clean_reply, flags=re.IGNORECASE)
	
	# 2. Second Pass: Split into lines and filter out anything that looks like internal metadata
	lines = clean_reply.split('\n')
	filtered_lines = []
	
	# Markers that indicate a line is internal metadata/action logging
	# We catch these anywhere in the line now for maximum safety
	bad_tokens = ["ACTION:", "CONTEXT:", "MEMORY:", "UPDATE_CONTEXT", "TAGGED:", "MISSION:", "LEARN", "ADD_FACT"]
	
	for line in lines:
		trimmed = line.strip()
		if not trimmed:
			filtered_lines.append(line)
			continue
			
		# If any bad token exists in the line (case-insensitive)
		if any(token.upper() in trimmed.upper() for token in bad_tokens):
			continue
			
		# Skip lines that are purely symbols or brackets
		if re.match(r'^[\s\W\[\]\|]+$', trimmed):
			continue
			
		filtered_lines.append(line)
	
	clean_reply = "\n".join(filtered_lines).strip()

	# 3. Final Polish: Clean up hanging artifacts and excess whitespace
	clean_reply = re.sub(r'\]\s*$', '', clean_reply, flags=re.MULTILINE)
	clean_reply = re.sub(r'^\s*\|\s*', '', clean_reply, flags=re.MULTILINE)
	clean_reply = re.sub(r'\n{3,}', '\n\n', clean_reply).strip()

	# If execution produced any failure notices (⚠), surface them even when the
	# LLM already wrote a success-sounding reply (prevents silent false-confirms).
	# This must run BEFORE the empty-reply fallback so failures aren't duplicated.
	failure_notices = [c for c in executed_cmds if c.startswith("\u26a0")]
	if failure_notices and clean_reply:
		clean_reply = clean_reply.rstrip() + "\n\n" + "\n".join(failure_notices)

	# If the LLM response contained ONLY tags (all stripped → empty), fall back to
	# a summary of what was executed.  Because executed_cmds already contains the
	# ⚠ notices we must NOT append them again — just join everything once.
	if not clean_reply and (executed_cmds or pending_actions):
		parts = executed_cmds + [f"⏳ Awaiting approval: {p['description']}" for p in pending_actions]
		clean_reply = "\n".join(parts)

	# Safety net: strip any remaining ROUTE tags (including malformed variants where
	# the model omitted 'ACTION:' or the closing ']') before the reply reaches the user.
	clean_reply = re.sub(
		r'\[(?:ACTION:\s*)?ROUTE\s*\|\s*CREW:\s*[a-z0-9_-]+\s*\]?',
		'', clean_reply, flags=re.IGNORECASE
	).strip()

	# Strip [AUDIT:...] tags from visible reply — these are internal self-verification
	# markers only. Agent-rules.md states they are never shown to the user.
	# Linear pattern [^\]] avoids catastrophic backtracking (CWE-1333).
	clean_reply = re.sub(
		r'\[AUDIT:[^\]]{0,300}\]?',
		'', clean_reply, flags=re.IGNORECASE
	).strip()

	# Strip lines that look like leaked internal instruction fragments.
	# These patterns match confabulated audit/system prompt echoes produced by
	# small models when audit context is present in the conversation history.
	_INTERNAL_INSTRUCTION_RE = re.compile(
		r'^\s*(?:tags from conversations\b|Verify all actions\b|\[AUDIT:|\[ACTION:)',
		re.IGNORECASE | re.MULTILINE,
	)
	if _INTERNAL_INSTRUCTION_RE.search(clean_reply):
		lines_out = [
			l for l in clean_reply.splitlines()
			if not _INTERNAL_INSTRUCTION_RE.match(l)
		]
		clean_reply = '\n'.join(lines_out).strip()

	# Structural phantom guard: raw reply contained mutating ACTION tags but nothing ran.
	# Language-agnostic — does not rely on confirmation phrases.
	if _reply_had_mutating_tags and not executed_cmds and not pending_actions:
		try:
			from app.services.translations import get_translations, get_user_lang
			_lang = "en"
			try:
				_lang = await get_user_lang()
			except Exception:
				pass
			_t = get_translations(_lang)
			_warn = _t.get("action_not_executed", "No action was executed — please try again.")
		except Exception:
			_warn = "No action was executed — please try again."
		clean_reply = clean_reply.rstrip() + "\n\n\u26a0 " + _warn
		logger.warning("parse_and_execute_actions: phantom confirmation — raw reply had mutating ACTION tags but nothing executed")

	return clean_reply, executed_cmds, pending_actions

async def execute_crew_programmatically(crew_id: str, input_context: str = "Scheduled execution sequence"):
	"""
	Public API for the Scheduler to legitimately run Crews without a raw LLM action tag.
	Uses the native crew engine.
	"""
	from app.services.crews import crew_registry
	from app.services.crews_native import native_crew_engine

	config = crew_registry.get(crew_id)
	if not config or not config.enabled:
		logger.warning("Programmatic execution aborted: Crew '%s' not found or disabled.", crew_id)
		return

	logger.info("Programmatically executing Crew '%s'...", crew_id)

	try:
		ans = await native_crew_engine.run_crew(crew_id, input_context)
		logger.info("Crew '%s' completed. Output length: %d", crew_id, len(ans))
	except Exception as e:
		logger.error("Programmatic execute_crew failed for '%s': %s", crew_id, e)
