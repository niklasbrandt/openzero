from typing import Optional
from telegram import Update, Bot, InlineKeyboardButton, InlineKeyboardMarkup, LinkPreviewOptions  # type: ignore[attr-defined]
from telegram.ext import (
	Application,
	CommandHandler,
	MessageHandler,
	CallbackQueryHandler,
	filters,
	ContextTypes,
)
from app.config import settings
from app.services.timezone import format_time, get_user_timezone
import asyncio
import pytz
import re
from datetime import datetime
import logging
from app.services.translations import get_translations, get_user_lang
from app.models.db import AsyncSessionLocal

logger = logging.getLogger(__name__)

bot_app: Application | None = None

async def _get_stats_footer() -> str:
	"""Consolidated stats/footer for Z's messages (no links)."""
	from app.services.memory import get_memory_stats
	from app.services.llm import last_model_used
	stats = await get_memory_stats()
	lang = await get_user_lang()
	t = get_translations(lang)

	model_name = last_model_used.get() or "local"
	model_tag = f" · {model_name}"
	stats_text = f"{t.get('memories_found', 'Memories')}: {stats['points']}{model_tag}" if stats['status'] != 'error' else f"{t.get('memory_search', 'Memory')}: Offline"
	return f"\n\n<i>{stats_text}</i>"

def get_nav_markup(t: Optional[dict] = None, token: str = "") -> InlineKeyboardMarkup:
	"""Standard navigation buttons (Large touch targets)."""
	if not t:
		t = get_translations("en")

	if not token:
		token = settings.DASHBOARD_TOKEN

	base_url = settings.BASE_URL.rstrip('/')
	auth_qs = f"/api/dashboard/auth?token={token}" if token else ""
	keyboard = [
		[
			InlineKeyboardButton(f"🏠 {t.get('dashboard', 'Dashboard')}", url=f"{base_url}{auth_qs + '&redirect=/dashboard' if auth_qs else '/dashboard'}"),
			InlineKeyboardButton(f"📅 {t.get('calendar', 'Calendar')}", url=f"{base_url}{auth_qs + '&redirect=/calendar' if auth_qs else '/calendar'}")
		],
		[
			InlineKeyboardButton(f"📋 {t.get('operator_board', 'Operator')}", url=f"{base_url}/api/dashboard/planka-redirect?target=operator"),
			InlineKeyboardButton(f"📁 {t.get('projects', 'Projects')}", url=f"{base_url}/api/dashboard/planka-redirect")
		],
		[
			InlineKeyboardButton("🧠 /memories", callback_data="call_memories"),
			InlineKeyboardButton("❓ /help", callback_data="call_help")
		]
	]
	return InlineKeyboardMarkup(keyboard)

# --- Context Persistence ---
chat_histories: dict[int, list[dict[str, str]]] = {} # chat_id -> list of dicts {'role': 'user/z', 'content': str}

# --- Message Coalescing ---
# Tracks in-flight LLM calls per chat. If Z is already thinking and more
# messages arrive, they are buffered and processed as a follow-up batch.
_thinking_locks: dict[int, asyncio.Lock] = {}  # chat_id -> Lock
_pending_messages: dict[int, list[str]] = {}   # chat_id -> buffered texts

# Strong references to background tasks so the GC cannot destroy them mid-execution.
# asyncio.create_task() returns a weak reference; without this set the task can
# be collected before it finishes (Python 3.12 asyncio GC behaviour).
_background_tasks: set = set()

# Abort events for in-flight crew executions, keyed by thinking_msg.message_id.
_crew_abort_events: dict[int, asyncio.Event] = {}

async def start_telegram_bot():
	"""Start the Telegram bot in polling mode within the FastAPI event loop."""
	global bot_app
	if not settings.TELEGRAM_BOT_TOKEN:
		logging.warning("TELEGRAM_BOT_TOKEN not set. Bot will not start.")
		return

	logger.debug("start_telegram_bot - step 1: Building app")
	bot_app = (
		Application.builder()
		.token(settings.TELEGRAM_BOT_TOKEN)
		.concurrent_updates(True)
		.build()
	)

	# Register handlers
	logger.debug("start_telegram_bot - step 2: Registering handlers")
	bot_app.add_handler(CommandHandler("start", cmd_start))
	bot_app.add_handler(CommandHandler("tree", cmd_tree))
	bot_app.add_handler(CommandHandler("search", cmd_search))
	bot_app.add_handler(CommandHandler("memories", cmd_memories))
	bot_app.add_handler(CommandHandler("unlearn", cmd_unlearn))
	bot_app.add_handler(CommandHandler("purge", cmd_purge))
	bot_app.add_handler(CommandHandler("week", cmd_week))
	bot_app.add_handler(CommandHandler("month", cmd_month))
	bot_app.add_handler(CommandHandler("quarter", cmd_quarter))
	bot_app.add_handler(CommandHandler("year", cmd_year))
	bot_app.add_handler(CommandHandler("day", cmd_day))
	bot_app.add_handler(CommandHandler("learn", cmd_learn))
	bot_app.add_handler(CommandHandler("add", cmd_learn))
	bot_app.add_handler(CommandHandler("protocols", cmd_protocols))
	bot_app.add_handler(CommandHandler("remind", cmd_remind))
	bot_app.add_handler(CommandHandler("custom", cmd_custom))
	bot_app.add_handler(CommandHandler("think", cmd_think))
	bot_app.add_handler(CommandHandler("personal", cmd_personal))
	bot_app.add_handler(CommandHandler("agent", cmd_agent))
	bot_app.add_handler(CommandHandler("skills", cmd_agent)) # Legacy support
	bot_app.add_handler(CommandHandler("crews", cmd_crews))
	bot_app.add_handler(CommandHandler("crew", cmd_crews))
	bot_app.add_handler(CallbackQueryHandler(handle_crew_abort, pattern="^crew_abort_"))
	bot_app.add_handler(CallbackQueryHandler(handle_approval, pattern="^think_"))
	bot_app.add_handler(CallbackQueryHandler(handle_unlearn_approval, pattern="^unlearn_"))
	bot_app.add_handler(CallbackQueryHandler(handle_wipe_confirm, pattern="^wipe_"))
	bot_app.add_handler(CallbackQueryHandler(handle_calendar_approval, pattern="^cal_"))
	bot_app.add_handler(CallbackQueryHandler(handle_draft_approval, pattern="^draft_"))
	bot_app.add_handler(CallbackQueryHandler(handle_memories_callback, pattern="^call_memories$"))
	bot_app.add_handler(CallbackQueryHandler(handle_help_callback, pattern="^call_help$"))
	bot_app.add_handler(CommandHandler("help", cmd_help))
	bot_app.add_handler(CommandHandler("commands", cmd_help))
	bot_app.add_handler(CommandHandler("status", cmd_status))
	bot_app.add_handler(CommandHandler("board", cmd_board))
	bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_freetext))
	bot_app.add_handler(MessageHandler(filters.VOICE, handle_voice))
	bot_app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
	bot_app.add_handler(MessageHandler(filters.Document.IMAGE, handle_photo))

	# Initialize and start polling (non-blocking)
	logger.debug("start_telegram_bot - step 3: Initializing")
	await bot_app.initialize()
	logger.debug("start_telegram_bot - step 4: Starting")
	await bot_app.start()
	logger.debug("start_telegram_bot - step 5: Start Polling (processing pending updates)")
	await bot_app.updater.start_polling(drop_pending_updates=False)
	logger.debug("start_telegram_bot - step 6: Polling started")

	# On every startup, check if the user sent messages that were never answered
	# (e.g. the previous process crashed or the LLM was still loading).
	async def send_startup_greeting():
		try:
			# Run the watchdog recovery first — it handles the unanswered messages path.
			# Then run the original recovery for deployment-changes notification.
			from app.services.message_watchdog import check_unanswered_messages
			await check_unanswered_messages()
			# Deployment changes banner (only if nothing was recovered above)
			await _send_changes_notification_if_needed()
		except Exception:
			logger.exception("FAILED to complete Telegram startup recovery")

	# Register send functions with the notifier shim so task modules can use them
	# without importing this module directly (breaks circular import cycles).
	from app.services import notifier as _notifier
	_notifier.register(
		send=send_notification,
		send_html=send_notification_html,
		send_voice=send_voice_message,
		stats_footer=_get_stats_footer,
		nav_markup=get_nav_markup,
	)

	# Register Telegram as a push channel in the message_bus so cross-channel
	# messages (e.g. dashboard conversations) are delivered here automatically.
	from app.services.message_bus import bus as _bus
	_bus.register_channel("telegram", push_fn=send_notification_html)

	# Launch greeting in background (keep a strong reference to prevent GC mid-run)
	_task = asyncio.create_task(send_startup_greeting())
	_background_tasks.add(_task)
	_task.add_done_callback(_background_tasks.discard)


def _is_error_stub(text: str) -> bool:
	"""Check if a Z reply is a known LLM-unavailable error stub, not a real response."""
	lower = text.lower()
	return any(s in lower for s in (
		"still waking up",
		"encountered friction",
		"having trouble reaching",
		"still warming up",
		"try again in a moment",
		"that specific thread was dropped",
	))

# Automated system messages that Z sends proactively (not in response to a user
# message). The recovery analysis must not treat these as real answers.
_SYSTEM_MESSAGE_PREFIXES = (
	"z is online",
	"🚀",
	"🎯 mission check",
)

def _is_system_message(text: str) -> bool:
	"""True for heartbeats, startup banners, and proactive nudges."""
	lower = text.lower().strip()
	return any(lower.startswith(p) for p in _SYSTEM_MESSAGE_PREFIXES)

async def _send_online_notification(recovery_html: str = ""):
	"""Notify the user that Z is back. If there are recovered messages the LLM
	reply is the whole message — no stiff banner. When idle, send a short casual
	note so the user knows Z is alive without any formal ceremony."""
	try:
		lang = await get_user_lang()
		t = get_translations(lang)
		if recovery_html:
			# LLM response already carries the greeting — send it as-is.
			msg = recovery_html
		else:
			# Nothing to recover — just a quiet "I'm back".
			msg = "<i>back.</i>"
		await send_notification_html(msg, reply_markup=get_nav_markup(t))
	except Exception as _e:
		logger.warning("Online notification failed: %s", _e)

_LATEST_CHANGES_PATH = "/app/agent/latest_changes.txt"

def _read_latest_changes() -> str:
	"""Read the latest deployment changes file (written by sync.sh).
	Does NOT delete -- call _consume_latest_changes() after successful delivery."""
	import os
	try:
		if not os.path.exists(_LATEST_CHANGES_PATH):
			return ""
		with open(_LATEST_CHANGES_PATH, "r") as f:
			return f.read().strip()
	except Exception as _e:
		logger.debug("latest_changes read failed: %s", _e)
		return ""

def _consume_latest_changes():
	"""Delete the changes file after successful delivery."""
	import os
	try:
		if os.path.exists(_LATEST_CHANGES_PATH):
			os.remove(_LATEST_CHANGES_PATH)
	except Exception as _e:
		logger.debug("Could not remove latest-changes file: %s", _e)

def _format_raw_changes_html(changes: str) -> str:
	"""Format raw commit messages as a minimal HTML fallback."""
	lines = [l.strip() for l in changes.splitlines() if l.strip().startswith("- ")]
	if not lines:
		return ""
	formatted = "\n".join(lines[:10])
	return f"<i>back.</i>\n\n<pre>{formatted}</pre>"

async def _send_changes_notification_if_needed():
	"""Send the deployment-changes banner if a latest_changes.txt exists.
	Called at startup after watchdog recovery handles any unanswered messages."""
	await asyncio.sleep(15)
	changes = _read_latest_changes()
	if not changes:
		await _send_online_notification()
		return
	logger.info("Startup: deployment changes detected, asking LLM to mention them.")
	try:
		from app.services.llm import chat_with_context
		changes_prompt = (
			"You came back online after a deployment. Casually let the user know you're back "
			"and mention what's new in 1–3 short sentences, in plain conversational language. "
			"Do NOT use bullet lists, formal headers, or 'Recent Logic Updates'. "
			"Just talk like a friend would. Keep it brief.\n\n"
			f"Deployment notes:\n{changes[:1500]}"
		)
		raw = await asyncio.wait_for(
			chat_with_context(
				changes_prompt,
				history=[],
				include_projects=False,
				include_people=False,
				use_agent=False,
				tier_override="fast",
				thinking=False,
			),
			timeout=60,
		)
		if raw and not _is_error_stub(raw):
			clean = strip_llm_time_header(raw)
			_consume_latest_changes()
			await _send_online_notification(recovery_html=_md_to_html(clean))
			return
	except Exception as _ce:
		logger.warning("Startup: changes LLM call failed (%r) — using raw fallback.", _ce, exc_info=True)
	fallback_html = _format_raw_changes_html(changes)
	if fallback_html:
		_consume_latest_changes()
		await _send_online_notification(recovery_html=fallback_html)
	else:
		await _send_online_notification()


async def _recover_unanswered_messages():
	"""Legacy startup recovery — kept for backwards-compat. The periodic watchdog
	(`message_watchdog.check_unanswered_messages`) is the canonical path now."""
	pass


async def stop_telegram_bot():
	"""Gracefully stop the bot."""
	global bot_app
	if bot_app:
		try:
			if bot_app.updater and bot_app.updater.running:
				await bot_app.updater.stop()
			if bot_app.running:
				await bot_app.stop()
			await bot_app.shutdown()
		except Exception as e:
			logging.warning("Telegram shutdown warning (non-fatal): %s", e)

async def send_notification(text: str, reply_markup=None):
	"""Send a message to the owner wrapped in an HTML blockquote island.

	Telegram enforces a 4096-character message limit.  Long briefings are
	split on paragraph boundaries and sent as consecutive messages; the
	reply_markup is only attached to the final chunk.
	"""
	if not settings.TELEGRAM_BOT_TOKEN or not settings.TELEGRAM_ALLOWED_USER_ID:
		return
	bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
	html_text = _md_to_html(text)

	MAX_CHARS = 3800  # Leave headroom for <blockquote> wrapper tags
	chat_id = int(settings.TELEGRAM_ALLOWED_USER_ID)

	if len(html_text) <= MAX_CHARS:
		await bot.send_message(
			chat_id=chat_id,
			text=f"<blockquote>{html_text}</blockquote>",
			parse_mode="HTML",
			reply_markup=reply_markup,
		)
		return

	# Split on double-newlines (paragraph breaks) to keep chunks coherent
	paragraphs = html_text.split("\n\n")
	chunks: list[str] = []
	current = ""
	for para in paragraphs:
		segment = (para + "\n\n") if current else para
		if len(current) + len(segment) > MAX_CHARS and current:
			chunks.append(current.rstrip())
			current = para + "\n\n"
		else:
			current += segment
	if current.strip():
		chunks.append(current.rstrip())

	for i, chunk in enumerate(chunks):
		is_last = (i == len(chunks) - 1)
		await bot.send_message(
			chat_id=chat_id,
			text=f"<blockquote>{chunk}</blockquote>",
			parse_mode="HTML",
			reply_markup=reply_markup if is_last else None,
		)

async def send_notification_html(text: str, reply_markup=None):
	"""Send an HTML-formatted message to the owner (already formatted)."""
	if not settings.TELEGRAM_BOT_TOKEN or not settings.TELEGRAM_ALLOWED_USER_ID:
		return
	bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
	await bot.send_message(
		chat_id=int(settings.TELEGRAM_ALLOWED_USER_ID),
		text=text,
		parse_mode="HTML",
		reply_markup=reply_markup,
		link_preview_options=LinkPreviewOptions(is_disabled=True),
	)

def _md_to_html(text: str) -> str:
	"""Minimal Markdown-to-HTML conversion for Telegram.

	Escapes raw HTML special characters first so that LLM-generated text
	containing '<', '>', or '&' cannot break Telegram's HTML parser.
	Intentional <b>, <i>, <a> tags are injected by the substitutions below.
	"""
	import html as _html
	# Escape raw HTML chars BEFORE injecting intentional tags.
	safe = _html.escape(text)

	# Bold: **text** or *text* -> <b>text</b>
	html = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', safe)
	html = re.sub(r'\*(.+?)\*', r'<b>\1</b>', html)
	# Italic: _text_ -> <i>text</i>
	html = re.sub(r'(?<!\w)_(.+?)_(?!\w)', r'<i>\1</i>', html)
	# Links: [text](url) -> <a href="url">text</a>
	html = re.sub(r'\[(.+?)\]\((.+?)\)', r'<a href="\2">\1</a>', html)

	# Support passthrough for common safe HTML tags that may be generated or
	# injected by Z (e.g. footers).
	for tag in ['b', 'i', 'code', 'u', 's', 'pre', 'blockquote']:
		html = html.replace(f"&lt;{tag}&gt;", f"<{tag}>")
		html = html.replace(f"&lt;/{tag}&gt;", f"</{tag}>")
	
	# Special case for <a> (requires attribute passthrough)
	html = re.sub(r'&lt;a href="(.+?)"&gt;(.+?)&lt;/a&gt;', r'<a href="\1">\2</a>', html)

	return html

def strip_llm_time_header(text: str) -> str:
	"""Remove LLM-generated time headers like '16:40 - Tuesday 3rd' from the start of text."""
	return re.sub(r'^\d{1,2}:\d{2}\s*[-\u2013]?\s*[^\n]*\n*', '', text, count=1).strip()

async def send_voice_message(audio_bytes: bytes, caption: Optional[str] = None):
	"""Send voice message to the owner."""
	if not settings.TELEGRAM_BOT_TOKEN or not settings.TELEGRAM_ALLOWED_USER_ID:
		return
	bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
	import io
	voice_file = io.BytesIO(audio_bytes)
	voice_file.name = "briefing.mp3"
	await bot.send_voice(
		chat_id=settings.TELEGRAM_ALLOWED_USER_ID,
		voice=voice_file,
		caption=f"<blockquote>{_md_to_html(caption)}</blockquote>" if caption else None,
		parse_mode="HTML"
	)

# --- Auth decorator ---
def owner_only(func):
	async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
		if str(update.effective_user.id) != settings.TELEGRAM_ALLOWED_USER_ID:
			return None  # Silently ignore strangers
		return await func(update, context)
	return wrapper

async def safe_reply(update: Update, text: str, reply_markup=None):
	"""Sends a reply wrapped in an HTML blockquote island."""
	msg = update.effective_message
	try:
		html_text = _md_to_html(text)
		await msg.reply_text(f"<blockquote>{html_text}</blockquote>", parse_mode="HTML", reply_markup=reply_markup)
	except Exception as e:
		logger.debug("HTML reply failed, falling back to plain: %s", e)
		await msg.reply_text(text, reply_markup=reply_markup)

async def safe_edit(message, text: str, parse_mode="HTML", reply_markup=None):
	"""Tries to edit a message, falls back to plain text on error."""
	try:
		await message.edit_text(text, parse_mode=parse_mode, reply_markup=reply_markup)
	except Exception as e:
		logger.debug("HTML edit failed, falling back to plain: %s", e)
		try:
			await message.edit_text(text)
		except Exception as _pe:
			logger.debug("safe_edit final fallback failed: %s", _pe)


async def _send_chunked_reply(thinking_msg, html_body: str, reply_markup=None):
	"""Deliver a response via the thinking message.

	If the content fits within Telegram's 4096-char limit, the thinking
	message is edited in-place.  Otherwise the thinking message is deleted
	and the response is sent as a sequence of new messages, split at
	paragraph boundaries to preserve coherence.
	"""
	MAX_CHARS = 3800  # Headroom for <blockquote> wrapper tags

	if len(html_body) <= MAX_CHARS:
		await safe_edit(thinking_msg, f"<blockquote>{html_body}</blockquote>",
			parse_mode="HTML", reply_markup=reply_markup)
		return

	# Content too long for a single message -- delete the thinking placeholder
	# and send as multiple messages.
	try:
		await thinking_msg.delete()
	except Exception as _e:
		logger.debug("Telegram delete (chunked reply) ignored: %s", _e)

	bot = thinking_msg.get_bot()
	chat_id = thinking_msg.chat_id

	# Split on paragraph boundaries
	paragraphs = html_body.split("\n\n")
	chunks: list[str] = []
	current = ""
	for para in paragraphs:
		segment = (para + "\n\n") if current else para
		if len(current) + len(segment) > MAX_CHARS and current:
			chunks.append(current.rstrip())
			current = para + "\n\n"
		else:
			current += segment
	if current.strip():
		chunks.append(current.rstrip())

	# Handle oversized single paragraphs by splitting at sentence boundaries
	final_chunks: list[str] = []
	for chunk in chunks:
		if len(chunk) <= MAX_CHARS:
			final_chunks.append(chunk)
		else:
			sentences = re.split(r'(?<=[.!?])\s+', chunk)
			sub = ""
			for s in sentences:
				if len(sub) + len(s) + 1 > MAX_CHARS and sub:
					final_chunks.append(sub.rstrip())
					sub = s
				else:
					sub = f"{sub} {s}" if sub else s
			if sub.strip():
				final_chunks.append(sub.rstrip())

	if not final_chunks:
		return

	for i, chunk in enumerate(final_chunks):
		is_last = (i == len(final_chunks) - 1)
		try:
			await bot.send_message(
				chat_id=chat_id,
				text=f"<blockquote>{chunk}</blockquote>",
				parse_mode="HTML",
				reply_markup=reply_markup if is_last else None,
			)
		except Exception as e:
			logger.warning("Chunked reply chunk %d failed: %s", i, e)
@owner_only
async def cmd_board(update: Update, context: ContextTypes.DEFAULT_TYPE):
	"""Show the exact Planka project → board → lists that Z targets, with a clickable link."""
	try:
		from app.services.planka import get_planka_auth_token
		from app.services.operator_board import operator_service
		import httpx
		import html as _html

		token = await get_planka_auth_token()
		async with httpx.AsyncClient(base_url=settings.PLANKA_BASE_URL, timeout=10.0,
									  headers={"Authorization": f"Bearer {token}"}) as client:
			# Force full re-resolve (bypass cache to get accurate IDs)
			operator_service._project_id = None
			operator_service._board_id = None
			project_id, board_id = await operator_service.initialize_board(client)

			# Fetch project details for name
			proj_resp = await client.get(f"/api/projects/{project_id}")
			proj_name = _html.escape(proj_resp.json().get("item", {}).get("name", "Unknown"))

			# Fetch board + lists
			b_resp = await client.get(f"/api/boards/{board_id}", params={"included": "lists"})
			b_data = b_resp.json()
			board_name = _html.escape(b_data.get("item", {}).get("name", "Unknown"))
			lists = b_data.get("included", {}).get("lists", [])
			list_names = [f"  • {_html.escape(l['name'])} (id: {l['id']})" for l in lists]

		base_url = settings.BASE_URL.rstrip('/')
		link = f"{base_url}/api/dashboard/planka-redirect?target_board_id={board_id}"

		msg = (
			f"<b>Z's Operator Board target</b>\n\n"
			f"Project: <code>{proj_name}</code> (id: <code>{project_id}</code>)\n"
			f"Board: <code>{board_name}</code> (id: <code>{board_id}</code>)\n\n"
			f"<b>Lists:</b>\n" + "\n".join(list_names) + "\n\n"
			f'<a href="{link}">Open in Planka →</a>'
		)
		await safe_reply(update, msg)
	except Exception as e:
		logger.error("cmd_board failed: %s", e)
		await safe_reply(update, "Board diagnostic failed. Check server logs.")


@owner_only
async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
	"""Deep status check of all integrations."""
	try:
		from app.services.memory import get_memory_stats
		from app.services.planka import get_planka_auth_token
		
		# 1. Memory
		m_stats = await get_memory_stats()
		m_text = "🟢 Active" if m_stats['status'] != 'error' else "🔴 Offline"
		
		# 2. Planka
		p_text = "🔴 Offline"
		try:
			token = await get_planka_auth_token()
			if token: p_text = "🟢 Connected"
		except Exception as _pe:
			logger.debug("cmd_status Planka check failed: %s", _pe)
		# 3. LLM — check all three tiers independently
		import httpx as _httpx
		from app.config import settings as _s

		async def _ping_tier(url: str) -> bool:
			try:
				async with _httpx.AsyncClient(timeout=_httpx.Timeout(5.0, connect=3.0)) as _c:
					r = await _c.get(f"{url}/health")
					return r.status_code < 500
			except Exception:
				return False

		local_ok = await _ping_tier(_s.LLM_LOCAL_URL)
		cloud_ok = _s.cloud_configured
		def dot(ok):
			return "🟢" if ok else "🔴"
		l_text = (
			f"{dot(local_ok)} Local  "
			f"{dot(cloud_ok)} Cloud"
		)
		lang = await get_user_lang()
		t = get_translations(lang)
		
		# Weekday mapping
		day_keys = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
		now_tz = datetime.now(pytz.timezone(get_user_timezone()))
		weekday_name = t.get(day_keys[now_tz.weekday()], now_tz.strftime('%A'))

		status_report = (
			f"🛰️ <b>{t.get('status_heading', 'System Status Report')}</b>\n\n"
			f"🧠 <b>{t.get('memory_search', 'Memory')}:</b> {m_text} ({m_stats.get('points', 0)} pts)\n"
			f"📋 <b>{t.get('operator_board', 'Task Board')}:</b> {p_text}\n"
			f"🤖 <b>{t.get('intelligence', 'Intelligence')}:</b> {l_text}\n\n"
			f"📍 <b>{weekday_name}, {now_tz.strftime('%H:%M:%S')}</b>"
		)
		await safe_reply(update, status_report, reply_markup=get_nav_markup(t))
	except Exception as e:
		logger.error("cmd_status failed: %s", e)
		await safe_reply(update, "System Status check failed. Check local backend logs.")

# --- Command Handlers ---
@owner_only
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
	await safe_reply(update, "Personal AI OS is online.")

@owner_only
async def cmd_tree(update: Update, context: ContextTypes.DEFAULT_TYPE):
	try:
		from app.services.planka import get_project_tree
		lang = await get_user_lang()
		t = get_translations(lang)
		tree = await get_project_tree(as_html=False)
		await safe_reply(update, tree, reply_markup=get_nav_markup(t))
	except Exception as e:
		await safe_reply(update, f"Failed to fetch mission tree: {e}")

@owner_only
async def cmd_personal(update: Update, context: ContextTypes.DEFAULT_TYPE):
	try:
		from app.services.personal_context import refresh_personal_context, get_personal_context_debug_report
		await refresh_personal_context()
		report = get_personal_context_debug_report()
		if len(report) > 3500:
			report = report[:3500] + "\n... (truncated — use dashboard to view full context)"
		await safe_reply(update, report)
	except Exception as e:
		await safe_reply(update, f"Personal context report failed: {e}")

@owner_only
async def cmd_week(update: Update, context: ContextTypes.DEFAULT_TYPE):
	try:
		from app.tasks.weekly import weekly_review
		report = await weekly_review()
		await safe_reply(update, report)
	except Exception as e:
		await safe_reply(update, f"Weekly review failed: {e}")

@owner_only
async def cmd_month(update: Update, context: ContextTypes.DEFAULT_TYPE):
	try:
		from app.tasks.monthly import monthly_review
		report = await monthly_review()
		await safe_reply(update, report)
	except Exception as e:
		await safe_reply(update, f"Monthly review failed: {e}")

@owner_only
async def cmd_protocols(update: Update, context: ContextTypes.DEFAULT_TYPE):
	from app.services.agent_actions import AVAILABLE_TOOLS
	tools_info = "\n".join([f"• *{t.name}*: {t.description}" for t in AVAILABLE_TOOLS])
	
	protocols_text = (
		"🤖 *Z Operator Protocols*\n\n"
		"I operate via **Semantic Action Tags**. These protocols allow me to transition from passive reasoning to active intervention.\n\n"
		f"*Available Strategic Actions:*\n{tools_info}\n\n"
		"_Every thought is an opportunity for evolution._"
	)
	await safe_reply(update, protocols_text)

@owner_only
async def cmd_remind(update: Update, context: ContextTypes.DEFAULT_TYPE):
	msg = update.message.text.replace("/remind", "").strip()
	if not msg:
		await safe_reply(update, "Usage: /remind 2 times an hour for 4 hours to drink water")
		return
		
	from app.services.llm import chat
	
	# Let the LLM parse the natural language into the action tag
	prompt = (
		"Convert this reminder request into a [ACTION: REMIND ...] tag.\n"
		"Format: [ACTION: REMIND | MESSAGE: <text> | INTERVAL: <minutes> | DURATION: <hours>]\n\n"
		f"Input: {msg}"
	)
	
	response = await chat(prompt, _feature="remind_parse")
	from app.services.agent_actions import parse_and_execute_actions
	_, executed, _ = await parse_and_execute_actions(response)
	
	if executed:
		await safe_reply(update, "\n".join(executed))
	else:
		await safe_reply(update, "Could not parse the reminder frequency. Try: /remind 30m for 4h drink water")

@owner_only
async def cmd_custom(update: Update, context: ContextTypes.DEFAULT_TYPE):
	msg = update.message.text.replace("/custom", "").strip()
	if not msg:
		await safe_reply(update, "Usage: /custom Every Monday at 12:00 remind me to check the stats")
		return
		
	from app.services.llm import chat
	
	prompt = (
		"Convert this custom schedule request into a [ACTION: SCHEDULE_CUSTOM ...] tag.\n"
		"Format: [ACTION: SCHEDULE_CUSTOM | NAME: <short_name> | MESSAGE: <text> | TYPE: <cron/interval> | SPEC: <spec>]\n"
		"CRON SPEC: minute hour day month day_of_week\n"
		"INTERVAL SPEC: minutes=N or hours=N\n\n"
		f"Input: {msg}"
	)
	
	response = await chat(prompt, _feature="custom_schedule_parse")
	from app.services.agent_actions import parse_and_execute_actions
	_, executed, _ = await parse_and_execute_actions(response)
	
	if executed:
		await safe_reply(update, "\n".join(executed))
	else:
		await safe_reply(update, "Could not parse. Try: /custom every day at 10am remind me...")

@owner_only
async def cmd_quarter(update: Update, context: ContextTypes.DEFAULT_TYPE):
	try:
		from app.tasks.quarterly import quarterly_review
		report = await quarterly_review()
		await safe_reply(update, report)
	except Exception as e:
		await safe_reply(update, f"Quarterly review failed: {e}")

@owner_only
async def cmd_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
	try:
		from app.tasks.morning import morning_briefing
		await morning_briefing()
	except Exception as e:
		await safe_reply(update, f"Morning briefing failed: {e}")

@owner_only
async def cmd_year(update: Update, context: ContextTypes.DEFAULT_TYPE):
	try:
		from app.tasks.yearly import yearly_review
		report = await yearly_review()
		await safe_reply(update, report)
	except Exception as e:
		await safe_reply(update, f"Yearly review failed: {e}")

@owner_only
async def cmd_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
	query = update.message.text.replace("/search", "").strip()
	from app.services.memory import semantic_search
	results = await semantic_search(query)
	await safe_reply(update, results)

@owner_only
async def cmd_unlearn(update: Update, context: ContextTypes.DEFAULT_TYPE):
	query = update.message.text.replace("/unlearn", "").strip()
	if not query:
		await safe_reply(update, "What should I unlearn? Provide a part of the memory text.")
		return

	from app.services.memory import get_qdrant, COLLECTION_NAME
	client = get_qdrant()
	
	# Find matching points
	from app.services.memory import get_embedder
	query_vector = get_embedder().encode(query).tolist()
	
	results = client.query_points(
		collection_name=COLLECTION_NAME,
		query=query_vector,
		limit=3
	)
	
	if not results.points:
		await safe_reply(update, "No matching memories found to unlearn.")
		return

	# Show matches with buttons
	keyboard = []
	for p in results.points:
		text = p.payload.get('text', '[No Text]')[:50] + "..."
		keyboard.append([InlineKeyboardButton(f"Unlearn: {text}", callback_data=f"unlearn_confirm_{p.id}")])
	
	keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="unlearn_cancel")])
	reply_markup = InlineKeyboardMarkup(keyboard)
	await safe_reply(update, "Select the knowledge I should unlearn:", reply_markup=reply_markup)

@owner_only
async def cmd_memories(update: Update, context: ContextTypes.DEFAULT_TYPE):
	from app.services.memory import get_qdrant, COLLECTION_NAME
	client = get_qdrant()
	# Fetch 50 instead of 100 to stay safe with message limits
	results, _ = client.scroll(collection_name=COLLECTION_NAME, limit=50)
	if not results:
		await safe_reply(update, "No memories stored in the vault.")
		return
	
	lines = []
	for p in results:
		text = p.payload.get('text', '[No Text]')
		# Escape basic markdown to prevent parsing errors
		clean_text = text.replace('*', '').replace('_', '').replace('`', '')
		lines.append(f"• {clean_text}")
	
	memory_list = "\n".join(lines)
	
	# Telegram limit is 4096. We stay safe at 3500.
	if len(memory_list) > 3500:
		memory_list = memory_list[:3500] + "\n... (Truncated for length)"
		
	await safe_reply(update, f"🧠 *Semantic Vault: Core Knowledge Vault*\n\n{memory_list}")

@owner_only
async def handle_unlearn_approval(update: Update, context: ContextTypes.DEFAULT_TYPE):
	query = update.callback_query
	await query.answer()
	
	if query.data == "unlearn_cancel":
		await query.edit_message_text("Cancelled. Information retained.")
		return
		
	point_id = query.data.replace("unlearn_confirm_", "")
	from app.services.memory import delete_memory
	success = await delete_memory(point_id)
	
	if success:
		await query.edit_message_text("✅ Information successfully unlearned and purged from the vault.")
	else:
		await query.edit_message_text("❌ Failed to unlearn. Check logs.")

@owner_only
async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
	lang = await get_user_lang()
	t = get_translations(lang)
	help_text = t.get("help_msg_full")
	if not help_text:
		# Fallback if full help not in translations.py yet
		help_text = (
			"\U0001f916 *Z -- Operator Controls*\n\n"
			"*Briefings & Reviews*\n"
			"/day -- Proactive morning briefing (contextual summary)\n"
			"/week -- Strategic review of all projects and roadmaps\n"
			"/month -- High-level 30-day mission review\n"
			"/quarter -- Strategic 90-day review and roadmap planning\n"
			"/year -- Yearly goal setting based on project themes\n\n"
			"*Mission Control*\n"
			"/tree -- Full life hierarchy and workspace overview\n"
			"/crews -- List all active Dify multi-agent crews and their statuses\n"
			"/crew -- Execute a specialized autonomous agent (crew)\n"
			"/think -- Complex reasoning with human-in-the-loop approval\n"
			"/remind -- Set a temporary recurring reminder\n"
			"/custom -- Create a persistent scheduled task\n"
			"/protocols -- Inspect Z's agentic tools (action tags)\n"
			"/board -- Show the exact Planka project target for Z's operations\n\n"
			"*Memory & Intelligence*\n"
			"/search -- Conceptual search of the semantic knowledge vault\n"
			"/memories -- List all core knowledge in permanent memory\n"
			"/learn -- Commit specific facts to long-term memory\n"
			"/unlearn -- Evolve past points in the vault\n\n"
			"*System*\n"
			"/personal -- Show personal context Z loaded from /personal\n"
			"/agent -- Show agent skill modules loaded from /agent\n"
			"/status -- Deep integration health check\n"
			"/start -- System status check and heartbeat\n"
			"/purge -- Permanently delete all memories\n\n"
			"_Tap any command to execute it directly._"
		)
	await safe_reply(update, help_text, reply_markup=get_nav_markup(t))

@owner_only
async def cmd_crews(update: Update, context: ContextTypes.DEFAULT_TYPE):
	"""Interrogates CrewRegistry and formats a list of active crews, or executes one."""
	from app.services.crews import crew_registry
	lang = await get_user_lang()
	t = get_translations(lang)
	
	# Execution mode: /crew <id> <input>
	if context.args:
		crew_id = context.args[0]
		user_input = " ".join(context.args[1:]) or "Execute autonomous cycle"
		
		config = crew_registry.get(crew_id)
		if config and config.enabled:
			await _process_crew_stream(update, context, crew_id, user_input, t)
			return
		elif config and not config.enabled:
			import html as _html
			await update.message.reply_text(f"<blockquote>⚠️ <i>Crew '<b>{_html.escape(crew_id)}</b>' {t.get('is_disabled', 'is disabled')}.</i></blockquote>", parse_mode="HTML")
			return
		# If first arg doesn't look like a crew ID, we fall through to list all (useful if user typed junk)

	await update.message.reply_text(f"<blockquote>📡 <i>{t.get('interrogating_topology', 'Interrogating internal Crew topology...')}</i></blockquote>", parse_mode="HTML")
	
	try:
		msg_parts = [f"🛸 <b>{t.get('crews_registry_status', 'Native Tactical Crews Status')}</b>\n"]
		active_crews = crew_registry.list_active()
		
		if not active_crews:
			msg_parts.append(f"<i>{t.get('no_crews_found', 'No Native Crews provisioned or active.')}</i>")
		else:
			for crew in active_crews:
				on_demand = t.get('on_demand', 'On-demand')
				cadence = crew.feeds_briefing or on_demand
				
				msg_parts.append(
					f"• <b>{crew.id}: {crew.name}</b>\n"
					f"  ├ Type: <code>{crew.type}</code>\n"
					f"  ├ Cadence: {cadence}\n"
					f"  └ <i>{crew.description}</i>\n"
				)
		
		await safe_reply(update, "\n".join(msg_parts))
	except Exception:
		await safe_reply(update, f"❌ {t.get('failed_fetch_crews', 'Failed to fetch Native Crew registry status.')}")

@owner_only
async def handle_memories_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
	await update.callback_query.answer()
	await cmd_memories(update, context)

@owner_only
async def handle_help_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
	await update.callback_query.answer()
	await cmd_help(update, context)

@owner_only
async def cmd_agent(update: Update, context: ContextTypes.DEFAULT_TYPE):
	try:
		from app.services.agent_context import refresh_agent_context, get_agent_skills_debug_report
		await refresh_agent_context()
		report = get_agent_skills_debug_report()
		if len(report) > 3500:
			report = report[:3500] + "\n... (truncated — use dashboard to view full skills list)"
		await safe_reply(update, report)
	except Exception as e:
		await safe_reply(update, f"Agent skills report failed: {e}")

@owner_only
async def cmd_learn(update: Update, context: ContextTypes.DEFAULT_TYPE):
	text = update.message.text
	topic = text.replace("/learn", "").replace("/add", "").strip()
	if not topic:
		await safe_reply(update, "What should I learn? Usage: /learn <fact>")
		return
	from app.services.memory import store_memory
	await store_memory(topic)
	await safe_reply(update, f"Stored: {topic}")

@owner_only
async def cmd_purge(update: Update, context: ContextTypes.DEFAULT_TYPE):
	"""Request semantic memory purge with detailed confirmation."""
	lang = await get_user_lang()
	t = get_translations(lang)
	keyboard = [
		[
			InlineKeyboardButton(f"\U0001f525 {t.get('purge_confirm_btn', 'Yes, purge everything')}", callback_data="wipe_confirm"),
			InlineKeyboardButton(f"\u270b {t.get('purge_cancel_btn', 'Cancel')}", callback_data="wipe_cancel"),
		]
	]
	reply_markup = InlineKeyboardMarkup(keyboard)
	default_deleted = (
		"- All stored facts, preferences, and personal context\n"
		"- All learned information from past conversations\n"
		"- All manually committed memories (/add)"
	)
	default_safe = (
		"- Your calendar, task boards, and projects (Planka)\n"
		"- Your circle of trust (people database)\n"
		"- Briefing history"
	)
	default_body = "This will permanently delete <b>all</b> facts stored in Z\u2019s long-term memory vault (Qdrant)."
	await update.message.reply_text(
		"<blockquote>"
		f"\u26a0\ufe0f <b>{t.get('purge_heading', 'Semantic Memory Purge')}</b>\n\n"
		f"{t.get('purge_body', default_body)}\n\n"
		f"<b>{t.get('purge_deleted_label', 'What gets deleted:')}</b>\n"
		f"{t.get('purge_deleted_items', default_deleted)}\n\n"
		f"<b>{t.get('purge_safe_label', 'What is NOT affected:')}</b>\n"
		f"{t.get('purge_safe_items', default_safe)}\n\n"
		f"{t.get('purge_irreversible', 'This action is <b>irreversible</b>. Z will start with a blank knowledge slate.')}"
		"</blockquote>",
		parse_mode="HTML",
		reply_markup=reply_markup
	)

@owner_only
async def handle_wipe_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
	query = update.callback_query
	await query.answer()
	lang = await get_user_lang()
	t = get_translations(lang)
	if query.data == "wipe_confirm":
		from app.services.memory import wipe_collection
		success = await wipe_collection(confirm=True)
		if success:
			await query.edit_message_text(t.get("purge_success", "\u2705 Semantic memory has been completely wiped."))
		else:
			await query.edit_message_text(t.get("purge_failed", "\u274c Failed to wipe memory. Check logs."))
	else:
		await query.edit_message_text(t.get("purge_cancelled", "Cancelled. Memories are safe."))

@owner_only
async def handle_freetext(update: Update, context: ContextTypes.DEFAULT_TYPE):
	"""Process freeform text via the default LLM with Context & History.
	Implements message coalescing: if Z is already thinking for this chat,
	new messages are buffered and folded into a follow-up response."""
	try:
		chat_id = update.effective_chat.id
		if chat_id not in chat_histories:
			chat_histories[chat_id] = []

		# If the user replied to a previous message, prepend the quoted content for context
		user_text = update.message.text
		if update.message.reply_to_message:
			quoted = update.message.reply_to_message.text or update.message.reply_to_message.caption or ""
			if quoted:
				user_text = f"[Replying to: \"{quoted[:500]}\"]\n\n{user_text}"

		from app.services.message_bus import bus
		# Save user message FIRST via the bus — guarantees persistence even if
		# the LLM times out, and returns cross-channel history in one call.
		_hist = await bus.ingest("telegram", user_text)

		llm_user_text = user_text

		# --- Message Coalescing ---
		if chat_id not in _thinking_locks:
			_thinking_locks[chat_id] = asyncio.Lock()

		lock = _thinking_locks[chat_id]
		if lock.locked():
			# Z is already thinking -- buffer this message for follow-up
			if chat_id not in _pending_messages:
				_pending_messages[chat_id] = []
			_pending_messages[chat_id].append(user_text)
			logger.info("Message coalesced (buffered %d msgs while Z thinks)", len(_pending_messages[chat_id]))
			return

		async with lock:
			await _process_freetext(update, context, chat_id, llm_user_text, history=_hist)

			# After responding, check if messages arrived while we were thinking
			while _pending_messages.get(chat_id):
				buffered = _pending_messages.pop(chat_id)
				combined = "\n".join(buffered)
				# Save the raw user messages (no internal framing) for dashboard display
				# and retrieve updated history including this exchange.
				_follow_hist = await bus.ingest("telegram", combined)
				# Add context hint only for the LLM so it knows these arrived mid-thought
				llm_text = f"[Follow-up messages sent while you were thinking:]\n{combined}"
				await _process_freetext(update, context, chat_id, llm_text, is_followup=True, history=_follow_hist)

	except Exception as e:
		logger.error("handle_freetext failed: %s", e)
		try:
			await safe_reply(update, "I encountered friction while processing that request. My local core is still active, but that specific thread was dropped.")
		except Exception as _se:
			logger.debug("handle_freetext error reporting failed: %s", _se)

async def _process_freetext(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_text: str, is_followup: bool = False, history: list | None = None):
	"""Core freetext processing — Telegram transport layer.

	All routing decisions (crew keyword match, ROUTE tag, phantom guard, etc.)
	are handled by app.services.router.route_message_stream.  This function
	only owns Telegram-specific concerns: thinking message, progressive edits,
	and HTML formatting.
	"""
	import time
	from app.services.router import route_message_stream
	from app.services.crews import resolve_active_crews

	lang = await get_user_lang()
	t = get_translations(lang)

	# For non-followup messages, check keyword routing first so we can hand off
	# to _process_crew_stream (which handles its own Telegram UX).
	if not is_followup:
		_h = history or []
		routed_crews = await resolve_active_crews(_h, user_text, lang=lang)
		if routed_crews:
			logger.info("Auto-routing '%s...' to crew panel %s", user_text[:40], routed_crews)
			await _process_crew_stream(update, context, routed_crews, user_text, t, already_ingested=True)
			return

	# Show thinking placeholder
	if is_followup:
		thinking_msg = await context.bot.send_message(
			chat_id=chat_id,
			text=f"<blockquote><i>{t.get('thinking_followup', 'Processing your follow-up...')}</i></blockquote>",
			parse_mode="HTML",
		)
	else:
		thinking_msg = await update.message.reply_text(
			f"<blockquote><i>{t.get('thinking', 'Thinking...')}</i></blockquote>",
			parse_mode="HTML",
		)

	if history is None:
		from app.models.db import get_global_history
		merged_history = await get_global_history(limit=10)
	else:
		merged_history = history

	# Stream via unified router — collect tokens for progressive edits
	token_stream, result_fut = await route_message_stream(
		user_text=user_text,
		history=merged_history,
		channel="telegram",
		lang=lang,
		save_history=True,
	)

	chunks: list[str] = []
	last_edit_time = time.time()
	EDIT_INTERVAL = 1.5

	async for token in token_stream:
		chunks.append(token)
		now = time.time()
		if now - last_edit_time >= EDIT_INTERVAL:
			partial = "".join(chunks)
			if len(partial.strip()) > 3:
				try:
					display = f"<blockquote><i>{_md_to_html(partial)}...</i></blockquote>"
					await safe_edit(thinking_msg, display, parse_mode="HTML")
				except Exception as _ee:
					logger.debug("Progressive edit skip: %s", _ee)
				last_edit_time = now

	result = await result_fut

	# Empty response — LLM timed out or returned nothing
	if not result.reply.strip():
		try:
			await thinking_msg.delete()
		except Exception as _e:
			logger.debug("Telegram delete ignored: %s", _e)
		return

	# If router redirected to a crew (ROUTE tag), delete thinking msg and hand off
	if result.routed_to_crew:
		try:
			await thinking_msg.delete()
		except Exception as _e:
			logger.debug("Telegram delete (route handoff) ignored: %s", _e)
		await _process_crew_stream(update, context, [result.routed_to_crew], user_text, t, already_ingested=True)
		return

	clean_reply = strip_llm_time_header(result.reply)
	html_reply = _md_to_html(clean_reply)
	footer = await _get_stats_footer()
	display_reply = f"<b>{format_time()}</b>\n\n{html_reply}{footer}"
	await _send_chunked_reply(thinking_msg, display_reply, reply_markup=get_nav_markup(t))

@owner_only
async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
	"""Process voice messages."""
	try:
		status_msg = await update.message.reply_text("<blockquote>🎙️ <i>Z is listening...</i></blockquote>", parse_mode="HTML")
		
		# 1. Download voice file
		voice_file = await context.bot.get_file(update.message.voice.file_id)
		voice_bytes = await voice_file.download_as_bytearray()
		
		# 2. Transcribe
		from app.services.voice import transcribe_voice
		transcript = await transcribe_voice(voice_bytes)
		
		import html as _html
		if not transcript or transcript.startswith("["):
			await safe_edit(status_msg, f"<blockquote>⚠️ <i>{_html.escape(transcript or 'Could not transcribe voice.')}</i></blockquote>", parse_mode="HTML")
			return

		await safe_edit(status_msg, f"<blockquote>📝 <b>Transcript:</b>\n<i>{_html.escape(transcript)}</i>\n\n<i>Thinking...</i></blockquote>", parse_mode="HTML")
		
		# 3. Process as text
		from app.services.llm import chat_with_context, last_model_used
		from app.services.message_bus import bus

		# Persist transcript via the bus so the dashboard and future LLM calls see it.
		merged_history = await bus.ingest("telegram", transcript)

		response = await chat_with_context(
			transcript,
			history=merged_history,
			include_projects=True,
			include_people=True
		)

		clean_reply, _, _ = await bus.commit_reply(
			channel="telegram",
			raw_reply=response,
			model=last_model_used.get(),
			user_text=transcript,
		)
		
		clean_reply = strip_llm_time_header(clean_reply)
		html_reply = _md_to_html(clean_reply)
		display_reply = f"📝 <b>Transcript:</b>\n<i>{_html.escape(transcript)}</i>\n\n<b>{format_time()}</b>\n\n{html_reply}"
		
		footer = await _get_stats_footer()
		await safe_edit(status_msg, f"<blockquote>{display_reply}{footer}</blockquote>", parse_mode="HTML", reply_markup=get_nav_markup())
	except Exception as e:
		logger.error("handle_voice failed: %s", e)
		await safe_reply(update, "Voice processing failed. There might be an issue with the transcription or intelligence layer.")

@owner_only
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
	"""Process photo and image document messages via the cloud vision LLM."""
	try:
		import html as _html
		status_msg = await update.message.reply_text("<blockquote>👁️ <i>Z is looking...</i></blockquote>", parse_mode="HTML")

		# Download — prefer highest-resolution photo; fall back to document
		if update.message.photo:
			tg_file = await context.bot.get_file(update.message.photo[-1].file_id)
		else:
			tg_file = await context.bot.get_file(update.message.document.file_id)
		image_bytes = bytes(await tg_file.download_as_bytearray())

		user_hint = update.message.caption or ""

		from app.services.vision import caption_image
		caption = await caption_image(image_bytes, user_hint)

		if not caption or caption.startswith("["):
			await safe_edit(status_msg, f"<blockquote>⚠️ <i>{_html.escape(caption or 'Could not process image.')}</i></blockquote>", parse_mode="HTML")
			return

		await safe_edit(status_msg, f"<blockquote>🖼️ <b>Seen:</b>\n<i>{_html.escape(caption)}</i>\n\n<i>Thinking...</i></blockquote>", parse_mode="HTML")

		# Feed caption into the full router pipeline (crew routing, memory, etc.)
		from app.services.message_bus import bus
		from app.services.router import route_message_stream
		from app.services.crews import resolve_active_crews

		lang = await get_user_lang()
		t = get_translations(lang)

		merged_history = await bus.ingest("telegram", caption)

		routed_crews = await resolve_active_crews(merged_history, caption, lang=lang)
		if routed_crews:
			try:
				await status_msg.delete()
			except Exception:
				pass
			await _process_crew_stream(update, context, routed_crews, caption, t, already_ingested=True)
			return

		token_stream, result_fut = await route_message_stream(
			user_text=caption,
			history=merged_history,
			channel="telegram",
			lang=lang,
			save_history=True,
		)
		async for _ in token_stream:
			pass
		result = await result_fut

		if not result.reply.strip():
			try:
				await status_msg.delete()
			except Exception:
				pass
			return

		if result.routed_to_crew:
			try:
				await status_msg.delete()
			except Exception:
				pass
			await _process_crew_stream(update, context, [result.routed_to_crew], caption, t, already_ingested=True)
			return

		clean_reply = strip_llm_time_header(result.reply)
		html_reply = _md_to_html(clean_reply)
		display_reply = f"🖼️ <b>Seen:</b>\n<i>{_html.escape(caption)}</i>\n\n<b>{format_time()}</b>\n\n{html_reply}"
		footer = await _get_stats_footer()
		await safe_edit(status_msg, f"<blockquote>{display_reply}{footer}</blockquote>", parse_mode="HTML", reply_markup=get_nav_markup(t))

	except Exception as e:
		logger.error("handle_photo failed: %s", e)
		await safe_reply(update, "Image processing failed.")

async def handle_crew_abort(update: Update, context: ContextTypes.DEFAULT_TYPE):
	"""Handles Abort button press during crew execution."""
	query = update.callback_query
	await query.answer()
	try:
		msg_id = int(query.data.split("_", 2)[2])
		event = _crew_abort_events.get(msg_id)
		if event:
			event.set()
	except (ValueError, IndexError) as _e:
		logger.debug("crew_abort callback parse ignored: %s", _e)


async def _process_crew_stream(update: Update, context: ContextTypes.DEFAULT_TYPE, crew_ids: "str | list", user_input: str, t: dict, already_ingested: bool = False):
	"""Executes a crew mission (or panel of crews) with progressive Telegram message updates."""
	from app.services.crews_native import native_crew_engine
	from app.services.message_bus import bus
	import time

	# Normalise to list so the rest of the function handles both call styles.
	if isinstance(crew_ids, str):
		crew_ids = [crew_ids]
	primary_id = crew_ids[0]

	# Persist the user's crew invocation to global_messages so dashboard stays in sync.
	# Skip if the caller already called bus.ingest (e.g. auto-routing from handle_freetext).
	if not already_ingested:
		await bus.ingest("telegram", f"/crew {primary_id} {user_input}".strip())

	crew_display = " + ".join(cid.replace('-', ' ').title() for cid in crew_ids)
	abort_event = asyncio.Event()

	thinking_msg = await update.message.reply_text(
		f"<blockquote><i>...thinking (crew: <b>{crew_display}</b>)</i></blockquote>",
		parse_mode="HTML",
		reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="crew_abort_0")]])
	)
	# Store abort event keyed by actual message_id now that we have it
	_crew_abort_events[thinking_msg.message_id] = abort_event
	# Edit to set the correct message_id in callback_data
	try:
		await thinking_msg.edit_reply_markup(
			reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Abort", callback_data=f"crew_abort_{thinking_msg.message_id}")]])
		)
	except Exception as _e:
		logger.debug("Telegram edit_reply_markup ignored: %s", _e)
	aborted = False

	# Section tracking for multi-crew display
	current_crew_id = primary_id
	current_section_chunks: list[str] = []
	all_sections: dict[str, str] = {}  # crew_id -> full text

	try:
		chunks: list[str] = []
		last_edit_time = time.time()
		EDIT_INTERVAL = 1.5

		stream = (
			native_crew_engine.run_crew_panel(crew_ids, user_input)
			if len(crew_ids) > 1
			else native_crew_engine.run_crew_stream(primary_id, user_input)
		)

		async for chunk in stream:
			if abort_event.is_set():
				aborted = True
				break
			# Detect section separator emitted by run_crew_panel
			if chunk.startswith("\n\n---crew:") and chunk.endswith("---\n\n"):
				all_sections[current_crew_id] = "".join(current_section_chunks)
				current_crew_id = chunk.strip().removeprefix("---crew:").removesuffix("---")
				current_section_chunks = []
				continue
			current_section_chunks.append(chunk)
			chunks.append(chunk)
			now = time.time()
			if now - last_edit_time >= EDIT_INTERVAL:
				partial_text = "".join(chunks)
				if len(partial_text.strip()) > 3:
					try:
						display = f"<blockquote><i>...thinking (crew: <b>{crew_display}</b>)</i>\n\n{_md_to_html(partial_text)}...</blockquote>"
						await safe_edit(thinking_msg, display, parse_mode="HTML",
							reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Abort", callback_data=f"crew_abort_{thinking_msg.message_id}")]]))
					except Exception as _e:
						logger.debug("Telegram crew stream update ignored: %s", _e)
					last_edit_time = now

		# Save last (or only) section
		if current_section_chunks:
			all_sections[current_crew_id] = "".join(current_section_chunks)

		if aborted:
			await safe_edit(thinking_msg, f"<blockquote><i>stopped (crew: <b>{crew_display}</b>)</i></blockquote>", parse_mode="HTML")
			return

		# Commit each section separately for correct action attribution.
		# Attribution footer is appended to the LAST section's raw_reply so it
		# is stored in DB — _last_attributed_crew needs it there for follow-up
		# continuation to work on the next user message.
		combined_clean_parts: list[str] = []
		all_executed_cmds: list = []
		attribution = ", ".join(crew_ids)
		section_items = list(all_sections.items())
		for idx, (cid, section_text) in enumerate(section_items):
			safe_cid = cid.replace("\n", "\\n").replace("\r", "\\r")
			logger.info("Crew panel '%s' raw output (%d chars): %s", safe_cid, len(section_text), section_text[:300])
			is_last = idx == len(section_items) - 1
			raw = section_text + (f"\n\n_(Reasoning by crew {attribution})_" if is_last else "")
			c_reply, e_cmds, p_actions = await bus.commit_reply(
				channel="telegram",
				raw_reply=raw,
				model=f"crew:{cid}",
				user_text=user_input,
			)
			if p_actions:
				logger.info("Crew '%s' pending actions: %s", safe_cid, p_actions)
			combined_clean_parts.append(c_reply)
			all_executed_cmds.extend(e_cmds)

		clean_reply = "\n\n---\n\n".join(combined_clean_parts)

		# Surface action errors and phantom confirmations so the user knows when
		# a card/board/task was not actually created.
		action_errors = [c for c in all_executed_cmds if isinstance(c, str) and c.startswith("\u26a0")]
		if action_errors:
			clean_reply += "\n\n" + "  ".join(action_errors)
			logger.warning("Crew panel '%s' action errors: %s", crew_display, action_errors)
		elif not all_executed_cmds:
			# No actions executed — check if the crew hallucinated a confirmation
			_phantom_words = ("created", "added", "saved", "set up", "scheduled", "built", "generated")
			if any(w in clean_reply.lower() for w in _phantom_words):
				clean_reply += (
					"\n\n\u26a0 Nothing was actually saved \u2014 "
					"the crew described the action without executing it. Please try again."
				)
				logger.warning("Crew panel '%s': phantom confirmation (no executed_cmds)", crew_display)
		else:
			logger.info("Crew panel '%s' executed actions: %s", crew_display, all_executed_cmds)

		# Attribution already included in last section via commit — no extra append needed.
		display_final = f"<b>{format_time()}</b>\n\n{_md_to_html(clean_reply)}"
		await _send_chunked_reply(thinking_msg, display_final, reply_markup=get_nav_markup(t))

		# Record crew session so follow-up messages route back to this crew
		from app.services.crews import record_crew_session
		record_crew_session("telegram", primary_id)

	except Exception as e:
		logger.error("Telegram Crew Stream Failed: %s", e)
		try:
			await safe_edit(thinking_msg, f"<blockquote><i>Crew execution failed: {e}</i></blockquote>", parse_mode="HTML")
		except Exception as _e:
			logger.debug("Telegram crew error edit ignored: %s", _e)
	finally:
		_crew_abort_events.pop(thinking_msg.message_id, None)


@owner_only
async def cmd_think(update: Update, context: ContextTypes.DEFAULT_TYPE):
	"""Initiate Deep Thinking with Context Approval."""
	if not settings.DEEP_THINK_PROVIDER:
		await safe_reply(update, "Deep Thinking is disabled. Configure a provider in .env to use this feature.")
		return

	query = update.message.text.replace("/think", "").strip()
	if not query:
		await safe_reply(update, "What should I think deeply about?")
		return
	
	await update.message.reply_text("<blockquote>⏳ <b>Z is analyzing required context...</b></blockquote>", parse_mode="HTML")
	
	from app.services.llm import generate_context_proposal
	from app.models.db import store_pending_thought

	# 1. Local LLM decides what data is needed
	proposal = await generate_context_proposal(query)
	
	# 2. Store in DB to wait for approval
	thought_id = await store_pending_thought(query, proposal["context_data"])
	
	# 3. Create Approval UI
	keyboard = [
		[
			InlineKeyboardButton("✅ Grant Access", callback_data=f"think_approve_{thought_id}"),
			InlineKeyboardButton("❌ Cancel", callback_data=f"think_cancel_{thought_id}"),
		]
	]
	reply_markup = InlineKeyboardMarkup(keyboard)
	
	import html as _html
	disclosure_msg = (
		f"<blockquote>\u2696\ufe0f <b>Privacy Disclosure</b>\n\n"
		f"To answer this deeply, I need to send the following to {_html.escape(str(settings.DEEP_THINK_PROVIDER))}:\n"
		f"{_html.escape(proposal['summary'])}\n\n"
		f"<b>Question:</b> {_html.escape(query)}</blockquote>"
	)
	await update.message.reply_text(disclosure_msg, parse_mode="HTML", reply_markup=reply_markup)

@owner_only
async def handle_approval(update: Update, context: ContextTypes.DEFAULT_TYPE):
	"""Handle User granting access to Cloud API."""
	query_data = update.callback_query.data
	thought_id = query_data.split("_")[-1]
	
	if "cancel" in query_data:
		await update.callback_query.edit_message_text("🚫 Deep Thinking cancelled. Context was not shared.")
		return

	await update.callback_query.edit_message_text("<blockquote>📡 <b>Access granted. Sending to Cloud API...</b></blockquote>", parse_mode="HTML")
	
	from app.models.db import get_pending_thought
	from app.services.llm import chat
	
	thought = await get_pending_thought(thought_id)
	if not thought:
		await update.callback_query.edit_message_text("❌ Error: Thought context expired.")
		return

	# Combine query with the approved context
	full_prompt = f"CONTEXT:\n{thought['context_data']}\n\nQUESTION: {thought['query']}"
	
	response = await chat(
		full_prompt, 
		provider=settings.DEEP_THINK_PROVIDER,
		model=settings.DEEP_THINK_MODEL,
		_feature="deep_think",
	)
	
	# Deliver the heavy-weight answer
	html_response = _md_to_html(response)
	await context.bot.send_message(
		chat_id=update.effective_chat.id,
		text=f"<blockquote>{html_response}</blockquote>",
		parse_mode="HTML"
	)

@owner_only
async def handle_calendar_approval(update: Update, context: ContextTypes.DEFAULT_TYPE):
	"""Handle User approving a detected calendar event from email."""
	query = update.callback_query
	await query.answer()
	
	data = query.data
	event_id = data.split("_")[-1]
	
	if "ignore" in data:
		await query.edit_message_text("✅ Event ignored.")
		return

	from app.models.db import get_pending_thought, LocalEvent
	import json
	
	thought = await get_pending_thought(event_id)
	if not thought:
		await query.edit_message_text("❌ Error: Request expired or not found.")
		return
	
	try:
		event_data = json.loads(thought["context_data"])
		
		async with AsyncSessionLocal() as db:
			# Simple ISO parsing: YYYY-MM-DD HH:MM
			new_event = LocalEvent(
				summary=event_data["summary"],
				description=event_data.get("description", ""),
				start_time=datetime.fromisoformat(event_data["start"].replace(" ", "T")),
				end_time=datetime.fromisoformat(event_data["end"].replace(" ", "T"))
			)
			db.add(new_event)
			await db.commit()
		
		await query.edit_message_text(f"<blockquote>🚀 <b>Added to Calendar:</b> {event_data['summary']}</blockquote>", parse_mode="HTML")
	except Exception as e:
		logger.warning("Calendar approval failed: %s", e)
		await query.edit_message_text("❌ Failed to add event. Check logs.")


@owner_only
async def handle_draft_approval(update: Update, context: ContextTypes.DEFAULT_TYPE):
	"""Handle user approving or discarding a Gmail draft prepared by Z."""
	query = update.callback_query
	await query.answer()

	data = query.data
	thought_id = data.split("_")[-1]

	if "discard" in data:
		await query.edit_message_text("❌ Draft discarded.")
		return

	from app.models.db import get_pending_thought
	thought = await get_pending_thought(thought_id)
	if not thought:
		await query.edit_message_text("❌ Error: Draft request expired or not found.")
		return

	try:
		import json as _json
		import html as _html
		draft_data = _json.loads(thought["context_data"])
		from app.services.gmail import create_draft_reply
		success = await create_draft_reply(draft_data["email_id"], draft_data["reply_body"])
		if success:
			await query.edit_message_text(
				f"✅ <b>Draft created in Gmail</b>\nTo: {_html.escape(str(draft_data.get('to', '')))}\nSubject: Re: {_html.escape(str(draft_data.get('subject', '')))}" ,
				parse_mode="HTML"
			)
		else:
			await query.edit_message_text("❌ Failed to create draft. Check Gmail credentials.")
	except Exception as e:
		logger.warning("Draft approval failed: %s", e)
		await query.edit_message_text("❌ Error creating draft. Check logs.")
