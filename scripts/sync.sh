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
    CURRENT_COMMIT=$(git rev-parse HEAD)
    if [ "$LAST_COMMIT" != "$CURRENT_COMMIT" ]; then
      # Use commit messages — readable for LLM summarization
      echo "Changes since last deployment:" > LATEST_CHANGES.txt
      git log --pretty=format:"- %s" "$LAST_COMMIT".."$CURRENT_COMMIT" >> LATEST_CHANGES.txt
      # Also add a short diff stat for technical context
      echo -e "\n\nFiles modified:" >> LATEST_CHANGES.txt
      git diff --stat "$LAST_COMMIT" "$CURRENT_COMMIT" | head -n 20 >> LATEST_CHANGES.txt
    fi
  else
    # First sync: Show last commit message
    echo "Initial deployment." > LATEST_CHANGES.txt
    git log --pretty=format:"- %s" -5 >> LATEST_CHANGES.txt
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
