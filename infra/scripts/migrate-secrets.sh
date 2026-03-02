#!/bin/bash
set -euo pipefail

MGMT_IP="${1:?Usage: migrate-secrets.sh <mgmt-vpc-ip>}"
PROD_IP="${2:-159.203.30.199}"
INFISICAL_URL="http://${MGMT_IP}:9080"

echo "=== Migrate secrets from .env to Infisical ==="
echo ""
echo "This script:"
echo "  1. Reads /opt/mcpworks/.env from prod ($PROD_IP)"
echo "  2. Creates a project in Infisical ($INFISICAL_URL)"
echo "  3. Imports each key/value into the 'prod' environment"
echo "  4. Creates a machine identity for the prod droplet"
echo ""
echo "Prerequisites:"
echo "  - Infisical is running and initial setup is complete"
echo "  - You have logged in via: infisical login --domain=$INFISICAL_URL"
echo "  - SSH tunnel is open to mgmt (run scripts/tunnel.sh first)"
echo ""
read -p "Continue? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 0
fi

# 1. Fetch .env from prod
echo "Fetching .env from prod..."
ENV_CONTENT=$(ssh "root@$PROD_IP" "cat /opt/mcpworks/.env")
echo "Found $(echo "$ENV_CONTENT" | grep -c '=') variables"

# 2. Create Infisical project
echo ""
echo "Creating Infisical project 'mcpworks-api'..."
PROJECT_ID=$(infisical projects create --name "mcpworks-api" --format json 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])" || true)

if [ -z "$PROJECT_ID" ]; then
    echo "Project may already exist. List projects with: infisical projects list"
    read -p "Enter project ID: " PROJECT_ID
fi
echo "Project ID: $PROJECT_ID"

# 3. Import secrets
echo ""
echo "Importing secrets into 'prod' environment..."
while IFS= read -r line; do
    [[ -z "$line" || "$line" =~ ^# ]] && continue

    KEY=$(echo "$line" | cut -d'=' -f1)
    VALUE=$(echo "$line" | cut -d'=' -f2-)

    VALUE=$(echo "$VALUE" | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//")

    if [ -n "$KEY" ] && [ -n "$VALUE" ]; then
        echo "  Setting $KEY..."
        infisical secrets set "$KEY=$VALUE" \
            --projectId "$PROJECT_ID" \
            --env prod \
            2>/dev/null || echo "  WARNING: Failed to set $KEY"
    fi
done <<< "$ENV_CONTENT"

echo ""
echo "=== Import complete ==="
echo ""
echo "Next steps:"
echo "  1. Verify in Infisical UI: http://localhost:9080"
echo "  2. Create a machine identity for the prod droplet in the Infisical UI"
echo "  3. Generate a universal auth token for the identity"
echo "  4. On prod, set INFISICAL_TOKEN and INFISICAL_PROJECT_ID in .env"
echo "  5. Redeploy the API with Infisical integration"
echo ""
echo "Project ID to use: $PROJECT_ID"
