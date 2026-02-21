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
DIM='\033[2m'
RESET='\033[0m'

echo ""
echo -e "${TEAL}  ╔═══════════════════════════════╗${RESET}"
echo -e "${TEAL}  ║      ${GREEN}OpenZero Dev Mode${TEAL}        ║${RESET}"
echo -e "${TEAL}  ╚═══════════════════════════════╝${RESET}"
echo ""

cleanup() {
    echo ""
    echo -e "${DIM}Shutting down...${RESET}"
    kill $BACKEND_PID $DASHBOARD_PID 2>/dev/null
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
"$BACKEND_DIR/.venv/bin/pip" install -q -r "$BACKEND_DIR/requirements.txt" 2>&1 | tail -1

# ── 2. Check Node deps ──
if [ ! -d "$DASHBOARD_DIR/node_modules" ]; then
    echo -e "${DIM}Installing dashboard dependencies...${RESET}"
    (cd "$DASHBOARD_DIR" && npm install --silent)
fi

# ── 3. Start Backend ──
echo -e "${GREEN}▸ Backend${RESET}    → http://localhost:8000"
(
    cd "$BACKEND_DIR"
    .venv/bin/uvicorn app.main:app --reload --port 8000 2>&1 | sed "s/^/  [backend]  /"
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
