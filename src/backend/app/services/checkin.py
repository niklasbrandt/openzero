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

async def _gather_day_data() -> dict:
	"""Collect the same raw data used by the morning briefing pipeline."""
	from app.services.calendar import fetch_calendar_events
	from app.services.weather import get_weather_forecast
	from app.services.planka import get_project_tree, get_recent_activity, get_stale_cards
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
		tree,
		recent_activity,
		stale_cards,
		lang,
	) = await asyncio.gather(
		_safe(fetch_calendar_events(days_ahead=0), []),
		_safe(get_weather_forecast()),
		_safe(get_project_tree(as_html=False)),
		_safe(get_recent_activity(hours=96)),
		_safe(get_stale_cards(min_days=5)),
		_safe(get_user_lang(), "en"),
	)
	return {
		"calendar": calendar_events,
		"weather": weather,
		"tree": tree,
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
	"""Ask the LLM to produce a JSON array of check-in stops from today's data."""
	from app.services.llm import chat
	from app.services.personal_context import get_personal_context_for_prompt_no_health

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

	prompt = (
		"You are Z, the personal AI companion. Generate a JSON array for today's guided morning check-in.\n\n"
		"Each item in the array must have exactly these fields:\n"
		'  {"id": "slug", "title": "Short Title", "body": "1-3 spoken sentences"}\n\n'
		"Required stop sequence:\n"
		'1. id="calibration" — A breathing or grounding exercise (12–20 seconds spoken, calm, physical, present-moment).\n'
		'2. id="weather"     — Weather + any calendar events for today. Keep it to 2 sentences.\n'
		'3. id="boards"      — Most important / stale items from the boards. Be specific, name cards. Max 3 sentences.\n'
		'4. One stop per life domain that has data: health, career, family, finance, creative.\n'
		'   Only include domains that have board cards or activity data.\n'
		'   id = domain slug (e.g. "health"), title = domain name.\n'
		'5. id="outro"       — Brief closing. Name one concrete action for today. End with "Irgendwas Neues heute?".\n\n'
		"Rules:\n"
		"- body must be natural spoken prose, not bullet points.\n"
		"- Never invent board data. Only reference cards that appear in the data below.\n"
		"- Keep each body under 50 words.\n"
		"- Output ONLY the JSON array, no other text.\n\n"
		f"Today's data:\n"
		f"Weather: {data.get('weather', 'unknown')}\n"
		f"Calendar:\n{calendar_text}\n"
		f"Boards overview:\n{str(data.get('tree', ''))[:1000]}\n"
		f"Recent activity (last 4 days):\n{str(data.get('recent_activity', ''))[:800]}\n"
		f"Stale cards:\n{str(data.get('stale_cards', ''))[:600]}\n"
		f"Personal context:\n{personal_ctx[:600]}\n\n"
		f"Language for body text: {data.get('lang', 'en')}\n"
		"Output JSON array only:"
	)

	try:
		raw = await asyncio.wait_for(
			chat(prompt, tier="cloud", _feature="checkin_build", include_health=False),
			timeout=90.0,
		)
		# Strip markdown fences if present
		cleaned = _JSON_STRIP_RE.sub("", raw).strip()
		parsed = json.loads(cleaned)
		stops = []
		for item in parsed:
			if isinstance(item, dict) and "id" in item and "body" in item:
				stops.append(CheckinStop(
					id=str(item["id"]),
					title=str(item.get("title", item["id"].title())),
					body=str(item["body"]),
				))
		if stops:
			return stops
	except Exception as exc:
		logger.warning("checkin: stop builder LLM failed (%s), using fallback stops", exc)

	return _FALLBACK_STOPS


# ─── TTS pre-compilation ──────────────────────────────────────────────────────

async def _compile_audio(stops: list[CheckinStop]) -> None:
	"""Generate slow TTS audio for each stop in place (fire-and-forget friendly)."""
	from app.services.tts import generate_speech
	from app.config import settings

	if not getattr(settings, "TTS_BASE_URL", None):
		return

	async def _gen(stop: CheckinStop) -> None:
		try:
			import httpx
			url = f"{settings.TTS_BASE_URL}/v1/audio/speech"
			data = {
				"model": "tts-1",
				"input": stop.body,
				"voice": "alloy",
				"speed": 0.80,   # Slower than default (0.85) for meditative pacing
			}
			async with httpx.AsyncClient(timeout=60.0) as client:
				resp = await client.post(url, json=data)
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
		task = asyncio.create_task(_compile_audio(stops))
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
