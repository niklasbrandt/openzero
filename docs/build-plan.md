# OpenZero — Personal AI Operating System – Implementation Guide

> **Target Server**: Cloud VPS Provider (e.g. 8 vCPU, 24 GB RAM, 200 GB NVMe)
> **OS**: Ubuntu 24.04 LTS
> **Monthly Cost**: ~$15–20

---

# 0. System Overview

```
User (Telegram + Planka PWA)
        ↓
┌─────────────────────────────────────┐
│         Tailscale VPN (Private)     │
├─────────────────────────────────────┤
│  FastAPI Backend (Uvicorn)          │
│    ├── APScheduler (Background)     │
│    ├── Telegram Bot (Polling)       │
│    └── LLM Client (→ Ollama)        │
├─────────────────────────────────────┤
│  PostgreSQL 16   (Structured Data)  │
│  Qdrant          (Semantic Memory)  │
│  Ollama          (Local LLM)        │
│  Planka          (Task Board)       │
└─────────────────────────────────────┘
        ↓
External (Read-Only):
  - Email API (e.g. Gmail API or other mail client API, OAuth2, polling)
  - Google Calendar API
```

---

# 1. Infrastructure Setup

## 1.1 Provision VPS

- **Provider**: Your preferred Cloud VPS
- **Specs**: A plan with at least 24 GB RAM
- **Region**: Close to your location
- **OS Image**: Ubuntu 24.04 LTS (Noble Numbat)

## 1.2 First Login & Hardening

After receiving the root password and IP, SSH in from your Mac:

```bash
ssh root@YOUR_SERVER_IP
```

### Step 1: System Update
```bash
apt update && apt upgrade -y
```

### Step 2: Create Non-Root User
```bash
adduser openzero
usermod -aG sudo openzero
```

### Step 3: Copy SSH Key for New User
```bash
# On your Mac (in a new terminal):
ssh-copy-id openzero@YOUR_SERVER_IP
```

### Step 4: Disable Root Login & Password Auth
```bash
sudo nano /etc/ssh/sshd_config
```
Set these values:
```
PermitRootLogin no
PasswordAuthentication no
PubkeyAuthentication yes
```
Then restart:
```bash
sudo systemctl restart sshd
```

### Step 5: Firewall (UFW)
Since we are using Tailscale, we only need SSH open to the public:
```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp comment "SSH"
sudo ufw enable
```

> **Important**: Do NOT open ports 80, 443, 5432, 6333, 11434.
> All services are accessed via Tailscale VPN only.

### Step 6: Fail2Ban
```bash
sudo apt install fail2ban -y
sudo cp /etc/fail2ban/jail.conf /etc/fail2ban/jail.local
sudo systemctl enable fail2ban
sudo systemctl start fail2ban
```

### Step 7: Automatic Security Updates
```bash
sudo apt install unattended-upgrades -y
sudo dpkg-reconfigure -plow unattended-upgrades
```

---

# 2. Install Docker (Official Method)

Do NOT use `apt install docker.io` — it's outdated. Use Docker's official repository:

```bash
# Install prerequisites
sudo apt install ca-certificates curl gnupg -y

# Add Docker GPG key
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

# Add Docker repository
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Install Docker Engine + Compose Plugin
sudo apt update
sudo apt install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin -y

# Allow non-root user to use Docker
sudo usermod -aG docker openzero
```

Log out and back in as `openzero` for Docker access without sudo.

---

# 3. Project Structure

```
/home/openzero/openzero/
├── docker-compose.yml
├── .env                        # Backend secrets (NEVER commit)
├── .env.planka                 # Planka-specific env
├── .env.example                # Template (commit this)
├── .gitignore
├── ollama-entrypoint.sh        # Auto-pull model on startup
├── agent-character.md          # Z (AI agent) personality spec
├── about-me.example.md         # Template — copy to personal/
├── requirements.example.md     # Template — copy to personal/
├── recurring-plans.md          # Daily/weekly/monthly routines
├── personal/                   #  GITIGNORED — your private data
│   ├── about-me.md             # Your personal info
│   └── requirements.md         # Your email rules, preferences
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── app/
│   │   ├── main.py             # FastAPI app + lifespan
│   │   ├── config.py           # Settings via pydantic-settings
│   │   ├── api/
│   │   │   ├── telegram.py     # Bot command handlers
│   │   │   └── health.py       # Health check endpoint
│   │   ├── services/
│   │   │   ├── gmail.py        # Email polling logic or other web services
│   │   │   ├── planka.py       # Planka REST client
│   │   │   ├── llm.py          # Ollama client
│   │   │   └── memory.py       # Qdrant operations
│   │   ├── models/
│   │   │   └── db.py           # SQLAlchemy models
│   │   └── tasks/
│   │       ├── scheduler.py    # APScheduler setup
│   │       ├── morning.py      # Morning briefing job
│   │       ├── weekly.py       # Weekly review job
│   │       ├── monthly.py      # Monthly review job
│   │       └── email_poll.py   # Email polling job or other web services
│   └── alembic/                # DB migrations
└── backups/                    # Encrypted DB dumps
```

---

# 4. docker-compose.yml

```yaml
version: '3.8'

services:

  postgres:
    image: postgres:16-alpine
    restart: always
    environment:
      POSTGRES_USER: ${DB_USER}
      POSTGRES_PASSWORD: ${DB_PASSWORD}
      POSTGRES_DB: ${DB_NAME}
    volumes:
      - pgdata:/var/lib/postgresql/data
    networks:
      - internal
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${DB_USER}"]
      interval: 10s
      timeout: 5s
      retries: 5

  qdrant:
    image: qdrant/qdrant:latest
    restart: always
    environment:
      QDRANT__SERVICE__API_KEY: ${QDRANT_API_KEY}
    volumes:
      - qdrant_data:/qdrant/storage
    networks:
      - internal

  ollama:
    image: ollama/ollama:0.5.7
    restart: always
    volumes:
      - ollama_data:/root/.ollama
      - ./scripts/ollama-entrypoint.sh:/entrypoint.sh
    entrypoint: ["/bin/bash", "/entrypoint.sh"]
    environment:
      - OLLAMA_HOST=0.0.0.0
      - OLLAMA_MODEL=${OLLAMA_MODEL}
    networks:
      - internal

  planka:
    image: ghcr.io/plankanban/planka:latest
    restart: always
    depends_on:
      postgres:
        condition: service_healthy
    env_file: .env.planka
    volumes:
      - planka_avatars:/app/public/user-avatars
      - planka_backgrounds:/app/public/project-background-images
      - planka_attachments:/app/private/attachments
    networks:
      - internal

  backend:
    build: ./backend
    restart: always
    depends_on:
      postgres:
        condition: service_healthy
      qdrant:
        condition: service_started
      ollama:
        condition: service_started
    env_file: .env
    volumes:
      - gmail_tokens:/app/tokens
    networks:
      - internal
    ports:
      - "8000:8000"

networks:
  internal:
    driver: bridge

volumes:
  pgdata:
  qdrant_data:
  ollama_data:
  planka_avatars:
  planka_backgrounds:
  planka_attachments:
  gmail_tokens:
```

---

# 5. Ollama Auto-Pull Entrypoint

Create `ollama-entrypoint.sh` in the project root:

```bash
#!/bin/bash
# Start Ollama server in the background
ollama serve &

# Wait for the server to be ready
echo "Waiting for Ollama to start..."
until curl -s http://localhost:11434/api/tags > /dev/null 2>&1; do
  sleep 2
done
echo "Ollama is ready."

# Pull model if not already present
if [ -n "$OLLAMA_MODEL" ]; then
  if ! ollama list | grep -q "$OLLAMA_MODEL"; then
    echo "Pulling $OLLAMA_MODEL model..."
    ollama pull "$OLLAMA_MODEL"
    echo "Model pulled successfully."
  else
    echo "Model $OLLAMA_MODEL already present."
  fi
fi

# Keep Ollama running in the foreground
wait
```

> **Why llama3.2:3b?** It is a highly efficient model optimized for edge devices and
> general task handling. It offers rapid response times on CPUs while maintaining 
> strong reasoning capabilities for daily automation.

---

# 6. Environment Files

## .env (Backend)
```bash
# Database
DB_USER=zero
DB_PASSWORD=CHANGE_ME_STRONG_PASSWORD
DB_NAME=zero_db
DB_HOST=postgres
DB_PORT=5432
DATABASE_URL=postgresql+asyncpg://${DB_USER}:${DB_PASSWORD}@${DB_HOST}:${DB_PORT}/${DB_NAME}

# Telegram
TELEGRAM_BOT_TOKEN=your_bot_token_from_botfather
TELEGRAM_ALLOWED_USER_ID=your_telegram_user_id

# Ollama
OLLAMA_BASE_URL=http://ollama:11434

# Qdrant
QDRANT_HOST=qdrant
QDRANT_PORT=6333
QDRANT_API_KEY=CHANGE_ME_QDRANT_KEY

# Planka
PLANKA_BASE_URL=http://planka:1337
PLANKA_ADMIN_EMAIL=admin@example.com
PLANKA_ADMIN_PASSWORD=CHANGE_ME_PLANKA_PASS

# Optional: Cloud LLM APIs (Uncomment to use)
# LLM_PROVIDER=groq # Options: ollama, groq, openai
# GROQ_API_KEY=your_groq_api_key
# OPENAI_API_KEY=your_openai_api_key

# Deep Thinking Configuration (triggered via /think)
DEEP_THINK_PROVIDER=groq
DEEP_THINK_MODEL=llama-3.3-70b-specdec  # or o1-mini, r1, etc.
```

## .env.planka
```bash
BASE_URL=http://planka:1337
DATABASE_URL=postgresql://zero:CHANGE_ME_STRONG_PASSWORD@postgres:5432/zero_db
SECRET_KEY=CHANGE_ME_RANDOM_64_CHAR_STRING
DEFAULT_ADMIN_EMAIL=admin@example.com
DEFAULT_ADMIN_PASSWORD=CHANGE_ME_PLANKA_PASS
DEFAULT_ADMIN_NAME=Admin
DEFAULT_ADMIN_USERNAME=admin
TRUST_PROXY=0
```

## .env.example (commit this to Git)
```bash
DB_USER=zero
DB_PASSWORD=
DB_NAME=zero_db
DB_HOST=postgres
DB_PORT=5432
TELEGRAM_BOT_TOKEN=
TELEGRAM_ALLOWED_USER_ID=
USER_TIMEZONE=America/New_York  # Set to current timezone for correct context
OLLAMA_BASE_URL=http://ollama:11434
QDRANT_HOST=qdrant
QDRANT_PORT=6333
QDRANT_API_KEY=
PLANKA_BASE_URL=http://planka:1337
PLANKA_ADMIN_EMAIL=
PLANKA_ADMIN_PASSWORD=

# Optional: Cloud LLM
LLM_PROVIDER=ollama
GROQ_API_KEY=
OPENAI_API_KEY=
DEEP_THINK_PROVIDER=groq
DEEP_THINK_MODEL=llama-3.3-70b-specdec
```

## .gitignore
```
# Personal data (NEVER commit)
personal/

# Secrets
.env
.env.planka
tokens/

# Runtime
__pycache__/
*.py[cod]
*.log

# Backups
backups/

# OS
.DS_Store
```

---

# 7. Backend (FastAPI)

## 7.1 requirements.txt
```
fastapi>=0.115.0
uvicorn[standard]>=0.34.0
sqlalchemy[asyncio]>=2.0
asyncpg>=0.30.0
alembic>=1.14.0
pydantic-settings>=2.7.0
python-telegram-bot>=21.0
httpx>=0.28.0
qdrant-client>=1.12.0
sentence-transformers>=3.4.0
apscheduler>=3.10.0
google-api-python-client>=2.160.0
google-auth-oauthlib>=1.2.0
google-auth-httplib2>=0.2.0
plankapy>=2.0.0
```

## 7.2 Dockerfile
```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

## 7.3 FastAPI App with Lifespan (app/main.py)

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.tasks.scheduler import start_scheduler, stop_scheduler
from app.api.telegram import start_telegram_bot, stop_telegram_bot

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup & shutdown logic."""
    # --- STARTUP ---
    await start_scheduler()
    await start_telegram_bot()
    yield
    # --- SHUTDOWN ---
    await stop_telegram_bot()
    await stop_scheduler()

app = FastAPI(title="Personal AI OS", lifespan=lifespan)

@app.get("/health")
async def health():
    return {"status": "ok"}
```

---

# 8. Background Tasks (APScheduler)

## 8.1 Scheduler Setup (app/tasks/scheduler.py)

Using FastAPI's `lifespan` ensures the scheduler starts and stops cleanly
with the app. No Celery or Redis needed for a single-user system.

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from app.tasks.morning import morning_briefing
from app.tasks.weekly import weekly_review
from app.tasks.email_poll import poll_gmail

scheduler = AsyncIOScheduler(timezone="America/New_York")

async def start_scheduler():
    # Morning Briefing — Mon–Fri at 07:30
    scheduler.add_job(
        morning_briefing,
        CronTrigger(day_of_week="mon-fri", hour=7, minute=30),
        id="morning_briefing",
        replace_existing=True,
    )

    # Weekly Review — Sunday at 10:00
    scheduler.add_job(
        weekly_review,
        CronTrigger(day_of_week="sun", hour=10, minute=0),
        id="weekly_review",
        replace_existing=True,
    )

    # Email Polling (via Gmail API or other mail client API) — every 10 minutes
    scheduler.add_job(
        poll_gmail,
        IntervalTrigger(minutes=10),
        id="poll_gmail",
        replace_existing=True,
    )

    scheduler.start()

async def stop_scheduler():
    scheduler.shutdown(wait=False)
```

## 8.2 Email Polling Job (app/tasks/email_poll.py)

```python
from app.services.gmail import fetch_unread_emails
from app.services.llm import summarize_email
from app.api.telegram import send_notification
from app.models.db import get_email_rules

async def poll_gmail():
    """Check for new emails, apply rules, notify if urgent."""
    rules = await get_email_rules()
    emails = await fetch_unread_emails(max_results=20)

    for email in emails:
        sender = email["from"].lower()
        subject = email["subject"]

        # Check against rules
        for rule in rules:
            if rule.sender_pattern in sender:
                if rule.action == "urgent":
                    await send_notification(
                        f" *URGENT EMAIL*\n"
                        f"From: {email['from']}\n"
                        f"Subject: {subject}"
                    )
                break
        else:
            # Non-urgent: store summary for morning briefing
            summary = await summarize_email(email["snippet"])
            # Store in Postgres for the morning briefing to pick up
```

---

# 9. Telegram Bot (Polling Mode)

Since the server is behind Tailscale VPN, Telegram cannot reach us via webhooks.
We use **long polling** instead — the bot actively asks Telegram for updates.

## 9.1 Bot Setup (app/api/telegram.py)

```python
from telegram import Update, Bot
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from app.config import settings
import asyncio

bot_app: Application | None = None

async def start_telegram_bot():
    """Start the Telegram bot in polling mode within the FastAPI event loop."""
    global bot_app
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
    bot_app.add_handler(CommandHandler("weekly", cmd_weekly))
    bot_app.add_handler(CommandHandler("daily", cmd_daily))
    bot_app.add_handler(CommandHandler("add", cmd_add_topic))
    bot_app.add_handler(CommandHandler("think", cmd_think))
    bot_app.add_handler(CallbackQueryHandler(handle_approval, pattern="^think_")) # Added this line
    bot_app.add_handler(MessageHandler(filters.TEXT, handle_freetext))

    # Initialize and start polling (non-blocking)
    await bot_app.initialize()
    await bot_app.start()
    await bot_app.updater.start_polling(drop_pending_updates=True)

async def stop_telegram_bot():
    """Gracefully stop the bot."""
    global bot_app
    if bot_app:
        await bot_app.updater.stop()
        await bot_app.stop()
        await bot_app.shutdown()

async def send_notification(text: str, reply_markup=None):
    """Send a message to the owner."""
    bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
    await bot.send_message(
        chat_id=settings.TELEGRAM_ALLOWED_USER_ID,
        text=text,
        parse_mode="Markdown",
        reply_markup=reply_markup, # Added reply_markup
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
    await update.message.reply_text(" Personal AI OS is online.")

@owner_only
async def cmd_tree(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Fetch project tree from Postgres and format
    from app.services.planka import get_project_tree
    tree = await get_project_tree()
    await update.message.reply_text(f"```\n{tree}\n```", parse_mode="Markdown")

@owner_only
async def cmd_review(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from app.tasks.weekly import weekly_review
    report = await weekly_review()
    await update.message.reply_text(report, parse_mode="Markdown")

@owner_only
async def cmd_memory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.replace("/memory", "").strip()
    from app.services.memory import semantic_search
    results = await semantic_search(query)
    await update.message.reply_text(results)

@owner_only
async def cmd_weekly(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from app.tasks.weekly import weekly_review
    report = await weekly_review()
    await update.message.reply_text(report, parse_mode="Markdown")

@owner_only
async def cmd_daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from app.tasks.morning import morning_briefing
    briefing = await morning_briefing()
    await update.message.reply_text(briefing, parse_mode="Markdown")

@owner_only
async def cmd_add_topic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    topic = update.message.text.replace("/add", "").strip()
    from app.services.memory import store_memory
    await store_memory(topic)
    await update.message.reply_text(f" Stored: {topic}")

@owner_only
async def handle_freetext(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process freeform text via the default LLM."""
    from app.services.llm import chat
    response = await chat(update.message.text)
    await update.message.reply_text(response)

@owner_only
async def cmd_think(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Initiate Deep Thinking with Context Approval."""
    query = update.message.text.replace("/think", "").strip()
    if not query:
        await update.message.reply_text("What should I think deeply about?")
        return
    
    await update.message.reply_text(" *Z is analyzing required context...*", parse_mode="Markdown")
    
    from app.services.llm import generate_context_proposal
    from app.models.db import store_pending_thought
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    # 1. Local LLM decides what data is needed
    proposal = await generate_context_proposal(query)
    
    # 2. Store in DB to wait for approval
    thought_id = await store_pending_thought(query, proposal["context_data"])
    
    # 3. Create Approval UI
    keyboard = [
        [
            InlineKeyboardButton(" Grant Access", callback_data=f"think_approve_{thought_id}"),
            InlineKeyboardButton(" Cancel", callback_data=f"think_cancel_{thought_id}"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    disclosure_msg = (
        f"️ *Privacy Disclosure*\n\n"
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
        await update.callback_query.edit_message_text(" Deep Thinking cancelled. Context was not shared.")
        return

    await update.callback_query.edit_message_text(" *Access granted. Sending to Cloud API...*", parse_mode="Markdown")
    
    from app.models.db import get_pending_thought
    from app.services.llm import chat
    
    thought = await get_pending_thought(thought_id)
    if not thought:
        await update.callback_query.edit_message_text(" Error: Thought context expired.")
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
```

---

# 10. Database Schema

```sql
-- Projects (hierarchical via parent_id)
CREATE TABLE projects (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    parent_id INT REFERENCES projects(id) ON DELETE SET NULL,
    status TEXT DEFAULT 'active',       -- active, paused, completed, archived
    priority INT DEFAULT 3,             -- 1 (highest) to 5 (lowest)
    domain TEXT DEFAULT 'general',      -- career, health, family, finance, creative
    last_reviewed TIMESTAMP,
    progress INT DEFAULT 0,             -- 0–100
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- User Preferences (key-value store)
CREATE TABLE preferences (
    id SERIAL PRIMARY KEY,
    key TEXT UNIQUE NOT NULL,
    value TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Email Rules
CREATE TABLE email_rules (
    id SERIAL PRIMARY KEY,
    sender_pattern TEXT NOT NULL,       -- substring match against sender
    subject_pattern TEXT,               -- optional: substring match against subject
    action TEXT NOT NULL DEFAULT 'urgent', -- urgent, archive, summarize
    created_at TIMESTAMP DEFAULT NOW()
);

-- Conversation Log (for LLM context window management)
CREATE TABLE conversations (
    id SERIAL PRIMARY KEY,
    role TEXT NOT NULL,                 -- user, assistant
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Email Summaries (for morning briefing aggregation)
CREATE TABLE email_summaries (
    id SERIAL PRIMARY KEY,
    sender TEXT NOT NULL,
    subject TEXT NOT NULL,
    summary TEXT,
    is_urgent BOOLEAN DEFAULT FALSE,
    processed_at TIMESTAMP DEFAULT NOW(),
    included_in_briefing BOOLEAN DEFAULT FALSE
);

-- Pending Thoughts (for HITL context approval)
CREATE TABLE pending_thoughts (
    id UUID PRIMARY KEY,
    query TEXT NOT NULL,
    context_data TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);
```

### Seed Data (Example)
```sql
-- Replace with your own rules in personal/requirements.md
INSERT INTO email_rules (sender_pattern, action) VALUES
('kids-school', 'urgent'),
('doctor-office', 'urgent'),
('important-contact', 'urgent');

INSERT INTO preferences (key, value) VALUES
('career_tone', 'confident, impact-driven, never desperate'),
('morning_briefing_time', '07:30'),
('timezone', 'America/New_York'),
('weekly_review_day', 'sunday');
```

→ See **[requirements.example.md](./requirements.example.md)** for the template.
  Copy to `personal/requirements.md` and fill in your own rules.

---

# 11. Memory System (Qdrant + Local Embeddings)

## 11.1 Embedding Model

We run the embedding model **locally** inside the backend container.
No data leaves your server.

**Recommended model**: `all-MiniLM-L6-v2`
- 80 MB model size (tiny)
- 384-dimensional embeddings
- Best speed-to-quality ratio for personal knowledge search

## 11.2 Memory Service (app/services/memory.py)

```python
from qdrant_client import QdrantClient, models
from sentence_transformers import SentenceTransformer
from app.config import settings

# Load embedding model once at import time
embedder = SentenceTransformer("all-MiniLM-L6-v2")
COLLECTION_NAME = "personal_memory"

def get_qdrant() -> QdrantClient:
    return QdrantClient(
        host=settings.QDRANT_HOST,
        port=settings.QDRANT_PORT,
        api_key=settings.QDRANT_API_KEY,
    )

async def ensure_collection():
    """Create collection if it doesn't exist."""
    client = get_qdrant()
    collections = [c.name for c in client.get_collections().collections]
    if COLLECTION_NAME not in collections:
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=models.VectorParams(
                size=384,
                distance=models.Distance.COSINE,
            ),
        )

async def store_memory(text: str, metadata: dict = None):
    """Embed text and store in Qdrant."""
    client = get_qdrant()
    embedding = embedder.encode(text).tolist()
    import uuid
    client.upsert(
        collection_name=COLLECTION_NAME,
        points=[
            models.PointStruct(
                id=str(uuid.uuid4()),
                vector=embedding,
                payload={"text": text, **(metadata or {})},
            )
        ],
    )

async def semantic_search(query: str, top_k: int = 5) -> str:
    """Search memory and return formatted results."""
    client = get_qdrant()
    query_vector = embedder.encode(query).tolist()
    results = client.search(
        collection_name=COLLECTION_NAME,
        query_vector=query_vector,
        limit=top_k,
    )
    if not results:
        return "No memories found."
    lines = []
    for i, hit in enumerate(results, 1):
        lines.append(f"{i}. (score: {hit.score:.2f}) {hit.payload['text']}")
    return "\n".join(lines)
```

---

# 12. Z — Agent Character

→ See **[agent-character.md](./agent-character.md)** for the full personality
spec, communication principles, motivational framing, guardrails, and the
career framing engine.

---

# 13. LLM Service (app/services/llm.py)

```python
import httpx
from datetime import datetime
import pytz
from app.config import settings

SYSTEM_PROMPT = """You are Z — the AI agent inside OpenZero, a private operating system.
You are not a generic assistant. You are an agent operator — sharp, warm, and direct.

Core behavior:
- Speak with calm intensity. No filler, no hype. Just clarity and momentum.
- Reframe problems into next moves. Never dwell on what went wrong.
- Reference the user's goals. Connect today's actions to what they're building.
- Celebrate progress — small or big. Most people never build what this user is building.
- Be honest. If a plan has a gap, say so — then offer the path forward.
- Treat projects like missions, goals like campaigns, weekly reviews like board meetings.

Rules:
- Never say "Great question!" or "Sure, I can help!" — just answer.
- Never auto-send emails or messages. Always present as a draft.
- When drafting career content, use confident impact language.
- Respond concisely unless the user asks for detail.

You have access to the user's project tree, calendar, emails, and semantic memory.
You remember what matters to them. Act like it."""

async def chat(
    user_message: str, 
    system_override: str = None, 
    provider: str = None, 
    model: str = None
) -> str:
    """Send a message to the configured LLM."""
    user_tz = pytz.timezone(getattr(settings, "USER_TIMEZONE", "UTC"))
    current_time = datetime.now(user_tz).strftime("%A, %Y-%m-%d %H:%M:%S %Z")
    
    context_header = f"Current Local Time: {current_time}\n\n"
    system_prompt = context_header + (system_override or SYSTEM_PROMPT)
    
    provider = (provider or getattr(settings, "LLM_PROVIDER", "ollama")).lower()

    async with httpx.AsyncClient(timeout=180.0) as client:
        # --- Option A: Local Ollama ---
        if provider == "ollama":
            response = await client.post(
                f"{settings.OLLAMA_BASE_URL}/api/chat",
                json={
                    "model": model or "llama3.1:8b",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message},
                    ],
                    "stream": False,
                },
            )
            data = response.json()
            return data.get("message", {}).get("content", "No response from Ollama.")

        # --- Option B: Groq (Ultra-Fast Cloud API) ---
        elif provider == "groq":
            response = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}"},
                json={
                    "model": model or "llama-3.1-70b-versatile",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message},
                    ],
                },
            )
            data = response.json()
            return data.get("choices", [{}])[0].get("message", {}).get("content", "No response from Groq.")

        # --- Option C: OpenAI ---
        elif provider == "openai":
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
                json={
                    "model": model or "gpt-4o",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message},
                    ],
                },
            )
            data = response.json()
            return data.get("choices", [{}])[0].get("message", {}).get("content", "No response from OpenAI.")

        return f"Unknown LLM provider: {provider}"

async def generate_context_proposal(query: str) -> dict:
    """Use Local LLM to identify relevant information for the user to approve."""
    # This involves logic to search memory/projects based on the query
    # and then formatting a response like:
    # {
    #   "summary": "- Project: 'OpenZero'\n- 3 Recent Memories\n- 2 Calendar Events",
    #   "context_data": "..." (the actual string to send)
    # }
    # For now, a simplified version:
    from app.services.memory import semantic_search
    memories = await semantic_search(query, top_k=3)
    
    return {
        "summary": f"• Local memories related to: '{query[:30]}...'",
        "context_data": f"Relevant Memories:\n{memories}"
    }

async def summarize_email(snippet: str) -> str:
    """Generate a one-line summary of an email snippet."""
    prompt = f"Summarize this email in one sentence:\n\n{snippet}"
    return await chat(prompt, system_override="You are a concise email summarizer.")
```

---

# 14. Email Integration (e.g. Gmail API or other mail client API)

## 13.1 Google Cloud Setup
1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a new project: `personal-ai-os`
3. Enable: **Gmail API** + **Google Calendar API**
4. Create **OAuth 2.0 Client ID** (Desktop App type)
5. Download `credentials.json` → place in `backend/tokens/`

**Scopes** (read-only email, with optional read-write calendar):
```text
https://www.googleapis.com/auth/gmail.readonly
https://www.googleapis.com/auth/calendar.readonly (or https://www.googleapis.com/auth/calendar for read-write)
```

## 13.2 Email Service (app/services/gmail.py)

```python
import os
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar.readonly", # Use "https://www.googleapis.com/auth/calendar" instead for read-write
]
TOKEN_PATH = "/app/tokens/token.json"
CREDS_PATH = "/app/tokens/credentials.json"

def get_gmail_service():
    """Authenticate and return email API service."""
    creds = None
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_PATH, "w") as token:
            token.write(creds.to_json())
    return build("gmail", "v1", credentials=creds)

async def fetch_unread_emails(max_results: int = 20) -> list[dict]:
    """Fetch recent unread emails."""
    service = get_gmail_service()
    results = service.users().messages().list(
        userId="me",
        q="is:unread",
        maxResults=max_results,
    ).execute()

    messages = results.get("messages", [])
    emails = []
    for msg in messages:
        detail = service.users().messages().get(
            userId="me", id=msg["id"], format="metadata",
            metadataHeaders=["From", "Subject"],
        ).execute()
        headers = {h["name"]: h["value"] for h in detail["payload"]["headers"]}
        emails.append({
            "id": msg["id"],
            "from": headers.get("From", ""),
            "subject": headers.get("Subject", ""),
            "snippet": detail.get("snippet", ""),
        })
    return emails
```

> **First-time OAuth**: You'll need to run the OAuth flow once manually
> (via SSH tunnel) to generate `token.json`. After that, it auto-refreshes.

---

# 15. Planka Integration

## 14.1 Using the plankapy Library

```python
from plankapy import Planka

planka = Planka(
    url="http://planka:1337",
    username="admin@example.com",
    password="CHANGE_ME_PLANKA_PASS",
)

# Get all projects
projects = planka.get_projects()

# Create a card on a specific board/list
def create_task(board_name: str, list_name: str, title: str):
    for project in projects:
        for board in project.boards:
            if board.name == board_name:
                for lst in board.lists:
                    if lst.name == list_name:
                        lst.create_card(name=title, position=65535)
```

## 14.2 Board Structure
Organize your Planka boards by life domain:

| Board         | Lists                                 |
|:--------------|:--------------------------------------|
| **Career**    | Inbox → In Progress → Blocked → Done |
| **Health**    | Inbox → Habits → Completed           |
| **Family**    | Inbox → This Week → Done             |
| **Finance**   | Inbox → Pending → Resolved           |
| **Creative**  | Ideas → Active → Shipped             |

---

# 16. Recurring Plans (Daily / Weekly / Monthly)

→ See **[recurring-plans.md](./recurring-plans.md)** for all scheduled routines:
morning briefing, weekly review, and monthly big-picture check — including
schedules, content structure, tone examples, and implementation code.

→ Career framing rules are in **[agent-character.md](./agent-character.md)**.

---

# 17. Project Tree Command

```python
async def get_project_tree() -> str:
    """Recursively build a text tree of all projects."""
    # Fetch all projects from DB
    projects = await fetch_all_projects()

    def build_tree(parent_id=None, indent=0):
        lines = []
        children = [p for p in projects if p.parent_id == parent_id]
        for child in sorted(children, key=lambda p: p.priority):
            status_icon = {"active": " [ACTIVE]", "paused": " [PAUSED]", "completed": " [DONE]"}.get(
                child.status, ""
            )
            lines.append(f"{'  ' * indent}{status_icon} {child.name} [{child.progress}%]")
            lines.extend(build_tree(child.id, indent + 1))
        return lines

    tree_lines = build_tree()
    return "\n".join(tree_lines) if tree_lines else "No projects found."
```

Example output:
```
[ACTIVE] Career [40%]
  [PAUSED] Job Applications [20%]
[ACTIVE] Family [60%]
   Kindergarten Registration [100%]
  [ACTIVE] Weekend Planning [30%]
[ACTIVE] Health [50%]
  [ACTIVE] Running Routine [50%]
```

---

# 18. Backups

## 19.1 Automated Daily Backup Script

Create `/home/user/openzero/backup.sh`:
```bash
#!/bin/bash
set -euo pipefail

BACKUP_DIR="/home/user/openzero/backups"
DATE=$(date +%Y-%m-%d_%H%M)
BACKUP_FILE="${BACKUP_DIR}/zero_db_${DATE}.sql"

mkdir -p "$BACKUP_DIR"

# Dump database from Docker
docker compose exec -T postgres pg_dump -U zero zero_db > "$BACKUP_FILE"

# Encrypt with GPG (symmetric, password from env)
gpg --batch --yes --symmetric --cipher-algo AES256 \
    --passphrase-file /home/user/.backup_passphrase \
    "$BACKUP_FILE"

# Remove unencrypted dump
rm "$BACKUP_FILE"

# Keep only last 30 days
find "$BACKUP_DIR" -name "*.sql.gpg" -mtime +30 -delete

echo "Backup completed: ${BACKUP_FILE}.gpg"
```

## 19.2 Cron Job
```bash
chmod +x /home/user/openzero/backup.sh

# Add to crontab
crontab -e
# Add this line:
0 3 * * * /home/user/openzero/backup.sh >> /home/user/openzero/backups/backup.log 2>&1
```

---

# 19. Security & VPN Integration (Tailscale)

For maximum privacy, we **do NOT expose any ports** to the public internet.

## 20.1 Install Tailscale on the VPS (Host-Level)

Instead of running Tailscale as a Docker container, install it directly on the host.
This is simpler and lets all Docker services be reachable via the Tailscale IP.

```bash
# Install Tailscale
curl -fsSL https://tailscale.com/install.sh | sh

# Authenticate (will give you a URL to open in your browser)
sudo tailscale up

# Enable subnet routing for Docker network (optional, advanced)
# sudo tailscale up --advertise-routes=172.18.0.0/16
```

## 20.2 Access Services via Tailscale

Once connected, your VPS gets a Tailscale IP (e.g., `100.x.y.z`) and a MagicDNS name.

| Service     | Access URL                        |
|:------------|:----------------------------------|
| Planka      | `http://100.x.y.z:1337`          |
| Backend API | `http://100.x.y.z:8000`          |
| Health      | `http://100.x.y.z:8000/health`   |

> **On your phone**: Install the Tailscale app → join the same network → open Planka
> in Safari/Chrome like a local web app. Add to Home Screen for PWA experience.

## 20.3 Security Checklist

- [x] SSH keys only (password auth disabled)
- [x] Fail2Ban active on SSH
- [x] UFW: only port 22 open to public
- [x] All services on internal Docker network
- [x] Tailscale for private access (zero public ports for services)
- [x] Telegram bot uses **polling** (no public webhook needed)
- [x] Email API: **read-only** scope (no sending/deleting yet, write capability might be added later)
- [x] No auto-sending of any external messages
- [x] Qdrant API key set
- [x] Database password in `.env` (never committed)
- [x] Encrypted daily backups with 30-day retention
- [x] Automatic security updates enabled
- [ ] Monthly: review `fail2ban-client status sshd`
- [ ] Monthly: `docker compose pull` for image updates
- [ ] Quarterly: rotate Tailscale auth key

---

# 20. Phased Rollout Plan

## Phase 1 — Foundation (Week 1–2)
- [x] Provision Cloud VPS
- [ ] Harden server (Section 1.2)
- [ ] Install Docker (Section 2)
- [ ] Deploy Postgres + Planka via docker-compose
- [ ] Set up Tailscale and verify access
- [ ] Create Telegram bot, verify polling works
- [ ] Basic `/start` and `/health` commands working

## Phase 2 — Intelligence (Week 3–4)
- [ ] Deploy Ollama + pull llama3.1:8b
- [ ] Implement LLM service (chat, summarize)
- [ ] Connect freetext Telegram messages → LLM
- [ ] Deploy Qdrant + implement memory system
- [ ] `/memory` and `/add` commands working

## Phase 3 — Google Integration (Week 5–6)
- [ ] Set up Google Cloud project + OAuth
- [ ] Implement email polling service (via Gmail API or web services)
- [ ] Create email rules engine
- [ ] First-time OAuth token generation (via SSH tunnel)
- [ ] Verify urgent email notifications via Telegram

## Phase 4 — Automation (Week 7–8)
- [ ] Morning briefing (APScheduler + LLM)
- [ ] Weekly review
- [ ] Career framing engine
- [ ] `/tree`, `/review`, `/weekly`, `/daily` commands
- [ ] Planka board structure + AI-driven card creation

## Phase 5 — Hardening (Ongoing)
- [ ] Automated backup cron
- [ ] Monitoring (simple: health endpoint + uptime check)
- [ ] Performance tuning (Ollama context window, Qdrant indexing)
- [ ] Extend email rules via Telegram chat

## Phase 6 — Self-Hosted Git (Future)
- [ ] Migrate repo from Bitbucket → GitHub (private repo, interim step)
- [ ] Add Gitea (or Forgejo) as a Docker container to the stack
- [ ] Configure behind Tailscale VPN (no public access)
- [ ] Mirror or move repo from GitHub → self-hosted Gitea
- [ ] Set up automated backups for Git data
- [ ] Optional: CI/CD via Gitea Actions or Woodpecker CI

> **Why**: Full data sovereignty means your code lives on your server too —
> not on Microsoft (GitHub) or Atlassian (Bitbucket). Gitea is lightweight
> (~100 MB RAM), has a full web UI, and runs as a single container.

# 21. Why This Architecture

This system is a custom-built, privacy-first AI assistant. Here is why this
architecture was chosen over framework-based alternatives (e.g., OpenClaw):

## 22.1 True Local AI — Zero API Costs

The LLM (Llama 3.1 via Ollama) runs **100% on the server**. No API keys,
no per-token billing, no cloud dependency. Framework-based assistants that
rely on cloud LLMs incur recurring API costs that
can reach $20–50/month with daily use. This system costs **$0 for AI — forever.**

Total monthly cost: **~$15–20 all-in** (server only). No hidden costs.

## 22.2 Semantic Memory (Qdrant Vector DB)

Memories are stored as high-dimensional vectors via Qdrant + `all-MiniLM-L6-v2`.
This enables **semantic search** — finding related memories by meaning, not just
keywords. Alternatives that store memory as flat Markdown or YAML files rely on
basic text matching, which breaks down at scale (500+ entries). Vector search
scales to tens of thousands of memories with sub-second response times.

## 22.3 Network-Level Security (Zero Public Ports)

All services sit behind **Tailscale VPN**. The server exposes **zero public ports**
for application traffic — Planka, the API, Qdrant, Ollama, and Postgres are all
invisible to the internet. Combined with SSH-key-only access, Fail2Ban, and
UFW firewall rules, this is a multi-layered defense that framework-based
alternatives typically do not provide. Frameworks that enforce security at the
application/gateway layer alone are vulnerable if that layer is compromised.

## 22.4 Complete Data Sovereignty

Every piece of data — conversations, memories, email summaries, tasks, preferences —
stays on hardware you control. No data is sent to third-party AI providers, no
conversation logs on someone else's servers, no dependency on external memory
services. The embedding model runs locally (80 MB). The LLM runs locally (~5 GB).
Email access is **read-only** (cannot send, delete, or modify, though write support might be added later). This is not
"privacy-friendly" — it is **privacy by architecture**.

## 22.5 Integrated Task Management (Planka)

Planka is a **self-hosted Kanban board** with a visual list-and-card interface that runs as a Docker
container on the same server. It is accessible as a PWA on your phone — no app
store, no cloud account, no data leaving your network. Alternatives that
suggest Notion or file-based task management add another cloud dependency
or sacrifice visual/interactive task management entirely.

## 22.6 Full Stack Ownership

Every component is understood, configured, and maintained by you. There is no
framework abstraction hiding how messages are routed, how memory is stored, or
how the LLM is called. This means:

- **No framework lock-in** — swap any component without migrating an entire ecosystem
- **No update surprises** — you control when and what gets updated
- **Full debuggability** — every line of code is yours to inspect and modify
- **Custom behavior** — the system does exactly what you need, nothing more

The trade-off is higher initial setup effort. But once running, this system is
simpler to operate than a framework with dozens of abstraction layers.

---

> **Philosophy**: Build iteratively. Stability over complexity. Every feature
> must work reliably before the next one begins. This is your personal
> infrastructure — treat it like a production system.
