# openZero

[![Agent Native](https://img.shields.io/badge/Agent--Native-Pure-black.svg)](https://github.com/niklasbrandt/openzero)
[![No GPU Required](https://img.shields.io/badge/No_GPU-Required_(Cloud_Optional)-orange.svg)](#stack)
[![Privacy First](https://img.shields.io/badge/Privacy-100%25_Local-purple.svg)](#security)
[![Self-Hosted](https://img.shields.io/badge/Deployment-Self--Hosted-blue.svg)](BUILD.md)
[![LLM Agnostic](https://img.shields.io/badge/LLM-Local_%2B_API_Agnostic-FF6B35.svg)](#stack)
[![Dual LLM Tier](https://img.shields.io/badge/Routing-Fast_%2B_Deep_Tier-blueviolet.svg)](#stack)
[![Autonomous Crews](https://img.shields.io/badge/Crews-40%2B_YAML_Scheduled-brightgreen.svg)](#autonomous-crews)
[![Crew Output](https://img.shields.io/badge/Crew_Output-Planka_Kanban-0079BF.svg)](#autonomous-crews)
[![Semantic Memory](https://img.shields.io/badge/Memory-Qdrant_Vector-8e44ad.svg)](#memory--learning)
[![Multi-Channel](https://img.shields.io/badge/Messaging-Telegram_%C2%B7_WhatsApp-25D366.svg)](#channels)
[![Voice I/O](https://img.shields.io/badge/Voice-Whisper_%2B_TTS-e74c3c.svg)](#stack)
[![Email Intelligence](https://img.shields.io/badge/Email-Rule_Engine-informational.svg)](#integrations)
[![DNS Filtering](https://img.shields.io/badge/DNS-Pi--hole_Builtin-c0392b.svg)](#stack)
[![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5-3178C6?logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![Vite](https://img.shields.io/badge/Vite-6-646CFF?logo=vite&logoColor=white)](https://vitejs.dev/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Redis](https://img.shields.io/badge/Redis-7.4-DC382D?logo=redis&logoColor=white)](https://redis.io/)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)](docker-compose.yml)
[![Tailscale](https://img.shields.io/badge/Zero_Trust-Tailscale-black?logo=tailscale&logoColor=white)](https://tailscale.com/)
[![WCAG 2.1 AA](https://img.shields.io/badge/Accessibility-WCAG%202.1%20AA-teal.svg)](https://www.w3.org/TR/WCAG21/)
[![GitHub Actions](https://img.shields.io/badge/CI-GitHub_Actions-2088FF?logo=githubactions&logoColor=white)](.github/workflows)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

Meet Z — a self-hosted personal AI operating system. Deploy on a VPS or homelab, connect to any inference provider. Your data stays with you.

---

## What it does

openZero is a private, composable AI system built around a single agent named Z. It bundles local LLM inference, semantic long-term memory, a real-time web dashboard, calendar and email intelligence, multi-channel messaging (Telegram, WhatsApp, ...), autonomous background crews, and a Kanban task engine — all running on your own hardware and reachable through a Tailscale private network.

The system is built with no proprietary lock-in: the LLM is swappable (llama.cpp, any OpenAI-compatible endpoint), the memory backend is open-source (Qdrant), and every service is a standard Docker container. Data never leaves your infrastructure unless you explicitly configure an external inference provider.

openZero is not a chatbot wrapper. It is an operational layer for a personal computing life: reading and writing your calendar, triaging your email, managing your projects, scheduling background intelligence tasks, monitoring its own hardware, and speaking to you in any of ten languages.

---

## Stack

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
│   └──────────────┬───────────────────────────┘   │
│                  ▼                               │
│   ┌──────────────────────────────────────────┐   │
│   │   FastAPI Backend + APScheduler          │   │
│   │     ├── Telegram Bot (long-polling)      │   │
│   │     ├── Semantic Action Tag Engine       │   │
│   │     ├── Email Polling + Rule Engine      │   │
│   │     ├── Morning Briefing Generator       │   │
│   │     └── Dashboard API (REST)             │   │
│   └──────────────────────────────────────────┘   │
│                                                  │
│   ┌───────────┐  ┌─────────┐  ┌──────────────┐  │
│   │ PostgreSQL│  │  Qdrant │  │  llama.cpp   │  │
│   │  (data)   │  │ (memory)│  │ (2-tier LLM) │  │
│   └───────────┘  └─────────┘  └──────────────┘  │
│                                                  │
│   ┌───────────┐  ┌─────────┐  ┌──────────────┐  │
│   │  Whisper  │  │   TTS   │  │   Planka     │  │
│   │  (STT)    │  │ (speech)│  │  (Kanban)    │  │
│   └───────────┘  └─────────┘  └──────────────┘  │
│                                                  │
│   ┌───────────┐                ┌──────────────┐  │
│   │   Crews   │                │   Redis      │  │
│   │  (.yaml)  │                │  (cache)     │  │
│   └───────────┘                └──────────────┘  │
└──────────────────────────────────────────────────┘
```

Two Docker networks: `internal` (all services) and `llm` (isolated inference). The LLM container cannot reach the database or memory stores directly.

---

## Quick Start

```bash
git clone https://github.com/your-org/openzero.git
cd openzero
cp config.example.yaml config.yaml && cp .env.example .env
# fill in your domain, secrets, and credentials
docker compose up -d
```

DB migrations run automatically on first boot. The Telegram bot starts as soon as `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` are set.

See [BUILD.md](BUILD.md) for a complete variable reference.

---

## Personal context

Z is grounded in your life through two local directories that are never committed:

```bash
cp -r personal.example/ personal/   # about-me, business, health, requirements
cp -r agent.example/   agent/       # agent-rules, crews.yaml, kanban config
```

These files are injected into every system prompt alongside live memory retrieval.

---

## Telegram commands

| Command           | Effect                        |
| ----------------- | ----------------------------- |
| `/briefing`       | Morning digest                |
| `/memory <query>` | Semantic memory search        |
| `/task <text>`    | Create a Planka card          |
| `/calendar`       | Upcoming events               |
| `/email`          | Inbox summary                 |
| `/crew <name>`    | Trigger a crew immediately    |
| `/crews`          | List crews and status         |
| `/status`         | Hardware and container health |
| `/lang <code>`    | Switch language               |

Free-form messages use full context: memory retrieval, personal context, and LLM generation.

---

## Autonomous crews

Crews are YAML-defined task sequences in `agent/crews.yaml`. No code changes needed to add one.

```yaml
- name: daily_briefing
  schedule: "0 7 * * *"
  steps: [weather, calendar, email, memory_summary]
```

Triggers: `cron` · `interval` · `on: <event>` · manual via Telegram or dashboard

---

## Dashboard

17 Shadow DOM Web Components — no React, Vue, or Angular.
38 HSLA theme presets, live switching, goo-mode elastic animations.
WCAG 2.1 AA, 10 languages, keyboard-navigable.

---

## Security

- LLM network-isolated from all data stores
- Bearer token required on every API endpoint
- 268 prompt injection tests across 25 attack categories run in CI
- 11-gate CI pipeline: `pip-audit`, `ruff`, `mypy`, `bandit`, `trufflehog`, regression, i18n, accessibility

---

## Development

```bash
bash scripts/dev.sh          # hot-reload backend + dashboard

pytest tests/ -v             # full suite
pytest tests/test_security_prompt_injection.py -v
pytest tests/test_i18n_coverage.py -v

cd src/dashboard && npm run dev

# deploy
git add -A && git commit -m "msg" && git push && bash scripts/sync.sh
```

---

## License

MIT. See [LICENSE](LICENSE).

openZero is personal infrastructure. You run it, you own it.
