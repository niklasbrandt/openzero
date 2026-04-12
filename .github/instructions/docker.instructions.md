---
description: "Docker Compose conventions for openZero infrastructure"
applyTo: "**/docker-compose.yml"
---

# Docker Compose Conventions (openZero)

## Secrets
- NEVER hardcode credentials in `docker-compose.yml`.
- Use `${VAR}` syntax referencing `.env` variables for all passwords, keys, and tokens.
- Example files (`.env.example`) must list every required variable with placeholder values.

## Volume Safety
- NEVER use `docker compose down -v` unless explicitly instructed for a specific reset task.
- Docker volumes contain production data. Treat them as immutable unless told otherwise.

## Network Isolation
- Services communicate via the internal Docker network.
- Only expose ports that need external access (Traefik handles routing).
- Pi-hole port 53: Tailscale-only (`100.64.0.0/10`), never `0.0.0.0`.

## Profile System
- Voice-related containers (Whisper, TTS) use Docker Compose profiles.
- Enable with `--profile voice` during `docker compose up`.
- Do not start voice containers by default.

## Image Pinning
- Use specific image tags, not `latest`.
- Document version changes in commit messages.
