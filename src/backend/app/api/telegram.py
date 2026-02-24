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
from datetime import datetime, timedelta

bot_app: Application | None = None

async def _get_stats_footer() -> str:
    """Consolidated footer for Z's messages."""
    from app.services.memory import get_memory_stats
    stats = await get_memory_stats()
    stats_text = f"🧠 Memories: {stats['points']}" if stats['status'] != 'error' else "🧠 Memory: Offline"
    
    base_url = settings.BASE_URL
    links = f"🔗 [Dashboard]({base_url}) 🔗 [Boards]({base_url}/boards) 🔗 [Calendar]({base_url}/calendar)"
    
    return f"\n\n{links}\n\n{stats_text}"

# --- Context Persistence ---
chat_histories = {} # chat_id -> list of dicts {'role': 'user/z', 'content': str}

async def start_telegram_bot():
    """Start the Telegram bot in polling mode within the FastAPI event loop."""
    global bot_app
    if not settings.TELEGRAM_BOT_TOKEN:
        print("TELEGRAM_BOT_TOKEN not set. Bot will not start.")
        return

    print("DEBUG: start_telegram_bot - step 1: Building app")
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
    bot_app.add_handler(CommandHandler("memory", cmd_memory))
    bot_app.add_handler(CommandHandler("wipe_memory", cmd_wipe_memory))
    bot_app.add_handler(CommandHandler("week", cmd_week))
    bot_app.add_handler(CommandHandler("month", cmd_month))
    bot_app.add_handler(CommandHandler("day", cmd_day))
    bot_app.add_handler(CommandHandler("year", cmd_year))
    bot_app.add_handler(CommandHandler("add", cmd_add_topic))
    bot_app.add_handler(CommandHandler("think", cmd_think))
    bot_app.add_handler(CallbackQueryHandler(handle_approval, pattern="^think_"))
    bot_app.add_handler(CallbackQueryHandler(handle_wipe_confirm, pattern="^wipe_"))
    bot_app.add_handler(CallbackQueryHandler(handle_calendar_approval, pattern="^cal_"))
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
    print("DEBUG: start_telegram_bot - step 5: Start Polling")
    await bot_app.updater.start_polling(drop_pending_updates=True)
    print("DEBUG: start_telegram_bot - step 6: Polling started")

    # Proactive greeting with Context & Stats (Run in background to avoid blocking startup)
    async def send_startup_greeting():
        try:
            from app.services.llm import chat
            from app.services.memory import get_memory_stats
            from app.models.db import AsyncSessionLocal, Person, LocalEvent
            from sqlalchemy import select
            
            print("DEBUG: start_telegram_bot - step 7: Fetching stats for greeting")
            stats = await get_memory_stats()
            stats_text = f"Memories: {stats['points']}" if stats['status'] != 'error' else "Memory: Offline"
            
            # Context gathering
            event_summary_parts = []
            now = datetime.now()

            calendar_offline = False
            # 1. Google Calendar
            try:
                from app.services.calendar import fetch_calendar_events
                import asyncio
                g_events = await asyncio.wait_for(fetch_calendar_events(max_results=3, days_ahead=1), timeout=5.0)
                if g_events:
                    for e in g_events:
                        time_str = e['start'].split('T')[1][:5] if 'T' in e['start'] else 'All Day'
                        event_summary_parts.append(f"• {e['summary']} ({time_str})")
            except Exception as ce:
                print(f"Google Calendar fetch failed: {ce}")
                calendar_offline = True

            # 2. Local & Birthdays
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
                
                # Local Events
                today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
                tomorrow_end = today_start + timedelta(days=2)
                res_local = await session.execute(select(LocalEvent).where(LocalEvent.start_time >= today_start, LocalEvent.start_time < tomorrow_end))
                for le in res_local.scalars().all():
                    event_summary_parts.append(f"• {le.summary} ({le.start_time.strftime('%H:%M')})")

            event_summary = "\n".join(event_summary_parts) if event_summary_parts else "No upcoming events scheduled."
            if calendar_offline and not event_summary_parts:
                event_summary = "Calendar Integration: OFFLINE (Check credentials/service)."

            greeting_prompt = (
                f"Z is coming online. System status: Ready. {stats_text}. CONTEXT: {event_summary}\n\n"
                "Greet the user with 'Welcome back.' then a very short status update strictly based on the provided CONTEXT. "
                "CRITICAL: If CONTEXT says 'OFFLINE', inform the user that you couldn't check the schedule. "
                "Mention birthdays prominently if found. NEVER invent or hallucinate. Be extremely concise. One short sentence."
            )
            print("Generating greeting...")
            greeting = await chat(greeting_prompt)
            print("Greeting generated.")
            
            footer = await _get_stats_footer()
            await send_notification(f"⚡ {greeting}{footer}")
            print("Startup notification sent.")
        except Exception as e:
            print(f"FAILED to send Telegram startup greeting: {e}")

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
    """Send a message to the owner."""
    if not settings.TELEGRAM_BOT_TOKEN or not settings.TELEGRAM_ALLOWED_USER_ID:
        return
    bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
    await bot.send_message(
        chat_id=settings.TELEGRAM_ALLOWED_USER_ID,
        text=text,
        parse_mode="Markdown",
        reply_markup=reply_markup,
    )

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
        caption=caption,
        parse_mode="Markdown"
    )

# --- Auth decorator ---
def owner_only(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if str(update.effective_user.id) != settings.TELEGRAM_ALLOWED_USER_ID:
            return  # Silently ignore strangers
        return await func(update, context)
    return wrapper

@owner_only
async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Deep status check of all integrations."""
    from app.services.memory import get_memory_stats
    from app.services.planka import get_planka_auth_token
    
    # 1. Memory
    m_stats = await get_memory_stats()
    m_text = "🟢 Active" if m_stats['status'] == 'ok' else "🔴 Offline"
    
    # 2. Planka
    p_text = "🔴 Offline"
    try:
        token = await get_planka_auth_token()
        if token: p_text = "🟢 Connected"
    except: pass
    
    # 3. LLM
    try:
        from app.services.llm import chat
        await chat("hi", model="llama3.2:3b")
        l_text = "🟢 Ready"
    except: l_text = "🔴 Error"

    status_report = (
        "🛰️ *System Status Report*\n\n"
        f"🧠 *Memory (Qdrant):* {m_text} ({m_stats.get('points', 0)} pts)\n"
        f"📋 *Task Board (Planka):* {p_text}\n"
        f"🤖 *Intelligence (Ollama):* {l_text}\n"
        f"📍 *Time:* {datetime.now().strftime('%H:%M:%S')}"
    )
    await update.message.reply_text(status_report, parse_mode="Markdown")

# --- Command Handlers ---
@owner_only
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚀 Personal AI OS is online.")

@owner_only
async def cmd_tree(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from app.services.planka import get_project_tree
    tree = await get_project_tree(as_html=False)
    await update.message.reply_text(tree, parse_mode="Markdown")

@owner_only
async def cmd_review(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from app.tasks.weekly import weekly_review
    report = await weekly_review()
    await update.message.reply_text(report, parse_mode="Markdown")

@owner_only
async def cmd_week(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from app.tasks.weekly import weekly_review
    report = await weekly_review()
    await update.message.reply_text(report, parse_mode="Markdown")

@owner_only
async def cmd_month(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from app.tasks.monthly import monthly_review
    report = await monthly_review()
    await update.message.reply_text(report, parse_mode="Markdown")

@owner_only
async def cmd_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from app.tasks.morning import morning_briefing
    await morning_briefing()

@owner_only
async def cmd_year(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from app.tasks.yearly import yearly_review
    report = await yearly_review()
    await update.message.reply_text(report, parse_mode="Markdown")

@owner_only
async def cmd_memory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.replace("/memory", "").strip()
    from app.services.memory import semantic_search
    results = await semantic_search(query)
    await update.message.reply_text(results)

@owner_only
async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "🤖 *Z Operator Controls*\n\n"
        "*Missions:*\n"
        "• `/tree` \\- OS Mission Overview\n"
        "• `/add <topic>` \\- Store something in memory\n\n"
        "*Intelligence:*\n"
        "• `/think <query>` \\- Multi-step reasoning\n"
        "• `/memory <query>` \\- Semantic search\n"
        "• `/day`, `/week`, `/month`, `/year` \\- Strategic briefings\n\n"
        "*System:*\n"
        "• `/wipe_memory` \\- Clear LLM recall\n"
        "• `/start` \\- Check status\n\n"
        "Type any message to chat with Z directly."
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")

@owner_only
async def cmd_add_topic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    topic = update.message.text.replace("/add", "").strip()
    from app.services.memory import store_memory
    await store_memory(topic)
    await update.message.reply_text(f"✅ Stored: {topic}")

@owner_only
async def cmd_wipe_memory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Trigger memory wipe with confirmation."""
    keyboard = [
        [
            InlineKeyboardButton("🔥 Confirm Wipe", callback_data="wipe_confirm"),
            InlineKeyboardButton("❌ Cancel", callback_data="wipe_cancel"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "⚠️ *DANGER ZONE*\n\nYou are about to wipe all semantic memories. This cannot be undone. Confirm?",
        parse_mode="Markdown",
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
    chat_id = update.effective_chat.id
    if chat_id not in chat_histories:
        chat_histories[chat_id] = []
    
    from app.services.llm import chat_with_context
    
    # Show typing action
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    
    response = await chat_with_context(
        update.message.text, 
        history=chat_histories[chat_id],
        include_projects=True,
        include_people=True
    )
    
    from app.services.agent_actions import parse_and_execute_actions
    from app.models.db import AsyncSessionLocal
    
    async with AsyncSessionLocal() as db:
        clean_reply, _ = await parse_and_execute_actions(response, db=db)

    # Update local history (use original response to keep actions in context for Z)
    chat_histories[chat_id].append({"role": "user", "content": update.message.text})
    chat_histories[chat_id].append({"role": "z", "content": response})
    
    # Keep history manageable
    if len(chat_histories[chat_id]) > 20:
        chat_histories[chat_id] = chat_histories[chat_id][-20:]

    # Final formatted message
    footer = await _get_stats_footer()
    await update.message.reply_text(f"{clean_reply}{footer}", parse_mode="Markdown")

@owner_only
async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process voice messages."""
    await update.message.reply_text("🎙️ *Z is listening...*", parse_mode="Markdown")
    
    # 1. Download voice file
    voice_file = await context.bot.get_file(update.message.voice.file_id)
    voice_bytes = await voice_file.download_as_bytearray()
    
    # 2. Transcribe
    from app.services.voice import transcribe_voice
    transcript = await transcribe_voice(voice_bytes)
    
    if not transcript or transcript.startswith("["):
        await update.message.reply_text(f"⚠️ {transcript or 'Could not transcribe voice.'}")
        return

    await update.message.reply_text(f"📝 *Transcript:* _{transcript}_", parse_mode="Markdown")
    
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
    
    footer = await _get_stats_footer()
    await update.message.reply_text(f"{clean_reply}{footer}", parse_mode="Markdown")

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
    
    await update.message.reply_text("⏳ *Z is analyzing required context...*", parse_mode="Markdown")
    
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
        f"⚖️ *Privacy Disclosure*\n\n"
        f"To answer this deeply, I need to send the following to {settings.DEEP_THINK_PROVIDER}:\n"
        f"{proposal['summary']}\n\n"
        f"*Question:* {query}"
    )
    await update.message.reply_text(disclosure_msg, parse_mode="Markdown", reply_markup=reply_markup)

async def handle_approval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle User granting access to Cloud API."""
    query_data = update.callback_query.data
    thought_id = query_data.split("_")[-1]
    
    if "cancel" in query_data:
        await update.callback_query.edit_message_text("🚫 Deep Thinking cancelled. Context was not shared.")
        return

    await update.callback_query.edit_message_text("📡 *Access granted. Sending to Cloud API...*", parse_mode="Markdown")
    
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
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=response,
        parse_mode="Markdown"
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
        
        await query.edit_message_text(f"🚀 *Added to Calendar:* {event_data['summary']}", parse_mode="Markdown")
    except Exception as e:
        print(f"DEBUG: Calendar approval failed: {e}")
        await query.edit_message_text(f"❌ Failed to add event: {str(e)}")
