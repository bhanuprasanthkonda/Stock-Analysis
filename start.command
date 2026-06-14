#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# start.sh — Local Stock Analyzer launcher (macOS + Linux)
#
# First run:  automatically installs all dependencies then starts the app.
# Later runs: skips install, starts immediately.
#
# macOS:  Double-click in Finder, or run ./start.sh in Terminal
# Linux:  chmod +x start.sh && ./start.sh  (or right-click → Run as Program)
# Windows: use start.bat instead
# ─────────────────────────────────────────────────────────────────────────────
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── macOS double-click: no TTY → reopen inside Terminal.app ──────────────────
if [[ "$OSTYPE" == "darwin"* ]] && [[ ! -t 1 ]]; then
    osascript \
        -e "tell application \"Terminal\" to activate" \
        -e "tell application \"Terminal\" to do script \"bash '$DIR/start.sh'\""
    exit 0
fi

# ── Linux double-click: no TTY → find a terminal emulator ────────────────────
if [[ "$OSTYPE" == "linux-gnu"* ]] && [[ ! -t 1 ]]; then
    for TERM_APP in gnome-terminal xterm konsole xfce4-terminal lxterminal; do
        if command -v "$TERM_APP" &>/dev/null; then
            "$TERM_APP" -- bash "$DIR/start.sh"
            exit 0
        fi
    done
    echo "No terminal emulator found. Run: bash start.sh" >&2
    exit 1
fi

set -e

echo "================================================"
echo "  Local Stock Analyzer"
echo "================================================"
echo ""

# ── Check Python ──────────────────────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
    echo "ERROR: python3 not found. Install Python 3.10+ from https://python.org"
    read -rp "Press Enter to exit..." _; exit 1
fi

# ── Check Node ────────────────────────────────────────────────────────────────
if ! command -v node &>/dev/null; then
    echo "ERROR: node not found. Install Node.js 18+ from https://nodejs.org"
    read -rp "Press Enter to exit..." _; exit 1
fi

# ── Backend: create venv if missing ──────────────────────────────────────────
if [ ! -d "$DIR/backend/venv" ]; then
    echo "[1/4] Creating Python virtual environment..."
    python3 -m venv "$DIR/backend/venv"
fi

# ── Backend: install packages if requirements changed ────────────────────────
STAMP="$DIR/backend/venv/.install_stamp"
REQ="$DIR/backend/requirements.txt"
if [ ! -f "$STAMP" ] || [ "$REQ" -nt "$STAMP" ]; then
    echo "[2/4] Installing backend packages..."
    "$DIR/backend/venv/bin/pip" install --quiet --upgrade pip
    "$DIR/backend/venv/bin/pip" install --quiet -r "$REQ"
    touch "$STAMP"
else
    echo "[2/4] Backend packages up to date."
fi

# ── Frontend: always run npm install so new/changed packages are picked up ────
# npm install is fast (no-op) when nothing changed; package-lock.json pins
# exact versions so installs are reproducible across machines.
echo "[3/4] Checking frontend packages..."
cd "$DIR/frontend"
npm install --silent

echo "[4/4] Starting servers..."
echo ""

# ── Graceful shutdown on Ctrl+C / window close ───────────────────────────────
cleanup() {
    echo ""
    echo "Stopping servers..."
    kill "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null
    wait "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null
    echo "Done. Goodbye."
}
trap cleanup EXIT INT TERM

# ── Start backend (logs printed directly — errors are visible here) ───────────
cd "$DIR/backend"
source venv/bin/activate
uvicorn app.main:app --reload --port 8000 --log-level info &
BACKEND_PID=$!

# ── Start frontend (logs saved to /tmp/stock-frontend.log) ───────────────────
cd "$DIR/frontend"
npm run dev >/tmp/stock-frontend.log 2>&1 &
FRONTEND_PID=$!

# ── Wait for backend to be ready ─────────────────────────────────────────────
printf "  Waiting for backend"
for i in $(seq 1 30); do
    curl -s http://localhost:8000/ &>/dev/null && break
    printf "."
    sleep 1
done
echo " ready."

# ── Open browser ──────────────────────────────────────────────────────────────
if [[ "$OSTYPE" == "darwin"* ]]; then
    open http://localhost:5173
elif command -v xdg-open &>/dev/null; then
    xdg-open http://localhost:5173
fi

echo ""
echo "  Backend  →  http://localhost:8000"
echo "  API docs →  http://localhost:8000/docs"
echo "  Frontend →  http://localhost:5173"
echo ""
echo "  Press Ctrl+C to stop."
echo ""

wait
