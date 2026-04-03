# openZero

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-blue.svg)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/Docker-Compose-blue.svg)](https://docs.docker.com/compose/)

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
