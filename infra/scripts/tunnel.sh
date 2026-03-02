#!/bin/bash
set -euo pipefail

MGMT_IP="${1:?Usage: tunnel.sh <mgmt-vpc-ip> [prod-public-ip]}"
PROD_IP="${2:-}"

echo "Opening SSH tunnels to mgmt services..."
echo "  Infisical:   http://localhost:9080"
echo "  Grafana:     http://localhost:3000"
echo "  Prometheus:  http://localhost:9090"
echo "  Uptime Kuma: http://localhost:3001"
echo ""
echo "Press Ctrl+C to close tunnels."
echo ""

if [ -n "$PROD_IP" ]; then
    ssh -N \
        -L 9080:127.0.0.1:9080 \
        -L 3000:127.0.0.1:3000 \
        -L 9090:127.0.0.1:9090 \
        -L 3001:127.0.0.1:3001 \
        -J "root@$PROD_IP" \
        "root@$MGMT_IP"
else
    ssh -N \
        -L 9080:127.0.0.1:9080 \
        -L 3000:127.0.0.1:3000 \
        -L 9090:127.0.0.1:9090 \
        -L 3001:127.0.0.1:3001 \
        "root@$MGMT_IP"
fi
