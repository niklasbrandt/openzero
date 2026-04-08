# openZero

[![Agent Native](https://img.shields.io/badge/Agent--Native-Pure-black.svg)](https://github.com/niklasbrandt/openzero)
[![Low Inference](https://img.shields.io/badge/Inference-Low_Resource_Optimized-orange.svg)](#stack)
[![Privacy First](https://img.shields.io/badge/Privacy-100%25_Local-purple.svg)](#security)
[![Self-Hosted](https://img.shields.io/badge/Deployment-Self--Hosted-blue.svg)](BUILD.md)
[![LLM Agnostic](https://img.shields.io/badge/LLM-Local_%2B_API_Agnostic-FF6B35.svg)](#stack)
[![Dual LLM Tier](https://img.shields.io/badge/Routing-Fast_%2B_Deep_Tier-blueviolet.svg)](#stack)
[![Autonomous Crews](https://img.shields.io/badge/Crews-YAML_Scheduled-brightgreen.svg)](#autonomous-crews)
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
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

Meet Z — a self-hosted personal AI operating system. Deploy on a VPS or homelab, connect to any inference provider. Your data stays with you.

---

## What it does

openZero is a private, composable AI system built around a single agent named Z. It bundles local LLM inference, semantic long-term memory, a real-time web dashboard, calendar and email intelligence, multi-channel messaging (Telegram, WhatsApp, ...), autonomous background crews, and a Kanban task engine — all running on your own hardware and reachable through a Tailscale private network.

The system is built with no proprietary lock-in: the LLM is swappable (llama.cpp, any OpenAI-compatible endpoint), the memory backend is open-source (Qdrant), and every service is a standard Docker container. Data never leaves your infrastructure unless you explicitly configure an external inference provider.

openZero is not a chatbot wrapper. It is an operational layer for a personal computing life: reading and writing your calendar, triaging your email, managing your projects, scheduling background intelligence tasks, monitoring its own hardware, and speaking to you in any of ten languages.

---

## Quick Start

```bash
git clone https://github.com/your-org/openzero.git
cd openzero
cp config.example.yaml config.yaml && cp .env.example .env
# fill in your domain, secrets, and credentials
docker compose up -d
```

DB migrations run automatically on first boot. Telegram starts as soon as `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` are set. WhatsApp requires a Meta Cloud API webhook — see [BUILD.md](BUILD.md).

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

## Messaging channels

Both Telegram and WhatsApp route to the same Z agent with full context: memory retrieval, personal context, and LLM generation.

### Telegram commands

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

### WhatsApp

Free-form messages work identically — every message goes through the full Z context pipeline. There are no slash commands; just write naturally.

---

## Crew routing

On every incoming message Z decides whether to answer directly or delegate to a specialist crew. The same logic applies across all channels. It has three layers, evaluated in order:

1. **Crew ID match** — if the crew's own ID appears as a whole word in the message (e.g. "hi dependents, ..."), Z routes to it immediately with no further evaluation.
2. **Keyword routing** — each crew in `agent/crews.yaml` can declare a `keywords` list. If any keyword matches (word-boundary, language-aware), Z routes to that crew without invoking the main LLM. Keywords are automatically translated to the user's configured language on first use and cached.
3. **LLM routing** — if neither of the above matches, Z passes the message to the fast-tier model with the full crew registry as context. The model returns the best-fit crew ID, or `none` to handle the message itself.

The routing decision is always logged, so you can tune keywords or add crews without touching code.

For example, the `nutrition` crew listens for words like `recipe`, `meal`, `cook`, `grocery`, `macro` — so sending "make me a high-protein dinner recipe for tonight" routes directly to it, runs the full multi-character crew, and outputs a structured Planka board with the recipe and shopping list. A message like "what should I eat to hit 180g protein today?" contains no exact keyword but the fast-tier model correctly identifies `nutrition` as the best crew and delegates accordingly.

### Crew panels

Crews can declare `intersects_with` — a list of related crew IDs whose domains often overlap. When a primary crew is selected and has `intersects_with` configured, each listed crew is offered a fast yes/no relevance gate (a single token from the local model). Any crew that judges the query relevant to its domain joins the response as a secondary panel. Secondaries receive the accumulated output as context and add their perspective without repeating what is already covered. The result is a single reply composed of up to three crew sections, each attributed to its crew. Crews that find the query outside their scope stay silent — so a recipe request pulls in nutrition and possibly health (dietary constraints), but not fitness.

---

## Autonomous crews

Crews are YAML-defined agent task sequences in `agent/crews.yaml`. No code changes needed to add one.

```yaml
- id: "flow"
  name: "Productivity, Stagnation & Deep Work Engine"
  description: "Unblocks stuck tasks and schedules deep work execution."
  group: "basic"
  type: "agent"
  feeds_briefing: "/week"
  briefing_day: "MON"
  instructions: |
    Scan Planka boards for tasks that lack recent activity.
    Propose actionable micro-tasks and identify optimal calendar blocks for deep work.
  characters:
    - name: "The Systems Auditor"
      role: "Flags deadlocked boards, deadline drift, and WIP violations."
    - name: "The Unblocker Strategist"
      role: "Outputs micro-tasks under 25 min to break inertia."
    - name: "The Session Architect"
      role: "Schedules dedicated deep work blocks into ideal energy windows."
```

```yaml
- id: "nutrition"
  name: "Precision Culinary & Macro Optimizer"
  description: "Generates weekly meal boards, recipes, and shopping lists."
  group: "private"
  type: "agent"
  feeds_briefing: "/week"
  briefing_day: "SUN"
  keywords:
    - recipe
    - meal
    - cook
    - grocery
    - macro
    - calories
    - ingredient
    - shopping list
  intersects_with:
    - health
    - fitness
  instructions: |
    Build comprehensive meal plans adhering to constraints in personal/health.md.
    Use metric units. Output deduplicated shopping checklists.
    Persist all output to Planka — board structure should fit the content.
  characters:
    - name: "The Clinical Nutritionist"
      role: "Strictly enforces health.md constraints (allergies, macros, exclusions)."
    - name: "The Production Head Chef"
      role: "Builds sequential, batch-optimized cooking instructions."
    - name: "The Shopping Logistics Officer"
      role: "Deduplicates all recipes into one aisle-mapped grocery checklist."
```

Scheduling: `feeds_briefing: /day|/week|/month|/quarter` (briefing-relative, recommended) · `schedule: "0 7 * * *"` (fixed cron)

Triggers: briefing-relative · fixed cron · manual via `/crew <id>` on Telegram or dashboard

---

## Dashboard

17 Shadow DOM Web Components — no React, Vue, or Angular.
38 HSLA theme presets, live switching, goo-mode elastic animations.
WCAG 2.1 AA, 10 languages, keyboard-navigable.

---

## Stack

```
┌──────────────────────────────────────────────────┐
│                 Your Devices                     │
│      (Phone / Laptop / Tablet)                   │
│                                                  │
│   Telegram     ──── Chat, Voice, Commands        │
│   WhatsApp     ──── Chat, Commands               │
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
│   │     ├── Telegram (long-polling)          │   │
│   │     ├── WhatsApp Cloud API (webhooks)    │   │
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

### Compute peer routing

openZero can offload inference to any Tailscale-connected device running Ollama or llama.cpp. Add one line to `.env`:

```
LLM_PEER_CANDIDATES=http://100.x.y.z:11434#MacBook
```

The `#MacBook` fragment sets the display name shown in the dashboard. Multiple candidates are comma-separated. Every 30 seconds, openZero probes all peers with a real inference call (not just a health check), measures actual tokens/s, and promotes the fastest peer automatically — but only if it reaches 80% of the VPS speed. A slower device stays on standby; the dashboard Diagnostics panel shows each peer's name, model, and live tok/s under **Inference Provider** inside the Local tier card.

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
