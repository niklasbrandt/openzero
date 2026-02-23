#!/bin/bash
set -e

# Configuration
REMOTE_USER="openzero"
REMOTE_HOST="your_vps_ip"
REMOTE_DIR="/home/openzero/openzero"

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

echo "🚀 Syncing code to $REMOTE_USER@$REMOTE_HOST:$REMOTE_DIR..."

# Sync source code
rsync -avz --delete "${EXCLUDES[@]}" ./ $REMOTE_USER@$REMOTE_HOST:$REMOTE_DIR/

echo "📦 Rebuilding and restarting containers on VPS..."

# Rebuild and restart using docker compose
ssh $REMOTE_USER@$REMOTE_HOST "cd $REMOTE_DIR && docker compose build backend && docker compose up -d"

echo "✅ Deployment complete."
