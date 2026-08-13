#!/usr/bin/env bash
#
# Starts the whole project with one command: backend, then frontend, with both
# shut down together on Ctrl+C.
#
# Everything here is idempotent — the venv, the pip install, the .env copy and
# the npm install are all skipped if they've already been done — so this is safe
# to run every time rather than only on first setup.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

BACKEND_PORT=8000
FRONTEND_PORT=5173

# ANSI colours, but only when stdout is a terminal — piping this to a file
# shouldn't fill it with escape codes.
if [ -t 1 ]; then
  BOLD=$'\033[1m'; DIM=$'\033[2m'; RED=$'\033[31m'; GREEN=$'\033[32m'
  YELLOW=$'\033[33m'; RESET=$'\033[0m'
else
  BOLD=""; DIM=""; RED=""; GREEN=""; YELLOW=""; RESET=""
fi

say()  { printf "%s\n" "${BOLD}$1${RESET}"; }
note() { printf "%s\n" "${DIM}   $1${RESET}"; }
warn() { printf "%s\n" "${YELLOW}   $1${RESET}"; }
fail() { printf "%s\n" "${RED}$1${RESET}" >&2; exit 1; }

# Both children are killed on any exit path, not just Ctrl+C. Without this the
# backend survives as an orphan holding port 8000, and the next run fails with a
# confusing "address already in use".
BACKEND_PID=""
cleanup() {
  if [ -n "$BACKEND_PID" ] && kill -0 "$BACKEND_PID" 2>/dev/null; then
    printf "\n%s\n" "${DIM}Stopping backend...${RESET}"
    kill "$BACKEND_PID" 2>/dev/null || true
    wait "$BACKEND_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

# --- prerequisites -----------------------------------------------------------

command -v python3 >/dev/null || fail "python3 not found. Install Python 3.11 or newer."
command -v npm     >/dev/null || fail "npm not found. Install Node 18 or newer from nodejs.org."

# --- backend -----------------------------------------------------------------

say "Backend"
cd "$ROOT/backend"

if [ ! -d .venv ]; then
  note "creating virtual environment"
  python3 -m venv .venv
fi
# Sourced rather than invoked so uvicorn and pip resolve from the venv for the
# rest of this script.
source .venv/bin/activate

note "checking Python packages"
pip install -q -r requirements.txt

if [ ! -f .env ]; then
  cp .env.example .env
  warn "created backend/.env from the example"
  warn "add your free NewsAPI key to it (https://newsapi.org/register),"
  warn "or carry on without one — country pins will show as 'no data'."
fi

if grep -q "NEWS_API_KEY=your_key_here" .env 2>/dev/null; then
  warn "backend/.env still has the placeholder key, so countries will be grey."
  warn "city drill-down works regardless — it needs no key."
fi

note "starting on http://127.0.0.1:${BACKEND_PORT}"
uvicorn app.main:app --reload --port "$BACKEND_PORT" &
BACKEND_PID=$!

# Wait for it to answer before starting Vite, so the first page load doesn't
# race the server and show a connection error.
printf "%s" "${DIM}   waiting for the API${RESET}"
for _ in $(seq 1 40); do
  if curl -sf "http://127.0.0.1:${BACKEND_PORT}/api/health" >/dev/null 2>&1; then
    printf " %s\n" "${GREEN}ready${RESET}"
    break
  fi
  if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
    fail "
Backend exited during startup. Scroll up for the error."
  fi
  printf "."
  sleep 0.5
done

# --- frontend ----------------------------------------------------------------

echo
say "Frontend"
cd "$ROOT/frontend"

if [ ! -d node_modules ]; then
  note "installing npm packages (first run only, takes a minute)"
  npm install --no-fund --no-audit
fi

echo
say "Open http://localhost:${FRONTEND_PORT}"
note "pins fill in over ~30s on a cold cache — that's the warm-up, not a fault"
note "Ctrl+C stops both servers"
echo

# Foreground, so Ctrl+C reaches this and the trap tears the backend down with it.
npm run dev -- --port "$FRONTEND_PORT"
