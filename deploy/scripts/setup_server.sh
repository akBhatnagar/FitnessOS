#!/usr/bin/env bash
# ============================================================
# FitnessOS — DigitalOcean Droplet Setup Script
# Run this ONCE on a fresh Ubuntu 22.04 droplet as root
# Usage: bash setup_server.sh
# ============================================================
set -euo pipefail

DOMAIN="${DEPLOY_DOMAIN:-your-domain.example}"
APP_USER="fitnessos"
APP_DIR="/opt/fitnessos"
DB_NAME="fitnessos"
DB_USER="fitnessos"
DB_PASS="$(openssl rand -hex 16)"

log() { echo -e "\n\033[1;32m>>> $*\033[0m\n"; }
err() { echo -e "\n\033[1;31m!!! $*\033[0m\n" >&2; exit 1; }

[[ $EUID -eq 0 ]] || err "Run as root: sudo bash setup_server.sh"

log "System update and essentials"
apt-get update -qq && apt-get upgrade -y -qq
apt-get install -y -qq \
    curl wget git unzip build-essential \
    nginx certbot python3-certbot-nginx \
    postgresql postgresql-contrib \
    redis-server \
    python3.11 python3.11-venv python3.11-dev \
    nodejs npm \
    libpq-dev pkg-config \
    ufw fail2ban

log "Installing Node.js 20 (LTS)"
curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
apt-get install -y nodejs
node --version
npm --version

log "Installing pnpm (faster than npm for Next.js)"
npm install -g pnpm pm2

log "Installing pgvector extension"
# Try apt first, fall back to source
if apt-get install -y postgresql-16-pgvector 2>/dev/null; then
    log "pgvector installed via apt"
else
    log "Compiling pgvector from source..."
    cd /tmp
    git clone --branch v0.7.0 https://github.com/pgvector/pgvector.git pgvector
    cd pgvector
    make
    make install
    cd /
    rm -rf /tmp/pgvector
fi

log "Configuring PostgreSQL"
systemctl enable postgresql
systemctl start postgresql

# Create DB user and database
sudo -u postgres psql <<PGSQL
DO \$\$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '${DB_USER}') THEN
    CREATE ROLE ${DB_USER} WITH LOGIN PASSWORD '${DB_PASS}';
  END IF;
END \$\$;
CREATE DATABASE ${DB_NAME} OWNER ${DB_USER};
GRANT ALL PRIVILEGES ON DATABASE ${DB_NAME} TO ${DB_USER};
\c ${DB_NAME}
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
\q
PGSQL

# Save credentials
echo "DB_PASS=${DB_PASS}" > /root/fitnessos_db_creds.txt
echo "DB_URL=postgresql+asyncpg://${DB_USER}:${DB_PASS}@localhost:5432/${DB_NAME}" >> /root/fitnessos_db_creds.txt
chmod 600 /root/fitnessos_db_creds.txt
log "DB credentials saved to /root/fitnessos_db_creds.txt"

log "Configuring Redis"
# Bind only to localhost for security
sed -i 's/^bind .*/bind 127.0.0.1 ::1/' /etc/redis/redis.conf
systemctl enable redis-server
systemctl restart redis-server

log "Creating app user"
if ! id "$APP_USER" &>/dev/null; then
    useradd -r -m -d "$APP_DIR" -s /bin/bash "$APP_USER"
fi
mkdir -p "$APP_DIR"
chown -R "$APP_USER:$APP_USER" "$APP_DIR"

log "Configuring UFW firewall"
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow ssh
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

log "Configuring fail2ban"
systemctl enable fail2ban
systemctl start fail2ban

log "Creating Nginx rate limiting config"
cat > /etc/nginx/conf.d/rate_limit.conf <<'NGINX'
limit_req_zone $binary_remote_addr zone=api:10m rate=10r/s;
limit_req_zone $binary_remote_addr zone=general:10m rate=30r/s;
NGINX

log "Removing default Nginx site"
rm -f /etc/nginx/sites-enabled/default

log "Setup complete!"
echo ""
echo "============================================================"
echo "Next steps:"
echo "1. Copy your app code: bash deploy.sh (from your local machine)"
echo "2. Set up SSL: certbot --nginx -d ${DOMAIN}"
echo "3. Edit /opt/fitnessos/backend/.env with real API keys"
echo "4. DB credentials are at: /root/fitnessos_db_creds.txt"
echo "============================================================"
