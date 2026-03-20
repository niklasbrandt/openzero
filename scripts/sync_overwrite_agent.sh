#!/bin/bash
set -e

echo "⚠️  WARNING: This will explicitly OVERWRITE the VPS 'agent/' directory with your local 'agent/' directory!"
echo "This includes 'crews.yaml', DSL templates, and capability directives."
read -p "Are you sure you want to proceed? [y/N] " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 1
fi

if [ -f .env ]; then
  export $(grep -v '^#' .env | grep -v '^$' | sed 's/[[:space:]]*#.*$//' | xargs 2>/dev/null)
fi

REMOTE_USER="${REMOTE_USER:-openzero}"
if [ -z "$REMOTE_HOST" ] && [ -n "$BASE_URL" ]; then
  REMOTE_HOST=$(echo "$BASE_URL" | sed -e 's|^[^/]*//||' -e 's|/.*$||' -e 's|:.*$||')
fi
REMOTE_HOST="${REMOTE_HOST:-your_vps_ip}"
REMOTE_DIR="${REMOTE_DIR:-/home/openzero/openzero}"

if [ ! -d "agent/" ]; then
  echo "❌ Error: Local 'agent/' directory not found."
  exit 1
fi

echo "🚀 Syncing local agent/ to $REMOTE_USER@$REMOTE_HOST:$REMOTE_DIR/agent/..."
# Ensure the remote directory exists
ssh $REMOTE_USER@$REMOTE_HOST "mkdir -p $REMOTE_DIR/agent/"
# Sync contents
rsync -avz --delete ./agent/ $REMOTE_USER@$REMOTE_HOST:$REMOTE_DIR/agent/

echo "✅ Agent configuration sync complete."
# Wait, for agent configs (crews.yaml), the backend might need a restart if it's running!
# The backend re-reads crews.yaml on startup. Let's restart backend seamlessly.
echo "🔄 Restarting openZero backend to load new crew configurations..."
ssh $REMOTE_USER@$REMOTE_HOST "cd $REMOTE_DIR && docker compose restart backend"
echo "✅ Backend restarted successfully."
