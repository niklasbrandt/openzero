#!/bin/bash
set -e

# Load exact host logic from main sync.sh
if [ -f .env ]; then
  export $(grep -v '^#' .env | grep -v '^$' | sed 's/[[:space:]]*#.*$//' | xargs)
fi

REMOTE_USER="${REMOTE_USER:-openzero}"
if [ -z "$REMOTE_HOST" ] && [ -n "$BASE_URL" ]; then
  REMOTE_HOST=$(echo "$BASE_URL" | sed -e 's|^[^/]*//||' -e 's|/.*$||' -e 's|:.*$||')
fi
REMOTE_HOST="${REMOTE_HOST:-your_vps_ip}"

echo "🔄 Target Host: $REMOTE_USER@$REMOTE_HOST"
echo "🚀 1/3: Running standard project sync..."
bash scripts/sync.sh

echo "📦 2/3: Syncing agent/ framework to VPS..."
rsync -avz --delete agent/ $REMOTE_USER@$REMOTE_HOST:~/openzero/agent/

echo "🧠 3/3: Syncing personal/ context files to VPS..."
rsync -avz --delete personal/ $REMOTE_USER@$REMOTE_HOST:~/openzero/personal/

echo "✅ All data synchronized successfully! The new 21-crew architecture is live."
