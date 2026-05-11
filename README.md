# openZero

[![Agent Native](https://img.shields.io/badge/Agent--Native-Pure-black.svg)](https://github.com/niklasbrandt/openzero)
[![Low Inference](https://img.shields.io/badge/Inference-Low_Resource_Optimized-orange.svg)](#stack)
[![Privacy First](https://img.shields.io/badge/Privacy-100%25_Local-purple.svg)](#security)
[![Self-Hosted](https://img.shields.io/badge/Deployment-Self--Hosted-blue.svg)](BUILD.md)
[![LLM Agnostic](https://img.shields.io/badge/LLM-Local_%2B_API_Agnostic-FF6B35.svg)](#stack)
[![Dual LLM Tier](https://img.shields.io/badge/Routing-Fast_%2B_Deep_Tier-blueviolet.svg)](#stack)
[![Autonomous Crews](https://img.shields.io/badge/Crews-YAML_Scheduled-brightgreen.svg)](#autonomous-crews)
[![Crew Output](https://img.shields.io/badge/Crew_Output-Planka_Kanban-0079BF.svg)](#autonomous-crews)
[![Web Search](https://img.shields.io/badge/Search-SearXNG_Self--Hosted-3498db.svg)](#stack)
[![Semantic Memory](https://img.shields.io/badge/Memory-Qdrant_Vector-8e44ad.svg)](#memory--learning)
[![Multi-Channel](https://img.shields.io/badge/Messaging-Telegram_%C2%B7_WhatsApp-25D366.svg)](#channels)
[![Voice I/O](https://img.shields.io/badge/Voice-Whisper_%2B_TTS-e74c3c.svg)](#stack)
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

openZero is a sovereign, self-hosted AI that builds a living memory of whatever domain you point it at — a life, a business, a research area, a team — and thinks alongside you there. Every byte stays on your hardware.

---

## In plain terms

You deploy openZero and connect it to your sources: calendar, email, documents, notes, voice, or any data feed you configure. It reads everything, builds a structured memory from it, and from that point forward operates as a context engine for that domain.

Ask it a question over Telegram or WhatsApp and it answers with full historical context — not just what you told it five minutes ago, but what it has observed across weeks or months of input. It knows which decisions were made and when, what has changed recently, and where two pieces of information conflict with each other.

On a schedule it runs autonomous reasoning tasks — called **crews** — that synthesise memory into structured output: briefings, analyses, plans. These arrive as step-by-step walk-throughs you move through at your own pace, or as cards in a self-hosted Kanban board (Planka).

The dashboard opens directly to the **Memory Atlas** — a navigable map of everything the system has learned, with relationships, timelines, decisions, and contradictions all queryable and traceable back to source evidence.

### What it is used for

openZero is domain-agnostic. You define the domain at setup time. One deployment is called an **instance** and is scoped to one domain. Common uses:

| Domain | What the substrate tracks |
| --- | --- |
| Personal life | Goals, habits, health history, journal entries, recurring decisions |
| Solo business or freelance | Client context, project decisions, proposal history, competitive research |
| Research | Sources and contradictions between them, hypothesis evolution, synthesis over time |
| Team operations | Meeting decisions, project state, onboarding context, shared institutional memory |
| Any long-running project | Anything where you spend time re-reading old notes to reconstruct what you already knew |

You can run multiple instances on the same hardware — `life-Z`, `work-Z`, `research-Z`, `team-Z` — each with its own memory, crew schedule, and visual theme. Federation (opt-in) lets instances share curated reasoning slices without exposing raw data.

---

## The problem it solves

**Context collapse.** The information exists — spread across emails, documents, meetings, messages, notes — but reconstructing the right slice at the right moment requires manual search and re-reading. Conventional tools manage tasks or store notes, but leave you as the context engine: you remember that a client changed direction in February, that last quarter's decision was superseded, that two project briefs contradict each other.

openZero inverts this. The substrate is the context engine. You interact with it conversationally, and it surfaces what is relevant, flags what conflicts, and alerts you when a past decision is due for review. You stop managing information and start thinking with it.

---

## How it works

### The substrate

openZero is not a chatbot layered over a file store. It is a **thinking substrate** — a structured memory layer that continuously ingests, relates, and re-examines everything it knows.

When a source is connected, the substrate works in four continuous passes:

1. **Ingest** — raw content is chunked, embedded, and stored in Qdrant, an open-source vector database that enables semantic retrieval rather than keyword search
2. **Relate** — entities are extracted and linked as nodes in a typed knowledge graph: people, projects, decisions, topics, events, facts
3. **Weight** — each node and relationship carries a confidence score, updated as confirming or contradicting evidence accumulates
4. **Surface** — changes, contradictions, and due decisions are tracked in structured tables and surfaced on demand or on a schedule

Nothing is summarised away at ingest. The substrate retains evidence and re-derives its structure as new information arrives.

### Crews — the reasoning layer

The substrate holds memory. **Crews** reason over it.

A crew is a YAML-defined team of specialist agent characters that executes a multi-step analysis and delivers structured output. Each character has a defined role and sees the output of the previous step. No code changes are required to add a crew — drop a new entry into `agent/crews.yaml`, restart the backend, and it is live.

Crews run on a schedule (daily, weekly, monthly, quarterly, or annually) or are triggered by message keywords. Output is written to two layers simultaneously:

- **Planka** — a self-hosted Kanban board used as the operational output layer (cards, lists, projects)
- **Qdrant** — key findings are stored back into the substrate as tagged memory points, so future crews and conversations build on accumulated reasoning rather than re-ingesting raw data

Briefing crews deliver output as **walk-throughs**: step-by-step summaries you move through one stop at a time, in the dashboard or via Telegram and WhatsApp.

### The Memory Atlas

The **Memory Atlas** is the primary view in the dashboard and the main interface for reading and interacting with the substrate's memory. Think of it as a live, navigable knowledge map of everything the system has learned — not a file browser or task list, but a structured, evidence-linked view with full traceability back to source.

Through the Atlas you can:

- **Browse nodes** — every entity the substrate has identified: people, projects, topics, events, facts
- **Read spines** — the substrate's inferred standing beliefs about your domain (e.g. "primary constraint is X", "recurring focus is Y"), each with a confidence score and the evidence behind it
- **Navigate timelines** — a chronological view of what the substrate has learned and when
- **Inspect decisions** — past decisions with their context, outcome, and revisit date; flagged automatically when a revisit is due
- **Trace contradictions** — conflicting signals held open until resolved; raised by the `contradiction_detector` crew from periodic memory scans
- **Walk through briefings** — scheduled or ad-hoc briefings delivered as sequenced stops, navigable with arrow keys or swipe
- **Ask why** — press `?` on any node, spine, or decision to see its source evidence, confidence derivation, and the reasoning path behind it
- **Explore the inferred domain** — a substrate-generated description of what this instance appears to be about, which you can confirm or refine

A persistent **diff ribbon** at the top of every page shows what the substrate has learned or changed since you last opened it — so you always know what is new without having to search.

### Two-tier inference

Every request is routed through two LLM tiers to minimise latency and cloud dependency:

- **Fast tier** — a small local model (llama.cpp or any OpenAI-compatible local endpoint) handles routing decisions, binary classifications, keyword extraction, and short-form answers. Runs in milliseconds with no cloud involvement.
- **Deep tier** — a larger model (local or cloud API) handles reasoning-heavy tasks: strategic analysis, contradiction resolution, synthesis, briefing generation. Requires explicit human-in-the-loop approval when called from the dashboard.

No cloud model is called by default. Cloud inference is opt-in via `CLOUD_LLM_URL` in `.env`.

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

Z is grounded in your domain through two local directories that are never committed:

```bash
cp -r personal.example/ personal/   # about-me, business, health, requirements
cp -r agent.example/   agent/       # agent-rules, crews.yaml, kanban config
```

These files are injected into every system prompt alongside live memory retrieval.

---

## Messaging channels

Both Telegram and WhatsApp route to the same Z agent with full context: memory retrieval, personal context, and LLM generation.

### Telegram commands

| Command            | Effect                                          |
| ------------------ | ----------------------------------------------- |
| `/start`           | Onboarding message and menu                     |
| `/help`            | List all commands (alias `/commands`)           |
| `/day`             | Daily briefing                                  |
| `/week`            | Weekly briefing                                 |
| `/month`           | Monthly briefing                                |
| `/quarter`         | Quarterly briefing                              |
| `/year`            | Annual briefing                                 |
| `/search <query>`  | Semantic memory search                          |
| `/memories`        | Browse stored memory points                     |
| `/learn <text>`    | Store a fact to long-term memory (alias `/add`) |
| `/unlearn <query>` | Remove a memory point (with confirmation)       |
| `/purge`           | Wipe memory (requires confirmation)             |
| `/board`           | Show the active Planka board                    |
| `/tree`            | Project / board / list tree                     |
| `/remind <text>`   | Schedule a one-off or repeating reminder        |
| `/custom <spec>`   | Register a persistent scheduled job             |
| `/protocols`       | List active Z protocols                         |
| `/personal`        | Show personal context summary                   |
| `/agent`           | Show agent rules summary (alias `/skills`)      |
| `/think <query>`   | Force the deep-tier model with HITL approval    |
| `/crew <id>`       | Trigger a named crew immediately                |
| `/crews`           | List crews and their status                     |
| `/status`          | Deep integration health check                   |

### WhatsApp

Free-form messages work identically — every message goes through the full Z context pipeline. There are no slash commands; just write naturally.

---

## Crews

Crews are YAML-defined multi-character agent tasks in `agent/crews.yaml`. They run on a schedule, fire in response to messages, or get triggered manually. No code changes needed to add one — define the crew, restart the backend, and it is live.

### Routing

On every incoming message Z decides whether to answer directly or delegate to a specialist crew. The same logic applies across all channels. It has three layers, evaluated in order:

1. **Crew ID match** — if the crew's own ID appears as a whole word in the message (e.g. "coach, am I on track this week?"), Z routes to it immediately with no further evaluation.
2. **Keyword routing** — each crew can declare a `keywords` list. If any keyword matches (word-boundary, language-aware), Z routes to that crew directly. Keywords are automatically translated to the user's configured language on first use and cached.
3. **LLM routing** — if neither of the above matches, Z passes the message to the fast-tier model with the full crew registry as context. The model returns the best-fit crew ID, or `none` to handle the message itself.

The routing decision is always logged, so you can tune keywords or add crews without touching code.

For example, the `nutrition` crew listens for words like `recipe`, `meal`, `cook`, `grocery`, `macro` — so sending "make me a high-protein dinner recipe for tonight" routes directly to it, runs the full multi-character crew, and outputs a structured Planka board with the recipe and shopping list. A message like "what should I eat to hit 180g protein today?" contains no exact keyword but the fast-tier model correctly identifies `nutrition` as the best crew and delegates accordingly.

### Panels

When a primary crew is selected, Z automatically identifies domain-similar candidates by computing word-overlap (Jaccard similarity) across crew names, descriptions, and character roles at startup — no manual configuration required. Each candidate is offered a fast yes/no relevance gate (a single token from the local model). Any crew that judges the query relevant joins the response as a secondary panel. Secondaries receive the accumulated output as context and add their perspective without repeating what is already covered. The result is a single reply composed of up to three crew sections, each attributed to its crew. Crews that find the query outside their scope stay silent — so a recipe request pulls in nutrition and possibly health (dietary constraints), but not fitness.

To explicitly prevent a specific crew from ever joining a panel, add `panel_exclude` to its YAML config.

**Example — one message, two crews, one board:**

> "I want to drop 3 kg over the next 6 weeks while keeping my training load up"

Z routes this to `fitness` (primary crew). The auto-similarity check identifies `nutrition` as a high-overlap candidate. Both crews submit to the relevance gate — both opt in. `fitness` produces a 6-week progressive programme; `nutrition` adds a calorie-deficit meal plan aligned to the training schedule. The full panel output is saved automatically as structured cards in the `Fitness` Planka board under a `Weekly Plan` list — no commands needed.

### Memory

Every crew writes to two memory layers:

- **Planka** — structured, human-readable output. Each crew creates or updates cards on its own board: recipes as cards with ingredient lists and cook steps, workout plans as weekly list layouts, research findings as titled task cards. This is the operational layer — you can act on it directly, modify it, or hand it off to a team.
- **Qdrant** — semantic vector memory. Key findings, preferences, and progress checkpoints are stored as tagged memory points (e.g. `[fitness-plan]`, `[nutrition-weekly]`) and retrieved automatically in future prompts. A crew running next Monday can recall what it decided last Monday without you repeating yourself.

You can ask Z "what did the coach crew say last week?" and it will retrieve the relevant memory points, while the original Planka card remains separately available as a reference artifact.

### Adding a crew

Drop a new entry into `agent/crews.yaml` and restart the backend — no code changes required:

```yaml
- id: "my-crew" # unique slug, used in /crew commands and routing
  name: "My Crew Display Name"
  description: "One sentence describing what this crew does."
  group: "private" # groups: basic | business | education | private
  type: "agent"
  feeds_briefing: "/week" # or /day | /month | /quarter — omit for cron-only
  briefing_day: "MON" # MON–SUN, required when feeds_briefing is /week
  # schedule: "0 14 * * 2"   # alternative: fixed cron, 5-field syntax
  keywords: # optional — word-boundary matches route here directly
      - trigger word
  # panel_exclude:            # optional — crew IDs blocked from co-running here
  #   - other-crew-id
  instructions: |
      Describe what the crew should do. Reference personal/health.md, personal/about-me.md,
      or personal/requirements.md for grounding. End instructions with explicit Planka
      persistence steps (CREATE_PROJECT / CREATE_BOARD / CREATE_LIST / CREATE_TASK).
  characters:
      - name: "The Role Name"
        role: "One sentence describing this character's specific function."
      - name: "The Second Role"
        role: "What this character contributes that the first does not."
```

Scheduling: `feeds_briefing: /day|/week|/month|/quarter` (briefing-relative, recommended) · `schedule: "0 7 * * *"` (fixed cron)

Triggers: briefing-relative · fixed cron · manual via `/crew <id>` on Telegram or dashboard

---

## Intent routing & semantic understanding

Z processes every incoming message through a layered interception pipeline before — and often instead of — calling a large language model. The goal is deterministic, reliable execution without hallucination, at sub-second latency for the majority of board operations.

### Interception pipeline

Steps are evaluated in order. Each step may short-circuit and return a response without reaching the next. Step numbers are fractional so that new intercept points can be inserted between existing ones without renumbering the chain.

| Step | Name                    | What it does                                                                                                                                                                                                                                                                                          |
| ---- | ----------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| −1   | Audit                   | Strips prompt-injection attempts from user input                                                                                                                                                                                                                                                      |
| 0    | Recall                  | Injects relevant Qdrant memory points into context                                                                                                                                                                                                                                                    |
| 0.5  | Structural intent       | Fast-path regex match across all known verb families in all 11 languages                                                                                                                                                                                                                              |
| 0.52 | Semantic board fallback | When step 0.5 finds no match, the fast-tier model is asked a single constrained binary question with a forced output format (`SORT_BOARD:<name>` or `NO`). Binary classification on a fixed schema is well within a small model's capability and avoids a cloud round-trip on every unmatched message |
| 0.55 | Board context injection | Fetches the full live state of the relevant Planka board (lists + card titles) and injects it as grounding context                                                                                                                                                                                    |
| 0.6  | Ambient capture         | Routes ambient notes, facts, and reminders to the capture pipeline                                                                                                                                                                                                                                    |
| 1    | Crew routing            | Keyword match → LLM crew classification → specialist crew                                                                                                                                                                                                                                             |
| 2    | LLM reply               | Full generation pass if no earlier step matched                                                                                                                                                                                                                                                       |

### Pre-existing deterministic intents

The following verb families have been handled deterministically since before this session — they never reach the LLM:

- `MOVE_CARD` / `MOVE_BOARD` — move a card or board by name
- `RENAME_CARD` / `RENAME_LIST` / `RENAME_PROJECT` / `RENAME_BOARD`
- `DELETE_CARD` / `DELETE_LIST` / `DELETE_BOARD` / `DELETE_PROJECT`
- `ARCHIVE_CARD` / `MARK_DONE`
- `CREATE_LIST` / `CREATE_CARD` (single form)
- `BOARD_ITEM_ADD` (single form) — "new task: meditation" adds to the correct list automatically

All of these are pattern-matched across 11 languages (EN, DE, ES, FR, PT, RU, JA, ZH, KO, HI, AR) with Unicode word-boundary awareness. Intent classification runs in microseconds.

### Ambient semantic capabilities

**`BOARD_ITEM_ADD` — bulk creation and semantic type classification**

A single message can create multiple items at once using colon-list syntax:

> "new life goals: home, eating garden, financial freedom"

The router parses the colon-list, then classifies each title through `_LIST_NOUNS` — a frozenset of intent-bearing words (`goal`, `dream`, `wish`, `aspiration`, `vision`, `project`, `area`, `theme`, `category`, `topic`) — against task-bearing words (`item`, `task`, `todo`, `action`, `step`, `note`). Items whose title contains a LIST noun become Planka lists; everything else becomes a card. No LLM involvement, no ambiguity.

**`SORT_BOARD` — fully deterministic board reorganisation**

When you ask Z to sort, organise, or clean up a board, the operation runs in three deterministic steps:

1. All existing lists are sorted alphabetically via direct Planka PATCH calls.
2. A fast-tier model produces a compact (~80 token) JSON reorganisation plan: `{"new_lists": [...], "moves": {"card title": "target list"}}`. No prose, no narrative — only machine-parseable structure.
3. The backend executes the plan deterministically: creates any new lists that do not exist, moves each card to its target list via the Planka API. The LLM never writes a confirmation message; the backend surfaces every create/move result directly.

This replaces what previously required a 300-second LLM generation timeout with a sub-10-second structured API sequence.

**Step 0.52 — semantic board fallback**

When no pattern in step 0.5 matches, and the message appears board-related, a fast-tier model is asked a single constrained binary question:

> "Is this message asking to reorganise, sort, or clean up a Planka board? Reply SORT_BOARD:<board name> or NO."

Binary classification against a fixed output schema is well within a small model's capability. Using the cloud model here would add latency to every unmatched message regardless of complexity. If the model returns a `SORT_BOARD:` prefix, the router constructs a `StructuralIntent` and dispatches it with the same deterministic path as a regex match.

**Anti-hallucination enforcement**

The LLM system prompt includes an explicit rule: Z must never confirm an action in the past tense. Confirmations are generated by the action execution layer from actual API responses, not by the model describing what it wishes it had done. Every result — success and failure alike — is surfaced to the user.

### What this achieves

- Natural board management without requiring exact command syntax or knowledge of action tags.
- Implicit intent recognition in colloquial phrasing across 11 languages.
- Sub-second responses for structural mutations — no LLM round-trip, no timeout risk.
- Reliable execution — deterministic Planka API calls, not generated prose, drive every state change.
- The LLM is reserved for what it is good at: reasoning, synthesis, and ambiguous open-ended tasks. Everything with a deterministic interpretation is handled without it.

---

## Dashboard

21 Shadow DOM Web Components — no React, Vue, or Angular.
38 HSLA theme presets, live switching.
WCAG 2.1 AA, 2 UI languages (EN, DE), keyboard-navigable.

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
│   │     ├── Email Ingestion (opt-in)         │   │
│   │     ├── Briefing + Walkthrough Engine    │   │
│   │     └── Dashboard API (REST)             │   │
│   └──────────────────────────────────────────┘   │
│                                                  │
│   ┌───────────┐  ┌─────────┐  ┌──────────────┐  │
│   │ PostgreSQL│  │  Qdrant │  │  llama.cpp   │  │
│   │  (data)   │  │ (memory)│  │  (llm-local) │  │
│   └───────────┘  └─────────┘  └──────────────┘  │
│                                                  │
│   ┌───────────┐  ┌─────────┐  ┌──────────────┐  │
│   │  Whisper  │  │   TTS   │  │   Planka     │  │
│   │  (STT)    │  │ (speech)│  │  (Kanban)    │  │
│   └───────────┘  └─────────┘  └──────────────┘  │
│                                                  │
│   ┌───────────┐  ┌─────────┐  ┌──────────────┐  │
│   │  SearXNG  │  │  Crews  │  │   Redis      │  │
│   │  (search) │  │ (.yaml) │  │  (cache)     │  │
│   └───────────┘  └─────────┘  └──────────────┘  │
└──────────────────────────────────────────────────┘
```

All services share the `internal` Docker network. The LLM container exposes only its inference port, and every backing store (PostgreSQL, Qdrant, Redis, Planka) is reached through the FastAPI backend, which holds all credentials.

### Web search

When the cloud tier model needs current information — news, prices, weather, recent events — it autonomously invokes a web search tool via standard OpenAI function-calling. The search runs against a self-hosted SearXNG instance (meta-search aggregator: Google, Bing, DuckDuckGo, Wikipedia) on the internal Docker network. No external API keys, no third-party services, full data sovereignty. Search queries are PII-sanitized when `CLOUD_LLM_SANITIZE=true`. Controlled by `CLOUD_LLM_TOOLS=true` (default on).

### Compute peer routing

openZero can offload inference to any Tailscale-connected device running Ollama or llama.cpp. Add one line to `.env`:

```
LLM_PEER_CANDIDATES=http://100.x.y.z:11434#MacBook
```

The `#MacBook` fragment sets the display name shown in the dashboard. Multiple candidates are comma-separated. Every 30 seconds, openZero probes all peers with a real inference call (not just a health check), measures actual tokens/s, and promotes the fastest peer automatically — but only if it reaches 80% of the VPS speed. A slower device stays on standby; the dashboard Diagnostics panel shows each peer's name, model, and live tok/s under **Inference Provider** inside the Local tier card.

---

## Security

Security in openZero is defined by an explicit allowlist, not a blocklist. The agent can only perform actions that are declared in its action vocabulary. Everything else is structurally impossible.

### Agent action vocabulary

Z speaks to external systems through a structured set of action tags embedded in its replies. Only tags in this allowlist are parsed and executed; anything outside it is silently ignored. The canonical list lives in `_MUTATING_TAG_RE` in `src/backend/app/services/agent_actions.py`.

| Action                                                            | What it does                                             |
| ----------------------------------------------------------------- | -------------------------------------------------------- |
| `CREATE_PROJECT`                                                  | Creates a Planka project                                 |
| `CREATE_BOARD`                                                    | Creates a Planka board inside a project                  |
| `CREATE_LIST`                                                     | Creates a list on a board                                |
| `CREATE_TASK`                                                     | Creates a card on a list                                 |
| `MOVE_CARD`                                                       | Moves a card to a different list                         |
| `MOVE_BOARD`                                                      | Moves a board to a different project                     |
| `MARK_DONE`                                                       | Marks a card as done                                     |
| `ARCHIVE_CARD`                                                    | Archives a card                                          |
| `APPEND_SHOPPING`                                                 | Appends an item to the shopping list                     |
| `SET_CARD_DESC`                                                   | Sets or updates a card description                       |
| `RENAME_CARD` / `RENAME_LIST` / `RENAME_PROJECT`                  | Renames the matching entity                              |
| `DELETE_CARD` / `DELETE_LIST` / `DELETE_BOARD` / `DELETE_PROJECT` | Hard-deletes the matching entity (sensitive — see below) |
| `SHARE_BOARD` / `SHARE_PROJECT`                                   | Issues a share link                                      |
| `INVITE_USER` / `INVITE_MEMBER`                                   | Invites a collaborator                                   |
| `AMBIENT_CAPTURE` / `AMBIENT_TEACH`                               | Routes ambient input into the capture pipeline           |
| `CREATE_EVENT`                                                    | Creates a calendar event                                 |
| `REMIND`                                                          | Sets a one-off or repeating reminder                     |
| `LEARN`                                                           | Stores a fact to Qdrant long-term memory                 |
| `SCHEDULE_CUSTOM`                                                 | Registers a persistent scheduled job                     |
| `RUN_CREW`                                                        | Triggers a named crew immediately                        |
| `SCHEDULE_CREW`                                                   | Schedules a crew at a cron spec                          |
| `PROXIMITY_TRACK`                                                 | Initiates a task proximity tracking session              |

Destructive actions (`DELETE_*`) are part of the vocabulary, not blocked at the parser layer. They are gated by the human-in-the-loop policy below — the safety guarantee is the HITL queue plus the structured allowlist, not the absence of delete verbs.

### Human-in-the-loop gate

A subset of actions that create persistent state or modify the agent's own behaviour are designated `SENSITIVE_ACTIONS`:

`CREATE_PROJECT` · `CREATE_BOARD` · `CREATE_LIST` · `LEARN` · `SCHEDULE_CUSTOM` · `RUN_CREW` · `SCHEDULE_CREW` · `PROXIMITY_TRACK`

When `require_hitl=True` is set on a reply (configurable per channel and per endpoint), sensitive actions are queued and require user confirmation before execution. Routine actions like `CREATE_TASK`, `MOVE_CARD`, and `CREATE_EVENT` execute immediately.

### Network and infrastructure isolation

- The local LLM container (`llm-local`, llama.cpp) runs on the internal Docker network with no direct access to the database, Qdrant, or Planka. All model calls go through the FastAPI backend, which owns every credential. The fast and deep tiers are routing decisions inside the backend, not separate containers.
- Bearer token required on every API endpoint — no unauthenticated routes.
- The entire stack is reachable only through the Tailscale mesh network. No ports are exposed to the public internet.
- DNS (port 53) is bound to the Tailscale interface only — Pi-hole is not publicly reachable.

### CI security gates

Every push runs the GitHub Actions pipeline:

- `pip-audit` — dependency CVE scan
- `npm audit` — frontend dependency CVE scan
- `bandit` — Python static security analysis
- `trufflehog` — secret leak detection in git history
- `ruff` + `mypy` — Python lint and type safety
- ESLint + `tsc --noEmit` — TypeScript lint and strict type-check
- CodeQL static-analysis pre-flight
- Lighthouse CI audit
- Playwright accessibility audit (WCAG 2.1 AA)
- Docker build smoke-test
- Prompt-injection test suite (`tests/test_security_prompt_injection.py`)
- i18n key parity (`tests/test_i18n_coverage.py`) and live regression tests

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
