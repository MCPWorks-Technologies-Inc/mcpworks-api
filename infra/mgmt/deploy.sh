#!/bin/bash
set -euo pipefail

MGMT_IP="${1:?Usage: deploy.sh <mgmt-vpc-ip> [prod-public-ip] [prod-vpc-ip]}"
PROD_IP="${2:-}"
PROD_VPC_IP="${3:-}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [ -n "$PROD_IP" ]; then
    SSH_CMD="ssh -J root@$PROD_IP root@$MGMT_IP"
    RSYNC_SSH="ssh -J root@$PROD_IP"
else
    SSH_CMD="ssh root@$MGMT_IP"
    RSYNC_SSH="ssh"
fi

echo "=== Deploying mgmt stack to $MGMT_IP ==="

# 1. Ensure Docker is installed
echo "Checking Docker..."
$SSH_CMD "command -v docker >/dev/null 2>&1 || (curl -fsSL https://get.docker.com | sh)"

# 2. Create remote directory
$SSH_CMD "mkdir -p /opt/mgmt"

# 3. Rsync mgmt files
echo "Syncing mgmt files..."
rsync -avz --delete \
    -e "$RSYNC_SSH" \
    --exclude='.env' \
    "$SCRIPT_DIR/" \
    "root@$MGMT_IP:/opt/mgmt/"

# 4. Substitute IP placeholders in config files
if [ -n "$PROD_VPC_IP" ]; then
    echo "Substituting PROD_VPC_IP=$PROD_VPC_IP in prometheus.yml..."
    $SSH_CMD "sed -i 's/PROD_VPC_IP/$PROD_VPC_IP/g' /opt/mgmt/prometheus/prometheus.yml"
else
    echo "WARNING: No PROD_VPC_IP provided — prometheus.yml still has placeholders"
fi

# 5. Generate .env if not present
$SSH_CMD "
if [ ! -f /opt/mgmt/.env ]; then
    echo 'Generating .env with random secrets...'
    cat > /opt/mgmt/.env << ENVEOF
INFISICAL_ENCRYPTION_KEY=\$(openssl rand -hex 16)
INFISICAL_AUTH_SECRET=\$(openssl rand -base64 32)
INFISICAL_DB_PASSWORD=\$(openssl rand -hex 16)
GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=\$(openssl rand -base64 16)
PROD_VPC_IP=${PROD_VPC_IP:-}
MGMT_VPC_IP=$MGMT_IP
ENVEOF
    echo '.env generated'
else
    echo '.env already exists, skipping'
fi
"

# 6. Start services
echo "Starting services..."
$SSH_CMD "cd /opt/mgmt && docker compose up -d"

# 7. Wait for health
echo "Waiting for services to start..."
sleep 10
$SSH_CMD "docker ps --format 'table {{.Names}}\t{{.Status}}'"

echo ""
echo "=== Deployment complete ==="
echo ""
echo "Open SSH tunnels to access:"
if [ -n "$PROD_IP" ]; then
    echo "  ./scripts/tunnel.sh $MGMT_IP $PROD_IP"
else
    echo "  ./scripts/tunnel.sh $MGMT_IP"
fi
