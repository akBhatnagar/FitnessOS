#!/usr/bin/env bash
# ============================================================
# FitnessOS — Deployment Script
# Run this from YOUR LOCAL MACHINE (not the server)
# Usage: bash deploy/scripts/deploy.sh
# ============================================================
set -euo pipefail

REMOTE_USER="${DEPLOY_USER:-root}"
REMOTE_HOST="${DEPLOY_HOST:?Set DEPLOY_HOST to your server IP or hostname}"
APP_DIR="/opt/fitnessos"
APP_USER="fitnessos"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DEPLOY_URL="${DEPLOY_URL:-https://your-domain.example}"

SSH="ssh -o StrictHostKeyChecking=no ${REMOTE_USER}@${REMOTE_HOST}"
SCP="scp -o StrictHostKeyChecking=no -r"

log() { echo -e "\n\033[1;36m>>> $*\033[0m\n"; }
ok()  { echo -e "\033[1;32m✓ $*\033[0m"; }

# ---- 1. Build frontend ----
log "Building Next.js frontend (standalone)"
cd "$REPO_ROOT/frontend"
if [[ ! -f ".env.production" ]]; then
    echo "ERROR: frontend/.env.production not found. Copy from .env.production and fill in values."
    exit 1
fi
npm run build

# ---- 2. Sync backend ----
log "Syncing backend to server"
rsync -az --delete \
    --exclude=".venv" \
    --exclude="__pycache__" \
    --exclude="*.pyc" \
    --exclude=".env*" \
    --exclude="alembic/versions/*.pyc" \
    "$REPO_ROOT/backend/" \
    "${REMOTE_USER}@${REMOTE_HOST}:${APP_DIR}/backend/"

# ---- 3. Sync frontend build ----
log "Syncing frontend build to server"
rsync -az --delete \
    --exclude="node_modules" \
    --exclude=".next/cache" \
    "$REPO_ROOT/frontend/.next/" \
    "${REMOTE_USER}@${REMOTE_HOST}:${APP_DIR}/frontend/.next/"

rsync -az \
    "$REPO_ROOT/frontend/public/" \
    "${REMOTE_USER}@${REMOTE_HOST}:${APP_DIR}/frontend/public/"

rsync -az \
    "$REPO_ROOT/frontend/package.json" \
    "$REPO_ROOT/frontend/next.config.ts" \
    "${REMOTE_USER}@${REMOTE_HOST}:${APP_DIR}/frontend/"

# ---- 4. Sync Nginx config ----
log "Updating Nginx config"
$SCP "$REPO_ROOT/deploy/nginx/fitnessos.conf" \
    "${REMOTE_USER}@${REMOTE_HOST}:/etc/nginx/sites-available/fitnessos"

# ---- 5. Remote: install deps + migrate + restart ----
log "Running remote setup commands"
$SSH <<'REMOTE'
set -euo pipefail
APP_DIR="/opt/fitnessos"
APP_USER="fitnessos"

echo ">>> Installing Python dependencies"
cd "$APP_DIR/backend"
if [[ ! -d ".venv" ]]; then
    python3.11 -m venv .venv
fi
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt

echo ">>> Running DB migrations"
.venv/bin/alembic upgrade head

echo ">>> Enabling Nginx site"
ln -sf /etc/nginx/sites-available/fitnessos /etc/nginx/sites-enabled/fitnessos
nginx -t && systemctl reload nginx

echo ">>> Installing/updating systemd services"
cp /opt/fitnessos/backend/../deploy/systemd/*.service /etc/systemd/system/ 2>/dev/null || true
systemctl daemon-reload

echo ">>> Restarting services"
systemctl enable fitnessos-backend fitnessos-frontend fitnessos-worker fitnessos-beat
systemctl restart fitnessos-backend fitnessos-frontend fitnessos-worker fitnessos-beat

echo ">>> Service status"
systemctl status fitnessos-backend --no-pager -l | tail -5
systemctl status fitnessos-frontend --no-pager -l | tail -5

echo ">>> Deploy complete!"
REMOTE

ok "Deployment finished. Visit ${DEPLOY_URL}"
log "To check logs: ssh ${REMOTE_USER}@${REMOTE_HOST} 'journalctl -u fitnessos-backend -f'"
