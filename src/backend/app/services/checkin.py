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
	board_id: Optional[str] = None
	options: list[str] = field(default_factory=list)
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

def _build_sorted_board_context(boards_data: dict, budget: int = 6000) -> str:
	"""Build a LLM-ready board context string from the bucketed boards data.

	Ensures the LLM sees the absolute master list of all boards first, then prints details in recency order.
	If budget is exceeded, card details are truncated but board headers remain.
	"""
	if not boards_data:
		return "(no boards found)"

	# Flatten the boards for building the context, keeping the order: Operator -> Crew -> Project
	flat_boards = []
	if boards_data.get("operator_board"):
		flat_boards.append(boards_data["operator_board"])
	flat_boards.extend(boards_data.get("crew_boards", []))
	flat_boards.extend(boards_data.get("project_boards", []))

	master_list = []
	for b in flat_boards:
		# Exclude Scrum and Focus from explicit stop list, but keep context for Meta Thoughts
		if b['name'].lower() in ["scrum", "focus"]:
			continue
		master_list.append(f"{b['project']} / {b['name']}")
		
	header_block = "MASTER BOARD LIST (Must generate a stop for each of these):\n" + "\n".join(f"- {m}" for m in master_list)

	lines_per_board: list[str] = []
	for b in flat_boards:
		days_ago = b.get("days_since_active", 0)
		age_label = f"{days_ago} days since last activity" if days_ago > 0 else "active today"

		header = f"[{b['project']} / {b['name']}] ({age_label})"
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


async def _fetch_recent_crew_conversations() -> dict[str, str]:
	"""Query the last 5 messages for each active crew domain from global_messages."""
	from app.models.db import AsyncSessionLocal
	from sqlalchemy import text
	
	domains = []
	try:
		from app.services.crews import get_crew_registry
		domains = [c.id for c in get_crew_registry().list_crews()]
	except Exception:
		pass
	histories = {}
	
	try:
		async with AsyncSessionLocal() as session:
			for dom in domains:
				model_tag = f"crew:{dom}"
				stmt = text(
					"SELECT role, content FROM global_messages "
					"WHERE model = :model_tag "
					"ORDER BY created_at DESC LIMIT 5"
				)
				res = await session.execute(stmt, {"model_tag": model_tag})
				rows = res.all()
				if rows:
					lines = []
					for role, content in reversed(rows):
						clean_content = content.split("_(Reasoning")[0].strip()
						lines.append(f"- {role.upper()}: {clean_content}")
					histories[dom] = "\n".join(lines)
	except Exception as exc:
		logger.warning("_fetch_recent_crew_conversations failed: %s", exc)
		
	return histories


async def _gather_day_data() -> dict:
	"""Collect the same raw data used by the morning briefing pipeline."""
	from app.services.calendar import fetch_calendar_events
	from app.services.weather import get_weather_forecast
	from app.services.planka import get_recent_activity, get_stale_cards, get_briefing_boards_data
	from app.services.translations import get_user_lang

	async def _safe(coro, fallback=""):
		try:
			return await coro
		except Exception as exc:
			logger.debug("checkin gather: %s", exc)
			return fallback

	lang = await _safe(get_user_lang(), "en")

	(
		calendar_events,
		weather,
		boards_data,
		recent_activity,
		stale_cards,
		crew_histories,
	) = await asyncio.gather(
		_safe(fetch_calendar_events(days_ahead=0), []),
		_safe(get_weather_forecast(lang=lang)),
		_safe(get_briefing_boards_data(), {}),
		_safe(get_recent_activity(hours=96)),
		_safe(get_stale_cards(min_days=5)),
		_safe(_fetch_recent_crew_conversations(), {}),
	)
	return {
		"calendar": calendar_events,
		"weather": weather,
		"boards_raw": boards_data,  # keeping the dict key name the same for compatibility with caller
		"recent_activity": recent_activity,
		"stale_cards": stale_cards,
		"lang": lang,
		"crew_histories": crew_histories,
	}



# ─── Stop builder ─────────────────────────────────────────────────────────────

_FALLBACK_STOPS = [
	CheckinStop("calibration", "Calibration", "Take a slow breath in for four counts, hold for four, and out for four. Let today begin deliberately. You are here."),
	CheckinStop("review", "Day Review", "Here is a quick look at what is on your plate today. Take it one item at a time."),
	CheckinStop("meta", "Meta Thoughts", "That is your full check-in for today. You have the picture. Now go make one thing move. Irgendwas Neues heute?"),
]

_JSON_STRIP_RE = re.compile(r'^```(?:json)?\s*|\s*```$', re.MULTILINE)


async def _build_stops(data: dict) -> list[CheckinStop]:
	"""Ask the LLM to produce a JSON object of check-in stop bodies from today's data."""
	from app.services.llm import chat
	from app.services.personal_context import get_personal_context_for_prompt_no_health

	_LANG_NAMES = {"de": "German (Deutsch)", "en": "English", "fr": "French", "es": "Spanish", "it": "Italian"}
	_lang_code = data.get("lang", "en")
	_lang_name = _LANG_NAMES.get(_lang_code, _lang_code)
	
	boards_data = data.get("boards_raw", {})
	_board_ctx = _build_sorted_board_context(boards_data, budget=6000)

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

	board_slug_map = {}
	op_cards_lines = []
	
	# Extract operator board details
	op_b = boards_data.get("operator_board")
	if op_b:
		op_days = op_b.get("days_since_active", 0)
		op_title = f"Operator Board ({op_days}d inaktiv)" if op_days > 0 else "Operator Board (heute aktiv)"
		stops.append(CheckinStop(id="operator", title=op_title, body="", board_id=op_b.get("board_id")))
		for _, cname, clist, _ in op_b.get("cards", []):
			if clist.lower() not in ["archive", "erledigt", "done", "trash"]:
				op_cards_lines.append(f"  - {cname} (List: {clist})")
	else:
		stops.append(CheckinStop(id="operator", title="Operator Board", body=""))

	# Process Crews and Projects
	for b in (boards_data.get("crew_boards", []) + boards_data.get("project_boards", [])):
		bname_lower = b["name"].lower()
		# Exclude Scrum and Focus stops as requested (handled in Meta/outro or standalone)
		if bname_lower in ["scrum", "focus"]:
			continue

		slug = bname_lower.replace(" ", "-").replace("/", "-")
		orig_slug = slug
		counter = 1
		while any(s.id == slug for s in stops):
			slug = f"{orig_slug}-{counter}"
			counter += 1

		days = b.get("days_since_active", 0)
		days_str = f" ({days}d seit letzter Aktivität)" if days > 0 else " (heute aktiv)"
		full_title = f"{b['name']}{days_str}"

		board_slug_map[slug] = b["name"]
		stops.append(CheckinStop(id=slug, title=full_title, body="", board_id=b.get("board_id")))

	stops.append(CheckinStop(id="meta", title="Meta Thoughts", body=""))

	operator_cards_ctx = "\n".join(op_cards_lines) if op_cards_lines else "  (No active cards on Operator Board)"

	# Expected JSON keys list
	expected_keys = [s.id for s in stops if s.id != "weather"]

	# Format crew histories context
	crew_history_lines = []
	for dom, hist in data.get("crew_histories", {}).items():
		crew_history_lines.append(f"[{dom.upper()} Crew Recent Conversation]:\n{hist}")
	crew_history_ctx = "\n\n".join(crew_history_lines)

	prompt = (
		f"You are Z, the personal AI companion. Generate the spoken text for today's guided morning check-in.\n"
		f"CRITICAL: ALL values in the JSON MUST be written in {_lang_name}. No exceptions.\n\n"
		f"You MUST return a JSON object containing exactly the following keys, with the spoken text as string values. Do not omit any keys:\n"
		f"{json.dumps(expected_keys)}\n\n"
		"Key Descriptions:\n"
		"- 'calibration': A breathing or grounding exercise (12–20 seconds spoken, calm, physical, present-moment).\n"
		"- 'operator': Operator Board active tasks. You MUST ONLY reference card titles explicitly listed under 'EXACT OPERATOR BOARD CARDS' below. Do NOT invent card names and do NOT take topics from recent chats. Provide 1 to 3 distinct actionable steps (ordered by highest outcome/significance first). Format EACH actionable step at the end of the text as '[OPTION] Action Label'.\n"
		"- Board slugs: For each domain board, look at its active cards, recent activity, AND 'Recent Crew Conversations'. You MUST extract active task topics or recent chat points. Provide 1 to 3 distinct concrete actionable steps (ordered by highest outcome/significance first). Format EACH actionable step at the end of the text as '[OPTION] Action Label'.\n"
		"- 'meta': Overarching meta thoughts, mood, direction. Synthesize top 1 to 3 actionable steps from across ALL areas (ordered by highest significance). Format EACH actionable step at the end as '[OPTION] Action Label'. End with a question about if there is anything new today.\n\n"
		"Rules:\n"
		f"- Write every value in {_lang_name}.\n"
		"- Keep each value short (1-2 natural spoken sentences, max 40 words per key) so the overall check-in is efficient and does not get cut off.\n"
		"- ACTIVITY METRIC RULE: For every board stop, you MUST state how many days since last activity in the text (e.g. '25 Tage seit letzter Aktivität.' or 'Seit 12 Tagen inaktiv.').\n"
		"- CARD PRESENCE RULE: If a board has active cards listed under 'Boards and Projects', those cards ARE active items and existing tasks. You MUST NOT say 'Keine Aktivitäten' (No activity) or 'Keine Tasks' when cards exist!\n"
		"- DIGITAL RECORDING RULE FOR AUREL / STOIC: NEVER ask or advise the user to write something down on physical paper or with a pen. Always tell the user to reply directly here in the chat so Aurel / Z can save and record it in memory and on the board.\n"
		"- OPTION TAG RULE: You MUST append 1 to 3 option tags to EVERY board stop and 'meta' stop at the end of the text (e.g. '[OPTION] Rollo reparieren [OPTION] Vermieter anrufen').\n"
		"- STRICT DOMAIN ADHERENCE: Action options MUST strictly match the specific domain/board of the current stop. Do not suggest actions unrelated to the current board's topic.\n"
		"- LOGICAL SEQUENCING (BOTTLENECKS FIRST): For action steps, always suggest the immediate next logical bottleneck. For example, if a project needs a decision (e.g., choosing a species) before buying equipment, the option MUST be to make that decision first, NOT to buy the equipment. Do not jump to distant future actions.\n"
		"- HIGH-VALUE ACTIONS ONLY: Options must be persistent, meaningful tasks worth tracking on a Kanban board. Do NOT suggest transient, trivial, or conversational actions (e.g., 'Film aussuchen', 'Reflexion teilen', 'Idee notieren') that do not warrant a permanent card.\n"
		"- UNIVERSAL ANTI-HALLUCINATION / GROUNDING RULE: ONLY reference card names, tasks, or facts that are explicitly listed in the provided data or recent conversations. NEVER invent or fabricate pickup times, appointments, meeting schedules, or card titles not present in the context.\n"
		"- Output ONLY the JSON object, no markdown, no wrapping other than valid JSON.\n\n"
		f"Today's data:\n"
		f"Weather: {data.get('weather', 'unknown')}\n"
		f"Calendar:\n{calendar_text}\n"
		f"EXACT OPERATOR BOARD CARDS (Ground Truth for 'operator' key):\n{operator_cards_ctx}\n\n"
		f"Recent Crew Conversations:\n{crew_history_ctx}\n\n"
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
		
		# Map the parsed text back to our programmatic stops using robust regex for [OPTION]
		for s in stops:
			if s.id == "weather":
				# Bypass LLM and use fixed template
				cal_hdr = "📅 Kalender:" if _lang_code == "de" else "📅 Calendar:"
				cal_body = calendar_text
				s.body = f"{data.get('weather', '')}\n\n{cal_hdr}\n{cal_body}"
				s.options = []
			elif s.id in parsed and parsed[s.id]:
				body_text = str(parsed[s.id])
				# Robust regex extraction of options anywhere in the text
				options = [opt.strip() for opt in re.findall(r'\[OPTION\]\s*([^\[\n]+)', body_text) if opt.strip()]
				clean_body = re.sub(r'\[OPTION\]\s*([^\[\n]+)', '', body_text).strip()
				clean_body = re.sub(r'\s+', ' ', clean_body).strip()
				s.body = clean_body
				s.options = options
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
			elif s.id == "meta":
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
	cadence: str = "daily",
) -> CheckinSession:
	"""Build and store a new check-in session (daily, weekly, or monthly)."""
	key = f"{channel}:{chat_id}"
	data = await _gather_day_data()
	stops = await _build_stops(data)

	session = CheckinSession(key=key, stops=stops, index=0)
	_SESSIONS[key] = session

	if compile_audio:
		_lang = data.get("lang", "en")
		task = asyncio.create_task(_compile_audio(stops, lang=_lang))
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
