#!/bin/bash
set -e

# Configuration (Load from .env if available)
if [ -f .env ]; then
  # Load env vars while ignoring comments and empty lines
  export $(grep -v '^#' .env | grep -v '^$' | sed 's/[[:space:]]*#.*$//' | xargs)
fi

REMOTE_USER="${REMOTE_USER:-openzero}"
# Extract host from BASE_URL if REMOTE_HOST isn't set
if [ -z "$REMOTE_HOST" ] && [ -n "$BASE_URL" ]; then
  REMOTE_HOST=$(echo "$BASE_URL" | sed -e 's|^[^/]*//||' -e 's|/.*$||' -e 's|:.*$||')
fi
REMOTE_HOST="${REMOTE_HOST:-your_vps_ip}"
REMOTE_DIR="${REMOTE_DIR:-/home/openzero/openzero}"

# Strict exclusions per agents.md rule 9
EXCLUDES=(
    --exclude '.git/'
    --exclude 'node_modules/'
    --exclude '__pycache__/'
    --exclude '.venv/'
    --exclude 'dist/'
    --exclude '.DS_Store'
    --exclude 'personal/'
    --exclude '*.log'
    --exclude '.env'
    --exclude '.env.planka'
    --exclude 'static/'
)

# Generate Release Notes for Z (Code-Level Context)
if [ -d .git ]; then
  LAST_SYNC_FILE=".last_sync_commit"
  if [ -f "$LAST_SYNC_FILE" ]; then
    LAST_COMMIT=$(cat "$LAST_SYNC_FILE")
    # Capture code-level changes (diff stat and summary)
    echo "Summary of Code Changes:" > LATEST_CHANGES.txt
    git diff --stat "$LAST_COMMIT" >> LATEST_CHANGES.txt
    echo -e "\nDetailed Logic Shifts:" >> LATEST_CHANGES.txt
    # Get a compact diff (0 context lines) to keep it brief for the LLM
    git diff -U0 "$LAST_COMMIT" | grep '^[+-]' | grep -v '^[+-][+-]' >> LATEST_CHANGES.txt || echo "Minor adjustments only." >> LATEST_CHANGES.txt
  else
    # First sync: Show last commit
    git show --stat HEAD > LATEST_CHANGES.txt
  fi
fi

echo "🚀 Syncing code to $REMOTE_USER@$REMOTE_HOST:$REMOTE_DIR..."

# Sync source code (including LATEST_CHANGES.txt if it exists)
rsync -avz --delete "${EXCLUDES[@]}" ./ $REMOTE_USER@$REMOTE_HOST:$REMOTE_DIR/

# Update sync marker
if [ -d .git ]; then
  git rev-parse HEAD > "$LAST_SYNC_FILE"
fi

# Rebuild and restart using docker compose
ssh $REMOTE_USER@$REMOTE_HOST "cd $REMOTE_DIR && docker compose build backend && docker compose up -d"

# Clean up local temporary file
rm -f LATEST_CHANGES.txt

echo "✅ Deployment complete."
