"""
Interactive Daily Check-in Service
────────────────────────────────────
Manages step-by-step, domain-by-domain guided check-in sessions.

Session lifecycle
  1. start_session()  — gather briefing data, ask LLM to build stops as JSON,
                         pre-generate TTS for each stop, store session state.
  2. current_stop()   — return the text + cached audio for the active stop.
  3. advance()        — move forward one step (wraps at final).
  4. retreat()        — move backward one step (wraps at first).
  5. close_session()  — remove session state.

Session state is stored in-memory in _SESSIONS keyed by
"{channel}:{chat_id}" so multiple channels never collide.

Stop structure
  Calibration → Intro → one stop per active domain → Outro

Each stop has:
  id        — slug e.g. "calibration", "health", "career"
  title     — short display title
  body      — 1–3 sentence spoken text
  audio     — bytes | None (pre-compiled by start_session)
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# ─── Session store ────────────────────────────────────────────────────────────

@dataclass
class CheckinStop:
	id: str
	title: str
	body: str
	audio: Optional[bytes] = field(default=None, compare=False, repr=False)

@dataclass
class CheckinSession:
	key: str                        # "{channel}:{chat_id}"
	stops: list[CheckinStop]
	index: int = 0                  # active stop index
	last_msg_ids: list[int] = field(default_factory=list) # IDs of messages sent for the current stop

	@property
	def current(self) -> CheckinStop:
		return self.stops[self.index]

	@property
	def total(self) -> int:
		return len(self.stops)

	@property
	def is_last(self) -> bool:
		return self.index >= self.total - 1

	@property
	def is_first(self) -> bool:
		return self.index == 0

	def advance(self) -> None:
		if not self.is_last:
			self.index += 1

	def retreat(self) -> None:
		if not self.is_first:
			self.index -= 1


_SESSIONS: dict[str, CheckinSession] = {}


def get_session(channel: str, chat_id: str | int) -> Optional[CheckinSession]:
	return _SESSIONS.get(f"{channel}:{chat_id}")


def get_any_session_for_channel(channel: str) -> Optional[CheckinSession]:
	"""Return the first active session for a given channel (single-owner helper)."""
	prefix = f"{channel}:"
	for key, session in _SESSIONS.items():
		if key.startswith(prefix):
			return session
	return None


def close_session(channel: str, chat_id: str | int) -> None:
	_SESSIONS.pop(f"{channel}:{chat_id}", None)


def close_any_session_for_channel(channel: str) -> None:
	"""Close all sessions for a channel (single-owner, max 1 expected)."""
	prefix = f"{channel}:"
	keys = [k for k in _SESSIONS if k.startswith(prefix)]
	for k in keys:
		_SESSIONS.pop(k, None)



# ─── Data helpers ─────────────────────────────────────────────────────────────

async def _fetch_boards_raw() -> list[dict]:
	"""Fetch all boards with their cards and per-card timestamps from Planka.

	Returns a list of dicts:
	  {"name": str, "project": str, "last_updated": datetime, "cards": [str, ...]}
	sorted by last_updated descending (most recent first).
	"""
	from app.services.planka import get_planka_auth_token, _is_done_list
	from app.config import settings
	import httpx
	from datetime import datetime

	boards: list[dict] = []
	try:
		token = await get_planka_auth_token()
		headers = {"Authorization": f"Bearer {token}"}
		async with httpx.AsyncClient(
			base_url=settings.PLANKA_BASE_URL, timeout=20.0, headers=headers
		) as client:
			resp = await client.get("/api/projects")
			projects = resp.json().get("items", [])

			# Fetch project details in parallel to get board lists
			project_resps = await asyncio.gather(
				*[client.get(f"/api/projects/{p['id']}") for p in projects],
				return_exceptions=True,
			)

			# Collect board stubs
			board_stubs: list[tuple[str, str, str]] = []  # (project_name, board_name, board_id)
			for p, p_resp in zip(projects, project_resps):
				if isinstance(p_resp, BaseException):
					continue
				p_data = p_resp.json()
				for b in p_data.get("included", {}).get("boards", []):
					board_stubs.append((p["name"], b["name"], b["id"]))

			# Fetch board details in parallel
			board_resps = await asyncio.gather(
				*[client.get(f"/api/boards/{bid}", params={"included": "lists,cards"})
				  for _, _, bid in board_stubs],
				return_exceptions=True,
			)

			now = datetime.utcnow()
			_epoch = datetime(1970, 1, 1)

			for (proj_name, board_name, _), b_resp in zip(board_stubs, board_resps):
				if isinstance(b_resp, BaseException):
					continue
				b_data = b_resp.json()
				lists = b_data.get("included", {}).get("lists", [])
				cards = b_data.get("included", {}).get("cards", [])
				done_ids = {l["id"] for l in lists if _is_done_list(l.get("name", ""))}
				list_map = {l["id"]: l.get("name", "?") for l in lists}

				active_cards: list[tuple[datetime, str, str, str]] = []  # (ts, card_name, list_name, desc)
				for card in cards:
					if card.get("listId") in done_ids:
						continue
					raw_u = card.get("updatedAt") or card.get("createdAt") or ""
					try:
						ts = datetime.fromisoformat(raw_u.replace("Z", "")) if raw_u else _epoch
					except ValueError:
						ts = _epoch
					list_name = list_map.get(card.get("listId", ""), "?")
					desc = card.get("description") or ""
					if len(desc) > 100:
						desc = desc[:97] + "..."
					active_cards.append((ts, card.get("name") or "?", list_name, desc))

				last_updated = max(card[0] for card in active_cards) if active_cards else _epoch
				boards.append({
					"project": proj_name,
					"name": board_name,
					"last_updated": last_updated,
					"cards": active_cards,  # list of (ts, name, list_name)
				})
	except Exception as exc:
		logger.warning("_fetch_boards_raw failed: %s", exc)

	# Sort by last active (most recent first), but empty/unused boards go to the bottom
	boards.sort(key=lambda b: b["last_updated"], reverse=True)
	return boards


def _build_sorted_board_context(boards_raw: list[dict], budget: int = 5000) -> str:
	"""Build a LLM-ready board context string.

	Ensures the LLM sees the absolute master list of all boards first, then prints details in recency order.
	If budget is exceeded, card details are truncated but board headers remain.
	"""
	from datetime import datetime

	if not boards_raw:
		return "(no boards found)"

	master_list = []
	for b in boards_raw:
		# Exclude Scrum and Focus from explicit stop list, but keep context for Meta Thoughts
		if b['name'].lower() in ["scrum", "focus"]:
			continue
		master_list.append(f"{b['project']} / {b['name']}")
		
	header_block = "MASTER BOARD LIST (Must generate a stop for each of these):\n" + "\n".join(f"- {m}" for m in master_list)

	lines_per_board: list[str] = []
	for b in boards_raw:
		if b["last_updated"] == datetime(1970, 1, 1):
			age_label = "no active cards/never active"
		else:
			days_ago = (datetime.utcnow() - b["last_updated"]).days
			age_label = f"{days_ago}d ago" if days_ago > 0 else "today"

		header = f"[{b['project']} / {b['name']}] (last active: {age_label})"
		if not b["cards"]:
			card_lines = ["  (no active cards / only finished or empty lists)"]
		else:
			card_lines = []
			for _, name, lst, desc in sorted(b["cards"], key=lambda x: x[0], reverse=True)[:15]:
				desc_str = f" - {desc}" if desc else ""
				card_lines.append(f"  - {name} ({lst}){desc_str}")
		lines_per_board.append("\n".join([header] + card_lines))

	# Include header block, then fit board details as much as possible
	result_parts = [header_block, "\nBOARD DETAILS:"]
	used = len(header_block) + 20
	for block in lines_per_board:
		cost = len(block) + 2
		if used + cost > budget:
			# Just append the header without card details to save budget
			header_only = block.split("\n")[0] + "\n  (details truncated due to context size)"
			result_parts.append(header_only)
			used += len(header_only) + 2
		else:
			result_parts.append(block)
			used += cost

	return "\n\n".join(result_parts)


async def _gather_day_data() -> dict:
	"""Collect the same raw data used by the morning briefing pipeline."""
	from app.services.calendar import fetch_calendar_events
	from app.services.weather import get_weather_forecast
	from app.services.planka import get_recent_activity, get_stale_cards
	from app.services.translations import get_user_lang

	async def _safe(coro, fallback=""):
		try:
			return await coro
		except Exception as exc:
			logger.debug("checkin gather: %s", exc)
			return fallback

	(
		calendar_events,
		weather,
		boards_raw,
		recent_activity,
		stale_cards,
		lang,
	) = await asyncio.gather(
		_safe(fetch_calendar_events(days_ahead=0), []),
		_safe(get_weather_forecast()),
		_safe(_fetch_boards_raw(), []),
		_safe(get_recent_activity(hours=96)),
		_safe(get_stale_cards(min_days=5)),
		_safe(get_user_lang(), "en"),
	)
	return {
		"calendar": calendar_events,
		"weather": weather,
		"boards_raw": boards_raw,
		"recent_activity": recent_activity,
		"stale_cards": stale_cards,
		"lang": lang,
	}



# ─── Stop builder ─────────────────────────────────────────────────────────────

_FALLBACK_STOPS = [
	CheckinStop("calibration", "Calibration", "Take a slow breath in for four counts, hold for four, and out for four. Let today begin deliberately. You are here."),
	CheckinStop("review", "Day Review", "Here is a quick look at what is on your plate today. Take it one item at a time."),
	CheckinStop("outro", "Checkout", "That is your full check-in for today. You have the picture. Now go make one thing move. Irgendwas Neues heute?"),
]

_JSON_STRIP_RE = re.compile(r'^```(?:json)?\s*|\s*```$', re.MULTILINE)


async def _build_stops(data: dict) -> list[CheckinStop]:
	"""Ask the LLM to produce a JSON object of check-in stop bodies from today's data."""
	from app.services.llm import chat
	from app.services.personal_context import get_personal_context_for_prompt_no_health

	_LANG_NAMES = {"de": "German (Deutsch)", "en": "English", "fr": "French", "es": "Spanish", "it": "Italian"}
	_lang_code = data.get("lang", "en")
	_lang_name = _LANG_NAMES.get(_lang_code, _lang_code)
	_board_ctx = _build_sorted_board_context(data.get("boards_raw", []), budget=6000)

	personal_ctx = ""
	try:
		personal_ctx = get_personal_context_for_prompt_no_health()
	except Exception:
		pass

	calendar_lines = []
	for ev in data.get("calendar", []):
		start = ev.get("start", "")
		time_str = start.split("T")[1][:5] if "T" in start else ""
		calendar_lines.append(f"- {time_str} {ev.get('summary', '')}".strip())
	calendar_text = "\n".join(calendar_lines) if calendar_lines else "No events today."

	# 1. Programmatically define all stops to ensure NO boards are skipped
	stops: list[CheckinStop] = []
	stops.append(CheckinStop(id="calibration", title="Calibration", body=""))
	stops.append(CheckinStop(id="weather", title="Weather & Calendar", body=""))
	stops.append(CheckinStop(id="operator", title="Operator Board", body=""))

	board_slug_map = {}
	for b in data.get("boards_raw", []):
		name = b["name"]
		# Exclude Scrum and Focus stops as requested (handled in Meta/outro or standalone)
		if name.lower() in ["scrum", "focus"]:
			continue
		slug = name.lower().replace(" ", "-").replace("/", "-")
		
		# Ensure unique slug
		orig_slug = slug
		counter = 1
		while any(s.id == slug for s in stops):
			slug = f"{orig_slug}-{counter}"
			counter += 1
			
		board_slug_map[slug] = name
		stops.append(CheckinStop(id=slug, title=name, body=""))

	stops.append(CheckinStop(id="meta", title="Meta Thoughts", body=""))
	stops.append(CheckinStop(id="outro", title="Checkout", body=""))

	# Expected JSON keys list
	expected_keys = [s.id for s in stops]

	prompt = (
		f"You are Z, the personal AI companion. Generate the spoken text for today's guided morning check-in.\n"
		f"CRITICAL: ALL values in the JSON MUST be written in {_lang_name}. No exceptions.\n\n"
		f"You MUST return a JSON object containing exactly the following keys, with the spoken text as string values. Do not omit any keys:\n"
		f"{json.dumps(expected_keys)}\n\n"
		"Key Descriptions:\n"
		"- 'calibration': A breathing or grounding exercise (12–20 seconds spoken, calm, physical, present-moment).\n"
		"- 'weather': Weather + any calendar events for today. Keep it to 2 sentences.\n"
		"- 'operator': Operator Board todos only. Be specific: name the actual card titles. Max 3 sentences.\n"
		"- Board slugs (e.g. 'appearance', 'clothing-brand'): Look at the board's active cards or recent activity logs.\n"
		"  Summarize active tasks or recent updates. If a board has no active cards/activity, ask if they want to add new focus areas or leave it dormant.\n"
		"- 'meta': Overarching meta thoughts, mood, direction, synthesized from Personal Context below. Do not parrot system goals.\n"
		"- 'outro': Brief closing. Name one concrete action. End with a question (in the target language) about if there is anything new today.\n\n"
		"Rules:\n"
		f"- Write every value in {_lang_name}.\n"
		"- Keep each value short (1-2 natural spoken sentences, max 40 words per key) so the overall check-in is efficient and does not get cut off.\n"
		"- Output ONLY the JSON object, no markdown, no wrapping other than valid JSON.\n\n"
		f"Today's data:\n"
		f"Weather: {data.get('weather', 'unknown')}\n"
		f"Calendar:\n{calendar_text}\n"
		f"Boards and Projects:\n{_board_ctx}\n"
		f"Recent board activity (last 4 days):\n{str(data.get('recent_activity', ''))[:2000]}\n"
		f"Stale cards (no update in 5+ days):\n{str(data.get('stale_cards', ''))[:1500]}\n"
		f"Personal context:\n{personal_ctx[:1000]}\n\n"
		f"Output language: {_lang_name}\n"
		"Output JSON object only:"
	)

	try:
		raw = await asyncio.wait_for(
			chat(prompt, tier="cloud", _feature="checkin_build", include_health=False),
			timeout=90.0,
		)
		cleaned = _JSON_STRIP_RE.sub("", raw).strip()
		parsed = json.loads(cleaned)
		
		# Map the parsed text back to our programmatic stops
		for s in stops:
			if s.id in parsed and parsed[s.id]:
				s.body = str(parsed[s.id])
			else:
				# A fallback body message in the target language if the key was skipped
				if _lang_code == "de":
					s.body = f"Lass uns über {s.title} sprechen. Gibt es hier neue Entwicklungen oder nächste Schritte?"
				else:
					s.body = f"Let's check in on {s.title}. Are there any new updates or next steps you want to define?"
					
		return stops
	except Exception as exc:
		logger.warning("checkin: stop builder LLM failed (%s), using fallback stops", exc)

	# Basic fallback
	for s in _FALLBACK_STOPS:
		if _lang_code == "de":
			if s.id == "calibration":
				s.body = "Atme langsam ein und aus. Du bist hier."
			elif s.id == "review":
				s.body = "Hier ist dein Tagesüberblick. Lass uns deine Boards durchgehen."
			elif s.id == "outro":
				s.body = "Das ist dein Check-in. Bring heute eine Sache in Bewegung. Irgendwas Neues?"
	return _FALLBACK_STOPS


# ─── TTS pre-compilation ──────────────────────────────────────────────────────

async def _compile_audio(stops: list[CheckinStop], lang: str = "en") -> None:
	"""Generate slow TTS audio for each stop in place (fire-and-forget friendly)."""
	from app.config import settings

	if not getattr(settings, "TTS_BASE_URL", None):
		return

	async def _gen(stop: CheckinStop) -> None:
		try:
			import httpx
			url = f"{settings.TTS_BASE_URL}/v1/audio/speech"
			payload: dict = {
				"model": "tts-1",
				"input": stop.body,
				"voice": "alloy",
				"speed": 0.80,
			}
			# Pass language hint — OpenAI API ignores it; local servers (kokoro,
			# xtts) use it to select the correct pronunciation model.
			if lang and lang != "en":
				payload["language"] = lang
			async with httpx.AsyncClient(timeout=60.0) as client:
				resp = await client.post(url, json=payload)
				if resp.status_code == 200:
					stop.audio = resp.content
		except Exception as exc:
			logger.debug("checkin TTS for stop '%s' failed: %s", stop.id, exc)

	await asyncio.gather(*[_gen(s) for s in stops])


# ─── Public API ───────────────────────────────────────────────────────────────

async def start_session(
	channel: str,
	chat_id: str | int,
	*,
	compile_audio: bool = True,
) -> CheckinSession:
	"""Build and store a new check-in session, replacing any existing one."""
	key = f"{channel}:{chat_id}"
	data = await _gather_day_data()
	stops = await _build_stops(data)

	session = CheckinSession(key=key, stops=stops, index=0)
	_SESSIONS[key] = session

	if compile_audio:
		# Fire audio compilation in background; Telegram can display text immediately
		_lang = data.get("lang", "en")
		task = asyncio.create_task(_compile_audio(stops, lang=_lang))
		# Keep a strong reference so GC doesn't collect it
		_audio_tasks.add(task)
		task.add_done_callback(_audio_tasks.discard)

	return session


# Strong reference set for background audio compilation tasks
_audio_tasks: set[asyncio.Task] = set()


def advance_session(channel: str, chat_id: str | int) -> Optional[CheckinSession]:
	session = get_session(channel, chat_id)
	if session:
		session.advance()
	return session


def retreat_session(channel: str, chat_id: str | int) -> Optional[CheckinSession]:
	session = get_session(channel, chat_id)
	if session:
		session.retreat()
	return session
