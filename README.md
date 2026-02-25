# openZero

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![Self-Hosted](https://img.shields.io/badge/Deployment-Self--Hosted-blue.svg)](./BUILD.md)
[![Privacy First](https://img.shields.io/badge/Privacy-100%25_Local-purple.svg)](#security--privacy)

## Open source. Zero Trust. Fully private agent operator OS.
> A self-hosted AI agent operator built on the principle of absolute data sovereignty.
>
> openZero is a **Personal AI Operating System** built for absolute data sovereignty. It serves as an autonomous assistant that synchronizes your projects, relationships, and digital communications within a private, self-hosted infrastructure. By automating task lifecycle management, cross-referencing social calendars, and transcribing voice notes into actionable tickets, Z reduces the cognitive overhead of daily organization. Every morning, the system delivers a **Multi-Modal Briefing**—available via text and local voice note—summarizing your priority communications, family commitments, and project milestones. You maintain oversight through a dedicated visual dashboard and mobile Kanban app, all secured within a **Zero-Trust network**.

## Built for Privacy & Openness

This is a **Personal AI Operating System** — a system that runs 24/7 on a remote server and acts as your second brain.

Most AI assistants force a trade-off: you get convenience, but you surrender your private conversations, schedule, and emails to corporate servers. **openZero rejects that trade-off.**

The local AI connects the dots between your email, your calendar, your tasks, and your personal memory to help you stay organized and make better decisions.

- **Operator board (The Hub)**: A central "Mission Control" board that automatically pulls high-priority tasks (marked with `!!` or `!`) from all other project boards. It identifies what matters *today*, so you don't have to go looking for it.
- **Unified Master Calendar**: Z integrates with a single primary calendar for total clarity. Instead of managing multiple calendars, Z identifies family routines, work commits, and social milestones on one unified timeline, cross-referencing them to protect your focus. **Pro-tip:** Add shared family or team calendars to your primary account; Z can automatically coordinate between them, identifying bottlenecks and optimizing your collaborative schedule.
- **Privacy-First Intelligence**: By default, the system runs locally via Ollama. Use the smart **Llama 3.1 8B** for deep reasoning, or toggle to the lightning-fast **Llama 3.2 3B** for instant CPU responses. For absolute edge cases, trigger "Deep Thinking" cloud models with one click but you always choose exactly what data is shared and need to approve it beforehand.
- **Voice & Text Freedom**: Z fluidly understands text and voice messages. Record a spoken thought while walking; Z transcribes it locally via Whisper, and updates your boards or memory immediately.
- **Multi-Modal Briefings**: Receive a hands-free morning briefing. Z can send a high-quality local TTS voice note summarizing your upcoming commits and priority tasks.
- **openZero Dashboard**: A visual interface to monitor your project tree, search semantic memory, and interact with Z in real-time.
- **Messenger App**: (e.g., Telegram) Your mobile cockpit. Send commands, draft emails, and offload thoughts via plain text or voice.
- **Planka (Self-Hosted Kanban)**: The visual engine for your journey. Accessible as a secure mobile PWA.
- **Zero-Trust Security:** The entire stack is sealed behind a Tailscale VPN. There are absolutely no public-facing ports.

### Core Intelligence: Memory Depth, Recall & Semantic Grounding

openZero is designed with native "Long-Term Retention" logic to ensure Z never asks the same question twice and maintains total context over long-running missions. This is powered by a sophisticated **Retrieval-Augmented Generation (RAG)** pipeline:

- **Ultra Fast Memory (L3 Context)**: With a **10-message active window** and **Context Compression**, Z maintains sharp thread continuity while ensuring lightning-fast local inference.
- **LLM Pre-Warming**: The system proactively loads the LLM weights into memory as you prepare to type, eliminating "first-message lag."
- **Semantic Chunking**: Your notes and emails are broken into meaningful fragments and transformed into high-dimensional vectors using local embedding models.
- **Vector Space (Qdrant)**: These vectors are stored in a private Qdrant instance. When you ask a question, Z calculates the "semantic distance" between your request and every memory you've ever recorded—finding matches based on *meaning*, not just keywords.
- **Precision Context Injection**: The most relevant memories are injected directly into the LLM's prompt at inference time, ensuring advice is always grounded in your actual history.
- **Ultra Deep Recall**: Using **Multi-Query Semantic Retrieval**, Z extracts key entities from every message to perform parallel searches across your personal database.
- **Autonomous Learning**: Every interaction, decision, and fact shared is automatically stored in your semantic vault via **Continuous Background Archiving**. 
- **Proactive Knowledge Rule**: Z treats your "Circle of Trust" (People, Relationships, Birthdays) as absolute truth.

> **Performance Note**: While **Autonomous Learning** ensures a perfectly synchronized second brain, increasing the complexity of background reasoning (e.g., recursive self-summarization or deeper multi-step memory searches) will increase the CPU response time for local LLMs.

---

## Chat & Commands

All interaction with openZero happens via your messenger bot or directly through the built-in **openZero Dashboard** chat interface. Commands are designed to give you instant control over your server's "Intelligence" layer.

| Command | Action | Management Value |
|:---|:---|:---|
| `/help` | **Quick Manual** | Shows the primary command matrix and usage tips. |
| `/day` | **Inbox & Goal Triage** | Z filters 100+ unread emails, summarizes only the relevant ones, and cross-references your calendar to block out "Deep Work" time. |
| `/week` | **Strategic Review** | Z audits your Planka boards and identifies "stagnant" projects. It acts as a project manager, suggesting the specific micro-tasks needed to get things moving again. |
| `/month` | **Monthly Overview** | High-level 30-day review of tree state and project progress, ensuring momentum is maintained. |
| `/year` | **Yearly Goal Setting** | Analyzes overarching themes and proposes 3 major goals for long-term objectives based on current open projects. |
| `/tree` | **Mental Offloading** | View your entire life hierarchy at once. Z pulls progress from your tasks, so you can stop keeping "mental tabs" on your various goals and domains. |
| `/think` | **Complex Reasoning** | **[High-Privacy Workflow]**: Z uses a local model to scan your data for relevant context → presents you with a "Disclosure Proposal" → waits for your click → sends to a Cloud LLM (Groq/OpenAI) for high-precision reasoning. |
| `/add` | **Instant Note-Taking** | Offload thoughts the moment they occur. Z stores them in semantic memory so you never lose an insight or a meeting detail again. |
| `/memory` | **Context Retrieval** | Powered by Qdrant vector database, this is profoundly more powerful than writing notes on Post-its, standard to-do lists, or SimpleNote. It uses semantic search technology—meaning you don't search by exact keywords, but by the *concept*. Search for "that conversation about the server" and the AI understands the context, instantly retrieving details that would normally be lost in physical notebooks or flat symptom lists. |
| `/start` | **System Status** | Pings the system to ensure your 24/7 assistant is online and connected to all data streams. |
| *any text* | **Local Deliberation** | Brainstorm privately. Draft professional emails, plan critical conversations, or work through complex problems. |


---

## How I Use It

### Reducing Operational Friction
- **The Morning Filter**: I wake up to a message from Z. Instead of seeing an inbox full of 40 emails from newsletters and Jira notifications, I see: *"You have 3 actual emails: a client feedback, a tax notice, and a school update. I've already drafted a reply for the feedback based on your memory."*
- **Inner Circle Care**: Z adds a specific section to my briefing: *"Leo has science homework due on Thursday. Propose to work on his robot hobby together tonight at 18:00?"* This keeps me connected to my family even during busy weeks.
- **Voice Offloading**: While walking, I send a voice note: *"The roof leak is fixed, invoice was $400."* Z automatically transcribes it locally, moves the "Fix roof" ticket to **Done** in Planka, and stores the price note in **Memory**.
- **Unified Social Sync**: Z sees that you added "Sarah - Moving House" to your master calendar. In your briefing, it suggests: *"Sarah is moving next week—maybe send a quick note to see if she needs a hand?"*
- **Operator Logic**: Z detected "Property Tax Due" on your calendar. It automatically created a priority ticket with `!!` in the title, which was instantly lifted from your **Family Board** into the **Today** column of your **Operator Board**.
- **Contextual Scheduling**: Z suggests blocking out 2 hours for task execution; if approved, it writes a synchronized reminder block back onto your calendar so your phone's default apps keep you on track.

### Task Management (Kanban)
- I open **[Planka](https://planka.app/)** on my phone (it's saved to my home screen as an app) and move cards around — a private and self-hosted visual board.
- **Why a Kanban Board?** Real-world execution requires visual mapping. The board gives a centralized overview of all moving pieces, preventing projects from slipping through the cracks. While it defaults to `Inbox`, `Active`, `Blocked`, and `Done` columns, **Z can intelligently restructure or create completely new projects with custom columns** designed specifically for the workflow at hand (e.g., `Backlog`, `In Review`, `Publish`).
- **Dynamic Task Population**: The AI doesn't just create single tasks; it can populate an entire board with tickets extracted from your semantic memory, pulling from notes you've taken or thoughts you've recently shared, ensuring nothing on your mind slips into the void. If an urgent email comes in, it automatically pushes a notification and adds a structured card to the appropriate board.

> **Deep Thinking (Decision Support):**
> When I need to make a hard choice (e.g., "Should I accept this job offer?"), I type `/think [details]`.
> 1. **Discovery (Local):** Z pulls my "About Me" requirements, my career board, and past notes on salary preferences.
> 2. **Disclosure (Local):** Z shows me: *"I will share your 'Career Goals' and 2 salary notes with Groq. Okay?"*
> 3. **Execution (Cloud):** Only now does the request leave your server to get the high-power reasoning you need.


### Email Intelligence
- Every 10 minutes, the system checks my email (via Gmail API or other mail client API). Note: Z can read your inbox and create **draft replies**, but it cannot send or delete anything without your manual interaction.
- **Rule-based Actions & Filters:** You can create custom rules and filters to handle large sets of emails all at once—so if an email matches (e.g., from my kid's school), it immediately pings me on my Messenger App or gets archived.
- **Auto-Tagging & Badging:** Z can automatically apply custom named badges to specific incoming emails based on your rules, making it incredibly easy to recall or recover them later via chat.
- All other emails are summarized and bundled into the morning briefing.

### Calendar Intelligence & Auto-Timezone
- Z integrates securely with your Calendar APIs, serving as your single source of truth. Since we avoid juggling other people's calendars, you just manage your inner circle's events on this single calendar.
- **Zero-Trust (Local Calendar):** If you prefer not to connect to Google or other external services, Z includes a high-performance **Local Calendar**. This is a **Zero-Trust** implementation: all events are stored in your private Postgres instance and are strictly accessible only via your Tailscale VPN. No metadata or schedule patterns are ever shared with third-party providers.
- **Unified Interaction Matrix:** Highlights include an **Interactive Month Matrix** and **Day-Cell Interaction**, allowing you to schedule events directly from the visual grid.
- **Deep Integration:** Optionally grant read-write access for Z to manage events and sync your schedule across your devices. Z can dynamically create task-blocks and auto-schedule actionable steps.
- **Context-Aware Briefings:** Z parses your calendar before your daily briefing so it can mentally prepare you for the day ahead, warning you if you have back-to-back blocks or early commitments.
- **Dynamic Timezone Scaling:** Instead of statically setting a single timezone string (e.g. `Europe/Berlin`), you can configure the timezone as `auto`. The system automatically parses your calendar events to deduce where you are—or where you *will be*—and adjusts scheduled background tasks (like Morning Briefings) so you always wake up to them at the correct local time.

### Weekly Reviews
- Every Sunday at 10:00, the AI sends me a structured weekly review via messenger: what went well, what's stuck, and what to focus on next week.
- **Project Stagnation Warnings:** As part of the review, the AI inherently flags projects that haven't moved. If there are many stagnant projects, it lists them explicitly to help me refocus.
- I can also trigger it anytime with `/weekly`.

> **Pro-Tip**: Use **Google Shared Calendars** to sync family or project schedules. Z can see these if they are added to your primary account, making it a powerful coordinator for shared lives.

---

## Tech Stack

| Component | Technology | Purpose |
|:---|:---|:---|
| **Server** | Cloud VPS Provider | e.g. 8 vCPU, 24 GB RAM, 200 GB NVMe |
| **OS** | Ubuntu 24.04 LTS | Stable, secure Linux foundation |
| **Backend** | [Python](https://www.python.org/) / [FastAPI](https://fastapi.tiangolo.com/) | Async API server, coordinates all services |
| **Local AI** | [Ollama](https://ollama.com/) | **Llama 3.1 8B (Smart)** or **Llama 3.2 3B (Fast)** |
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

---

## Pro Tip: Getting started with Z

The better Z understands your context, values, and mission, the better it can support you.

- **Introduce Yourself**: Start by telling Z what is important to you. Share your long-term mission, your core values, and what keeps you up at night. Z will store this in its semantic memory to inform future decisions.
- **Set the Stage**: Ask Z to ask you specific questions to build your profile. For example: "Z, I want you to act as my chief of staff. Ask me 10 questions to understand my current priorities and how I make decisions."
- **Context is King**: The more you share about your high-priority projects and relationships, the more effectively Z can triage your emails and cross-reference your calendar for high-impact consultancy empowering you to make better decisions.

---

### Architecture Diagram

```
┌─────────────────────────────────────────────┐
│							 Your Devices										 │
│	 (Phone / Laptop / Tablet)									 │
│																							 │
│	 Messenger App ──── Chat with AI						 │
│	 Planka PWA	 ──── Kanban Board							 │
└──────────────┬───────────────────────────────┘
							 │	Tailscale VPN (encrypted)
							 ▼
┌─────────────────────────────────────────────┐
│								VPS Provider									 │
│																							 │
│	 ┌─────────────────────────────────────┐		 │
│	 │	FastAPI Backend										 │		 │
│	 │		├── Messenger Bot (polling)			 │		 │
│	 │		├── APScheduler (cron jobs)			 │		 │
│	 │		└── LLM Client → Ollama					│			│
│	 └─────────────────────────────────────┘		 │
│																							 │
│	 ┌──────────┐	 ┌────────┐	 ┌──────────┐			│
│	 │ Postgres │	 │ Qdrant │	 │	Ollama	│			│
│	 │ (data)		│	 │(memory)│	 │	(AI)		│			│
│	 └──────────┘	 └────────┘	 └──────────┘			│
│																							 │
│	 ┌──────────┐	 ┌────────┐										│
│	 │ Whisper	│	 │	TTS		│ ← Voice Engines		 │
│	 │ (STT)		│	 │ (Audio)│										│
│	 └──────────┘	 └────────┘										│
│																							 │
│	 ┌──────────┐																 │
│	 │	Planka	│ ← Kanban board								 │
│	 └──────────┘																 │
│																							 │
│	 External APIs:															 │
│		 → Email API (read-only, polling 10 min)	 │
│		 → Calendar APIs (optional read-write)		 │
└─────────────────────────────────────────────┘
```

---

## Execution Modes

openZero is designed to run in two distinct environments, optimized for either rapid creation or stable operation.

### Local Development Mode (`./scripts/dev.sh`)
This is the **"God Mode" workspace** used for building and testing. It provides a hybrid environment where the infrastructure is stable but the application is alive.
- **Instant Updates**: Code changes are injected live without restarting containers.
- **Hybrid Architecture**: Core databases (Postgres, Qdrant) and AI engines (Ollama) run in Docker, while the application logic (Python/FastAPI) and Dashboard run directly on your host machine. Configure to use Ollama 3.2 3B for fast response on older machines.
- **Transparent Access**: Ports are exposed to `localhost` so you can inspect databases and logs with ease.

### Production Mode (`docker compose up -d`)
This is the **"Final OS"** designed to run 24/7 on a server or home lab.
- **Immutable & Clean**: The entire stack is "baked" into Docker images. You don't even need Python or Node installed on the machine.
- **Hardened Security**: All services are sealed inside a private virtual network. Only the main entry points are exposed.
- **Set & Forget**: Designed for zero-maintenance stability.

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

## Cloud Deployment (Managed by AI)

If you use a Cloud VPS, you can have the AI automate the entire deployment process.

### Step 1: Provision your VPS
- **OS**: Ubuntu 24.04 LTS
- **RAM**: 24 GB+ (Recommended for local LLM performance)

> **Pro-Tip**: You don't *need* a VPS. For maximum privacy and zero monthly cost, you can run openZero on a local machine (e.g., Mac Mini, old laptop, or home server) and use Tailscale to access it securely from anywhere in the world.

### Step 2: Connection & Setup
1. Provide the AI with your **Server IP** and **Root Password**.
2. The AI will:
	 - Perform initial server hardening (Security updates, firewall setup).
	 - Install **Docker** & **Tailscale** official engines.
	 - Create a dedicated system user named `openzero`.
	 - Setup SSH key-only access (Disabling insecure password logins).
	 - Sync your code and environment secrets to the server.
	 - Start all services using `docker compose`.

### Step 3: Secure Your Access (Tailscale)
Once the setup is complete, you need to manually link your server to your Tailscale network to access the private ports:
1. SSH into your server: `ssh openzero@YOUR_IP`
2. Run: `sudo tailscale up`
3. Authenticate via the link provided in the terminal.

### Step 4: Stop Local Development
To avoid Telegram bot conflicts, ensure you have stopped any local instances of `dev.sh` before the cloud bot takes over control.

---

## Security & Privacy

This system is designed with a privacy-first approach:
- **100% Privacy by Design:** Everything you share with Z stays on your server. No cloud data harvesting.
- **Local AI — Llama runs on your server, not in the cloud.**
- **Multi-Service OS:** Includes a Task Board (Planka), Vector Memory (Qdrant), and a Secure Proxy (Nginx).
- **No public ports** — all services are behind Tailscale VPN
- **Drafting Engine (Not Sending):** The system interacts with your email via API to read and **create proposed replies in your Drafts folder**. This allows Z to prepare your communications while keeping you in total control—nothing is sent until you manually review and click 'Send' in your mail client.
- **Zero-Trust (Local Calendar):** All events are stored in your private Postgres instance and are strictly accessible only via your Tailscale VPN. No metadata or schedule patterns are ever shared with third-party providers.
- **Operator Board (Mission Control):** A central priority hub that you control; Z only suggests and organizes, you execute.
- **SSH keys only** — password login is disabled
- **Fail2Ban** — brute-force protection on SSH
- **Human-in-the-Loop (HITL) Approval** — Z asks for your consent before sharing any context with Cloud LLMs (while using /think)
- **Encrypted backups** — daily, with 30-day retention
- **Messenger restricted** — the bot only responds to your user ID

Even if someone found your server's IP address, they would see zero open ports (except SSH). All services are invisible to the internet.

---

## Backups & Migrations

openZero stores data exclusively within isolated Docker volumes or bound databases, making backups and migrations transparent and fully under your physical control.

### How Data Storage Works
- **PostgreSQL (`openzero_pgdata`)**: Contains your project trees, Inner Circle contacts, email rules, and system configurations.
- **Qdrant (`openzero_qdrant_storage`)**: Contains your vectorized memory—every thought, log, and note you've ever recorded.
- **Planka Volumes**: Holds your self-hosted Kanban board states, profile avatars, and uploaded attachments.

### Manual Backup Process
The safest way to back up your system is to archive your environment variables and the raw Docker volumes.

```bash
# 1. Stop the services to ensure data consistency
docker compose stop

# 2. Archive your configuration files (contains your database passwords & API keys)
tar -czvf openzero-config.tar.gz .env .env.planka

# 3. Archive the raw Docker volumes (using Alpine tar for portability)
docker run --rm -v openzero_pgdata:/vol -v $(pwd):/backup alpine tar -czvf /backup/pgdata.tar.gz -C /vol .
docker run --rm -v openzero_qdrant_storage:/vol -v $(pwd):/backup alpine tar -czvf /backup/qdrant.tar.gz -C /vol .
# ...repeat for Planka volumes

# 4. Restart the system
docker compose start
```

### Migrating to a New Build or Server
If you're moving your intelligence layer to a more powerful server or rebuilding:
1. Clone the `openzero` repository on the new machine.
2. Transfer and extract your `.env` and `.env.planka` config files into the new directory.
3. Bring up the new infrastructure quickly (`docker compose up -d`) and then immediately shut it down (`docker compose stop`). This forces Docker to create the empty named volumes.
4. Extract your backed-up data back into the new volumes:
	 ```bash
	 docker run --rm -v openzero_pgdata:/vol -v $(pwd):/backup alpine sh -c "cd /vol && tar -xzvf /backup/pgdata.tar.gz"
	 ```
5. Start the system again `docker compose start`. Your AI, full memory, and Kanban board will resume precisely where you left off.

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

### Upgrade or Lightweight the AI Model
If you need more speed or more intelligence, change `OLLAMA_MODEL` in your `.env`:
- **Speed**: Use `llama3.2:3b` for instant responses on standard CPUs.
- **Intelligence**: Use `llama3.1:70b` for high-precision reasoning (requires GPU).
- Simply run: `docker compose exec ollama ollama pull <model_name>` after updating the config.

---


## File Structure

```
openzero/
├── src/								# Core implementation
│		├── backend/				# FastAPI, SQLAlchemy, APScheduler
│		└── dashboard/			# Vanilla TS Web Components dashboard
├── docs/								# Architecture guides & prompt specs
├── scripts/						# Deployment & backup tools
├── personal/						# GITIGNORED — your private data
├── docker-compose.yml	# Service orchestration
├── .env.example				# Backend secrets template
├── .env.planka.example # Planka secrets template
├── BUILD.md						# Human-readable build guide
└── README.md						# This file
```

---

## Getting Started

See **[docs/build-plan.md](./docs/build-plan.md)** for the complete, step-by-step implementation guide — from server provisioning to the final deployment.

---

## The Open Source Philosophy & Contributing

Good open-source repositories thrive on transparency, collaboration, and a shared mission. **openZero** embraces this best practice. We believe that personal intelligence should not be gatekept by corporate data silos. Our codebase is open because absolute privacy requires verifiable, auditable code.

### How to Contribute
We welcome developers, designers, and privacy advocates to help improve openZero. Whether it's adding a new API integration, refining the web dashboard, or improving local LLM performance, your contributions matter:
- **Pull Requests**: Please open an issue to discuss proposed changes before submitting a PR.
- **Bug Reports**: Let us know if you encounter any friction in the build process or daily operation.
- **Feature Requests**: Share how you use openZero and what integrations would make your life easier.

### Contributors
This project is continuously evolving thanks to the community.

[![Niklas Brandt](https://github.com/niklasbrandt.png?size=40)](https://n1991.com) **[Niklas Brandt](https://n1991.com)** — Creator & Lead Developer

*(More to come as the project grows!)* 

If you are using openZero, star the repository and join the movement towards sovereign AI.

---

*Built with privacy in mind. Powered by open-source software. Runs on your terms.*
