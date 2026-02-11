#!/bin/bash
set -euo pipefail

# MCPWorks Production Server Setup Script
# Run as root on a fresh Ubuntu 22.04 LTS server

echo "=== MCPWorks Production Server Setup ==="

# Update system
echo "[1/8] Updating system packages..."
apt-get update && apt-get upgrade -y

# Install dependencies
echo "[2/8] Installing dependencies..."
apt-get install -y \
    apt-transport-https \
    ca-certificates \
    curl \
    gnupg \
    lsb-release \
    git \
    ufw \
    fail2ban \
    unattended-upgrades

# Install Docker
echo "[3/8] Installing Docker..."
if ! command -v docker &> /dev/null; then
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null
    apt-get update
    apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
    systemctl enable docker
    systemctl start docker
fi

# Install nsjail dependencies (for building if needed)
echo "[4/8] Installing nsjail dependencies..."
apt-get install -y \
    autoconf \
    bison \
    flex \
    gcc \
    g++ \
    git \
    libprotobuf-dev \
    libnl-route-3-dev \
    libtool \
    make \
    pkg-config \
    protobuf-compiler

# Create app user
echo "[5/8] Creating mcpworks user..."
if ! id "mcpworks" &>/dev/null; then
    useradd -m -s /bin/bash mcpworks
    usermod -aG docker mcpworks
fi

# Create app directories
echo "[6/8] Creating application directories..."
mkdir -p /opt/mcpworks
mkdir -p /opt/mcpworks/data
mkdir -p /opt/mcpworks/logs
mkdir -p /opt/mcpworks/sandbox
chown -R mcpworks:mcpworks /opt/mcpworks

# Configure firewall
echo "[7/8] Configuring firewall..."
ufw default deny incoming
ufw default allow outgoing
ufw allow ssh
# No HTTP/HTTPS ports needed - Cloudflare Tunnel handles ingress
ufw --force enable

# Configure fail2ban
echo "[8/8] Configuring fail2ban..."
systemctl enable fail2ban
systemctl start fail2ban

# Enable automatic security updates
dpkg-reconfigure -plow unattended-upgrades

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Next steps:"
echo "1. Copy docker-compose.prod.yml to /opt/mcpworks/"
echo "2. Create /opt/mcpworks/.env with production secrets"
echo "3. Run: cd /opt/mcpworks && docker compose -f docker-compose.prod.yml up -d"
echo ""
echo "Server is ready for MCPWorks deployment!"
