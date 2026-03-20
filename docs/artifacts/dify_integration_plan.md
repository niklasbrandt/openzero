# Integration Plan: Dify Crews and Crew Loops in openZero

## 1. Overview
This plan outlines the integration of **Dify** (open-source LLM app development platform) into **openZero**. The goal is to allow Z to delegate complex, multi-agent tasks ("crews") to Dify and support autonomous, repeating agentic workflows ("crew loops").

## 2. Architecture: The Z-Dify Bridge
Z remains the primary operator and interface. Dify acts as a specialized multi-agent execution engine.

- **Outbound**: Z triggers a Dify application via a new `RUN_CREW` action tag.
- **Inbound**: Dify "External Tools" call back into openZero's tools (Planka, Memory, Calendar) via a secured Integration API.
- **Loops**: Scheduled tasks in openZero's APScheduler trigger Dify workflows periodically.

## 3. Phase 1: Foundation & Connectivity

### 3.1 Configuration (`app/config.py`)
Add support for Dify settings and an integration token in `.env`.
```python
DIFY_API_URL: str = "http://dify-api:5001"
DIFY_API_KEY: Optional[str] = None
INTEGRATION_TOKEN: str = "GENERATED_ON_BOOT"
```

### 3.2 Service Layer (`app/services/dify.py`)
- [x] **Phase 1: Foundation & Connectivity**
  - [x] Add `DIFY_API_URL`, `DIFY_API_KEY`, and `INTEGRATION_TOKEN` to `app/config.py`.
  - [x] Create `app/services/dify.py` for Workflow/Agent API interaction.
  - [x] Update `ACTION_TAG_DOCS` in `llm.py` to include `RUN_CREW` and `SCHEDULE_CREW`.

- [x] **Phase 2: Outbound Execution (RUN_CREW)**
  - [x] Implement regex parser and handler in `agent_actions.py`.
  - [x] Add `_exec_crew` helper that calls the Dify Workflow API.
  - [x] Ensure audit trail in `global_messages`.

- [x] **Phase 3: Autonomous Loops (SCHEDULE_CREW)**
  - [x] Update `SCHEDULE_CREW` handler to map to `CustomTask`.
  - [x] Modify `scheduler.py` to make custom tasks "action-aware" (execute tags if present).
Allow the `/custom` command and `CustomTask` model to explicitly handle Crew triggers.
```bash
/custom "Run Weekly Research Crew" every Monday at 9am
```

### 5.2 Scheduler Integration
Updates to `scheduler.py` to fetch active "Crew Loops" and execute them via `dify_service`.

## 6. Phase 4: Bidirectional Tooling (Dify → openZero)

### 6.1 Integration API (`app/api/external.py`)
- [x] Expose a new router for external systems:
  - [x] `POST /api/v1/external/planka/create-task`
  - [x] `POST /api/v1/external/memory/learn`
  - [x] Secured via `X-Integration-Token`.

### 6.2 Dify External Tools
Configure Dify "External Tools" or "API Tools" to point to these endpoints. This allows a Dify Crew to:
- "Hey Z, we found a bug, I've created a task on your Operator Board."
- "I've learned a new preference about the user and updated your memory."

## 7. Phase 5: Dashboard Visibility

### 7.1 Crew Management Widget
- [x] Status indicator in Diagnostics widget for Dify bridge.
- List available Dify applications (TBD - needs discovery).

### 7.2 Hardware/Software Status
- [x] Update the Diagnostics widget to include the Dify service status (Online/Offline/Connected).

## 8. Deployment Changes (`docker-compose.yml`)
(Optional) Provide a `dify-standalone.yml` or add Dify services as optional blocks for users with enough RAM (e.g., 32GB+). 
By default, the integration should target an external Dify URL to keep the core openZero footprint small.

## 9. Security & Privacy
- **Integration Tokens**: Unique tokens generated per installation.
- **PII Scrubbing**: Apply existing `sanitize_prompt` logic to any data sent to Dify if the Dify instance is hosted in the cloud.
- **Audit Logs**: Record all crew executions in `global_messages` so the user can see what the "teams" are doing.
