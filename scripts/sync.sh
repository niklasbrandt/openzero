#!/bin/bash
set -e

# Usage: bash scripts/sync.sh [--test]
# Tests are skipped by default. Pass --test to run the regression suite.
RUN_TESTS=false
for arg in "$@"; do
  [[ "$arg" == "--test" ]] && RUN_TESTS=true
done

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
    --exclude '.github/'
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
echo "--------------------------------------------------------------------------------"
echo "🛡️  Protection Mode: Active (Data Sovereignty Rule 9)"
echo "Excluded from this sync: personal/, .env, *.log, databases, Docker volumes"
echo "To sync personal context, use: bash scripts/sync_overwrite_personal.sh"
echo "--------------------------------------------------------------------------------"

# Sync source code (including LATEST_CHANGES.txt if it exists)
rsync -avz --delete "${EXCLUDES[@]}" ./ $REMOTE_USER@$REMOTE_HOST:$REMOTE_DIR/

# Update sync marker
if [ -d .git ]; then
  git rev-parse HEAD > "$LAST_SYNC_FILE"
fi

# Restart backend to load any rsync'd Python file changes from the volume mount.
# Pass --rebuild to also rebuild the Docker image (e.g. new requirements.txt).
REBUILD_CMD="docker compose restart backend"
for arg in "$@"; do
  [[ "$arg" == "--rebuild" ]] && REBUILD_CMD="docker compose build backend && docker compose rm -f --stop backend && docker compose up -d"
done

ssh $REMOTE_USER@$REMOTE_HOST "cd $REMOTE_DIR \
  && $REBUILD_CMD \
  && docker builder prune -f \
  && docker image prune -f"

# Clean up local temporary file
rm -f LATEST_CHANGES.txt

echo "✅ Deployment complete."
echo "💡 Reminder: Use 'bash scripts/sync-personal.sh' if you also need to update personal context."

# ── Post-deploy regression tests ─────────────────────────────────────────────
if [ "$RUN_TESTS" = false ]; then
  echo "⏭  Tests skipped (pass --test to run regression suite)."
  exit 0
fi

# Derive backend URL from BASE_URL or fallback to Tailscale/IP direct
TEST_URL="${BASE_URL:-http://${REMOTE_HOST}:8000}"

# Strip trailing slash
TEST_URL="${TEST_URL%/}"

echo ""
echo "🧪 Running post-deploy regression suite against $TEST_URL ..."
echo -n "   Waiting for backend "
for i in $(seq 25 -1 1); do
  echo -n "."
  sleep 1
done
echo " ready!"

# Check Python + httpx available
if ! python3 -c "import httpx, asyncio" 2>/dev/null; then
  echo "⚠️  httpx not installed locally — installing..."
  pip3 install httpx --quiet
fi

# Run the suite with unbuffered output (-u) so progress prints in real-time
if python3 -u tests/test_live_regression.py --url "$TEST_URL" && python3 -u tests/test_native_crew.py; then
  echo ""
  echo "✅ All regression tests passed (including Native Tactical Brain)."
  echo "📄 Full report saved to: docs/artifacts/regression_results.md"
else
  echo ""
  echo "❌ REGRESSION DETECTED — review output above before proceeding."
  echo "📄 Partial/Failed report saved to: docs/artifacts/regression_results.md"
  exit 1
fi
