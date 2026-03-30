#!/bin/bash
set -euo pipefail

DEPLOY_DIR="/opt/mcpworks"
SRC_DIR="${DEPLOY_DIR}/src"
LOG_FILE="${DEPLOY_DIR}/deploy.log"

log() { echo "[$(date -Iseconds)] $*" | tee -a "$LOG_FILE"; }

log "=== Deploy started ==="

cd "$SRC_DIR"

log "Pulling latest code..."
git fetch origin main
git reset --hard origin/main

log "Rebuilding Docker image..."
cd "$DEPLOY_DIR"
sudo docker compose build api

log "Running migrations..."
sudo docker compose run --rm api alembic upgrade head 2>&1 || log "Migration skipped or failed (non-fatal)"

log "Restarting API..."
sudo docker compose up -d api

log "Waiting for health check..."
for i in $(seq 1 12); do
    sleep 5
    if sudo docker compose ps api 2>/dev/null | grep -q "(healthy)"; then
        log "API is healthy"
        break
    fi
    log "  attempt $i/12..."
done

if ! sudo docker compose ps api 2>/dev/null | grep -q "(healthy)"; then
    log "WARNING: API not healthy after 60s"
    sudo docker logs mcpworks-api --tail 30 >> "$LOG_FILE" 2>&1
    exit 1
fi

sudo docker image prune -f >> "$LOG_FILE" 2>&1

log "=== Deploy complete ==="
