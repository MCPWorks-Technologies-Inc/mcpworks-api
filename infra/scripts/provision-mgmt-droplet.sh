#!/bin/bash
set -euo pipefail

REGION="tor1"
DROPLET_NAME="mcpworks-mgmt"
DROPLET_SIZE="s-1vcpu-2gb"
DROPLET_IMAGE="ubuntu-22-04-x64"
PROD_DROPLET_NAME="mcpworks-prod"

echo "=== mcpworks mgmt droplet provisioning (TOR1) ==="

# 1. Detect prod droplet's VPC (mgmt must be in the same VPC)
PROD_DROPLET_ID=$(doctl compute droplet list --format ID,Name --no-header | grep "$PROD_DROPLET_NAME" | awk '{print $1}')
if [ -n "$PROD_DROPLET_ID" ]; then
    VPC_ID=$(doctl compute droplet get "$PROD_DROPLET_ID" --format VPCUUID --no-header)
    VPC_CIDR=$(doctl vpcs get "$VPC_ID" --format IPRange --no-header)
    PROD_PRIVATE_IP=$(doctl compute droplet get "$PROD_DROPLET_ID" --format PrivateIPv4 --no-header)
    echo "Found prod droplet in VPC $VPC_ID (CIDR: $VPC_CIDR)"
    echo "Prod private IP: $PROD_PRIVATE_IP"
else
    echo "WARNING: Prod droplet '$PROD_DROPLET_NAME' not found."
    echo "Creating new VPC for standalone mgmt deployment..."
    VPC_NAME="mcpworks-vpc-tor1"
    VPC_ID=$(doctl vpcs list --format ID,Name --no-header | grep "$VPC_NAME" | awk '{print $1}')
    if [ -z "$VPC_ID" ]; then
        VPC_ID=$(doctl vpcs create \
            --name "$VPC_NAME" \
            --region "$REGION" \
            --ip-range "10.137.0.0/16" \
            --format ID --no-header)
        echo "Created VPC: $VPC_ID"
    fi
    VPC_CIDR=$(doctl vpcs get "$VPC_ID" --format IPRange --no-header)
fi

# 2. Get SSH key ID (use first available)
SSH_KEY_ID=$(doctl compute ssh-key list --format ID --no-header | head -1)
if [ -z "$SSH_KEY_ID" ]; then
    echo "ERROR: No SSH keys found. Add one with: doctl compute ssh-key create"
    exit 1
fi
echo "Using SSH key: $SSH_KEY_ID"

# 3. Create mgmt droplet (no public IP, VPC-only)
echo "Creating droplet '$DROPLET_NAME'..."
DROPLET_ID=$(doctl compute droplet create "$DROPLET_NAME" \
    --region "$REGION" \
    --size "$DROPLET_SIZE" \
    --image "$DROPLET_IMAGE" \
    --vpc-uuid "$VPC_ID" \
    --ssh-keys "$SSH_KEY_ID" \
    --enable-private-networking \
    --no-header --format ID \
    --wait)
echo "Created droplet: $DROPLET_ID"

# 4. Get private IP
sleep 5
MGMT_PRIVATE_IP=$(doctl compute droplet get "$DROPLET_ID" --format PrivateIPv4 --no-header)
MGMT_PUBLIC_IP=$(doctl compute droplet get "$DROPLET_ID" --format PublicIPv4 --no-header)
echo "Mgmt private IP: $MGMT_PRIVATE_IP"
echo "Mgmt public IP:  $MGMT_PUBLIC_IP (will be removed after firewall setup)"

# 5. Create firewall — allow SSH + Loki from VPC only
FW_NAME="mcpworks-mgmt-fw"
EXISTING_FW=$(doctl compute firewall list --format ID,Name --no-header | grep "$FW_NAME" | awk '{print $1}')
if [ -z "$EXISTING_FW" ]; then
    echo "Creating firewall '$FW_NAME' (CIDR: $VPC_CIDR)..."
    doctl compute firewall create \
        --name "$FW_NAME" \
        --droplet-ids "$DROPLET_ID" \
        --inbound-rules "protocol:tcp,ports:22,address:$VPC_CIDR" \
        --inbound-rules "protocol:tcp,ports:3100,address:$VPC_CIDR" \
        --outbound-rules "protocol:tcp,ports:all,address:0.0.0.0/0" \
        --outbound-rules "protocol:udp,ports:all,address:0.0.0.0/0"
    echo "Firewall created"
else
    echo "Firewall already exists, adding droplet..."
    doctl compute firewall add-droplets "$EXISTING_FW" --droplet-ids "$DROPLET_ID"
fi

echo ""
echo "=== Provisioning complete ==="
echo ""
echo "Mgmt droplet: $DROPLET_NAME ($DROPLET_ID)"
echo "Private IP:   $MGMT_PRIVATE_IP"
echo "Region:       $REGION"
echo "VPC:          $VPC_ID (CIDR: $VPC_CIDR)"
if [ -n "${PROD_PRIVATE_IP:-}" ]; then
    echo "Prod VPC IP:  $PROD_PRIVATE_IP"
fi
echo ""
echo "Next steps:"
PROD_PUBLIC_IP=$(doctl compute droplet get "${PROD_DROPLET_ID:-}" --format PublicIPv4 --no-header 2>/dev/null || echo "<prod-public-ip>")
echo "  1. Deploy mgmt stack:      ./mgmt/deploy.sh $MGMT_PRIVATE_IP $PROD_PUBLIC_IP ${PROD_PRIVATE_IP:-<prod-vpc-ip>}"
echo "  2. Deploy prod exporters:  ./prod/deploy-exporters.sh $PROD_PUBLIC_IP $MGMT_PRIVATE_IP"
echo "  3. Open tunnels:           ./scripts/tunnel.sh $MGMT_PRIVATE_IP $PROD_PUBLIC_IP"
