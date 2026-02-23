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

bot_app: Application | None = None

# --- Context Persistence ---
chat_histories = {} # chat_id -> list of dicts {'role': 'user/z', 'content': str}

async def start_telegram_bot():
    """Start the Telegram bot in polling mode within the FastAPI event loop."""
    global bot_app
    if not settings.TELEGRAM_BOT_TOKEN:
        print("TELEGRAM_BOT_TOKEN not set. Bot will not start.")
        return

    bot_app = (
        Application.builder()
        .token(settings.TELEGRAM_BOT_TOKEN)
        .build()
    )

    # Register handlers
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
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_freetext))
    bot_app.add_handler(MessageHandler(filters.VOICE, handle_voice))

    # Initialize and start polling (non-blocking)
    await bot_app.initialize()
    await bot_app.start()
    await bot_app.updater.start_polling(drop_pending_updates=True)

    # Proactive greeting with Context & Stats
    try:
        from app.services.llm import chat
        from app.services.memory import get_memory_stats
        
        stats = await get_memory_stats()
        stats_text = f"Memory: {stats['points']} points" if stats['status'] != 'error' else "Memory: Offline"
        
        # Recall important stuff for today
        try:
            from app.services.calendar import fetch_calendar_events
            import asyncio
            events = await asyncio.wait_for(fetch_calendar_events(max_results=3, days_ahead=1), timeout=5.0)
            event_summary = ""
            if events:
                ev_list = [f"• {e['summary']} ({e['start'].split('T')[1][:5] if 'T' in e['start'] else 'All Day'})" for e in events]
                event_summary = "\nUpcoming today:\n" + "\n".join(ev_list)
        except Exception as ce:
            print(f"Calendar fetch failed during greeting: {ce}")
            event_summary = ""

        greeting_prompt = (
            f"Z is coming online. System status: Ready. {stats_text}. {event_summary}\n\n"
            "Greet the user sharply. Remind them of any urgent calendar events mentioned above if applicable. Use only provided info, don't invent anything."
        )
        greeting = await chat(greeting_prompt)
        await send_notification(f"⚡ {greeting}\n\n_System: {stats_text}_")
    except Exception as e:
        print(f"Could not send startup greeting: {e}")
        await send_notification("⚡ Z is online.")

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

# --- Command Handlers ---
@owner_only
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚀 Personal AI OS is online.")

@owner_only
async def cmd_tree(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from app.services.planka import get_project_tree
    tree = await get_project_tree()
    await update.message.reply_text(f"```\n{tree}\n```", parse_mode="Markdown")

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
    
    # Update local history
    chat_histories[chat_id].append({"role": "user", "content": update.message.text})
    chat_histories[chat_id].append({"role": "z", "content": response})
    
    # Keep history manageable
    if len(chat_histories[chat_id]) > 20:
        chat_histories[chat_id] = chat_histories[chat_id][-20:]
        
    await update.message.reply_text(response)

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
    
    chat_histories[chat_id].append({"role": "user", "content": transcript})
    chat_histories[chat_id].append({"role": "z", "content": response})
    
    await update.message.reply_text(response)

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
