# openZero

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![Self-Hosted](https://img.shields.io/badge/Deployment-Self--Hosted-blue.svg)](./BUILD.md)
[![Privacy First](https://img.shields.io/badge/Privacy-100%25_Local-purple.svg)](#security-and-privacy)
[![Agent Native](https://img.shields.io/badge/Agent--Native-Pure-black.svg)](https://github.com/niklasbrandt/openzero)
[![CPU Optimized](https://img.shields.io/badge/CPU--Only-No_GPU_Required-orange.svg)](#local-intelligence)

## Personal AI Operating System

openZero is a self-hosted agentic platform built for absolute data sovereignty. It runs entirely on your own hardware -- no GPU required, no cloud dependency, no third-party data leakage. The system synchronizes projects, calendars, emails, and communications within a private infrastructure, automating tasks and coordinating schedules around the clock.

The platform is personified as **Z**, an autonomous operator who builds, organizes, and executes on your behalf. Z maintains a persistent semantic memory of your preferences, relationships, and long-term goals. Every interaction is grounded in actual history, not re-prompted context windows.

Z directly manages your **unified schedule** by integrating with existing **CalDAV** servers (Nextcloud, Fastmail, Baikal) or your Google account. Z proactively blocks time for deep work, identifies scheduling conflicts, detects events embedded in emails, and remembers family milestones like birthdays -- automatically creating tasks when they approach. Your sensitive temporal data never leaves servers you control.

Every weekday morning, Z delivers a **multi-modal briefing** -- a structured text summary plus a high-quality voice note -- covering priority tasks, calendar events, weather, email digests, social circle updates, and a rotating mental calibration exercise. Users control the environment via a visual **dashboard** or a mobile **Kanban app** (Planka PWA), secured inside a Zero Trust mesh network. Primary interaction happens through a **Telegram bot** or the integrated dashboard chat UI.

## What it does

The system runs 24/7 on a remote VPS or local homelab. It links email, calendars, project boards, weather, and semantic memory without corporate oversight.

### Zero Trust Network

openZero avoids opening public ports. Instead, it creates a private **Tailscale** mesh network. Your phone and laptop connect as if they were in the same room as your server. This provides end-to-end encryption and eliminates the need for managing TLS certificates for internal names.

To support vanity domains like `http://open.zero`, the system uses an internal **Pi-hole** instance. By configuring Tailscale's Split DNS to use the VPS as a nameserver for the `open.zero` domain, your devices resolve the server without any global DNS record leakage.

### Local Intelligence

A 3-tier **llama.cpp** architecture runs optimized GGUF models directly on your CPU:

| Tier         | Model                        | Purpose                                                    | Typical Speed |
| :----------- | :--------------------------- | :--------------------------------------------------------- | :------------ |
| **Instant**  | Qwen3-1.7B (Q4_K_M)          | Greetings, confirmations, trivial Q&A, memory distillation | 8-18 tok/s    |
| **Standard** | Qwen3-8B (Q4_K_M)           | Conversation, creative tasks, planning, agent actions      | 2-5 tok/s     |
| **Deep**     | Qwen3-14B (Q4_K_M)          | Complex analysis, briefings, strategic reasoning           | 1-3 tok/s     |

The default profile targets a 24 GB VPS with all three tiers active. On 8-16 GB systems, the deep tier routes to standard. On Apple Silicon homelab, the deep tier can run Qwen3-32B. See `.env.example` for hardware profiles.

All three tiers use the Qwen3 generation (Apache 2.0). Qwen3-8B benchmarks on-par with Qwen2.5-14B; Qwen3-14B on-par with Qwen2.5-32B — at the same RAM footprint as their predecessors. Qwen3-14B also supports hybrid thinking mode (CoT blocks are stripped from user-facing output automatically).

Cloud reasoning is only engaged via a "Disclosure Proposal" workflow for shared memories -- never silently.

### Dashboard

A **TypeScript** web application built with native Web Components (Shadow DOM) and served via Vite:

- **Chat Interface** -- Direct conversation with Z, with streaming responses and full command support.
- **Life Overview** -- Real-time project tree, social circle summary, and 3-day timeline in a unified grid.
- **Calendar Agenda** -- Merged view of Google Calendar, CalDAV, and local events with inline event creation.
- **Memory Search** -- Semantic search across the knowledge vault with result previewing.
- **Briefing History** -- Archive of all daily, weekly, monthly, quarterly, and yearly briefings.
- **Circle Manager** -- Manage Inner Circle (family) and Close Circle (friends) with birthday tracking, relationship context, and per-person notes.
- **Email Rules** -- Pattern-based email triage engine: mark senders as Urgent (instant Telegram alert + auto-draft reply), Summarize (daily briefing digest), or Ignore.
- **User Profile** -- Identity editor with language selector, briefing time, timezone, and personal context.
- **Hardware Benchmark** -- CPU identification, SIMD instruction badges, and per-tier LLM throughput measurement with color-coded tok/s results.
- **Onboarding Wizard** -- Step-by-step setup tracker for profile, inner circle, and calendar integration. Dismissable once complete.
- **Planka SSO** -- Background auto-login bridge to the Kanban app via hidden iframe redirect, so Planka is always authenticated.

### Operator Board

A centralized **hub board** that pulls high-priority tasks from all project boards into a single view. The board auto-syncs on a configurable interval, so the "Today" list always reflects what needs attention right now. Z monitors this board and sends **proactive follow-up nudges** every 3 hours during work hours for any uncompleted items.

### Proactive Automation

Z does not wait to be asked. The system runs scheduled automation cycles that act on your data:

- **Morning Briefing** (Mon-Fri, configurable time) -- Gathers projects, calendar, weather, emails, social circle birthdays, and recent memories into a structured prompt. Generates a text briefing and a TTS voice note. Includes a rotating **mental calibration exercise** (gratitude, breathing, visualization, journaling) and a **closing literary reflection** from authors like Frost, Camus, Rumi, and Aurelius.
- **Contextual Automation** -- Scans circle calendars for upcoming birthdays, deadlines, and priority events within 3 days and auto-creates Kanban tasks.
- **Email Polling** (every 10 minutes) -- Fetches unread emails via Gmail API, applies user-defined rules, detects embedded calendar events (with approval buttons), and auto-drafts replies for urgent senders.
- **Proactive Follow-ups** (every 3 hours, 9AM-9PM) -- Checks the Operator Board "Today" list and sends warm, direct mission-check nudges via Telegram.
- **Proximity Tracking** -- Time-boxed mission sessions with per-segment milestone nudges and a final wrap-up report. Each segment deadline triggers a targeted progress check.
- **Weekly Review** (Sundays) -- Summarizes progress, identifies stagnant projects (no activity in 7+ days), and proposes micro-tasks to unblock them.
- **Monthly / Quarterly / Yearly Reviews** -- Escalating strategic analysis at each cadence, stored as browsable briefings.
- **Daily Backup** (4 AM) -- Automated system backup script execution.
- **Timezone Sync** (every 4 hours) -- Re-detects user timezone to handle travel and DST transitions.
- **Custom Persistent Tasks** -- User-defined cron or interval schedules created via `/custom` that survive restarts (stored in database, hot-loaded into the scheduler).

### Semantic Action Tags

Z uses a custom **Semantic Action Tag** system for agent actions. When the user requests a task, event, or project, the LLM emits structured tags in its response that the backend parses and executes:

- `CREATE_TASK` -- Creates a card on any Planka board/list.
- `CREATE_PROJECT` / `CREATE_BOARD` / `CREATE_LIST` -- Scaffolds entire project structures in bulk.
- `CREATE_EVENT` -- Creates calendar events (synced to CalDAV and local DB).
- `LEARN` -- Silently commits a distilled fact to the semantic vault when the user shares something meaningful.
- `ADD_PERSON` -- Adds a new contact to the Inner or Close circle.
- `REMIND` -- Sets a temporary recurring reminder with configurable interval and duration.
- `SCHEDULE_CUSTOM` -- Creates a persistent cron/interval task.
- `PROXIMITY_TRACK` -- Initiates a high-precision time-boxed mission with per-segment milestones.

Tags are invisible to the user. Z never mentions them unless explicitly asked via `/protocols`.

### Multi-Language Support

Z speaks your language. The dashboard includes a language selector supporting **20 languages** across global and Western regions. The chosen language propagates to all AI responses, briefings, and notifications with zero performance overhead for the default English path.

**Global:** English, Mandarin Chinese, Hindi, Spanish, French, Arabic, Portuguese, Russian, Japanese, German.
**Western:** Italian, Dutch, Polish, Swedish, Greek, Romanian, Turkish, Czech, Danish, Norwegian.

### Calendar and Scheduling

openZero features a unified schedule that merges **Google Calendar**, private **CalDAV** servers (Nextcloud, Fastmail, Baikal, Radicale), and local database events into a single, deduplicated view. Z creates events via voice or text commands, and the system syncs bidirectionally with your CalDAV server.

The calendar engine also performs **proactive event detection**: when an incoming email contains date/time references, Z extracts them and presents approval buttons via Telegram ("Add to Calendar" / "Ignore") before committing.

### Weather Intelligence

Hourly forecasts from **Open-Meteo** (no API key required) are segmented into morning, afternoon, and evening blocks with precipitation probability and wind data. The system auto-detects **travel context** from calendar events containing keywords like "flight to" or "trip to" and fetches weather for the destination city instead of the home location.

### Voice and Text

- **Speech-to-Text:** Local transcription via Whisper. Voice notes sent to the Telegram bot are transcribed and processed as regular messages.
- **Text-to-Speech:** openedai-speech generates high-quality audio briefings delivered as voice messages alongside the text version.

## Architecture

The stack is optimized for single-server CPU-only deployment with full privacy:

- **Semantic Action Tags:** Z acts as the core autonomous operator, using a custom tag-based tool system to create tasks, events, projects, and memories. The LLM emits structured tags that the backend parses and executes asynchronously.
- **Memory:** Qdrant stores semantic vectors. Retrieval depends on meaning rather than keywords. A guardrail filter prevents noise (greetings, confirmations) from polluting the vault.
- **Tasking:** Planka provides the visual Kanban engine and runs as a secure PWA. Background SSO auto-login from the dashboard keeps sessions seamless.
- **Scheduling:** APScheduler manages all recurring jobs (briefings, email polling, follow-ups, backups, timezone sync, custom tasks) with timezone-aware triggers and DST handling.
- **Network:** Traefik manages routing and Pi-hole blocks tracking. Tailscale secures the perimeter with a Zero Trust mesh.
- **Async Execution:** Redis powers the Celery task queue. Background reasoning keeps the UI responsive during long-running LLM operations.

## Tech Stack

| Component        | Technology                                                                                                                                                                                                                                                                             | Purpose                                                                                             |
| :--------------- | :------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | :-------------------------------------------------------------------------------------------------- |
| **Core OS**      | ![Ubuntu](https://img.shields.io/badge/Ubuntu-E9433F?style=flat&logo=ubuntu&logoColor=white) ![Python](https://img.shields.io/badge/Python-3776AB?style=flat&logo=python&logoColor=white) ![Docker](https://img.shields.io/badge/Docker-2496ED?style=flat&logo=docker&logoColor=white) | Containerized foundation on Linux with Python backend.                                              |
| **Intelligence** | ![llama.cpp](https://img.shields.io/badge/llama.cpp-black?style=flat)                                                                                                                                                                                                                  | 3-tier local LLM (instant/standard/deep) via llama-server with streaming. CPU-only, SIMD-optimized. |
| **Dashboard**    | ![TypeScript](https://img.shields.io/badge/TypeScript-3178C6?style=flat&logo=typescript&logoColor=white) ![Vite](https://img.shields.io/badge/Vite-646CFF?style=flat&logo=vite&logoColor=white)                                                                                        | Native Web Components (Shadow DOM) with hot-reload development.                                     |
| **Mobile**       | ![Telegram](https://img.shields.io/badge/Telegram-2CA5E0?style=flat&logo=telegram&logoColor=white)                                                                                                                                                                                     | Primary mobile interface via long-polling bot with inline keyboards.                                |
| **Storage**      | ![PostgreSQL](https://img.shields.io/badge/PostgreSQL-4169E1?style=flat&logo=postgresql&logoColor=white) ![Qdrant](https://img.shields.io/badge/Qdrant-red?style=flat)                                                                                                                 | Relational data paired with high-dimensional semantic vector memory.                                |
| **Execution**    | ![Redis](https://img.shields.io/badge/Redis-DC382D?style=flat&logo=redis&logoColor=white) ![Celery](https://img.shields.io/badge/Celery-37814A?style=flat&logo=celery&logoColor=white)                                                                                                 | Asynchronous task delegation and high-speed message brokering.                                      |
| **Scheduling**   | ![APScheduler](https://img.shields.io/badge/APScheduler-green?style=flat)                                                                                                                                                                                                              | Timezone-aware cron/interval job scheduler with DST handling.                                       |
| **Networking**   | ![Traefik](https://img.shields.io/badge/Traefik-2496ED?style=flat&logo=traefik&logoColor=white) ![Tailscale](https://img.shields.io/badge/Tailscale-4A23B6?style=flat&logo=tailscale&logoColor=white)                                                                                  | Zero Trust perimeter with automated internal routing.                                               |
| **DNS**          | ![Pi-hole](https://img.shields.io/badge/Pi--hole-96060C?style=flat&logo=pi-hole&logoColor=white)                                                                                                                                                                                       | DNS sinkhole blocking container telemetry and enabling vanity domains.                              |
| **Tasking**      | ![Planka](https://img.shields.io/badge/Planka-blue?style=flat)                                                                                                                                                                                                                         | Self-hosted Kanban engine accessible as a mobile PWA.                                               |
| **Voice**        | ![Whisper](https://img.shields.io/badge/Whisper-black?style=flat) ![TTS](https://img.shields.io/badge/openedai--speech-green?style=flat)                                                                                                                                                      | Local speech-to-text and high-quality audio generation.                                             |
| **Weather**      | ![Open-Meteo](https://img.shields.io/badge/Open--Meteo-blue?style=flat)                                                                                                                                                                                                                | Hourly forecasts with travel-aware location detection. No API key needed.                           |

```
┌──────────────────────────────────────────────────┐
│                 Your Devices                     │
│      (Phone / Laptop / Tablet)                   │
│                                                  │
│   Telegram Bot ──── Chat, Voice, Commands        │
│   Dashboard    ──── Web UI, Benchmark, Config    │
│   Planka PWA   ──── Kanban Boards                │
└───────────────┬──────────────────────────────────┘
                │  Tailscale VPN (encrypted mesh)
                ▼
┌──────────────────────────────────────────────────┐
│               VPS / Homelab                      │
│                                                  │
│   ┌──────────────────────────────────────────┐   │
│   │         Traefik / Pi-hole                │   │
│   │    (Routing, DNS, Telemetry Blocking)    │   │
│   └──────────────────┬───────────────────────┘   │
│                      ▼                           │
│   ┌──────────────────────────────────────────┐   │
│   │   FastAPI Backend + APScheduler          │   │
│   │     ├── Telegram Bot (long-polling)      │   │
│   │     ├── Semantic Action Tag Engine       │   │
│   │     ├── Email Polling + Rule Engine      │   │
│   │     ├── Morning Briefing Generator       │   │
│   │     ├── Proactive Follow-up System       │   │
│   │     └── Dashboard API (REST)             │   │
│   └──────────────────────────────────────────┘   │
│                                                  │
│   ┌───────────┐  ┌─────────┐  ┌──────────────┐  │
│   │ PostgreSQL│  │  Qdrant │  │  llama.cpp   │  │
│   │  (data)   │  │ (memory)│  │ (3-tier AI)  │  │
│   └───────────┘  └─────────┘  └──────────────┘  │
│                                                  │
│   ┌───────────┐  ┌─────────┐  ┌──────────────┐  │
│   │  Whisper  │  │  Coqui  │  │   Planka     │  │
│   │  (STT)    │  │  (TTS)  │  │  (Kanban)    │  │
│   └───────────┘  └─────────┘  └──────────────┘  │
│                                                  │
│   ┌───────────┐  ┌─────────┐                     │
│   │   Redis   │  │ Celery  │  Background Workers │
│   │  (Queue)  │  │ (Tasks) │                     │
│   └───────────┘  └─────────┘                     │
│                                                  │
│   External APIs (outbound only):                 │
│     Gmail API, Google Calendar, Open-Meteo       │
└──────────────────────────────────────────────────┘
```

## Commands

All commands are available via the Telegram bot and the dashboard chat interface.

| Command      | Description                                                                                                                                                     |
| :----------- | :-------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `/help`      | Display the full overview of operator controls.                                                                                                                 |
| `/start`     | System status check and heartbeat.                                                                                                                              |
| `/day`       | Trigger the morning briefing (calendar, weather, emails, projects, calibration, voice note).                                                                    |
| `/week`      | Weekly strategic review with stagnation detection for dormant projects.                                                                                         |
| `/month`     | 30-day mission review with initiative tracking.                                                                                                                 |
| `/quarter`   | 90-day strategic review and roadmap planning.                                                                                                                   |
| `/year`      | Yearly goal setting based on project themes and trajectory analysis.                                                                                            |
| `/custom`    | Create a persistent scheduled task with cron or interval syntax (e.g., every Monday at 10am). Survives restarts.                                                |
| `/tree`      | Full life hierarchy: projects, boards, lists, and social circles.                                                                                               |
| `/think`     | Deep reasoning using the 14B model with human-in-the-loop approval.                                                                                             |
| `/search`    | Semantic search of the knowledge vault -- finds by meaning, not keywords.                                                                                       |
| `/memories`  | List all core knowledge currently in permanent memory.                                                                                                          |
| `/personal`  | Display the personal context files currently loaded from the `personal/` folder (about-me, requirements and more).                                              |
| `/unlearn`   | Refine Z's memory by evolving or removing specific points in the vault.                                                                                         |
| `/add`       | Commit specific facts to Z's permanent knowledge vault (bypasses the noise filter).                                                                             |
| `/remind`    | Set a temporary recurring reminder with interval and expiry (e.g., every 30 min for 4h).                                                                        |
| `/protocols` | Inspect Z's Semantic Action Tags and available agentic tools.                                                                                                   |
| `/purge`     | Permanently delete all semantic memories from the vault (Qdrant). Does **not** affect task boards, people, or briefing history. Requires explicit confirmation. |

## Memory and Intelligence Principles

Z follows a strict **"Core Knowledge, not Noise"** logic for long-term intelligence:

- **Permanent Memory:** Preferences, family members, project goals, health facts, and life milestones are committed to the **Semantic Vault** (Qdrant). Z learns proactively -- when you mention "I am dust allergic" in conversation, it is silently distilled and stored.
- **Transient Traffic:** Status updates ("I'm at the store"), transient chat history, and bot responses are **intentionally ignored** by the memory vault to prevent hallucination loops and context pollution.
- **The Guardrail:** Automatic filtering via a local reasoning pass ensures trivialities like "thanks" or "hello" never hit the vault. The system distinguishes between factual data worth keeping (preferences, people, plans) and ephemeral chatter.
- **Manual Control:** Use `/add` to explicitly override the filter when you have critical context Z must never forget.
- **Memory Review:** Each morning briefing includes a "New Memories (Last 24h)" section, showing exactly what was stored. Use `/unlearn` to correct any mistakes.

## Maintenance

### Backups and Migration

The system runs an **automated backup** every night at 4 AM. Environment variables and raw Docker volumes require archiving to protect data integrity.

- **Archiving:** Stop services via `docker compose stop` before creating tarballs of `.env` and named volumes (pgdata, qdrant_storage, planka_data).
- **Moving Data:** To migrate, clone the repo on the new host, transfer the `.env` and `.env.planka` files, and extract volume archives into the new Docker environment.
- **Integrity:** Local, encrypted backups with a 30 day retention policy are recommended.

### Continuous Testing

The platform includes a live regression suite (`tests/test_live_regression.py`). Tests are skipped by default during deployment; pass `--test` to run them:

```bash
bash scripts/sync.sh --test
```

Because openZero relies heavily on AI behavior, traditional unit tests are insufficient. The integrated suite tests the end-to-end capabilities of the live environment by:

- Verifying the `System Health API` (including OS RAM and CPU metrics).
- Testing Qdrant memory persistence through semantic extraction and retrieval.
- Injecting full Semantic Action Tags to ensure the LLM parser correctly interacts with Planka (projects, boards, lists, tasks) and the OS database (calendar events, people).
- Validating the 3-tier routing logic.
- Cleaning up test data seamlessly.

Run it manually at any time via: `python3 tests/test_live_regression.py --url http://YOUR_SERVER_IP --token your_token_here`

### Prompt Injection Test Suite

A dedicated offline test suite (`tests/test_security_prompt_injection.py`) validates the structural integrity of the prompt construction pipeline against **282 tests across 23 categories**. The suite runs without any infrastructure -- no LLM, no database, no network required.

Categories include: direct prompt injection, indirect injection via memory/calendar/documents, jailbreak attempts (DAN, developer mode, grandma exploit), context manipulation (ChatML/LLaMA/Phi/Qwen token injection), memory poisoning, identity hijacking, data exfiltration, privilege escalation, encoding-based evasion (base64, ROT13, homoglyphs, Zalgo, leetspeak), multi-turn manipulation, structured data injection (JSON, YAML, SQL, SSTI), Telegram-specific attacks, dashboard XSS/CSS injection, API endpoint attacks (CRLF, path traversal), combined advanced attacks, and production integration tests that import and validate the actual `sanitise_input()` and `_ADVERSARIAL_PATTERNS` implementations.

The production code implements 5 hardening measures identified by the test findings: input sanitisation with model control token stripping (`sanitise_input()` in `llm.py`), adversarial content filtering in memory storage (`memory.py`), action tag stripping from retrieved memory context, and history role filtering (system-role messages dropped from client-provided chat history). Full results and architecture details are in [`docs/artifacts/prompt_injection_tests.md`](docs/artifacts/prompt_injection_tests.md).

Run it with:

```bash
python -m pytest tests/test_security_prompt_injection.py -v --tb=short
```

## Setting it up

A VPS with **24GB RAM** or a local Mac Mini/homelab is recommended. The entire stack is optimized for **CPU-only inference** using quantized GGUF models with llama.cpp. No GPU required -- the system auto-detects AVX2/AVX-512 SIMD capabilities and configures thread counts per tier. Use the built-in benchmark widget to measure actual throughput on your hardware.

Typical throughput on a 4-core EPYC VPS: 5-12 tok/s (instant tier), 2-5 tok/s (standard tier), 1-3 tok/s (deep tier).

1. **Deploy:** Run `docker compose up -d`. First-time model downloads happen automatically per tier.
2. **Secure:** Link the server to the Tailscale network. Configure Pi-hole Split DNS for your vanity domain.
3. **Configure:** Open the dashboard, complete the onboarding wizard, connect calendars, and set your language and briefing time.

> [!WARNING]
> **Ubuntu / Debian: Port 53 is blocked by default.** `systemd-resolved` binds a stub DNS listener on `127.0.0.53:53`, preventing Pi-hole from starting. If `docker compose logs pihole` shows "address already in use" on port 53, run these three commands on the VPS once before starting the stack:
>
> ```bash
> sudo sed -r -i.orig 's/#?DNSStubListener=yes/DNSStubListener=no/g' /etc/systemd/resolved.conf
> sudo sh -c 'rm /etc/resolv.conf && ln -s /run/systemd/resolve/resolv.conf /etc/resolv.conf'
> sudo systemctl restart systemd-resolved
> ```
>
> Then restart Pi-hole: `docker compose restart pihole`. Full details in [BUILD.md](BUILD.md).

### Private Calendar Setup (CalDAV)

openZero keeps your schedule private. To sync with your existing self-hosted calendar:

1. **Find your URL:**
    - **Nextcloud:** Open Calendar, Settings icon, "Copy primary CalDAV address".
    - **iCloud:** Use your full iCloud email and an App-Specific Password.
    - **Baikal / Radicale:** Copy the specific calendar collection link (ending in `.php/dav/...`).
    - **Fastmail:** Use Settings, Calendars, CalDAV connection details.
2. **Edit your `.env`:** Fill in `CALDAV_URL`, `CALDAV_USERNAME`, and `CALDAV_PASSWORD`.
3. **Sync:** The system automatically fetches events every few minutes and syncs new entries created through Z.

### Personal Context Folder

The `personal/` folder is a local-only, git-ignored directory that gives Z deep persistent knowledge about you. Files placed here are loaded on startup, refreshed every hour, and injected into every system prompt as the highest-authority context block.

**Supported file types:** `.md`, `.txt`, `.docx`, `.pdf` -- diaries, CVs, certificates, instructions all work.

**Setup:**

```
cp docs/about-me.example.md personal/about-me.md
cp docs/requirements.example.md personal/requirements.md
```

Edit both files with your real personal details, then start the stack.

**How it works:**

- Z treats facts in this folder as the definitive source of truth about you -- they override all LLM defaults.
- Content is compressed in two stages at scan time (deterministic, then LLM-assisted) to fit within a token budget. Compression results are cached, so there is zero latency impact on conversation.
- The folder is bind-mounted read-only into the container (`./personal:/app/personal:ro`), so the backend can never write to it.
- The folder is excluded from all `git` tracking and `rsync` deployments. It never leaves your local machine.

**Security hardening applied to personal files:**

- Action tags (`[ACTION: ...]`) are stripped before injection to prevent personal files from inadvertently triggering Z's agentic tool system.
- Symlink traversal and archive-bomb attacks are blocked (PDF page cap 50, DOCX paragraph cap 500, file size gate 512 KB, parse timeout 30 s).
- File magic bytes are validated against declared extensions -- a renamed binary is skipped with a warning.

### Deployment Expectations

First-time builds and model downloads incur significant durations:

- **Cold Builds:** Using `--no-cache` or major dependency updates can take 45-60 minutes for pip resolution.
- **Model Downloads:** The 3-tier LLM models total approximately 15GB (Qwen3-1.7B ~1.1GB, Qwen3-8B ~5GB, Qwen3-14B ~9GB). Download time depends on your server's bandwidth.
- **Media Engines:** Pulling the voice engines (Whisper and Coqui TTS) requires approximately 6GB of model data. Depending on network speed, this may total 2-3 hours for a complete first-time setup.
- **Subsequent Starts:** Once images and models are cached, the stack starts in seconds.

## Security and Privacy

The build follows a strict privacy-first model:

- **All AI processing remains local** by default. No data leaves your server unless you explicitly use Gmail/Google Calendar APIs or a cloud LLM provider.
- **Cloud LLM PII sanitization** strips all named entities (people, emails, phone numbers, locations, organisations) from outbound prompts using an offline spaCy NER model before they reach cloud APIs (Groq, OpenAI). Responses are re-hydrated with real values before returning to the caller. The replacement map is request-scoped only — never logged or persisted.
- **Tailscale + UFW** enforce a closed perimeter. Port 80 is restricted to the Tailscale interface via `ufw allow in on tailscale0`. The public internet has no reachable entry point.
- **Pi-hole** blocks telemetry from all containers, ensuring no Docker image phones home.
- **Backups** remain local and under physical control. No cloud backup service is used.
- **No analytics, no tracking, no third-party cookies.** The dashboard is a static SPA served from your own server.
- **Disclosure Proposal workflow** ensures cloud reasoning is never engaged silently for shared memories.

## Contributors

[![Niklas Brandt](https://github.com/niklasbrandt.png?size=40)](https://n1991.com) **[Niklas Brandt](https://n1991.com)** -- Creator

Engineering, design, and privacy advocacy contributions are welcome. Report issues or star the repository to support the project.
