# OpenZero
## Open source. Zero Trust. Fully private agent operator OS.
> A self-hosted AI agent operator built on the principle of absolute data sovereignty.
>
> OpenZero is a **Personal AI Operating System** built for absolute data sovereignty. It serves as an autonomous assistant that synchronizes your projects, relationships, and digital communications within a private, self-hosted infrastructure. By automating task lifecycle management, cross-referencing social calendars, and transcribing voice notes into actionable tickets, Z reduces the cognitive overhead of daily organization. Every morning, the system delivers a **Multi-Modal Briefing**—available via text and local voice note—summarizing your priority communications, family commitments, and project milestones. You maintain oversight through a dedicated visual dashboard and mobile Kanban app, all secured within a **Zero-Trust network**.

## Built for Privacy & Openness

This is a **Personal AI Operating System** — a system that runs 24/7 on a remote server and acts as your second brain.

Most AI assistants force a trade-off: you get convenience, but you surrender your private conversations, schedule, and emails to corporate servers. **OpenZero rejects that trade-off.**

- **Privacy-First (Hybrid AI):** By default, the system runs 100% locally via Ollama (Llama 3.1 8B). For complex missions, you can optionally trigger "Deep Thinking" models (like Groq or OpenAI). Every automated task stays local. You choose exactly when and what data is shared.
- **Voice Support**: Z understands voice messages. Record a thought or command while walking; Z transcribes it locally (or via high-privacy Cloud APIs) and acts on it immediately.
- **Inner Circle (Social Focus)**: Manage routines for both **Family** (care focus) and **Friends** (social focus). Z tracks schedules, hobbies, and birthdays, proactively suggesting connection points in your morning briefing.
- **Multi-Modal Briefings**: Z doesn't just text you; it can send a high-quality **Local TTS voice note** of your daily briefing, allowing you to consume your briefing hands-free.
- **Contextual Automation**: Z scans your synced social calendars for priority events (birthdays, deadlines) and automatically stages tasks in your Planka board for you.
- **Visual Control Center**: A dedicated web dashboard built with Vanilla TypeScript & Web Components to visualize your project tree, search semantic memories, manage email rules, and view briefing history.
- **Zero-Trust Security:** The entire stack is sealed behind a Tailscale VPN. There are absolutely no public-facing ports.

1. **Messenger App** *(e.g. Telegram)* — Chat with your AI via your phone or laptop. Send it commands, ask it questions, or just talk to it in plain text.
2. **Visual Control Center** — A dedicated web dashboard to visualize your project tree, search memory, and manage configurations.
3. **Planka (Kanban Board)** ([planka.app](https://planka.app/)) — A visual board for your projects and tasks, accessible as an app on your phone.

The AI connects the dots between your email, your calendar, your tasks, and your personal memory to help you stay organized and make better decisions.

---

## Messenger Commands

All interaction with OpenZero happens via your messenger bot. Commands are designed to give you instant control over your server's "Intelligence" layer.

| Command | Action | Management Value |
|:---|:---|:---|
| `/daily` | **Inbox & Goal Triage** | Z filters 100+ unread emails, summarizes only the relevant ones, and cross-references your calendar to block out "Deep Work" time. |
| `/weekly` | **Strategic Review** | Z audits your Planka boards and identifies "stagnant" projects. It acts as a project manager, suggesting the specific micro-tasks needed to get things moving again. |
| `/tree` | **Mental Offloading** | View your entire life hierarchy at once. Z pulls progress from your tasks, so you can stop keeping "mental tabs" on your various goals and domains. |
| `/think` | **Complex Reasoning** | **[High-Privacy Workflow]**: Z uses a local model to scan your data for relevant context → presents you with a "Disclosure Proposal" → waits for your click → sends to a Cloud LLM (Groq/OpenAI) for high-precision reasoning. |
| `/add` | **Instant Note-Taking** | Offload thoughts the moment they occur. Z stores them in semantic memory so you never lose an insight or a meeting detail again. |
| `/memory` | **Context Retrieval** | Forget keywords. Search for "that conversation about the server" and Z retrieves the exact note based on meaning and content. |
| `/start` | **System Status** | Pings the system to ensure your 24/7 assistant is online and connected to all data streams. |
| *any text* | **Local Deliberation** | Brainstorm privately. Draft professional emails, plan critical conversations, or work through complex problems. |

---

## How I Use It

### Reducing Operational Friction
- **The Morning Filter**: I wake up to a message from Z. Instead of seeing an inbox full of 40 emails from newsletters and Jira notifications, I see: *"You have 3 actual emails: a client feedback, a tax notice, and a school update. I've already drafted a reply for the feedback based on your memory."*
- **Inner Circle Care**: Z adds a specific section to my briefing: *"Leo has science homework due on Thursday. Propose to work on his robot hobby together tonight at 18:00?"* This keeps me connected to my family even during busy weeks.
- **Voice Offloading**: While walking, I send a voice note: *"The roof leak is fixed, invoice was $400."* Z automatically transcribes it locally, moves the "Fix roof" ticket to **Done** in Planka, and stores the price note in **Memory**.
- **Social Calendar Sync**: Z sees that my friend Sarah has "Moving House" on her calendar next Saturday. In my morning briefing, it suggests: *"Sarah is moving next week—maybe ask if she needs help or a lunch delivery?"*
- **Contextual Automation**: Z detected "Property Tax Due" on my spouse's calendar and automatically created a priority ticket in our **Family Inbox** with a 3-day reminder.

> **Deep Thinking (Decision Support):**
> When I need to make a hard choice (e.g., "Should I accept this job offer?"), I type `/think [details]`.
> 1. **Discovery (Local):** Z pulls my "About Me" requirements, my career board, and past notes on salary preferences.
> 2. **Disclosure (Local):** Z shows me: *"I will share your 'Career Goals' and 2 salary notes with Groq. Okay?"*
> 3. **Execution (Cloud):** Only now does the request leave your server to get the high-power reasoning you need.

### Task Management (Kanban)
- I open **[Planka](https://planka.app/)** on my phone (it's saved to my home screen as an app) and move cards around — a private and self-hosted visual board.
- **Why a Kanban Board?** Real-world execution requires visual mapping. The board gives a centralized overview of all moving pieces, preventing projects from slipping through the cracks. It includes `Inbox`, `Active`, `Blocked`, and `Done` columns for each life domain.
- The AI can also create tasks for me. If an urgent email comes in, it automatically pushes a notification and can add a card to the right board.

### Email Intelligence
- Every 10 minutes, the system checks my email (via Gmail API or other mail client API, read-only, it cannot send or delete anything).
- **Rule-based Actions & Filters:** You can create custom rules and filters to handle large sets of emails all at once—so if an email matches (e.g., from my kid's school), it immediately pings me on my Messenger App or gets archived.
- **Auto-Tagging & Badging:** Z can automatically apply custom named badges to specific incoming emails based on your rules, making it incredibly easy to recall or recover them later via chat.
- All other emails are summarized and bundled into the morning briefing.

### Calendar Intelligence & Auto-Timezone
- Z integrates securely with your Calendar APIs. You can grant read-only access for Z to proactively learn about your schedule, or optionally grant read-write access so Z can create dates and change events for you.
- **Context-Aware Briefings:** Z parses your calendar before your daily briefing so it can mentally prepare you for the day ahead, warning you if you have back-to-back blocks or early commitments.
- **Dynamic Timezone Scaling:** Instead of statically setting a single timezone string (e.g. `Europe/Berlin`), you can configure the timezone as `auto`. The system automatically parses your calendar events to deduce where you are—or where you *will be*—and adjusts scheduled background tasks (like Morning Briefings) so you always wake up to them at the correct local time.

### Weekly Reviews
- Every Sunday at 10:00, the AI sends me a structured weekly review via messenger: what went well, what's stuck, and what to focus on next week.
- **Project Stagnation Warnings:** As part of the review, the AI inherently flags projects that haven't moved. If there are many stagnant projects, it lists them explicitly to help me refocus.
- I can also trigger it anytime with `/weekly`.

---

## Tech Stack

| Component | Technology | Purpose |
|:---|:---|:---|
| **Server** | Cloud VPS Provider | e.g. 8 vCPU, 24 GB RAM, 200 GB NVMe |
| **OS** | Ubuntu 24.04 LTS | Stable, secure Linux foundation |
| **Backend** | [Python](https://www.python.org/) / [FastAPI](https://fastapi.tiangolo.com/) | Async API server, coordinates all services |
| **Local AI** | [Ollama](https://ollama.com/) + [Llama 3.1](https://ai.meta.com/llama/) (8B) | Runs 100% on the server for all automated tasks |
| **Cloud AI** (Opt) | [Groq](https://groq.com/) / [OpenAI](https://openai.com/) | Optional high-power reasoning via `/think` command |
| **Database** | [PostgreSQL 16](https://www.postgresql.org/) | Projects, preferences, email rules, conversations |
| **Vector Memory** | [Qdrant](https://qdrant.tech/) | Semantic search over your memories and notes |
| **Embeddings** | [sentence-transformers](https://sbert.net/) | `all-MiniLM-L6-v2` — runs locally, 80 MB |
| **Task Board** | [Planka](https://planka.app/) | Self-hosted Kanban board, accessible as PWA |
| **Voice STT** | [Whisper](https://openai.com/research/whisper) | Local container for speech-to-text transcription |
| **Voice TTS** | [OpenedAI Speech](https://github.com/moshloop/openedai-speech) | Local container for high-quality audio briefings |
| **Chat Interface** | Messenger Bot | Primary UI — available on phone, desktop, web |
| **Scheduler** | [APScheduler](https://apscheduler.readthedocs.io/) | Morning briefings, weekly reviews, email polling |
| **VPN** | [Tailscale](https://tailscale.com/) | Zero-trust private network — no public ports |
| **Containers** | [Docker Compose](https://docs.docker.com/compose/) | Everything runs in isolated containers |

### Architecture Diagram

```
┌─────────────────────────────────────────────┐
│              Your Devices                    │
│  (Phone / Laptop / Tablet)                   │
│                                              │
│  Messenger App ──── Chat with AI             │
│  Planka PWA  ──── Kanban Board               │
└──────────────┬───────────────────────────────┘
               │  Tailscale VPN (encrypted)
               ▼
┌─────────────────────────────────────────────┐
│               VPS Provider                   │
│                                              │
│  ┌─────────────────────────────────────┐     │
│  │  FastAPI Backend                    │     │
│  │    ├── Messenger Bot (polling)      │     │
│  │    ├── APScheduler (cron jobs)      │     │
│  │    └── LLM Client → Ollama         │     │
│  └─────────────────────────────────────┘     │
│                                              │
│  ┌──────────┐  ┌────────┐  ┌──────────┐     │
│  │ Postgres │  │ Qdrant │  │  Ollama  │     │
│  │ (data)   │  │(memory)│  │  (AI)    │     │
│  └──────────┘  └────────┘  └──────────┘     │
│                                              │
│  ┌──────────┐  ┌────────┐                   │
│  │ Whisper  │  │  TTS   │ ← Voice Engines    │
│  │ (STT)    │  │ (Audio)│                   │
│  └──────────┘  └────────┘                   │
│                                              │
│  ┌──────────┐                                │
│  │  Planka  │ ← Kanban board                 │
│  └──────────┘                                │
│                                              │
│  External APIs:                              │
│    → Email API (read-only, polling 10 min)   │
│    → Calendar APIs (optional read-write)     │
└─────────────────────────────────────────────┘
```

---

## [Planka](https://planka.app/) — Mobile App Access

[Planka](https://planka.app/) is a **Progressive Web App (PWA)**. This means you don't need to download anything from the App Store or Play Store. You simply open it in your browser and "install" it to your home screen.

### How to add Planka to your phone:

**iPhone (Safari):**
1. Connect to Tailscale on your phone
2. Open Safari and go to `http://YOUR_TAILSCALE_IP:1337` *(Port 1337 is the default port the Planka Docker container runs on)*
3. Tap the **Share** button (square with arrow)
4. Tap **"Add to Home Screen"**
5. Name it "Planka" → Tap **Add**

**Android (Chrome):**
1. Connect to Tailscale on your phone
2. Open Chrome and go to `http://YOUR_TAILSCALE_IP:1337` *(Port 1337 is the default port for Planka)*
3. Tap the **⋮ menu** (three dots, top right)
4. Tap **"Add to Home screen"** or **"Install app"**
5. Name it "Planka" → Tap **Add**

Once added, it opens as a **full-screen app** without the browser bar. It looks and feels like a native app.

> **Note**: You must be connected to your **Tailscale VPN** to access Planka, because the server has no public ports open. This is a security feature, not a limitation.

---

## Security & Privacy

This system is designed with a **privacy-first** approach:

- **No public ports** — all services are behind Tailscale VPN
- **Local AI** — Llama 3.1 runs on your server, not in the cloud
- **Email access is read-only** — the system reads your email via API but cannot send, delete, or modify anything (write capabilities might be added later)
- **Calendar control** — optionally grant read-write access so Z can create and manage events for you
- **SSH keys only** — password login is disabled
- **Fail2Ban** — brute-force protection on SSH
- **Human-in-the-Loop (HITL) Approval** — Z asks for your consent before sharing any context with Cloud LLMs (while using /think)
- **Encrypted backups** — daily, with 30-day retention
- **Messenger restricted** — the bot only responds to your user ID

Even if someone found your server's IP address, they would see zero open ports (except SSH). All services are invisible to the internet.

---

## Extending the System

This system is designed to grow with you. Here are some ideas:

### Add More Messenger Commands
Add new command handlers in `backend/app/api/messenger.py`. Register them in the `start_messenger_bot()` function.

### Add More Email Rules
Send a message to your bot or insert directly into the `email_rules` database table. Future versions could support `/addrule sender@example.com urgent` via your messenger.

### Add New Scheduled Jobs
Edit `backend/app/tasks/scheduler.py` to add new APScheduler jobs. Examples:
- Daily exercise reminder
- Bill payment alerts

### Connect More APIs
The FastAPI backend can integrate with any API. Ideas:
- **Todoist / Notion** — sync tasks
- **Spotify** — "what did I listen to this week" in the weekly review
- **Weather API** — include weather in the morning briefing
- **Bank API** — financial status in the weekly review

### Upgrade the AI Model
If you upgrade the VPS or add a GPU:
- Switch from `llama3.1:8b` to `llama3.1:70b` for deeper reasoning
- Or try `mistral`, `phi-3`, `gemma` — Ollama supports 100+ models
- Simply run: `docker compose exec ollama ollama pull <model_name>`

---

## Monthly Cost

| Item | Cost |
|:---|:---|
| Cloud VPS Provider | ~$15–20/month |
| Tailscale | Free (personal use) |
| Planka | Free (open source) |
| Ollama + Llama 3.1 | Free (open source) |
| Messenger Bot | Free |
| Gmail API or other mail client API | Free |
| **Total** | **~$15–20/month** |

---

## File Structure

```
openzero/
├── src/                # Core implementation
│   ├── backend/        # FastAPI, SQLAlchemy, APScheduler
│   └── dashboard/      # Vanilla TS Web Components dashboard
├── docs/               # Architecture guides & prompt specs
├── scripts/            # Deployment & backup tools
├── personal/           # GITIGNORED — your private data
├── docker-compose.yml  # Service orchestration
├── .env.example        # Backend secrets template
├── .env.planka.example # Planka secrets template
├── BUILD.md            # Human-readable build guide
└── README.md           # This file
```

---

## Getting Started

See **[docs/build-plan.md](./docs/build-plan.md)** for the complete, step-by-step implementation guide — from server provisioning to the final deployment.

---

*Built with privacy in mind. Powered by open-source software. Runs on your terms.*
