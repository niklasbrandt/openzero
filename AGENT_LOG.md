# Agent Behavior & Correction Log

This file tracks policy violations, behavioral corrections, and manual overrides of AI agent actions in this repository. Agents MUST read this log at the beginning of every interaction to learn from past mistakes.

## Violations & Corrections

- **TabError in Python files**: Agent used tabs for new code in `config.py` (per agents.md tab rule) but Python enforces consistency within a file. The file already used 4-space indentation, so mixing tabs caused `TabError: inconsistent use of tabs and spaces`. Rule: For Python files, match the existing indentation style (spaces) even though agents.md says tabs. Python's strict indentation rules override.

- **Wrong HuggingFace model URLs**: Used `microsoft/phi-4-mini-instruct-gguf` which is gated (returns "Invalid username or password"). Correct ungated source: `unsloth/Phi-4-mini-instruct-GGUF`. Also used non-existent filename `Meta-Llama-3.1-8B-Instruct-Q4_0.gguf` in bartowski repo -- the correct filename is `Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf`. Always verify HuggingFace GGUF filenames exist before configuring.

- **Wrong Docker image registry**: Used `ghcr.io/ggerganov/llama.cpp:server` which does not exist. The llama.cpp project moved to `ghcr.io/ggml-org/llama.cpp:server`. Always verify Docker image availability before deployment.

- **Wrong binary path in container**: Assumed `llama-server` was on PATH inside `ghcr.io/ggml-org/llama.cpp:server`. The binary is at `/app/llama-server`. Always inspect container filesystem before writing entrypoints.

- **Mismatched env var names for LLM threads**: docker-compose.yml referenced `LLM_THREADS_INSTANT`, `LLM_THREADS_STANDARD`, `LLM_THREADS_DEEP` but .env defined `LLM_INSTANT_THREADS`, `LLM_STANDARD_THREADS`, `LLM_DEEP_THREADS`. The reversed naming caused all containers to silently fall back to defaults (2/2/4 threads instead of 4/4/6). Always ensure docker-compose env var references match the exact names in .env and .env.example.

- **SECRET LEAK: .env.remote committed to git**: The file `.env.remote` containing real Telegram bot token, database password, Planka admin credentials, Qdrant API key, Pi-hole password, personal email, and Tailscale IP was tracked by git and pushed to the remote repository. The file was not listed in `.gitignore`. Fix: removed from git tracking (`git rm --cached`), added to `.gitignore`. All exposed secrets should be rotated since they exist in git history. Always verify that any file containing real credentials is covered by `.gitignore` before committing.
