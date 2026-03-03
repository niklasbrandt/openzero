# Agent Behavior & Correction Log

This file tracks policy violations, behavioral corrections, and manual overrides of AI agent actions in this repository. Agents MUST read this log at the beginning of every interaction to learn from past mistakes.

## Violations & Corrections

- **Missing database migration for new ORM columns**: Added `color_primary`, `color_secondary`, `color_tertiary` columns to the `Person` SQLAlchemy model but never ran a corresponding `ALTER TABLE` migration. The live PostgreSQL database did not have these columns, causing every query to the `people` table to crash with `UndefinedColumnError`. This broke both the UserCard widget and the Life Overview widget. Fix: ran `ALTER TABLE people ADD COLUMN IF NOT EXISTS color_primary VARCHAR; ...` directly on the VPS postgres container. Rule: whenever a new column is added to an ORM model (db.py), **always** immediately write and run a matching SQL migration (`ALTER TABLE ... ADD COLUMN IF NOT EXISTS ...`) on the live database. Never leave the DB schema behind the ORM model.

- **TabError in Python files**: Agent used tabs for new code in `config.py` (per agents.md tab rule) but Python enforces consistency within a file. The file already used 4-space indentation, so mixing tabs caused `TabError: inconsistent use of tabs and spaces`. Rule: For Python files, match the existing indentation style (spaces) even though agents.md says tabs. Python's strict indentation rules override.

- **Wrong HuggingFace model URLs**: Used `microsoft/phi-4-mini-instruct-gguf` which is gated (returns "Invalid username or password"). Correct ungated source: `unsloth/Phi-4-mini-instruct-GGUF`. Also used non-existent filename `Meta-Llama-3.1-8B-Instruct-Q4_0.gguf` in bartowski repo -- the correct filename is `Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf`. Always verify HuggingFace GGUF filenames exist before configuring.

- **Wrong Docker image registry**: Used `ghcr.io/ggerganov/llama.cpp:server` which does not exist. The llama.cpp project moved to `ghcr.io/ggml-org/llama.cpp:server`. Always verify Docker image availability before deployment.

- **Wrong binary path in container**: Assumed `llama-server` was on PATH inside `ghcr.io/ggml-org/llama.cpp:server`. The binary is at `/app/llama-server`. Always inspect container filesystem before writing entrypoints.

- **Mismatched env var names for LLM threads**: docker-compose.yml referenced `LLM_THREADS_INSTANT`, `LLM_THREADS_STANDARD`, `LLM_THREADS_DEEP` but .env defined `LLM_INSTANT_THREADS`, `LLM_STANDARD_THREADS`, `LLM_DEEP_THREADS`. The reversed naming caused all containers to silently fall back to defaults (2/2/4 threads instead of 4/4/6). Always ensure docker-compose env var references match the exact names in .env and .env.example.

- **SECRET LEAK: .env.remote committed to git**: The file `.env.remote` containing real Telegram bot token, database password, Planka admin credentials, Qdrant API key, Pi-hole password, personal email, and Tailscale IP was tracked by git and pushed to the remote repository. The file was not listed in `.gitignore`. Fix: removed from git tracking (`git rm --cached`), added to `.gitignore`. All exposed secrets should be rotated since they exist in git history. Always verify that any file containing real credentials is covered by `.gitignore` before committing.

- **Syntax error in startup greeting caused crash loop**: Added a startup greeting to `main.py` with a malformed `try/except` block (`except` on same line as `logging.info`). This caused the backend container to crash-loop repeatedly. The startup greeting was also a duplicate of one already in `telegram.py`. Rule: Never add duplicate functionality without checking if it already exists. Always verify syntax before committing code to critical startup paths.

- **Scheduler timezone double-init**: `scheduler.py` initialized `AsyncIOScheduler` at module level with `get_user_timezone()` which always returned the fallback "Europe/Berlin" because the DB cache wasn't populated yet (populated later by `refresh_user_settings()` in the startup sequence). Then `start_scheduler()` reconfigured it with the correct timezone from DB. Fix: initialize with `pytz.utc` at module level since `start_scheduler()` always reconfigures. Rule: Never rely on DB-cached values at module-load time; they aren't populated until the async startup sequence runs.

- **Streaming path silently missing birthday tags**: `chat_stream_with_context().fetch_people()` was a ~140-line duplicate of `chat_with_context().fetch_people()` but the streaming copy was missing birthday proximity tags. The duplication caused silent feature drift. Rule: When logic is duplicated, extract shared helpers to avoid divergence.

- **LLM container healthchecks checking wrong port**: `ghcr.io/ggml-org/llama.cpp:server` image has a built-in healthcheck that probes `localhost:8080`. openZero runs llm-instant/standard/deep on ports 8081/8082/8083 respectively. The image's built-in healthcheck was never satisfied, leaving all three containers permanently `unhealthy` despite being fully functional. Fix: override with explicit `healthcheck` blocks in docker-compose.yml pointing to the correct port for each service. Rule: Always override image-level healthchecks in docker-compose when the container port differs from the image default.

- **Stray backtick in template literal broke TypeScript build**: During the accessibility pass on `LifeOverview.ts`, a replacement introduced a stray backtick at the start of a template literal inner expression (`` `<div class="timeline-item"... ``), terminating the outer template literal prematurely. This caused 20+ TypeScript errors (TS1005, TS1128, TS1161) and broke the Docker build. Fix: remove the extra backtick. Rule: When replacing lines inside template literals (backtick strings in TypeScript/JavaScript), always verify the replacement does not introduce an unmatched backtick that would terminate the outer string context before committing.

