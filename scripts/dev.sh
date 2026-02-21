#!/bin/bash
set -e

# ─────────────────────────────────────────────
# OpenZero Dev Launcher
# Starts backend + dashboard in parallel
# ─────────────────────────────────────────────

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/src/backend"
DASHBOARD_DIR="$ROOT_DIR/src/dashboard"

# Colors
TEAL='\033[0;36m'
GREEN='\033[0;32m'
RED='\033[0;31m'
DIM='\033[2m'
RESET='\033[0m'

echo ""
echo -e "${TEAL}  ╔═══════════════════════════════╗${RESET}"
echo -e "${TEAL}  ║      ${GREEN}OpenZero Dev Mode${TEAL}        ║${RESET}"
echo -e "${TEAL}  ╚═══════════════════════════════╝${RESET}"
echo ""

# ── 0. Start Docker Infrastructure ──
echo -e "${TEAL}󱐋${RESET} ${DIM}Starting Docker infrastructure...${RESET}"
if ! docker info > /dev/null 2>&1; then
    echo -e "${RED}✘ Error: Docker is not running. Please start Docker Desktop first.${RESET}"
    exit 1
fi

# Attempt to pull and start, with a repair retry if it fails (common on Mac)
if ! docker compose up -d postgres qdrant ollama planka 2>&1; then
    echo -e "${RED}󱙝 Potential Docker corruption detected. Attempting repair...${RESET}"
    docker system prune -f > /dev/null 2>&1
    docker compose up -d postgres qdrant ollama planka
fi

cleanup() {
    echo ""
    echo -e "${DIM}Shutting down...${RESET}"
    kill $BACKEND_PID $DASHBOARD_PID 2>/dev/null
    # Stop containers gracefully
    docker compose stop postgres qdrant ollama planka > /dev/null 2>&1
    wait $BACKEND_PID $DASHBOARD_PID 2>/dev/null
    echo -e "${GREEN}✓ All services stopped.${RESET}"
}
trap cleanup EXIT INT TERM

# ── 1. Check Python venv / deps ──
if [ ! -d "$BACKEND_DIR/.venv" ]; then
    echo -e "${DIM}Setting up Python virtual environment...${RESET}"
    python3 -m venv "$BACKEND_DIR/.venv"
fi

echo -e "${DIM}Installing backend dependencies...${RESET}"
"$BACKEND_DIR/.venv/bin/pip" install --upgrade pip -q 2>&1 | tail -1
"$BACKEND_DIR/.venv/bin/pip" install -r "$BACKEND_DIR/requirements.txt" 2>&1 | grep -E "(error|ERROR|Successfully|already satisfied)" | head -5
echo -e "${GREEN}✓ Backend dependencies ready.${RESET}"

# ── 2. Check Node deps ──
if [ ! -d "$DASHBOARD_DIR/node_modules" ]; then
    echo -e "${DIM}Installing dashboard dependencies...${RESET}"
    (cd "$DASHBOARD_DIR" && npm install --silent)
fi

# ── 3. Start Backend ──
echo -e "${GREEN}▸ Backend${RESET}    → http://localhost:8000"
(
    cd "$BACKEND_DIR"
    .venv/bin/python -m uvicorn app.main:app --reload --port 8000 2>&1 | sed "s/^/  [backend]  /"
) &
BACKEND_PID=$!

# ── 4. Start Dashboard ──
echo -e "${GREEN}▸ Dashboard${RESET}  → http://localhost:5173"
echo ""
(
    cd "$DASHBOARD_DIR"
    npx vite --host 2>&1 | sed "s/^/  [dashboard] /"
) &
DASHBOARD_PID=$!

# ── Wait ──
wait
