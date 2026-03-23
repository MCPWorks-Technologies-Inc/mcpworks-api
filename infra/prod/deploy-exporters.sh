#!/bin/bash
set -euo pipefail

PROD_IP="${1:?Usage: deploy-exporters.sh <prod-ip> [mgmt-vpc-ip]}"
MGMT_VPC_IP="${2:-}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== Deploying exporters to prod ($PROD_IP) ==="

# 1. Create remote directory
ssh "root@$PROD_IP" "mkdir -p /opt/mcpworks/monitoring/promtail"

# 2. Rsync exporter files
echo "Syncing exporter files..."
rsync -avz \
    "$SCRIPT_DIR/docker-compose.exporters.yml" \
    "root@$PROD_IP:/opt/mcpworks/monitoring/"

rsync -avz \
    "$SCRIPT_DIR/promtail/" \
    "root@$PROD_IP:/opt/mcpworks/monitoring/promtail/"

# 3. Substitute IP placeholders in promtail config
if [ -n "$MGMT_VPC_IP" ]; then
    echo "Substituting MGMT_VPC_IP=$MGMT_VPC_IP in promtail-config.yml..."
    ssh "root@$PROD_IP" "sed -i 's/MGMT_VPC_IP/$MGMT_VPC_IP/g' /opt/mcpworks/monitoring/promtail/promtail-config.yml"
else
    echo "WARNING: No MGMT_VPC_IP provided — promtail-config.yml still has placeholders"
fi

# 4. Start exporters
echo "Starting exporters..."
ssh "root@$PROD_IP" "cd /opt/mcpworks/monitoring && docker compose -f docker-compose.exporters.yml up -d"

# 5. Verify
echo "Checking status..."
ssh "root@$PROD_IP" "docker ps --filter name=mcpworks-node-exporter --filter name=mcpworks-promtail --format 'table {{.Names}}\t{{.Status}}'"

echo ""
echo "=== Exporters deployed ==="
echo "  node-exporter: port 9100"
echo "  promtail: shipping logs to Loki"
