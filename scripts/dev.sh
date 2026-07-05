#!/usr/bin/env bash
# ============================================================
# FitnessOS — Local Development Startup Script
# ============================================================
# Usage: ./scripts/dev.sh
#
# Starts: PostgreSQL, Redis, FastAPI backend, Next.js frontend
# All logs go to their respective terminal tabs.
# ============================================================

set -e
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  FitnessOS — Starting Local Development Environment"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# ── 1. Services ──────────────────────────────────────────────
echo "▶ Starting PostgreSQL and Redis..."
brew services start postgresql@16 > /dev/null 2>&1 || true
brew services start redis > /dev/null 2>&1 || true
sleep 1
echo "  ✓ PostgreSQL and Redis running"

# ── 2. Database check ───────────────────────────────────────
echo "▶ Checking database..."
if ! psql fitnessos -c "SELECT 1" > /dev/null 2>&1; then
  echo "  Creating database..."
  createdb fitnessos
  psql fitnessos -c "CREATE EXTENSION IF NOT EXISTS vector;" > /dev/null
  psql fitnessos -c "CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\";" > /dev/null
fi
echo "  ✓ Database ready"

# ── 3. Migrations ────────────────────────────────────────────
echo "▶ Running migrations..."
cd "$ROOT/backend"
.venv/bin/alembic upgrade head > /dev/null 2>&1
echo "  ✓ Migrations applied"

# ── 4. Seed dev user (if needed) ─────────────────────────────
echo "▶ Seeding dev user..."
.venv/bin/python scripts/seed_dev_user.py 2>&1 | grep -E "✅|Skipping"
cd "$ROOT"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Starting servers..."
echo "  Backend  → http://localhost:8000"
echo "  Frontend → http://localhost:3000"
echo "  API Docs → http://localhost:8000/docs"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# ── 5. Start both servers ────────────────────────────────────
if command -v gnome-terminal &>/dev/null; then
  gnome-terminal -- bash -c "cd $ROOT/backend && .venv/bin/uvicorn app.main:app --reload --port 8000; exec bash"
  gnome-terminal -- bash -c "cd $ROOT/frontend && npm run dev; exec bash"
elif command -v osascript &>/dev/null; then
  # macOS: open in new Terminal tabs
  osascript <<EOF
tell application "Terminal"
  do script "cd $ROOT/backend && .venv/bin/uvicorn app.main:app --reload --port 8000"
  do script "cd $ROOT/frontend && npm run dev"
end tell
EOF
else
  # Fallback: run both in background
  cd "$ROOT/backend" && .venv/bin/uvicorn app.main:app --reload --port 8000 &
  BACKEND_PID=$!
  cd "$ROOT/frontend" && npm run dev &
  FRONTEND_PID=$!

  echo "Backend PID:  $BACKEND_PID"
  echo "Frontend PID: $FRONTEND_PID"
  echo ""
  echo "Press Ctrl+C to stop both servers."

  trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit 0" INT
  wait
fi
