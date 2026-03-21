---
description: Synchronize project to VPS and restart services
---

// turbo-all
1.	Check if Docker is running
2.	Choose the appropriate sync script based on the task:
	-	General Sync: `bash scripts/sync.sh` (Syncs source code + `agent/` folder; excludes `personal/` and sensitive data)
	-	Agent & Personal Sync: `bash scripts/sync-agent.sh` (Advanced: syncs project + explicitly syncs `agent/` and `personal/` context)
	-	Personal Sync: `bash scripts/sync-personal.sh` (Context update: syncs `personal/` and restarts backend)
	-	Agent-Only Overwrite: `bash scripts/sync_overwrite_agent.sh` (Fast: syncs `agent/` and restarts backend for immediate effect)
3.	Verify Traefik and Backend status on VPS

## Data Sovereignty and Protection Rules

### What is OK to replace
-	Application logic and source code (`src/`, `docker-compose.yml`, etc.)
-	Utility scripts and dashboard components
-	Service configurations and API logic

### What MUST NOT be replaced or overwritten
-	Remote memories (stored in VPS-side Docker volumes or Qdrant)
-	Active `.env` secrets on the VPS
-	Remote database files or persistent state not present locally

### Why these rules exist
-	Memory Integrity: Overwriting remote data leads to permanent loss of cloud memories and historical context that the agent has built over time.
-	Security: Secrets and private identifiers must stay isolated on their respective hosts to prevent leaks between environments.
-	Continuity: The openZero system relies on persistent remote state to maintain its "Universal Context" across different interaction channels.
