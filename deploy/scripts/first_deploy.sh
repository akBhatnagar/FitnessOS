#!/usr/bin/env bash
# ============================================================
# FitnessOS — First Deploy (run ONCE after setup_server.sh)
# Run from your LOCAL MACHINE
# Usage: bash deploy/scripts/first_deploy.sh
# ============================================================
set -euo pipefail

REMOTE_USER="${DEPLOY_USER:-root}"
REMOTE_HOST="${DEPLOY_HOST:?Set DEPLOY_HOST to your server IP or hostname}"
APP_DIR="/opt/fitnessos"
APP_USER="fitnessos"
DOMAIN="${DEPLOY_DOMAIN:?Set DEPLOY_DOMAIN to your app hostname}"
DEPLOY_EMAIL="${DEPLOY_EMAIL:-admin@example.com}"

SSH="ssh -o StrictHostKeyChecking=no ${REMOTE_USER}@${REMOTE_HOST}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

log() { echo -e "\n\033[1;36m>>> $*\033[0m\n"; }
warn() { echo -e "\033[1;33m⚠  $*\033[0m"; }
ok()   { echo -e "\033[1;32m✓ $*\033[0m"; }

# ---- Pre-flight checks ----
log "Pre-flight checks"
command -v rsync >/dev/null || { echo "Install rsync first: brew install rsync"; exit 1; }
[[ -f "$REPO_ROOT/backend/.env.production" ]] || {
    warn "backend/.env.production not found!"
    warn "Copy backend/.env.production and fill in your secrets before deploying."
    exit 1
}
[[ -f "$REPO_ROOT/frontend/.env.production" ]] || {
    warn "frontend/.env.production not found!"
    exit 1
}

# ---- Create directory structure on server ----
log "Creating directory structure on server"
$SSH <<REMOTE
mkdir -p ${APP_DIR}/{backend,frontend,logs}
chown -R ${APP_USER}:${APP_USER} ${APP_DIR} 2>/dev/null || true
REMOTE

# ---- Copy environment files ----
log "Copying production environment files"
scp -o StrictHostKeyChecking=no \
    "$REPO_ROOT/backend/.env.production" \
    "${REMOTE_USER}@${REMOTE_HOST}:${APP_DIR}/backend/.env"

scp -o StrictHostKeyChecking=no \
    "$REPO_ROOT/frontend/.env.production" \
    "${REMOTE_USER}@${REMOTE_HOST}:${APP_DIR}/frontend/.env.production"

# ---- Copy deploy configs ----
log "Copying systemd service files"
scp -o StrictHostKeyChecking=no \
    "$REPO_ROOT/deploy/systemd/"*.service \
    "${REMOTE_USER}@${REMOTE_HOST}:/etc/systemd/system/"

# ---- Run full deploy ----
log "Running full deployment"
bash "$REPO_ROOT/deploy/scripts/deploy.sh"

# ---- SSL Certificate ----
log "Setting up SSL with Let's Encrypt"
$SSH "certbot --nginx -d ${DOMAIN} --non-interactive --agree-tos -m ${DEPLOY_EMAIL} || echo 'SSL setup failed — check DNS and try: certbot --nginx -d ${DOMAIN}'"

# ---- Seed the database ----
log "Seeding database"
$SSH <<'REMOTE'
cd /opt/fitnessos/backend
echo ">>> Seeding dev user..."
.venv/bin/python scripts/seed_dev_user.py && echo "✓ Dev user seeded"
echo ">>> Seeding exercises..."
.venv/bin/python scripts/seed_exercises.py && echo "✓ Exercises seeded"
echo ">>> Seeding food database..."
.venv/bin/python scripts/seed_food_database.py && echo "✓ Food database seeded"
echo ">>> Seeding knowledge base..."
.venv/bin/python scripts/seed_knowledge_base.py && echo "✓ Knowledge base seeded"
REMOTE

ok "First deployment complete!"
echo ""
echo "============================================================"
echo " FitnessOS is live at: https://${DOMAIN}"
echo "============================================================"
echo ""
echo "Useful commands:"
echo "  Check backend:  ssh ${REMOTE_USER}@${REMOTE_HOST} 'journalctl -u fitnessos-backend -f'"
echo "  Check frontend: ssh ${REMOTE_USER}@${REMOTE_HOST} 'journalctl -u fitnessos-frontend -f'"
echo "  Check worker:   ssh ${REMOTE_USER}@${REMOTE_HOST} 'journalctl -u fitnessos-worker -f'"
echo "  Re-deploy:      bash deploy/scripts/deploy.sh"
echo "============================================================"
