from telegram import Update, Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
	Application,
	CommandHandler,
	MessageHandler,
	CallbackQueryHandler,
	filters,
	ContextTypes,
)
from app.config import settings
import asyncio
import pytz
from datetime import datetime, timedelta
import logging

bot_app: Application | None = None

async def _get_stats_footer() -> str:
	"""Consolidated stats/footer for Z's messages (no links)."""
	from app.services.memory import get_memory_stats
	from app.services.llm import last_model_used
	stats = await get_memory_stats()
	
	# Determine Model Level from actual use
	model_name = last_model_used.get() or "ollama"
	model_tag = f" · {model_name}"

	stats_text = f"Memories: {stats['points']}{model_tag}" if stats['status'] != 'error' else "Memory: Offline"
	return f"\n\n<i>{stats_text}</i>"

def get_nav_markup() -> InlineKeyboardMarkup:
	"""Standard navigation buttons (Large touch targets)."""
	base_url = settings.BASE_URL.rstrip('/')
	keyboard = [
		[
			InlineKeyboardButton("🏠 Dashboard", url=f"{base_url}/home"),
			InlineKeyboardButton("📋 Operator", url=f"{base_url}/api/dashboard/planka-redirect?target=operator")
		],
		[
			InlineKeyboardButton("📁 Projects", url=f"{base_url}/api/dashboard/planka-redirect"),
			InlineKeyboardButton("📅 Calendar", url=f"{base_url}/calendar")
		],
		[
			InlineKeyboardButton("❓ Help / Commands", callback_data="call_help")
		]
	]
	return InlineKeyboardMarkup(keyboard)

# --- Context Persistence ---
chat_histories = {} # chat_id -> list of dicts {'role': 'user/z', 'content': str}

async def start_telegram_bot():
	"""Start the Telegram bot in polling mode within the FastAPI event loop."""
	global bot_app
	if not settings.TELEGRAM_BOT_TOKEN:
		logging.warning("TELEGRAM_BOT_TOKEN not set. Bot will not start.")
		return

	logging.info("DEBUG: start_telegram_bot - step 1: Building app")
	bot_app = (
		Application.builder()
		.token(settings.TELEGRAM_BOT_TOKEN)
		.build()
	)

	# Register handlers
	print("DEBUG: start_telegram_bot - step 2: Registering handlers")
	bot_app.add_handler(CommandHandler("start", cmd_start))
	bot_app.add_handler(CommandHandler("tree", cmd_tree))
	bot_app.add_handler(CommandHandler("review", cmd_review))
	bot_app.add_handler(CommandHandler("search", cmd_search))
	bot_app.add_handler(CommandHandler("memories", cmd_memories))
	bot_app.add_handler(CommandHandler("unlearn", cmd_unlearn))
	bot_app.add_handler(CommandHandler("purge", cmd_purge))
	bot_app.add_handler(CommandHandler("wipe_memory", cmd_purge))  # legacy alias
	bot_app.add_handler(CommandHandler("week", cmd_week))
	bot_app.add_handler(CommandHandler("month", cmd_month))
	bot_app.add_handler(CommandHandler("quarter", cmd_quarter))
	bot_app.add_handler(CommandHandler("year", cmd_year))
	bot_app.add_handler(CommandHandler("day", cmd_day))
	bot_app.add_handler(CommandHandler("add", cmd_add_topic))
	bot_app.add_handler(CommandHandler("protocols", cmd_protocols))
	bot_app.add_handler(CommandHandler("remind", cmd_remind))
	bot_app.add_handler(CommandHandler("custom", cmd_custom))
	bot_app.add_handler(CommandHandler("think", cmd_think))
	bot_app.add_handler(CallbackQueryHandler(handle_approval, pattern="^think_"))
	bot_app.add_handler(CallbackQueryHandler(handle_unlearn_approval, pattern="^unlearn_"))
	bot_app.add_handler(CallbackQueryHandler(handle_wipe_confirm, pattern="^wipe_"))
	bot_app.add_handler(CallbackQueryHandler(handle_calendar_approval, pattern="^cal_"))
	bot_app.add_handler(CallbackQueryHandler(handle_help_callback, pattern="^call_help$"))
	bot_app.add_handler(CommandHandler("help", cmd_help))
	bot_app.add_handler(CommandHandler("commands", cmd_help))
	bot_app.add_handler(CommandHandler("status", cmd_status))
	bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_freetext))
	bot_app.add_handler(MessageHandler(filters.VOICE, handle_voice))

	# Initialize and start polling (non-blocking)
	print("DEBUG: start_telegram_bot - step 3: Initializing")
	await bot_app.initialize()
	print("DEBUG: start_telegram_bot - step 4: Starting")
	await bot_app.start()
	print("DEBUG: start_telegram_bot - step 5: Start Polling (dropping old updates)")
	await bot_app.updater.start_polling(drop_pending_updates=True)
	print("DEBUG: start_telegram_bot - step 6: Polling started")

	# Proactive greeting with Context & Stats (Run in background to avoid blocking startup)
	async def send_startup_greeting():
		try:
			from app.services.llm import chat
			from app.services.memory import get_memory_stats
			from app.models.db import AsyncSessionLocal, Person
			from sqlalchemy import select
			import os
			
			logging.info("DEBUG: start_telegram_bot - step 7: Fetching stats for greeting")
			stats = await get_memory_stats()
			stats_text = f"Memories: {stats['points']}" if stats['status'] != 'error' else "Memory: Offline"
			
			# 1. Release Notes (Deployment Detection)
			release_info = ""
			notes_file = "LATEST_CHANGES.txt"
			if os.path.exists(notes_file):
				print("DEBUG: Greeting Seq - Step 1: Release Notes detected")
				try:
					with open(notes_file, "r") as f:
						changes = f.read().strip()
					if changes:
						release_info = f"DEPLOYMENT UPDATE - TECHNICAL DIFF SUMMARY:\n{changes[:2000]}\n"
					os.remove(notes_file)
				except: pass

			# Unified Context gathering
			event_summary_parts = []
			now = datetime.now(pytz.timezone(settings.USER_TIMEZONE))

			print("DEBUG: Greeting Seq - Step 2: Fetching Unified Calendar")
			try:
				from app.services.calendar import fetch_unified_events
				# Use a safe timeout to prevent blocking the greeting forever if CalDAV is slow
				all_events = await asyncio.wait_for(fetch_unified_events(days_ahead=1), timeout=10.0)
				
				if all_events:
					for e in all_events:
						# All events from unified source have 'start' as ISO string YYYY-MM-DDTHH:MM:SSZ
						time_str = e['start'].split('T')[1][:5] if 'T' in e['start'] else None
						if time_str == "00:00": time_str = None
						
						source_tag = f" [{e.get('source', '?')}]"
						display_item = f"• {e['summary']}{source_tag}"
						if time_str: display_item += f" ({time_str})"
						event_summary_parts.append(display_item)
			except Exception as cal_err:
				print(f"DEBUG: Calendar Greeting Error: {cal_err}")

			# 2. Birthdays (Still separate until integrated into unified service)
			logging.info("DEBUG: Greeting Seq - Step 3: Local People/Birthdays")
			async with AsyncSessionLocal() as session:
				# Birthdays
				res_people = await session.execute(select(Person).where(Person.birthday.isnot(None)))
				for p in res_people.scalars().all():
					try:
						pts = p.birthday.split('.')
						if len(pts) >= 2:
							bday = datetime(now.year, int(pts[1]), int(pts[0]))
							if bday.date() == now.date():
								event_summary_parts.append(f"🎂 Today is {p.name}'s Birthday!")
							elif (bday.date() - now.date()).days == 1:
								event_summary_parts.append(f"🎂 Tomorrow: {p.name}'s Birthday")
					except: pass

			event_summary = "\n".join(event_summary_parts) if event_summary_parts else "No upcoming events scheduled."
			print(f"DEBUG: Greeting Seq - Context Ready ({len(event_summary_parts)} items)")
			
			has_events = bool(event_summary_parts)
			events_block = f"Events (REAL DATA):\n{event_summary}" if has_events else "Events: NONE — do NOT invent or mention any events."

			greeting_prompt = (
				f"SYSTEM_DATA:\n"
				f"Status: {stats_text}\n"
				f"Changes: {release_info or 'No recent changes'}\n"
				f"{events_block}\n\n"
				"TASK: As Z (the agent), write a concise but informative greeting.\n"
				"1. Brief welcome back (1 sentence).\n"
				"2. If 'Changes' has updates: add a 'Recent Logic Updates' section. "
				"For each change, write 1-2 sentences explaining what it does in plain language — not just repeating the commit title.\n"
				"3. ONLY mention events if they appear in the REAL DATA above. If events say NONE, skip entirely.\n"
				"Be direct, professional, and human. No filler. No invented content."
			)

			system_override = (
				"You are Z. Output ONLY the greeting. "
				"ALWAYS begin your response with the formatted current time and day on the first line "
				"(e.g. '16:40 - Mo. 2nd'), followed by a blank line, then your message. "
				"NEVER invent data not present in SYSTEM_DATA."
			)
			print(f"DEBUG: Greeting Seq - Calling Ollama ({settings.OLLAMA_MODEL_SMART})")

			# Strings returned by llm.py on timeout/failure — must not reach the user
			_ERROR_INDICATORS = ["initializing my local core", "synchronize my reasoning", "Error connecting", "No response from"]
			def _is_error(text: str) -> bool:
				return any(ind.lower() in text.lower() for ind in _ERROR_INDICATORS)

			raw_greeting = await chat(greeting_prompt, system_override=system_override, model=settings.OLLAMA_MODEL_SMART)

			# Fallback 1: smart model timed out — try fast model
			if _is_error(raw_greeting):
				print("DEBUG: Greeting - Smart model timeout, falling back to fast model")
				raw_greeting = await chat(greeting_prompt, system_override=system_override, model=settings.OLLAMA_MODEL_FAST)

			# Fallback 2: both models failed — send clean static greeting
			if _is_error(raw_greeting):
				print("DEBUG: Greeting - Both models unavailable, using static greeting")
				from app.services.timezone import format_time
				time_str = format_time() + "\n"
				
				changes_note = f"\n\n🔄 *Recent Logic Updates:*\n{release_info.strip()}" if release_info else ""
				events_note = f"\n\n📅 *Events:*\n{event_summary}" if has_events else ""
				raw_greeting = f"{time_str}\nBack online. {stats_text}.{changes_note}{events_note}"

			# Clean action tags from output
			from app.services.agent_actions import parse_and_execute_actions
			greeting, _ = await parse_and_execute_actions(raw_greeting)
			print("DEBUG: Greeting Seq - OK")

			# Prepend real current time (don't trust LLM for timestamps)
			from app.services.timezone import format_time
			import re
			# Strip any LLM-generated time header
			greeting_clean = re.sub(r'^\d{1,2}:\d{2}\s*[-–]?\s*[^\n]*\n*', '', greeting, count=1).strip()
			real_time = format_time()
			
			await send_notification_html(
				f"<blockquote><b>{real_time}</b>\n\n{_md_to_html(greeting_clean)}\n\n<i>{stats_text}</i></blockquote>",
				reply_markup=get_nav_markup()
			)
			logging.info("DEBUG: Greeting Seq - Notification Delivered")
		except Exception as e:
			logging.error(f"FAILED to send Telegram startup greeting: {e}")

	# Launch greeting in background
	asyncio.create_task(send_startup_greeting())

async def stop_telegram_bot():
	"""Gracefully stop the bot."""
	global bot_app
	if bot_app:
		await bot_app.updater.stop()
		await bot_app.stop()
		await bot_app.shutdown()

async def send_notification(text: str, reply_markup=None):
	"""Send a message to the owner wrapped in an HTML blockquote island."""
	if not settings.TELEGRAM_BOT_TOKEN or not settings.TELEGRAM_ALLOWED_USER_ID:
		return
	bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
	html_text = _md_to_html(text)
	await bot.send_message(
		chat_id=int(settings.TELEGRAM_ALLOWED_USER_ID),
		text=f"<blockquote>{html_text}</blockquote>",
		parse_mode="HTML",
		reply_markup=reply_markup,
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
	)

def _md_to_html(text: str) -> str:
	"""Minimal Markdown-to-HTML conversion for Telegram."""
	import re
	# Bold: **text** or *text* -> <b>text</b>
	html = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
	html = re.sub(r'\*(.+?)\*', r'<b>\1</b>', html)
	# Italic: _text_ -> <i>text</i>
	html = re.sub(r'(?<!\w)_(.+?)_(?!\w)', r'<i>\1</i>', html)
	# Links: [text](url) -> <a href="url">text</a>
	html = re.sub(r'\[(.+?)\]\((.+?)\)', r'<a href="\2">\1</a>', html)
	return html

async def send_voice_message(audio_bytes: bytes, caption: str = None):
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
			return	# Silently ignore strangers
		return await func(update, context)
	return wrapper

async def safe_reply(update: Update, text: str, reply_markup=None):
	"""Sends a reply wrapped in an HTML blockquote island."""
	msg = update.effective_message
	try:
		html_text = _md_to_html(text)
		await msg.reply_text(f"<blockquote>{html_text}</blockquote>", parse_mode="HTML", reply_markup=reply_markup)
	except Exception as e:
		print(f"DEBUG: HTML reply failed, falling back to plain: {e}")
		await msg.reply_text(text, reply_markup=reply_markup)

async def safe_edit(message, text: str, parse_mode="HTML", reply_markup=None):
	"""Tries to edit a message, falls back to plain text on error."""
	try:
		await message.edit_text(text, parse_mode=parse_mode, reply_markup=reply_markup)
	except Exception as e:
		print(f"DEBUG: HTML edit failed, falling back to plain: {e}")
		try:
			await message.edit_text(text)
		except: pass

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
		except: pass
		
		# 3. LLM
		try:
			from app.services.llm import chat
			await chat("hi", model=settings.OLLAMA_MODEL_FAST)
			l_text = "🟢 Ready"
		except: l_text = "🔴 Error"

		status_report = (
			"🛰️ *System Status Report*\n\n"
			f"🧠 *Memory (Qdrant):* {m_text} ({m_stats.get('points', 0)} pts)\n"
			f"📋 *Task Board (Planka):* {p_text}\n"
			f"🤖 *Intelligence (Ollama):* {l_text}\n"
			f"📍 *Time:* {datetime.now(pytz.timezone(settings.USER_TIMEZONE)).strftime('%H:%M:%S')}"
		)
		await safe_reply(update, status_report, reply_markup=get_nav_markup())
	except Exception as e:
		print(f"ERROR: cmd_status failed: {e}")
		await update.message.reply_text("🛰️ System Status check failed. Check local backend logs.")

# --- Command Handlers ---
@owner_only
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
	await update.message.reply_text("🚀 Personal AI OS is online.")

@owner_only
async def cmd_tree(update: Update, context: ContextTypes.DEFAULT_TYPE):
	try:
		from app.services.planka import get_project_tree
		tree = await get_project_tree(as_html=False)
		await safe_reply(update, tree, reply_markup=get_nav_markup())
	except Exception as e:
		await update.message.reply_text(f"❌ Failed to fetch mission tree: {e}")

@owner_only
async def cmd_review(update: Update, context: ContextTypes.DEFAULT_TYPE):
	try:
		from app.tasks.weekly import weekly_review
		report = await weekly_review()
		await safe_reply(update, report)
	except Exception as e:
		await update.message.reply_text(f"❌ Review generation failed: {e}")

@owner_only
async def cmd_week(update: Update, context: ContextTypes.DEFAULT_TYPE):
	try:
		from app.tasks.weekly import weekly_review
		report = await weekly_review()
		await safe_reply(update, report)
	except Exception as e:
		await update.message.reply_text(f"❌ Weekly review failed: {e}")

@owner_only
async def cmd_month(update: Update, context: ContextTypes.DEFAULT_TYPE):
	try:
		from app.tasks.monthly import monthly_review
		report = await monthly_review()
		await safe_reply(update, report)
	except Exception as e:
		await update.message.reply_text(f"❌ Monthly review failed: {e}")

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
		await update.message.reply_text("Usage: /remind 2 times an hour for 4 hours to drink water")
		return
		
	from app.services.agent_actions import parse_and_execute_actions
	from app.services.llm import chat
	
	# Let the LLM parse the natural language into the action tag
	prompt = (
		"Convert this reminder request into a [ACTION: REMIND ...] tag.\n"
		"Format: [ACTION: REMIND | MESSAGE: <text> | INTERVAL: <minutes> | DURATION: <hours>]\n\n"
		f"Input: {msg}"
	)
	
	response = await chat(prompt)
	clean_reply, executed = await parse_and_execute_actions(response)
	
	if executed:
		await update.message.reply_text("\n".join(executed))
	else:
		await update.message.reply_text("Could not parse the reminder frequency. Try: '/remind 30m for 4h drink water'")

@owner_only
async def cmd_custom(update: Update, context: ContextTypes.DEFAULT_TYPE):
	msg = update.message.text.replace("/custom", "").strip()
	if not msg:
		await update.message.reply_text("Usage: /custom Every Monday at 12:00 remind me to check the stats")
		return
		
	from app.services.agent_actions import parse_and_execute_actions
	from app.services.llm import chat
	
	prompt = (
		"Convert this custom schedule request into a [ACTION: SCHEDULE_CUSTOM ...] tag.\n"
		"Format: [ACTION: SCHEDULE_CUSTOM | NAME: <short_name> | MESSAGE: <text> | TYPE: <cron/interval> | SPEC: <spec>]\n"
		"CRON SPEC: minute hour day month day_of_week\n"
		"INTERVAL SPEC: minutes=N or hours=N\n\n"
		f"Input: {msg}"
	)
	
	response = await chat(prompt)
	clean_reply, executed = await parse_and_execute_actions(response)
	
	if executed:
		await update.message.reply_text("\n".join(executed))
	else:
		await update.message.reply_text("Could not parse. Try: '/custom every day at 10am remind me...'")

@owner_only
async def cmd_quarter(update: Update, context: ContextTypes.DEFAULT_TYPE):
	try:
		from app.tasks.quarterly import quarterly_review
		report = await quarterly_review()
		await safe_reply(update, report)
	except Exception as e:
		await update.message.reply_text(f"❌ Quarterly review failed: {e}")

@owner_only
async def cmd_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
	try:
		from app.tasks.morning import morning_briefing
		await morning_briefing()
	except Exception as e:
		await update.message.reply_text(f"❌ Morning briefing failed: {e}")

@owner_only
async def cmd_year(update: Update, context: ContextTypes.DEFAULT_TYPE):
	try:
		from app.tasks.yearly import yearly_review
		report = await yearly_review()
		await safe_reply(update, report)
	except Exception as e:
		await update.message.reply_text(f"❌ Yearly review failed: {e}")

@owner_only
async def cmd_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
	query = update.message.text.replace("/search", "").strip()
	from app.services.memory import semantic_search
	results = await semantic_search(query)
	await update.message.reply_text(results)

@owner_only
async def cmd_unlearn(update: Update, context: ContextTypes.DEFAULT_TYPE):
	query = update.message.text.replace("/unlearn", "").strip()
	if not query:
		await update.message.reply_text("What should I unlearn? Provide a part of the memory text.")
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
		await update.message.reply_text("No matching memories found to unlearn.")
		return

	# Show matches with buttons
	keyboard = []
	for p in results.points:
		text = p.payload.get('text', '[No Text]')[:50] + "..."
		keyboard.append([InlineKeyboardButton(f"Unlearn: {text}", callback_data=f"unlearn_confirm_{p.id}")])
	
	keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="unlearn_cancel")])
	reply_markup = InlineKeyboardMarkup(keyboard)
	await update.message.reply_text("Select the knowledge I should unlearn:", reply_markup=reply_markup)

@owner_only
async def cmd_memories(update: Update, context: ContextTypes.DEFAULT_TYPE):
	from app.services.memory import get_qdrant, COLLECTION_NAME
	client = get_qdrant()
	# Fetch 50 instead of 100 to stay safe with message limits
	results, _ = client.scroll(collection_name=COLLECTION_NAME, limit=50)
	if not results:
		await update.message.reply_text("No memories stored in the vault.")
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
		"/think -- Complex reasoning with human-in-the-loop approval\n"
		"/remind -- Set a temporary recurring reminder (e.g. every 30 min for 4h)\n"
		"/custom -- Create a persistent scheduled task (e.g. every Monday at 10am)\n\n"
		"*Memory & Intelligence*\n"
		"/search -- Conceptual search of the semantic knowledge vault\n"
		"/memories -- List all core knowledge in permanent memory\n"
		"/add -- Commit specific facts to Z's permanent knowledge vault\n"
		"/unlearn -- Evolve past points in the vault\n"
		"/protocols -- Inspect Z's agentic tools and Semantic Action Tags\n\n"
		"*System*\n"
		"/status -- Deep integration health check\n"
		"/purge -- Permanently delete all semantic memories (irreversible)\n\n"
		"_Tap any command to execute it directly._"
	)
	await safe_reply(update, help_text, reply_markup=get_nav_markup())

async def handle_help_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
	await update.callback_query.answer()
	await cmd_help(update, context)

@owner_only
async def cmd_add_topic(update: Update, context: ContextTypes.DEFAULT_TYPE):
	topic = update.message.text.replace("/add", "").strip()
	from app.services.memory import store_memory
	await store_memory(topic)
	await update.message.reply_text(f"✅ Stored: {topic}")

@owner_only
async def cmd_evolve(update: Update, context: ContextTypes.DEFAULT_TYPE):
	evolve_text = (
		"🧬 *Agent Evolution: Semantic Capabilities*\n\n"
		"Z operates by emitting the following action tags. These allow the agent to command and evolve the environment:\n\n"
		"• *Task Management:* `CREATE_TASK`, `CREATE_PROJECT`, `CREATE_BOARD`\n"
		"• *Scheduling:* `CREATE_EVENT` (Calendar Sync)\n"
		"• *Social Graph:* `ADD_PERSON` (Inner/Close Circles)\n"
		"• *Cognition:* `LEARN` (Commit to Semantic Vault)\n"
		"• *Precision:* `PROXIMITY_TRACK` (Task breakdown & deep-tracking)\n\n"
		"_\"I don't just chat; I execute. Every interaction is an opportunity to evolve your OS.\"_"
	)
	await safe_reply(update, evolve_text)

@owner_only
async def cmd_purge(update: Update, context: ContextTypes.DEFAULT_TYPE):
	"""Request semantic memory purge with detailed confirmation."""
	keyboard = [
		[
			InlineKeyboardButton("\U0001f525 Yes, purge everything", callback_data="wipe_confirm"),
			InlineKeyboardButton("\u270b Cancel", callback_data="wipe_cancel"),
		]
	]
	reply_markup = InlineKeyboardMarkup(keyboard)
	await update.message.reply_text(
		"<blockquote>"
		"\u26a0\ufe0f <b>Semantic Memory Purge</b>\n\n"
		"This will permanently delete <b>all</b> facts stored in Z's long-term memory vault (Qdrant).\n\n"
		"<b>What gets deleted:</b>\n"
		"- All stored facts, preferences, and personal context\n"
		"- All learned information from past conversations\n"
		"- All manually committed memories (/add)\n\n"
		"<b>What is NOT affected:</b>\n"
		"- Your calendar, task boards, and projects (Planka)\n"
		"- Your circle of trust (people database)\n"
		"- Briefing history\n\n"
		"This action is <b>irreversible</b>. Z will start with a blank knowledge slate."
		"</blockquote>",
		parse_mode="HTML",
		reply_markup=reply_markup
	)

async def handle_wipe_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
	query = update.callback_query
	await query.answer()
	
	if query.data == "wipe_confirm":
		from app.services.memory import wipe_collection
		success = await wipe_collection(confirm=True)
		if success:
			await query.edit_message_text("✅ Semantic memory has been completely wiped.")
		else:
			await query.edit_message_text("❌ Failed to wipe memory. Check logs.")
	else:
		await query.edit_message_text("Cancelled. Memories are safe.")

@owner_only
async def handle_freetext(update: Update, context: ContextTypes.DEFAULT_TYPE):
	"""Process freeform text via the default LLM with Context & History."""
	try:
		chat_id = update.effective_chat.id
		if chat_id not in chat_histories:
			chat_histories[chat_id] = []
		
		from app.services.llm import chat_with_context
		from app.models.db import get_global_history, save_global_message
		
		# Show initial acknowledgment
		thinking_msg = await update.message.reply_text("<blockquote><i>Thinking...</i></blockquote>", parse_mode="HTML")
		
		from app.services.agent_actions import parse_and_execute_actions
		from app.models.db import AsyncSessionLocal

		# Recover Merged History (cross-channel context — last 10 messages)
		merged_history = await get_global_history(limit=10)

		response = await chat_with_context(
			update.message.text, 
			history=merged_history,
			include_projects=True,
			include_people=True
		)
		
		async with AsyncSessionLocal() as db:
			clean_reply, _ = await parse_and_execute_actions(response, db=db)

		# Sync to Global Central Memory
		await save_global_message("telegram", "user", update.message.text)
		await save_global_message("telegram", "z", clean_reply)

		# Memory is user-driven only (via /add or LEARN action tag)

		# Prepend real time (strip any LLM-generated time header)
		from app.services.timezone import format_time
		import re
		clean_reply = re.sub(r'^\d{1,2}:\d{2}\s*[-–]?\s*[^\n]*\n*', '', clean_reply, count=1).strip()
		html_reply = _md_to_html(clean_reply)
		display_reply = f"<b>{format_time()}</b>\n\n{html_reply}"

		footer = await _get_stats_footer()
		await safe_edit(thinking_msg, f"<blockquote>{display_reply}{footer}</blockquote>", parse_mode="HTML", reply_markup=get_nav_markup())
	except Exception as e:
		print(f"ERROR: handle_freetext failed: {e}")
		# If bit failed to edit, try fresh message
		try:
			await update.message.reply_text("⚖️ I encountered friction while processing that request. My local core is still active, but that specific thread was dropped.")
		except: pass

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
		
		if not transcript or transcript.startswith("["):
			await safe_edit(status_msg, f"<blockquote>⚠️ <i>{transcript or 'Could not transcribe voice.'}</i></blockquote>", parse_mode="HTML")
			return

		await safe_edit(status_msg, f"<blockquote>📝 <b>Transcript:</b>\n<i>{transcript}</i>\n\n<i>Thinking...</i></blockquote>", parse_mode="HTML")
		
		# 3. Process as text
		from app.services.llm import chat_with_context
		chat_id = update.effective_chat.id
		if chat_id not in chat_histories:
			chat_histories[chat_id] = []

		response = await chat_with_context(
			transcript,
			history=chat_histories[chat_id],
			include_projects=True,
			include_people=True
		)
		
		from app.services.agent_actions import parse_and_execute_actions
		from app.models.db import AsyncSessionLocal
		
		async with AsyncSessionLocal() as db:
			clean_reply, _ = await parse_and_execute_actions(response, db=db)
		
		chat_histories[chat_id].append({"role": "user", "content": transcript})
		chat_histories[chat_id].append({"role": "z", "content": response})
		
		from app.services.timezone import format_time
		import re
		clean_reply = re.sub(r'^\d{1,2}:\d{2}\s*[-–]?\s*[^\n]*\n*', '', clean_reply, count=1).strip()
		html_reply = _md_to_html(clean_reply)
		display_reply = f"📝 <b>Transcript:</b>\n<i>{transcript}</i>\n\n<b>{format_time()}</b>\n\n{html_reply}"
		
		footer = await _get_stats_footer()
		await safe_edit(status_msg, f"<blockquote>{display_reply}{footer}</blockquote>", parse_mode="HTML", reply_markup=get_nav_markup())
	except Exception as e:
		print(f"ERROR: handle_voice failed: {e}")
		await update.message.reply_text("⚠️ Voice processing failed. There might be an issue with the transcription or intelligence layer.")

@owner_only
async def cmd_think(update: Update, context: ContextTypes.DEFAULT_TYPE):
	"""Initiate Deep Thinking with Context Approval."""
	if not settings.DEEP_THINK_PROVIDER:
		await update.message.reply_text("🚫 Deep Thinking is disabled. Please configure a provider in `.env` to use this feature.")
		return

	query = update.message.text.replace("/think", "").strip()
	if not query:
		await update.message.reply_text("What should I think deeply about?")
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
	
	disclosure_msg = (
		f"<blockquote>\u2696\ufe0f <b>Privacy Disclosure</b>\n\n"
		f"To answer this deeply, I need to send the following to {settings.DEEP_THINK_PROVIDER}:\n"
		f"{proposal['summary']}\n\n"
		f"<b>Question:</b> {query}</blockquote>"
	)
	await update.message.reply_text(disclosure_msg, parse_mode="HTML", reply_markup=reply_markup)

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
		model=settings.DEEP_THINK_MODEL
	)
	
	# Deliver the heavy-weight answer
	html_response = _md_to_html(response)
	await context.bot.send_message(
		chat_id=update.effective_chat.id,
		text=f"<blockquote>{html_response}</blockquote>",
		parse_mode="HTML"
	)

async def handle_calendar_approval(update: Update, context: ContextTypes.DEFAULT_TYPE):
	"""Handle User approving a detected calendar event from email."""
	query = update.callback_query
	await query.answer()
	
	data = query.data
	event_id = data.split("_")[-1]
	
	if "ignore" in data:
		await query.edit_message_text("✅ Event ignored.")
		return

	from app.models.db import get_pending_thought, AsyncSessionLocal, LocalEvent
	import json
	from datetime import datetime
	
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
		print(f"DEBUG: Calendar approval failed: {e}")
		await query.edit_message_text(f"❌ Failed to add event: {str(e)}")
