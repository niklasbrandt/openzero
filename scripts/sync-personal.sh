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
REMOTE_DIR="${REMOTE_DIR:-/home/openzero/openzero}"

if [ ! -d "personal/" ]; then
	echo "❌ Error: Local 'personal/' directory not found."
	exit 1
fi

echo "🚀 Syncing local personal/ to $REMOTE_USER@$REMOTE_HOST:$REMOTE_DIR/personal/..."
ssh $REMOTE_USER@$REMOTE_HOST "mkdir -p $REMOTE_DIR/personal/"
rsync -avz --delete ./personal/ $REMOTE_USER@$REMOTE_HOST:$REMOTE_DIR/personal/

echo "✅ Personal context sync complete."
echo "🔄 Restarting openZero backend to load new context..."
ssh $REMOTE_USER@$REMOTE_HOST "cd $REMOTE_DIR && docker compose restart backend"
echo "✅ Backend restarted successfully."
