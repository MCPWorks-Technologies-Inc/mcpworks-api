#!/bin/bash
# setup-sandbox-network.sh — Configure host-level iptables for MACVLAN sandbox networking.
#
# Run on the HOST (not inside the container) after container startup.
# With clone_newnet + MACVLAN, sandbox traffic bypasses the container's
# network namespace entirely — iptables rules must be on the host.
#
# Called by: deployment workflow (CI/CD or manual)
# Idempotent: uses -C (check) before -I/-A (insert/append)
#
# Network architecture:
#   Free tier:  clone_newnet with no MACVLAN = zero connectivity
#   Paid tiers: clone_newnet with MACVLAN on container's eth0
#               Sandbox IP: 172.18.128-254.1-254 (same subnet as Docker bridge)
#               Gateway: Docker bridge (172.18.0.1)
#               NAT: Docker's existing MASQUERADE handles outbound

set -euo pipefail

# Sandbox IPs use the high range of the Docker bridge subnet
SANDBOX_SUBNET="172.18.128.0/17"

echo "=== MCPWorks Sandbox Network Setup ==="

if ! command -v iptables >/dev/null 2>&1; then
    echo "ERROR: iptables not found"
    exit 1
fi

# FORWARD: block sandbox -> sensitive destinations (inserted at top of chain)
# Note: sandbox is on Docker bridge subnet (172.18.X.Y), so we can't block
# 172.16.0.0/12 broadly. Instead block specific dangerous destinations.
for BLOCKED in 169.254.169.254/32 127.0.0.0/8 10.0.0.0/8; do
    iptables -C FORWARD -s "${SANDBOX_SUBNET}" -d "${BLOCKED}" -j DROP 2>/dev/null || \
    iptables -I FORWARD -s "${SANDBOX_SUBNET}" -d "${BLOCKED}" -j DROP
done
echo "[OK] Blocked sandbox -> metadata, localhost, 10/8"

# FORWARD: block sandbox -> Docker low-range IPs (containers, but not gateway)
# Docker assigns container IPs in 172.18.0.2-127 range. Block sandbox access
# to other containers. Gateway 172.18.0.1 is handled at L2, not FORWARD.
iptables -C FORWARD -s "${SANDBOX_SUBNET}" -d 172.18.0.0/25 -j DROP 2>/dev/null || \
iptables -I FORWARD -s "${SANDBOX_SUBNET}" -d 172.18.0.0/25 -j DROP
echo "[OK] Blocked sandbox -> Docker containers (172.18.0.0/25)"

# FORWARD: rate limit outbound TCP
iptables -C FORWARD -s "${SANDBOX_SUBNET}" -p tcp --syn \
    -m hashlimit --hashlimit-above 10/sec --hashlimit-burst 20 \
    --hashlimit-name sandbox_fwd_rate --hashlimit-mode srcip -j DROP 2>/dev/null || \
iptables -A FORWARD -s "${SANDBOX_SUBNET}" -p tcp --syn \
    -m hashlimit --hashlimit-above 10/sec --hashlimit-burst 20 \
    --hashlimit-name sandbox_fwd_rate --hashlimit-mode srcip -j DROP
echo "[OK] Rate limited sandbox TCP (10/sec burst 20)"

# FORWARD: allow DNS, block other UDP
iptables -C FORWARD -s "${SANDBOX_SUBNET}" -p udp --dport 53 -j ACCEPT 2>/dev/null || \
iptables -A FORWARD -s "${SANDBOX_SUBNET}" -p udp --dport 53 -j ACCEPT
iptables -C FORWARD -s "${SANDBOX_SUBNET}" -p udp -j DROP 2>/dev/null || \
iptables -A FORWARD -s "${SANDBOX_SUBNET}" -p udp -j DROP
echo "[OK] Allowed DNS, blocked other UDP"

# FORWARD: log sandbox egress (sampled)
iptables -C FORWARD -s "${SANDBOX_SUBNET}" -p tcp --syn \
    -m limit --limit 5/min --limit-burst 10 \
    -j LOG --log-prefix "SANDBOX_EGRESS: " --log-level info 2>/dev/null || \
iptables -A FORWARD -s "${SANDBOX_SUBNET}" -p tcp --syn \
    -m limit --limit 5/min --limit-burst 10 \
    -j LOG --log-prefix "SANDBOX_EGRESS: " --log-level info
echo "[OK] Logging sandbox egress"

# FORWARD: allow remaining sandbox traffic (after DROPs above)
# Docker may have a default DROP policy on FORWARD, so we need explicit ACCEPT.
iptables -C FORWARD -s "${SANDBOX_SUBNET}" -j ACCEPT 2>/dev/null || \
iptables -A FORWARD -s "${SANDBOX_SUBNET}" -j ACCEPT
iptables -C FORWARD -d "${SANDBOX_SUBNET}" -j ACCEPT 2>/dev/null || \
iptables -A FORWARD -d "${SANDBOX_SUBNET}" -j ACCEPT
echo "[OK] Allowed remaining sandbox FORWARD traffic"

# NAT: ensure MASQUERADE for sandbox subnet (Docker may already handle this
# for the bridge subnet, but add explicitly to be safe)
iptables -t nat -C POSTROUTING -s "${SANDBOX_SUBNET}" ! -d 172.18.0.0/16 -j MASQUERADE 2>/dev/null || \
iptables -t nat -A POSTROUTING -s "${SANDBOX_SUBNET}" ! -d 172.18.0.0/16 -j MASQUERADE
echo "[OK] NAT masquerade for sandbox -> internet"

echo ""
echo "=== Sandbox network setup complete ==="
echo "Verify: iptables -L FORWARD -n -v | grep 172.18.128"
echo "Verify: iptables -t nat -L POSTROUTING -n -v | grep 172.18.128"
