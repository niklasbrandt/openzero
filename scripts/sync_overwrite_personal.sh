#!/bin/bash
set -e

echo "⚠️  WARNING: This will explicitly OVERWRITE the VPS 'personal/' directory with your local 'personal/' directory!"
echo "Any edits made directly on the server will be lost."
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

if [ ! -d "personal/" ]; then
  echo "❌ Error: Local 'personal/' directory not found."
  exit 1
fi

echo "🚀 Syncing local personal/ to $REMOTE_USER@$REMOTE_HOST:$REMOTE_DIR/personal/..."
# Ensure the remote directory exists
ssh $REMOTE_USER@$REMOTE_HOST "mkdir -p $REMOTE_DIR/personal/"
# Sync contents
rsync -avz --delete ./personal/ $REMOTE_USER@$REMOTE_HOST:$REMOTE_DIR/personal/

echo "✅ Personal context sync complete."
