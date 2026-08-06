"""General Conversation Recorder
---------------------------------
Records meaningful non-crew user conversations to a "General" board on Planka.

Structure mirrors the crew_memory.py pattern:
  Project:  <crews_project_name>   (i18n, default "Crews")
  Board:    "General"              (constant — not crew-specific)
  List:     "Conversation"         (same i18n key as crew boards)
  Card:     <date_str>             (e.g. "2026.08.07")
  Description: Rolling log of today's Z exchanges.

Formatting rules:
  - User messages are preserved verbatim (trimmed to 500 chars hard cap per turn).
  - Z responses are compressed to key points only.
  - Clear [USER] / [Z] role labels in every entry.

Public API:
  record_general_exchange(user_msg, z_response)
      Called after every meaningful non-crew Z reply. Fire-and-forget.

  is_meaningful(user_msg) -> bool
      Heuristic gate — returns False for trivial messages.
"""
import logging
import re
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Hard cap on user message length stored per turn (verbatim preservation up to this limit)
_USER_MSG_MAX_CHARS = 500
# Soft cap on Z response stored per turn before truncation marker
_Z_RESP_MAX_CHARS = 400
# Minimum user message length to be considered meaningful
_MIN_MEANINGFUL_LEN = 40

# Patterns that classify a message as trivial / not worth recording
_TRIVIAL_RE = re.compile(
	r'^(?:'
	r'ok|okay|k|thanks?|thx|ty|np|sure|yep|yup|nope|nah|ja|nein|danke|bitte|'
	r'yes|no|got it|got\s+it|alright|cool|nice|great|perfect|good|super|'
	r'understood|noted|done|fertig|erledigt|verstanden|'
	r'hi|hey|hello|hallo|moin|ciao|'
	r'bye|tschuss|ciao|auf wiedersehen'
	r')[\s!?.]*$',
	re.IGNORECASE,
)

# Board name for general (non-crew) conversations
_GENERAL_BOARD_NAME = "General"


def is_meaningful(user_msg: str) -> bool:
	"""Return True if the message is substantial enough to be worth recording."""
	stripped = user_msg.strip()
	if len(stripped) < _MIN_MEANINGFUL_LEN:
		return False
	if stripped.startswith('/'):
		return False
	if _TRIVIAL_RE.match(stripped):
		return False
	return True


async def record_general_exchange(user_msg: str, z_response: str) -> None:
	"""Create or update today's general conversation card for non-crew Z exchanges.

	Silently no-ops if Planka is unavailable or the message is not meaningful.
	Always fire-and-forget — never await the result from a critical path.
	"""
	try:
		if not is_meaningful(user_msg):
			return

		from app.services.crew_memory import (
			_planka_client,
			_get_or_create_crews_project,
			_get_or_create_crew_board,
			_get_or_create_conversation_list,
			_get_or_create_today_card,
			_patch_card_description,
			_get_user_date_format,
			_get_user_timezone,
		)
		from app.services.translations import get_translations, get_user_lang

		lang = await get_user_lang()
		t = get_translations(lang)
		project_name: str = t.get("crews_project_name", "Crews")
		list_name: str = t.get("crew_conversation_list", "Conversation")

		date_fmt = await _get_user_date_format()
		try:
			tz = await _get_user_timezone()
			now_local = datetime.now(tz)
		except Exception:
			now_local = datetime.now(timezone.utc)

		date_str = now_local.strftime(date_fmt)
		time_str = now_local.strftime("%H:%M")

		# Reuse crew_id slot as "general" for persisted list ID key
		_CREW_ID_KEY = "general"

		async with await _planka_client() as client:
			project_id = await _get_or_create_crews_project(client, project_name)
			if not project_id:
				return
			board_id = await _get_or_create_crew_board(client, project_id, _GENERAL_BOARD_NAME)
			if not board_id:
				return
			list_id = await _get_or_create_conversation_list(client, board_id, list_name, _CREW_ID_KEY)
			if not list_id:
				return
			card_id, current_desc = await _get_or_create_today_card(client, board_id, list_id, date_str)
			if not card_id:
				return

			updated_desc = await _compress_general_exchange(current_desc, user_msg, z_response, time_str)
			await _patch_card_description(client, card_id, updated_desc)
			logger.info("conversation_recorder: updated General conversation card (%s)", date_str)
	except Exception as e:
		logger.warning("conversation_recorder: record_general_exchange failed (non-fatal): %s", e)


# Maximum total chars kept in the General conversation card description
_MAX_CARD_CHARS = 4000


async def _compress_general_exchange(current: str, user_msg: str, z_response: str, time_str: str) -> str:
	"""Append this exchange and compress if needed.

	Design:
	- User messages are kept verbatim (up to _USER_MSG_MAX_CHARS).
	- Z responses are summarised into key points only.
	- Clear role labels make the record easy to scan.
	"""
	try:
		from app.services.llm import chat
		import re as _re

		# Strip action tags from Z response
		clean_z = _re.sub(r'\[?ACTION:[^\]]+\]?', '', z_response).strip()
		clean_z = _re.sub(r'\n{3,}', '\n\n', clean_z)

		# Verbatim user message (hard cap)
		user_verbatim = user_msg.strip()
		if len(user_verbatim) > _USER_MSG_MAX_CHARS:
			user_verbatim = user_verbatim[:_USER_MSG_MAX_CHARS] + ' [...]'

		prompt = (
			f"You are a dense information recorder for openZero.\n"
			f"Update the general conversation log for today.\n\n"
			f"Existing log:\n\"\"\"\n{current}\n\"\"\"\n\n"
			f"New exchange to append:\n"
			f"- Time: {time_str}\n"
			f"- [USER] (verbatim): {user_verbatim}\n"
			f"- [Z] response: {clean_z}\n\n"
			f"Rules:\n"
			f"1. PRESERVE the [USER] message EXACTLY as written — do not paraphrase, shorten, or alter the user's words.\n"
			f"2. COMPRESS [Z]'s response to key decisions, answers, and recommendations only (1-3 bullet points max).\n"
			f"3. Keep ALL previous entries from the existing log intact.\n"
			f"4. Format every entry as:\n"
			f"   [HH:MM] [USER]: <exact user words>\n"
			f"   [HH:MM] [Z]: <compressed key points>\n"
			f"   ---\n"
			f"5. CRITICAL: Do NOT use emojis. Indent using tabs. No markdown headers.\n"
			f"6. Keep the total log under {_MAX_CARD_CHARS} characters. If the existing log is very long, "
			f"truncate the OLDEST entries first, never the newest.\n"
		)

		summary = await chat(
			user_message=prompt,
			system_override="You are a precise conversation logger. Preserve user intent exactly.",
			tier="cloud",
		)
		if summary and summary.strip():
			return summary.strip()
	except Exception as e:
		logger.warning("conversation_recorder: LLM compression failed, using raw append: %s", e)

	# Fallback: raw append without LLM
	return _raw_append(current, user_msg, z_response, time_str)


def _raw_append(current: str, user_msg: str, z_response: str, time_str: str) -> str:
	"""Append a new exchange as plain text without LLM compression."""
	import re as _re
	clean_z = _re.sub(r'\[?ACTION:[^\]]+\]?', '', z_response).strip()
	clean_z = _re.sub(r'\n{3,}', '\n\n', clean_z)

	user_verbatim = user_msg.strip()
	if len(user_verbatim) > _USER_MSG_MAX_CHARS:
		user_verbatim = user_verbatim[:_USER_MSG_MAX_CHARS] + ' [...]'

	z_trimmed = clean_z[:_Z_RESP_MAX_CHARS] + ('...' if len(clean_z) > _Z_RESP_MAX_CHARS else '')

	new_entry = (
		f"[{time_str}] [USER]: {user_verbatim}\n"
		f"[{time_str}] [Z]: {z_trimmed}\n"
		"---\n"
	)
	updated = current + new_entry if current else new_entry

	if len(updated) > _MAX_CARD_CHARS:
		truncated = updated[-_MAX_CARD_CHARS:]
		nl = truncated.find('\n')
		if nl > 0:
			truncated = truncated[nl + 1:]
		updated = '[...earlier conversation omitted...]\n' + truncated

	return updated
