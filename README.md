# openZero

[![Agent Native](https://img.shields.io/badge/Agent--Native-Pure-black.svg)](https://github.com/niklasbrandt/openzero)
[![Low Inference](https://img.shields.io/badge/Inference-Low_Resource_Optimized-orange.svg)](#the-stack)
[![Privacy First](https://img.shields.io/badge/Privacy-100%25_Local-purple.svg)](#network-perimeter)
[![Self-Hosted](https://img.shields.io/badge/Deployment-Self--Hosted-blue.svg)](BUILD.md)
[![LLM Agnostic](https://img.shields.io/badge/LLM-Local_%2B_API_Agnostic-FF6B35.svg)](#the-stack)
[![Dual LLM Tier](https://img.shields.io/badge/Routing-Fast_%2B_Deep_Tier-blueviolet.svg)](#the-stack)
[![Autonomous Crews](https://img.shields.io/badge/Crews-YAML_Scheduled-brightgreen.svg)](#crews)
[![Crew Output](https://img.shields.io/badge/Crew_Output-Planka_Kanban-0079BF.svg)](#crews)
[![Web Search](https://img.shields.io/badge/Search-SearXNG_Self--Hosted-3498db.svg)](#the-stack)
[![Semantic Memory](https://img.shields.io/badge/Memory-Qdrant_Vector-8e44ad.svg)](#memory-connections)
[![Multi-Channel](https://img.shields.io/badge/Messaging-Telegram_%C2%B7_WhatsApp-25D366.svg)](#channels)
[![Voice I/O](https://img.shields.io/badge/Voice-Whisper_%2B_TTS-e74c3c.svg)](#the-stack)
[![DNS Filtering](https://img.shields.io/badge/DNS-Pi--hole_Builtin-c0392b.svg)](#the-stack)
[![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5-3178C6?logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![Vite](https://img.shields.io/badge/Vite-6-646CFF?logo=vite&logoColor=white)](https://vitejs.dev/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org/)

openZero is a self-hosted AI companion — called Z — that you talk to through Telegram, WhatsApp, or a web dashboard. It builds a persistent memory from every conversation and from the work its background agents do on your behalf. Optionally, it reads your calendar and email. Everything runs on hardware you own, inside a network perimeter you control.

Background agents — called crews — run on schedules you define. They reason over Z's accumulated memory, calendar events, and email to produce briefings you can act on.

---

## Scheduled agents

The most important work happens without you.

Background agents — called crews — run on schedules you define. Each crew is a council of purpose-shaped reasoning characters that work over Z's accumulated conversation memory, calendar events (if connected), email (if connected), and the memory points from prior crew outputs. By the time your morning briefing arrives, Z has already cross-referenced what it knows about you, identified what needs your attention, and proposed concrete next steps.

Briefings arrive at whatever cadence you configure: daily, weekly, monthly, quarterly, yearly. They are not digests. They are reasoned assessments grounded in everything Z has learned about you. A morning briefing might surface a stalled project, a meeting conflict, a market signal, or a health observation — not because you set rules for any of it, but because Z had built enough context to notice the relationship.

Between briefings, you talk to Z the same way you text anyone: via Telegram, WhatsApp, or the web dashboard. Z reads the same memory. The conversation is continuous across all three channels.

---

## The stack

Every service runs in Docker Compose on a single VPS you own.

| Service | Role |
|---|---|
| llama.cpp | Local LLM inference — all interactive chat, auto-sized to your hardware |
| Qdrant | Vector memory store — semantic search over everything Z has learned |
| PostgreSQL | Relational store — structured state, task boards, conversation history |
| Redis | Task queue and pub/sub message bus |
| Planka | Kanban board — crews can create and move cards; you can too |
| Traefik | Internal reverse proxy — routes dashboard, API, and board traffic |
| Pi-hole | DNS resolver — resolves `open.zero` within your Tailscale network |
| SearXNG | Self-hosted meta-search — web search without API keys or tracking |
| Whisper | Speech-to-text (optional, `voice` profile) |
| openedai-speech | Text-to-speech (optional, `voice` profile) |

The dashboard and backend are built from source; everything else runs from published images with pinned version tags. No service binds to a public port. All external access goes through Tailscale.

---

## Hardware

Z auto-detects available RAM and CPU count on every start and sizes the LLM context window, thread count, batch size, and memory strategy accordingly. You do not need to tune these unless you want to override a specific value.

| Profile | RAM | vCPU | Default model |
|---|---|---|---|
| Minimal | 8 GB | 4 | Qwen3-1.7B Q4\_K\_M |
| Standard | 12 GB | 4-6 | Qwen3-1.7B Q4\_K\_M |
| Comfortable | 24 GB | 8 | Qwen3-4B Q4\_K\_M |

A Raspberry Pi 5 runs the Minimal profile. A mid-range cloud VPS (~4 EUR/month, 4 vCPU / 8 GB) runs Standard. Voice services are off by default on 8 GB machines to free RAM for the LLM; enable them with `docker compose --profile voice up -d` on 12 GB+.

An optional cloud LLM tier (any OpenAI-compatible API) handles requests the local model is not sized for. A spaCy NER sanitization layer exists in the codebase — it can strip named entities from prompts before they leave your server and re-inject them into the response — but it is disabled by default due to false-positive rates on non-personal content. Enable it with `CLOUD_LLM_SANITIZE=true` in `.env` if you are routing genuinely personal data through a cloud provider.

---

## Quick start

You need: a VPS running Ubuntu 24.04, Docker installed, Tailscale installed on both server and client, and a Telegram bot token.

**1. Prepare the server**

```bash
	# Add swap — mandatory first step
	sudo fallocate -l 8G /swapfile
	sudo chmod 600 /swapfile
	sudo mkswap /swapfile
	sudo swapon /swapfile
	echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

	# Create the project user
	adduser openzero
	usermod -aG sudo openzero
	usermod -aG docker openzero

	# Firewall — port 80 only through Tailscale, never public
	sudo ufw allow ssh
	sudo ufw allow in on tailscale0 to any port 80
	sudo ufw deny 80
	sudo ufw allow in on tailscale0 from 100.64.0.0/10 to any port 53 proto udp
	sudo ufw allow in on tailscale0 from 100.64.0.0/10 to any port 53 proto tcp
	sudo ufw allow in from 172.16.0.0/12 to any port 53 proto udp
	sudo ufw allow in from 172.16.0.0/12 to any port 53 proto tcp
	sudo ufw --force enable
```

**2. Clone and configure (on your laptop)**

```bash
	git clone https://github.com/your-org/openzero.git
	cd openzero
	cp .env.example .env
```

Edit `.env` and set at minimum:

```bash
	TELEGRAM_BOT_TOKEN=your_bot_token
	REMOTE_HOST=your_server_ip
	REMOTE_USER=openzero
	REDIS_PASSWORD=$(openssl rand -hex 24)
	DASHBOARD_TOKEN=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
	BASE_URL=http://open.zero
	LLM_LOCAL_MODEL_URL=https://huggingface.co/unsloth/Qwen3-1.7B-GGUF/resolve/main/Qwen3-1.7B-Q4_K_M.gguf
	LLM_LOCAL_MODEL_FILE=Qwen3-1.7B-Q4_K_M.gguf
```

**3. Set up your personal context**

```bash
	cp -r personal.example personal
	# Edit personal/*.md with your actual details.
	# This folder is never committed and never synced to git.
	# It is injected into every system prompt on the server.
```

**4. Set up your agent skills and crews**

```bash
	cp -r agent.example agent
	# Edit agent/crews.yaml to activate the crews you want.
	# Edit agent/agent-rules.md to add hard-coded behavioral rules.
	# This folder is never committed and never synced to git.
```

**5. Configure Planka (on the server)**

```bash
	cp .env.planka.example .env.planka
	# Edit .env.planka:
	#   BASE_URL=http://your_server_ip
	#   DATABASE_URL — update password to match DB_PASSWORD in .env
	#   SECRET_KEY — replace with a long random string
	#   Default admin password — set something you will remember
```

**6. Deploy**

```bash
	./scripts/sync.sh
```

The sync script builds the dashboard, copies all non-sensitive files to the server over SSH, and brings the stack up. The LLM container downloads the model file on first start — this takes a few minutes depending on connection speed.

**7. Access the dashboard**

```
	http://open.zero/dashboard?token=your_dashboard_token
```

Open this once in your browser. The token is saved to `localStorage` and stripped from the URL. Subsequent visits do not need it. On mobile, open it once, then bookmark the stripped URL.

---

## Configuration

openZero configuration lives in three places.

**`config.yaml`** (feature toggles and schedules)

Copy `config.example.yaml` to `config.yaml`. Toggle integrations on or off, set briefing times and days, and adjust polling intervals. Key defaults:

```yaml
	features:
	  messenger_bot: true
	  whatsapp_bot: false
	  task_board_integration: false
	  email_monitoring: false
	  calendar_monitoring: false

	schedules:
	  morning_briefing:
	    enabled: true
	    time: "07:30"
	    days: "mon-fri"
	  weekly_review:
	    enabled: true
	    time: "10:00"
	    day: "sun"
```

Email and calendar integrations are opt-in. When `email_monitoring: false`, no email surface exists anywhere in the system — no UI, no API routes, no nav link. Z behaves as if email does not exist. The same principle applies to every integration: off means absent, not hidden.

**`.env`** (secrets and infrastructure)

See `.env.example` for the full list. Critical vars: `TELEGRAM_BOT_TOKEN`, `REDIS_PASSWORD`, `DASHBOARD_TOKEN`, `BASE_URL`, `LLM_LOCAL_MODEL_URL`. Optional: `LLM_CLOUD_BASE_URL` and `LLM_CLOUD_API_KEY` for cloud fallback, `BACKUP_PASSPHRASE` for encrypted exports.

**`agent/` folder** (operator identity and crews)

The agent folder is bind-mounted read-only into the backend container. Changes take effect on the next container restart or crew execution cycle.

- `crews.yaml` — crew definitions, schedules, and character priming
- `agent-rules.md` — hard-coded behavioral rules injected into every prompt
- `kanban.md` and `planka.md` — operational methodology (pre-filled; edit or leave as-is)
- Any additional `.md`, `.txt`, `.pdf`, or `.docx` files are loaded as skill context

---

## Crews

Crews are multi-character background agents. Each crew is a set of reasoning archetypes that collaborate over a question or domain, running on a schedule or triggered by conversation keywords. Their output feeds briefings, creates Planka board cards, or stores memory points in Qdrant.

The crew registry lives in `agent/crews.yaml` — bind-mounted read-only into the container, never committed to git, never leaves your machine except via rsync to your own server.

The shipped example includes two system-level crews:

**scrum** — monitors your Planka boards for stalled items, blocked tasks, and WIP violations. Surfaces the single most actionable next step at each daily briefing and tracks every verbal commitment made in conversation, converting them into board cards before they disappear into chat history.

**focus** — reads all available context (memory, briefings, calendar, boards, recent conversations) and surfaces what is objectively most important right now. Cuts through noise and competing priorities to give you one clear answer: what to do next.

Personal and domain crews — health, nutrition, coaching, research, travel, security, and whatever else fits your life — are defined entirely by you in `agent/crews.yaml`. The YAML schema and character priming documentation in the file header explain how to write them. The example file ships with a generic life-coaching crew as a starting template.

Each crew specifies which briefing cadence it feeds (`feeds_briefing: "/day"`, `"/week"`, `"/month"`, etc.) and how many minutes before briefing time it should start. The scheduler handles the timing automatically.

Character names in a crew definition are semantic priming, not display labels. Naming a character "The Contrarian Auditor" rather than "the devil's advocate" causes the underlying model to adopt a more rigorous adversarial reasoning pattern. This is documented in the YAML header.

---

## Channels

Z maintains a single context state regardless of where you interact with it.

**Telegram** — the primary channel. Z polls for messages and streams replies. Crew briefings arrive here by default.

**WhatsApp** — optional second channel via the Meta WhatsApp Cloud API (free tier, no monthly fee). Requires a Meta developer account and a dedicated phone number. Enable with `whatsapp_bot: true` in `config.yaml` and the corresponding `WHATSAPP_*` vars in `.env`. Messages are routed through the same message bus; replies appear in both the WhatsApp thread and the dashboard conversation view.

**Dashboard** — a web application served at `http://open.zero/dashboard` behind your Tailscale network. Provides a chat interface, memory search, briefing history, calendar view, hardware health monitoring, crew status, and the Memory Atlas — a visual map of Z's accumulated memory and the connections between ideas, people, and events.

All three channels receive briefings. A fix to message handling in one channel is applied to all three simultaneously.

---

## Network perimeter

Port 80 is blocked on all public interfaces. The dashboard, API, and Planka board are only reachable through the `tailscale0` interface. DNS (port 53) is only reachable from within the Tailscale CGNAT range (`100.64.0.0/10`). No service binds an external port in `docker-compose.yml`.

This means openZero does not need TLS certificates, a domain name, or a CDN. It is not on the internet. You access it from devices enrolled in your Tailscale network, which resolves `open.zero` to the Pi-hole DNS container on the server.

---

## Backup and export

The dashboard includes an encrypted backup export. The archive is encrypted client-side with AES using a passphrase you provide before it streams to your browser. The passphrase is never stored on the server. Automated exports can be scripted against the `/api/dashboard/backup/export` endpoint with a `BACKUP_PASSPHRASE` env var set in `.env`.

Minimum passphrase length is 12 characters. If you lose the passphrase, existing archives cannot be decrypted.

---

## Running the quality gate

Before any commit:

```bash
	# TypeScript type check
	cd src/dashboard && npx tsc --noEmit

	# Python linting
	cd src/backend && ruff check app/

	# i18n key parity (all keys in _EN must exist in _DE)
	pytest tests/test_i18n_coverage.py -v

	# Security and static analysis
	pytest tests/test_security_prompt_injection.py tests/test_static_analysis.py -v
```

The full test suite includes 268 security tests across 25 attack classes, Playwright accessibility audits (axe-core, WCAG 2.1 AA), i18n coverage gates, and a live regression suite that runs against a deployed instance.

---

## Project structure

```
	agent/              operator skills, rules, and crew definitions (not committed)
	agent.example/      template for agent/ (committed, sanitized)
	docs/artifacts/     design decisions, phase plans, architectural records
	personal/           highest-priority context injected into every prompt (not committed)
	personal.example/   template for personal/ (committed, sanitized)
	scripts/            sync, backup, dev utilities
	src/backend/        FastAPI application — API, services, tasks, LLM routing
	src/dashboard/      TypeScript Web Components dashboard — Shadow DOM, no framework
	tests/              full test suite — security, a11y, i18n, regression
	agent.json          Z's identity and voice configuration
	config.yaml         feature toggles and briefing schedules
	docker-compose.yml  service definitions
```

The backend is a single FastAPI application. Services for LLM routing, memory, calendar, Gmail, web search, voice, crews, and notifiers live in `src/backend/app/services/`. API endpoints are in `src/backend/app/api/`.

The dashboard is built with native Web Components using Shadow DOM. No framework dependency. Each component is a single TypeScript file with encapsulated CSS and full i18n support. The build output in `src/dashboard/dist/` is served as static files by the backend container.

---

## Federation

openZero supports optional peer federation. Reasoning slices — structured summaries derived from memory — can be exchanged between instances without raw data ever leaving either instance's perimeter. This enables, for example, a `work-Z` and `life-Z` instance to share relevant signals without merging their memory stores or exposing personal data to a work context.

Federation is disabled by default and requires explicit configuration in `.env`. The protocol ships structured reasoning artifacts, not conversation history.

---

## Memory connections

Z's memory currently grows from three sources: your conversations, the outputs crews write as memory points, and the optional calendar and email integrations.

The backend uses a MemorySource plugin architecture. Additional connectors — note vaults, document folders, Slack workspaces, RSS feeds — can be registered as plugins without modifying core services. None of these connectors exist yet as first-party integrations; they are the natural next layer for operators who want Z to know more without telling it manually.

---

## License

MIT License. Copyright (c) 2026 OpenZero Contributors.

You are free to use, modify, and distribute this software under the terms of the MIT License. See the `LICENSE` file at the repository root for the full text.
