# AI Agent Guidelines

> This file contains instructions and rules for AI assistants (like Z, Cursor, or other coding agents) interacting with this repository.

## 0. Mandatory Initial Step
- **CRITICAL:** At the beginning of EVERY interaction or whenever you are prompted for a new task, you MUST read and analyze **agents.md**, **AGENT_LOG.md**, and **README.md**.
- You must use the context from these files to ensure your behavior aligns with the project's specific boundaries and that you do not repeat errors recorded in the log.

## 10. Build Documentation Maintenance
- **Post-Task Audit:** After completing a task or prompt execution, you MUST check if the changes you made should be reflected in the project's build instructions (typically located in `docs/build-plan.md`).
- Ensure that the setup, deployment, or architectural instructions remain accurate and up-to-date with your latest modifications.

## 1. Version Control & Pushing
- **DO NOT automatically push to the remote repository.**
- The user prefers to review all commits and perform the push themselves.
- You may stage and commit changes locally if part of a task, but **always stop before pushing** and leave that step to the user.

## 2. Editor & Syntax Best Practices
- **Indentation:** Use **TABS** for indentation (not spaces), except where rigidly required by a schema (like YAML). For all other code (HTML, CSS, JS, Markdown, etc.), use tabs.
- **Trailing Whitespace:** Remove trailing whitespace from modified lines.
- **File Endings:** Ensure all files end with a single newline character.
## 3. Documentation Standards
- **No Emojis:** Do not use emojis in any Markdown (`.md`) files. Documentation should remain clean and professional without decorative symbols.

## 4. Configuration & Example Files
- **Example Clones:** Many configuration files (like `.env` or `config.yaml`) have `.example` clones (e.g., .env.example, config.example.yaml). If you modify the structure or options of a configuration file, **you MUST apply those same structural changes to the corresponding example file.** This ensures that new users have an up-to-date template to follow.

## 5. Web Component Styling
- **Shadow DOM CSS Encapsulation:** Native Web Components in this project use `<style>` blocks populated via template literals directly inside their `.ts` definition wrappers. Do not extract this CSS into separate files. This single-file encapsulation pattern is intentional and considered the best practice for this repository to ensure isolated styling without a complex CSS bundling layer.
## 6. Cloud Deployment
- **DO NOT deploy to a Cloud VPS automatically.** 
- You may only initiate a cloud deployment if the user explicitly instructs you to do so. 
- You should proactively ask the user if a cloud deployment makes sense in the current context (e.g., if code is stable and ready for production), but you must never proceed without explicit confirmation.

## 7. Local Resource Cleanup
- **Always terminate local development processes** (e.g., `dev.sh`, local Docker containers) before or immediately after a cloud deployment.
- This is critical to prevent conflicts, especially with the Telegram bot, which can only have one active polling instance at a time.

## 8. Agent Behavior Log (AGENT_LOG.md)
- **DO NOT include dates** in entries in `AGENT_LOG.md`. The log should be a continuous list of violations and corrections without time-stamping.

## 9. Data Sovereignty & Protection
- **NEVER overwrite data on remote servers.** Your synchronization focus must strictly be on application logic (code), not data.
- **Strict Rsync Exclusions:** When syncing to a remote server, you MUST exclude the following patterns to prevent overwriting cloud memories or private local data:
  - `.git/`, `node_modules/`, `__pycache__/`, `.venv/`, `dist/`
  - `.DS_Store`
  - `personal/` (All private local files)
  - Raw database files or Docker volume folders if mapped locally.
- **Volume Safety:** NEVER use commands that delete Docker volumes (like `docker compose down -v`) unless explicitly instructed for a specific reset task.

## 11. Secret & Privacy Protection
- **STRICT LEAK PREVENTION:** NEVER commit or include real secrets (API keys, passwords, tokens) or personal identifiers (real emails, public IPs, Tailscale IPs) in the repository's codebase, scripts, or documentation.
- **Use Placeholders:** Always use generic placeholders like `your_api_key`, `your_vps_ip`, or `admin@example.com` in `.example` files and shared scripts.
- **Verify Gitignore:** Before creating new files that might contain sensitive data (logs, temp state, credentials), ensure their pattern is covered in `.gitignore`.
- **Sanitize Scripts:** Ensure utility scripts (e.g., `sync.sh`) load sensitive configuration from environment variables or `.env` files rather than hardcoding them.
- **No Personal Data:** Avoid using the user's real name, company email, or specific location in any code comments or example data.
- **Audit Before Sync:** Always perform a quick audit for hardcoded secrets when preparing a deployment or large code change.
