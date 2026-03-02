#!/bin/bash
set -euo pipefail

REGION="tor1"
VPC_NAME="mcpworks-vpc-tor1"
OLD_DROPLET_NAME="mcpworks-prod"
NEW_DROPLET_NAME="mcpworks-prod"
SNAPSHOT_NAME="mcpworks-prod-pre-tor1-migration"

echo "=== Migrate mcpworks-prod from NYC1 to TOR1 ==="
echo ""
echo "This script will:"
echo "  1. Snapshot the current prod droplet"
echo "  2. Transfer the snapshot to TOR1"
echo "  3. Create a new droplet from the snapshot in TOR1 VPC"
echo "  4. Print the new IP for DNS update"
echo ""
echo "You must manually:"
echo "  - Update DNS (api.mcpworks.io) to the new IP"
echo "  - Update GitHub secrets (DEPLOY_HOST)"
echo "  - Verify the new droplet works"
echo "  - Destroy the old droplet"
echo ""
read -p "Continue? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 0
fi

# 1. Find the current prod droplet
OLD_DROPLET_ID=$(doctl compute droplet list --format ID,Name --no-header | grep "$OLD_DROPLET_NAME" | awk '{print $1}')
if [ -z "$OLD_DROPLET_ID" ]; then
    echo "ERROR: Droplet '$OLD_DROPLET_NAME' not found"
    exit 1
fi
echo "Found prod droplet: $OLD_DROPLET_ID"

# 2. Power off and snapshot
echo "Powering off droplet for clean snapshot..."
doctl compute droplet-action power-off "$OLD_DROPLET_ID" --wait
echo "Powered off."

echo "Creating snapshot '$SNAPSHOT_NAME'..."
doctl compute droplet-action snapshot "$OLD_DROPLET_ID" --snapshot-name "$SNAPSHOT_NAME" --wait
echo "Snapshot created."

# Power back on so prod stays live during migration
echo "Powering prod back on..."
doctl compute droplet-action power-on "$OLD_DROPLET_ID" --wait
echo "Prod is back online."

# 3. Get snapshot ID
SNAPSHOT_ID=$(doctl compute snapshot list --format ID,Name --no-header | grep "$SNAPSHOT_NAME" | awk '{print $1}')
echo "Snapshot ID: $SNAPSHOT_ID"

# 4. Transfer snapshot to TOR1
echo "Transferring snapshot to $REGION (this may take several minutes)..."
doctl compute image-action transfer "$SNAPSHOT_ID" --region "$REGION" --wait
echo "Transfer complete."

# 5. Ensure VPC exists
VPC_ID=$(doctl vpcs list --format ID,Name --no-header | grep "$VPC_NAME" | awk '{print $1}')
if [ -z "$VPC_ID" ]; then
    echo "Creating VPC '$VPC_NAME' in $REGION..."
    VPC_ID=$(doctl vpcs create \
        --name "$VPC_NAME" \
        --region "$REGION" \
        --ip-range "10.130.0.0/20" \
        --format ID --no-header)
fi
echo "VPC: $VPC_ID"

# 6. Get SSH key
SSH_KEY_ID=$(doctl compute ssh-key list --format ID --no-header | head -1)

# 7. Create new droplet from snapshot
echo "Creating new droplet in $REGION..."
NEW_DROPLET_ID=$(doctl compute droplet create "${NEW_DROPLET_NAME}-tor1" \
    --region "$REGION" \
    --size "s-2vcpu-4gb" \
    --image "$SNAPSHOT_ID" \
    --vpc-uuid "$VPC_ID" \
    --ssh-keys "$SSH_KEY_ID" \
    --enable-private-networking \
    --no-header --format ID \
    --wait)
echo "Created: $NEW_DROPLET_ID"

sleep 5
NEW_PUBLIC_IP=$(doctl compute droplet get "$NEW_DROPLET_ID" --format PublicIPv4 --no-header)
NEW_PRIVATE_IP=$(doctl compute droplet get "$NEW_DROPLET_ID" --format PrivateIPv4 --no-header)

echo ""
echo "=== Migration snapshot created ==="
echo ""
echo "New droplet:    ${NEW_DROPLET_NAME}-tor1 ($NEW_DROPLET_ID)"
echo "New public IP:  $NEW_PUBLIC_IP"
echo "New private IP: $NEW_PRIVATE_IP"
echo "Region:         $REGION"
echo ""
echo "Manual steps remaining:"
echo "  1. Verify: ssh root@$NEW_PUBLIC_IP 'docker ps'"
echo "  2. Start services: ssh root@$NEW_PUBLIC_IP 'cd /opt/mcpworks && docker compose -f docker-compose.prod.yml up -d'"
echo "  3. Test: curl -k https://$NEW_PUBLIC_IP/v1/health"
echo "  4. Update DNS: api.mcpworks.io → $NEW_PUBLIC_IP"
echo "  5. Update GitHub secret DEPLOY_HOST → $NEW_PUBLIC_IP"
echo "  6. Wait for DNS propagation, verify production"
echo "  7. Rename droplet: doctl compute droplet rename $NEW_DROPLET_ID --droplet-name mcpworks-prod"
echo "  8. Destroy old droplet: doctl compute droplet delete $OLD_DROPLET_ID"
echo "  9. Delete snapshot: doctl compute snapshot delete $SNAPSHOT_ID"
