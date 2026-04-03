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
		await send_notification(f"🔔 *Z: Periodic Reminder*\n\n{message}")

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

AVAILABLE_TOOLS = [create_task, create_project, create_event, learn_memory, schedule_reminder, schedule_persistent_custom, move_card, run_crew]

SENSITIVE_ACTIONS = {"SCHEDULE_CUSTOM", "LEARN", "CREATE_PROJECT", "ADD_PERSON", "CREATE_BOARD", "CREATE_LIST", "PROXIMITY_TRACK", "RUN_CREW", "SCHEDULE_CREW"}

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
	from app.services.planka import move_card as planka_move_card
	from app.models.db import store_pending_thought
	import json
	
	executed_cmds = []
	pending_actions = []
	clean_reply = reply

	# helper to clean tag from reply
	def strip_tag(text, tag_match):
		return text.replace(tag_match, "").strip()

	async def handle_action(action_type, raw_tag, executor_coro, description):
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
	proj_pattern = r"\[?ACTION: CREATE_PROJECT \| NAME: ([^\|\]]+)(?:\s*\|\s*DESCRIPTION:\s*([^\|\]]+))?\]?"
	for match in re.finditer(proj_pattern, reply):
		raw_tag = match.group(0)
		name = match.group(1).strip().strip('"\'')
		desc = (match.group(2) or "").strip().strip('"\'')

		async def _exec_project(name=name, desc=desc):
			try:
				result = await planka_create_project(name=name, description=desc)
				if result:
					proj_id = result.get("id") if isinstance(result, dict) else None
					if proj_id:
						newly_created_projects[name.lower()] = proj_id
					return f"Project '{name}' created."
				return f"\u26a0 Failed to create project '{name}'. Check Planka connection."
			except Exception as _e:
				logger.error("CREATE_PROJECT failed: %s", _e)
				return f"\u26a0 Failed to create project '{name}'. System error."

		await handle_action("CREATE_PROJECT", raw_tag, _exec_project, f"Create project '{name}'")
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

		await handle_action("CREATE_BOARD", raw_tag, _exec_board, f"Create board '{board_name}' in project '{proj_name}'")
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

		async def _exec_list(board_name=board_name, list_name=list_name):
			try:
				from app.services.planka_common import get_planka_auth_token
				import httpx
				from app.config import settings

				async def _post_list_on_board(bid: str) -> str:
					token = await get_planka_auth_token()
					async with httpx.AsyncClient(base_url=settings.PLANKA_BASE_URL, timeout=15.0, headers={"Authorization": f"Bearer {token}"}) as client:
						resp = await client.post(f"/api/boards/{bid}/lists", json={"name": list_name, "position": 65535})
						resp.raise_for_status()
					return f"List '{list_name}' created in '{board_name}'."

				# Fast path A: board was just created in this response
				board_id = newly_created_boards.get(board_name.lower())
				if board_id:
					return await _post_list_on_board(board_id)

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
						return await _post_list_on_board(bid)

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
						return await _post_list_on_board(_bid)

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
							return await _post_list_on_board(_bid2)

				return f"\u26a0 Failed to create list '{list_name}' \u2014 board '{board_name}' not found."
			except Exception as _e:
				logger.error("CREATE_LIST failed: %s", _e)
				return f"\u26a0 Failed to create list '{list_name}'. System error."

		await handle_action("CREATE_LIST", raw_tag, _exec_list, f"Create list '{list_name}' on board '{board_name}'")
		clean_reply = strip_tag(clean_reply, raw_tag)

	# 4. Create Task Tag — runs AFTER scaffolding so the board/list already exists.
	task_pattern = r"\[?ACTION: CREATE_TASK \| BOARD: ([^\|\]]+) \| LIST: ([^\|\]]+) \| TITLE: ([^\|\]]+)\]?"
	for match in re.finditer(task_pattern, reply):
		raw_tag = match.group(0)
		board, llist, title = match.groups()
		board, llist, title = board.strip().strip('"\''), llist.strip().strip('"\''), title.strip().strip('"\'')

		async def _exec_task(board=board, llist=llist, title=title):
			path = await planka_create_task(board_name=board, list_name=llist, title=title)
			if path:
				return f"Task '{title}' created in {path}."
			return f"\u26a0 Failed to create task '{title}'. Check Planka connection."

		await handle_action("CREATE_TASK", raw_tag, _exec_task, f"Create task '{title}' on {board}")
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
			if len(fields) != 5:
				return "\u26a0 Error: CRON spec must be exactly 5 fields."
			
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
			success = await planka_move_card(card_title_fragment=card_frag, destination_list=dest_list, board_name=board)
			if success:
				return f"Card '{card_frag}' moved to '{dest_list}'."
			return f"\u26a0 Could not find card matching '{card_frag}'. Check Planka board."

		await handle_action("MOVE_CARD", raw_tag, _exec_move, f"Move card '{card_frag}' to '{dest_list}'")
		clean_reply = strip_tag(clean_reply, raw_tag)

	# 10. Mark Done Tag (shortcut: moves card to Done list)
	mark_done_pattern = r"\[?ACTION: MARK_DONE \| CARD: ([^\|\]]+)\]?"
	for match in re.finditer(mark_done_pattern, reply):
		raw_tag = match.group(0)
		card_frag = match.group(1).strip()

		async def _exec_done(card_frag=card_frag):
			success = await planka_move_card(card_title_fragment=card_frag, destination_list="Done", board_name="")
			if success:
				return f"Card '{card_frag}' marked done."
			return f"\u26a0 Could not find card matching '{card_frag}'. Check Planka board."

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
