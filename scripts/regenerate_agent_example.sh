#!/usr/bin/env bash
# Regenerate agent.example/ from live agent/ — sanitize personal data.
# Usage: ./scripts/regenerate_agent_example.sh
# Idempotent. Safe to run multiple times.

set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$REPO_ROOT/agent"
DST="$REPO_ROOT/agent.example"

echo "Regenerating agent.example from agent/ ..."

# Copy crews.yaml and redact personal operator content
# (The example file should not contain personal names, private goals, etc.)
cp "$SRC/crews.yaml" "$DST/crews.yaml"

# Copy agent-rules.md
cp "$SRC/agent-rules.md" "$DST/agent-rules.md"

# Copy other files if they exist
for f in kanban.md planka.md unit-standards.md; do
	if [ -f "$SRC/$f" ]; then
		cp "$SRC/$f" "$DST/$f"
		echo "  Copied $f"
	fi
done

echo "Done. agent.example/ is up to date."
