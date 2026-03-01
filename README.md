# openZero

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![Self-Hosted](https://img.shields.io/badge/Deployment-Self--Hosted-blue.svg)](./BUILD.md)
[![Privacy First](https://img.shields.io/badge/Privacy-100%25_Local-purple.svg)](#security-and-privacy)
[![Agent Native](https://img.shields.io/badge/Agent--Native-Pure-black.svg)](https://github.com/niklasbrandt/openzero)

## Personal AI Operating System

openZero is a self-hosted agentic platform built for absolute data sovereignty. It synchronizes projects, calendars, and communications within a private infrastructure. The system automates tasks, transcribes voice notes, and coordinates schedules without third party data leakage.

The platform is personified as **Z**, an autonomous operator. Z focuses on building, organizing, and executing. It maintains a persistent memory of user preferences and long-term goals, ensuring interactions remain grounded in actual history.

Every morning, the system delivers a local briefing summarizing priority tasks and family commitments. Users control the environment via a visual dashboard or a mobile Kanban app, secured inside a Zero Trust network. Interaction occurs primarily through a mobile messenger bot or the integrated dashboard chat UI.

## What it does

The system runs 24/7 on a remote server or local homelab. It links email, calendars, and memory without corporate oversight.

* **Security:** Everything stays sealed behind a Tailscale VPN. Traefik handles internal TLS and Pi-hole sinkholes outbound telemetry. Public ports do not exist.
* **The Hub:** A central board pulls high-priority tasks from all other projects, highlighting exactly what needs attention today.
* **Unified Scheduling:** Z coordinates routines and social milestones on a single timeline to protect deep work blocks.
* **Local Intelligence:** Ollama runs Llama 3 models on local hardware. Cloud reasoning is only engaged via a "Disclosure Proposal" workflow for shared memories.
* **Voice and Text:** Voice notes allow local transcription via Whisper.
* **Multi-Modal Briefings:** Local TTS summarizes the day in a high quality voice note.

## Architecture

The stack focuses on performance and privacy:

* **Agent-Native Engineering:** Built with LangGraph. Z acts as the core autonomous operator, using multi-step planning loops to command and evolve the environment. It is built to be interacted with primarily by agents.
* **Memory:** Qdrant stores semantic vectors. Retrieval depends on meaning rather than keywords.
* **Tasking:** Planka provides the visual Kanban engine and runs as a secure PWA.
* **Network:** Traefik manages routing and Pi-hole blocks tracking. Tailscale secures the perimeter.
* **Async Execution:** Redis handles the task queue. Background reasoning keeps the UI responsive.

## Tech Stack

| Component | Technology | Management Value |
|:---|:---|:---|
| **Core OS** | ![Ubuntu](https://img.shields.io/badge/Ubuntu-E9433F?style=flat&logo=ubuntu&logoColor=white) ![Python](https://img.shields.io/badge/Python-3776AB?style=flat&logo=python&logoColor=white) ![Docker](https://img.shields.io/badge/Docker-2496ED?style=flat&logo=docker&logoColor=white) | Stable, containerized foundation using Python and Linux. |
| **Agent-Native Logic** | ![Ollama](https://img.shields.io/badge/Ollama-black?style=flat) ![LangGraph](https://img.shields.io/badge/LangGraph-orange?style=flat) | Local Llama 3 models orchestrated via agent-native state machines. |
| **Storage** | ![PostgreSQL](https://img.shields.io/badge/PostgreSQL-4169E1?style=flat&logo=postgresql&logoColor=white) ![Qdrant](https://img.shields.io/badge/Qdrant-red?style=flat) | Relational data paired with high-dimensional vector memory. |
| **Execution** | ![Redis](https://img.shields.io/badge/Redis-DC382D?style=flat&logo=redis&logoColor=white) ![Celery](https://img.shields.io/badge/Celery-37814A?style=flat&logo=celery&logoColor=white) | Asynchronous task delegation and high-speed message brokering. |
| **Networking** | ![Traefik](https://img.shields.io/badge/Traefik-2496ED?style=flat&logo=traefik&logoColor=white) ![Tailscale](https://img.shields.io/badge/Tailscale-4A23B6?style=flat&logo=tailscale&logoColor=white) | Zero Trust perimeter with automated internal routing and TLS. |
| **Observability** | ![Pi-hole](https://img.shields.io/badge/Pi--hole-96060C?style=flat&logo=pi-hole&logoColor=white) | Mandatory DNS sinkhole to identify and block container telemetry. |
| **Tasking** | ![Planka](https://img.shields.io/badge/Planka-blue?style=flat) | Self-hosted Kanban engine accessible as a mobile PWA. |
| **Voice** | ![Whisper](https://img.shields.io/badge/Whisper-black?style=flat) ![TTS](https://img.shields.io/badge/Coqui_TTS-green?style=flat) | Local speech-to-text and high-quality audio generation. |


```
┌─────────────────────────────────────────────┐
│               Your Devices                  │
│    (Phone / Laptop / Tablet)                │
│                                             │
│    Messenger / Dashboard ── Chat with AI    │
│    Planka PWA    ──── Kanban Board          │
└──────────────┬───────────────────────────────┘
               │  Tailscale VPN (encrypted)
               ▼
┌─────────────────────────────────────────────┐
│                VPS Provider                 │
│                                             │
│    ┌─────────────────────────────────────┐  │
│    │        Traefik / Pi-hole            │  │
│    └─────────────────┬───────────────────┘  │
│                      ▼                      │
│    ┌─────────────────────────────────────┐  │
│    │  FastAPI Backend / LangGraph Agent  │  │
│    │    ├── Messenger Bot (polling)      │  │
│    │    ├── Redis Task Queue             │  │
│    │    └── LLM Client → Ollama          │  │
│    └─────────────────────────────────────┘  │
│                                             │
│    ┌──────────┐  ┌────────┐  ┌──────────┐   │
│    │ Postgres │  │ Qdrant │  │  Ollama  │   │
│    │ (data)   │  │(memory)│  │   (AI)   │   │
│    └──────────┘  └────────┘  └──────────┘   │
│                                             │
│    ┌──────────┐  ┌────────┐                 │
│    │ Whisper  │  │  TTS   │ ← Voice Engines │
│    │ (STT)    │  │ (Audio)│                 │
│    └──────────┘  └────────┘                 │
│                                             │
│    ┌──────────┐  ┌────────┐                 │
│    │  Planka  │  │ Redis  │ ← Pub/Sub &     │
│    │(Tasking) │  │(Queue) │    Storage      │
│    └──────────┘  └────────┘                 │
│                                             │
│    External APIs:                           │
│     → API via Background Async Worker       │
└─────────────────────────────────────────────┘
```

## Commands

| Command | Description |
| :--- | :--- |
| `/help` | Display this overview of operator controls. |
| `/start` | System status check and heartbeat. |
| `/day` | Proactive morning briefing (Contextual summary). |
| `/week` | Strategic review of all projects and roadmaps. |
| `/month` | High-level 30-day mission review. |
| `/quarter` | Strategic 90-day review and roadmap planning. |
| `/custom` | Create a persistent scheduled task/turnus (e.g. every Monday at 10am). |
| `/year` | Yearly goal setting based on project themes. |
| `/tree` | Full life hierarchy and workspace overview. |
| `/think` | Complex reasoning with human-in-the-loop approval. |
| `/search` | Conceptual search of the semantic knowledge vault. |
| `/memories` | List all core knowledge currently in permanent memory. |
| `/unlearn` | Refine Z's internal context by evolving past points in the vault. |
| `/add` | Commit specific facts to Z's permanent knowledge vault. |
| `/remind` | Set a periodic reminder with natural language (e.g., 2x an hour for 4h). |
| `/protocols` | Inspect Z's agentic tools and Semantic Action Tags. |
| `/wipe_memory` | Clear long-term LLM recall (Purge current chat context). |

## Memory & Intelligence Principles

Z follows a strict **"Core Knowledge, not Noise"** logic for long-term intelligence:

*   **Permanent Memory:** Preferences, family members, project goals, and life milestones are committed to the **Semantic Vault** (Qdrant).
*   **Transient Traffic:** Status updates ("I'm at the store"), transient chat history, and bot responses are **intentionally ignored** by the memory vault to prevent "hallucination loops" and context pollution.
*   **The Guardrail:** Automatic filtering via a local reasoning pass ensures trivialities like "thanks" or "hello" never hit the vault.
*   **Manual Control:** Use `/add` to explicitly override the filter when you have critical context Z must never forget.

## Maintenance

### Backups and Migration

Environment variables and raw Docker volumes require archiving to protect data integrity.

* **Archiving:** Stop services via `docker compose stop` before creating tarballs of `.env` and named volumes (pgdata, qdrant_storage, planka_data).
* **Moving Data:** To migrate, clone the repo on the new host, transfer the `.env` files, and extract volume archives into the new Docker environment.
* **Integrity:** Local, encrypted backups with a 30 day retention policy are recommended.

## Setting it up

A VPS with 24GB RAM or a local Mac Mini/homelab is recommended.

1. **Deploy:** Run `docker compose up -d`.
2. **Secure:** Link the server to the Tailscale network.
3. **Configure:** Connect calendars and define the user profile.

### Deployment Expectations

First-time builds or updates following major architectural changes incur significant durations:
*   **Cold Builds:** Using `--no-cache` or major dependency updates (e.g., adding LangGraph, Redis) can take 45–60 minutes for `pip` resolution.
*   **Media Engines:** Pulling the voice engines (Whisper and Coqui TTS) requires downloading approximately 6GB of data. Depending on network speed, this may total 2–3 hours for a complete first-time setup.
*   **Subsequent Starts:** Once images are cached, the stack starts in seconds.

## Security and Privacy

The build follows a strict privacy-first model:
* AI processing remains local by default.
* Tailscale prevents opening public ports.
* Backups remain local and under physical control.

## Contributors

[![Niklas Brandt](https://github.com/niklasbrandt.png?size=40)](https://n1991.com) **[Niklas Brandt](https://n1991.com)** — Creator

Engineering, design, and privacy advocacy contributions are welcome. Report issues or star the repository to support the project.
