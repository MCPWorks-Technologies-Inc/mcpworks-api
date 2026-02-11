#!/bin/bash
set -euo pipefail

# MCPWorks Deployment Script
# Run from local machine to deploy to production VM

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Configuration
VM_USER="${VM_USER:-mcpworks}"
VM_HOST="${VM_HOST:-}"
DEPLOY_DIR="/opt/mcpworks"

if [ -z "$VM_HOST" ]; then
    echo "Error: VM_HOST environment variable not set"
    echo "Usage: VM_HOST=your-vm-ip ./scripts/deploy.sh"
    exit 1
fi

echo "=== MCPWorks Deployment ==="
echo "Target: ${VM_USER}@${VM_HOST}"
echo ""

# Build Docker image locally and save
echo "[1/5] Building Docker image..."
docker build -t mcpworks-api:latest "$PROJECT_DIR"

echo "[2/5] Saving Docker image..."
docker save mcpworks-api:latest | gzip > /tmp/mcpworks-api.tar.gz

echo "[3/5] Copying files to server..."
scp /tmp/mcpworks-api.tar.gz "${VM_USER}@${VM_HOST}:${DEPLOY_DIR}/"
scp "$PROJECT_DIR/docker-compose.prod.yml" "${VM_USER}@${VM_HOST}:${DEPLOY_DIR}/"
scp -r "$PROJECT_DIR/deploy/nsjail" "${VM_USER}@${VM_HOST}:${DEPLOY_DIR}/"

echo "[4/5] Loading image and restarting services..."
ssh "${VM_USER}@${VM_HOST}" << 'ENDSSH'
cd /opt/mcpworks
gunzip -c mcpworks-api.tar.gz | docker load
rm mcpworks-api.tar.gz
docker compose -f docker-compose.prod.yml pull redis postgres cloudflared
docker compose -f docker-compose.prod.yml up -d --force-recreate api
docker compose -f docker-compose.prod.yml ps
ENDSSH

echo "[5/5] Running health check..."
sleep 10
ssh "${VM_USER}@${VM_HOST}" "curl -sf http://localhost:8000/health || echo 'Health check failed'"

echo ""
echo "=== Deployment Complete ==="
rm -f /tmp/mcpworks-api.tar.gz
