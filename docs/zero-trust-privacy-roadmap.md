# openZero Architecture Roadmap: Zero Trust, Privacy & Scale

This document captures the strategic propositions for hardening and scaling the openZero homelab stack. It outlines the evolution from a monolithic "version 1.0" approach towards an enterprise-grade, privacy-first personal AI operating system.

## 🟢 Phase 1: Native LLM Tool Calling (Agent Reliability)
**Current State:** The agent uses string parsing (regex) to detect `[ACTION: ...] ` tags in the LLM output.
**Proposed Upgrade:** Move to native JSON-based function/tool calling (supported natively by modern models like Llama 3 via Ollama).
**Impact:** Drastically reduces model hallucinations, malformed actions, and regex parsing errors. Standardizes the communication protocol between the intelligence tier and the execution backend.

## 🟢 Phase 2: Network Zero Trust (Traefik & Pi-hole)
**Current State:** Unified internal routing via Traefik. Internal traffic is isolated and secured. Traffic is routed via Docker labels.
**Proposed Upgrade:** 
- Swap Nginx for **Traefik** with a local CA/DNS challenge to mint and easily configure internal TLS certificates using Docker labels.
- Introduce **Pi-hole** or AdGuard Home as a mandatory local DNS sinkhole to block tracking, telemetry, and malicious outbound requests natively from containers.
**Impact:** Provides encryption on the wire and enforces strict visibility and control over outbound data leaving the local network. 

## 🟢 Phase 3: Agent Orchestration (LangGraph / CrewAI)
**Current State:** A monolithic custom agent loop (`llm.py`) built around the "Z" persona with all reasoning logic combined into one big system prompt context.
**Proposed Upgrade:** Implement **LangGraph** or CrewAI to convert the agent into a state machine. The monolithic agent becomes a team of specialized sub-agents (e.g., Executive Orchestrator, Memory Analyst, Schedule Coordinator).
**Impact:** Reduces context-window overload and allows reflection loops where the agent double-checks its tool payload before making API requests, increasing system resilience and autonomy safely.

## 🟢 Phase 4: Execution Sandbox & Asynchronous Processing
**Current State:** The backend runs everything synchronously or via the same generic asyncio loop. The agent executes tools directly with backend container privileges. File storage uses generic Docker volumes.
**Proposed Upgrade:**
- Stand up **Redis** combined with a queueing system like Celery or ARQ to offload background LLM reasoning, allowing the backend main loop to respond instantly to the user interface.
- Deploy an execution sandbox for arbitrary code evaluation, keeping unverified code execution strictly sealed from the main Postgres or Qdrant databases.
**Impact:** Substantially bolsters security against prompt injection while smoothing UI performance through proper asynchronous background job delegation.

## Additional Recommendations (High Return, Medium Priority)
- **MinIO Object Storage:** Upgrade from raw Docker filesystem mounts to an S3-compatible, version-controlled object storage system for persistent media and attachments.
- **Dedicated Embedding Service:** Extract `sentence-transformers` out of the FastAPI container into a dedicated Text-Embeddings Service (e.g. TEI), alleviating memory pressure and letting the web tier focus squarely on HTTP routing.
- **Centralized Observability:** Deploy Grafana, Prometheus, and Promtail/Loki to provide comprehensive monitoring of vector queries, LLM latency, and system memory consumption—especially important as local AI compute scales.
