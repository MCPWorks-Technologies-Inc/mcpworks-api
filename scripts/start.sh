#!/bin/bash
# Production startup script
# Runs database migrations before starting the application

set -e

echo "========================================"
echo "MCPWorks API Startup"
echo "Environment: ${APP_ENV:-development}"
echo "========================================"

# Wait for database to be ready
echo "Checking database connection..."
python -c "
import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
import os

async def check_db():
    engine = create_async_engine(os.environ['DATABASE_URL'])
    async with engine.connect() as conn:
        await conn.execute(text('SELECT 1'))
    await engine.dispose()
    print('Database connection successful')

asyncio.run(check_db())
"

# Run database migrations
echo "Running database migrations..."
alembic upgrade head
echo "Migrations complete"

# Initialize sandbox (production only)
if [ "${SANDBOX_DEV_MODE:-true}" != "true" ]; then
    echo "Initializing sandbox environment..."

    # Create device nodes for nsjail rootfs
    DEVDIR="/opt/mcpworks/rootfs/dev"
    mkdir -p "${DEVDIR}"
    if [ ! -e "${DEVDIR}/null" ]; then
        mknod -m 666 "${DEVDIR}/null" c 1 3
        mknod -m 666 "${DEVDIR}/zero" c 1 5
        mknod -m 444 "${DEVDIR}/urandom" c 1 9
    fi

    # ORDER-002: Set up aggregate cgroup limits for sandbox
    if [ -x /opt/mcpworks/bin/setup-cgroups.sh ]; then
        /opt/mcpworks/bin/setup-cgroups.sh || echo "Warning: cgroup setup failed (non-fatal)"
    fi

    # Verify nsjail binary
    if [ -x /usr/local/bin/nsjail ]; then
        echo "nsjail version: $(/usr/local/bin/nsjail --version 2>&1 || echo 'unknown')"
    else
        echo "WARNING: nsjail binary not found at /usr/local/bin/nsjail"
    fi

    # Verify sandbox packages
    if [ -d /opt/mcpworks/sandbox-root/site-packages ]; then
        PKG_COUNT=$(ls -1d /opt/mcpworks/sandbox-root/site-packages/*/ 2>/dev/null | wc -l)
        echo "Sandbox packages available: ${PKG_COUNT} directories"
    else
        echo "WARNING: Sandbox packages not found"
    fi

    # F-16: UID-based network isolation for sandbox tiers.
    #
    # Two UIDs are used to distinguish free vs paid sandbox executions:
    #   UID 65534 (nobody)  = free tier  → ALL outbound blocked
    #   UID 65533 (sandbox) = paid tiers → outbound allowed, internal blocked
    #
    # spawn-sandbox.sh overrides the nsjail UID mapping for paid tiers.
    if command -v iptables >/dev/null 2>&1; then

        # === FREE TIER (UID 65534): Block ALL outbound traffic ===
        # No internet, no DNS, no nothing. Complete network isolation.
        iptables -C OUTPUT -m owner --uid-owner 65534 -j DROP 2>/dev/null || \
        iptables -A OUTPUT -m owner --uid-owner 65534 -j DROP
        echo "Blocked ALL outbound for free tier (uid 65534)"

        # === PAID TIERS (UID 65533): Block internal, allow internet ===

        # Resolve internal service IPs from Docker DNS
        POSTGRES_IP=$(getent hosts postgres 2>/dev/null | awk '{print $1}')
        REDIS_IP=$(getent hosts redis 2>/dev/null | awk '{print $1}')

        if [ -n "${POSTGRES_IP}" ]; then
            iptables -C OUTPUT -d "${POSTGRES_IP}" -p tcp --dport 5432 -m owner --uid-owner 65533 -j DROP 2>/dev/null || \
            iptables -A OUTPUT -d "${POSTGRES_IP}" -p tcp --dport 5432 -m owner --uid-owner 65533 -j DROP
            echo "Blocked paid sandbox (uid 65533) -> postgres (${POSTGRES_IP}:5432)"
        fi

        if [ -n "${REDIS_IP}" ]; then
            iptables -C OUTPUT -d "${REDIS_IP}" -p tcp --dport 6379 -m owner --uid-owner 65533 -j DROP 2>/dev/null || \
            iptables -A OUTPUT -d "${REDIS_IP}" -p tcp --dport 6379 -m owner --uid-owner 65533 -j DROP
            echo "Blocked paid sandbox (uid 65533) -> redis (${REDIS_IP}:6379)"
        fi

        iptables -C OUTPUT -d 169.254.169.254 -m owner --uid-owner 65533 -j DROP 2>/dev/null || \
        iptables -A OUTPUT -d 169.254.169.254 -m owner --uid-owner 65533 -j DROP
        echo "Blocked paid sandbox (uid 65533) -> metadata (169.254.169.254)"

        iptables -C OUTPUT -d 127.0.0.0/8 -m owner --uid-owner 65533 -j DROP 2>/dev/null || \
        iptables -A OUTPUT -d 127.0.0.0/8 -m owner --uid-owner 65533 -j DROP
        echo "Blocked paid sandbox (uid 65533) -> localhost (127.0.0.0/8)"

        DOCKER_SUBNET=$(ip route | awk '/172\.[0-9]+\.0\.0/ {print $1}')
        if [ -n "${DOCKER_SUBNET}" ]; then
            iptables -C OUTPUT -d "${DOCKER_SUBNET}" -m owner --uid-owner 65533 -j DROP 2>/dev/null || \
            iptables -A OUTPUT -d "${DOCKER_SUBNET}" -m owner --uid-owner 65533 -j DROP
            echo "Blocked paid sandbox (uid 65533) -> Docker subnet (${DOCKER_SUBNET})"
        else
            for SUBNET in 172.16.0.0/12 10.0.0.0/8; do
                iptables -C OUTPUT -d "${SUBNET}" -m owner --uid-owner 65533 -j DROP 2>/dev/null || \
                iptables -A OUTPUT -d "${SUBNET}" -m owner --uid-owner 65533 -j DROP
            done
            echo "Blocked paid sandbox (uid 65533) -> Docker subnets (172.16.0.0/12, 10.0.0.0/8)"
        fi

        OUR_IPS=$(getent hosts api.mcpworks.io 2>/dev/null | awk '{print $1}')
        for IP in ${OUR_IPS}; do
            iptables -C OUTPUT -d "${IP}" -m owner --uid-owner 65533 -j DROP 2>/dev/null || \
            iptables -A OUTPUT -d "${IP}" -m owner --uid-owner 65533 -j DROP
            echo "Blocked paid sandbox (uid 65533) -> mcpworks API (${IP})"
        done

        iptables -C OUTPUT -m owner --uid-owner 65533 -p tcp --syn \
            -m hashlimit --hashlimit-above 10/sec --hashlimit-burst 20 \
            --hashlimit-name sandbox_rate --hashlimit-mode srcip -j DROP 2>/dev/null || \
        iptables -A OUTPUT -m owner --uid-owner 65533 -p tcp --syn \
            -m hashlimit --hashlimit-above 10/sec --hashlimit-burst 20 \
            --hashlimit-name sandbox_rate --hashlimit-mode srcip -j DROP
        echo "Rate limited paid sandbox (uid 65533) outbound TCP (10/sec burst 20)"

        iptables -C OUTPUT -m owner --uid-owner 65533 -p tcp --syn \
            -m limit --limit 5/min --limit-burst 10 \
            -j LOG --log-prefix "SANDBOX_EGRESS: " --log-level info 2>/dev/null || \
        iptables -A OUTPUT -m owner --uid-owner 65533 -p tcp --syn \
            -m limit --limit 5/min --limit-burst 10 \
            -j LOG --log-prefix "SANDBOX_EGRESS: " --log-level info
        echo "Logging paid sandbox (uid 65533) outbound connections"

        iptables -C OUTPUT -m owner --uid-owner 65533 -p udp --dport 53 -j ACCEPT 2>/dev/null || \
        iptables -A OUTPUT -m owner --uid-owner 65533 -p udp --dport 53 -j ACCEPT
        iptables -C OUTPUT -m owner --uid-owner 65533 -p udp -j DROP 2>/dev/null || \
        iptables -A OUTPUT -m owner --uid-owner 65533 -p udp -j DROP
        echo "Allowed paid sandbox (uid 65533) DNS, blocked other UDP"
    else
        echo "Warning: iptables not available, sandbox can reach internal services"
    fi

    echo "Sandbox initialization complete"
fi

# Start the application
UVICORN_CMD="uvicorn mcpworks_api.main:app \
    --host 0.0.0.0 \
    --port ${APP_PORT:-8000} \
    --workers ${UVICORN_WORKERS:-1} \
    --log-level ${LOG_LEVEL:-info}"

if [ -n "${INFISICAL_TOKEN:-}" ] && [ -n "${INFISICAL_PROJECT_ID:-}" ] && command -v infisical >/dev/null 2>&1; then
    echo "Starting uvicorn with Infisical secrets injection..."
    exec infisical run \
        --token "$INFISICAL_TOKEN" \
        --projectId "$INFISICAL_PROJECT_ID" \
        --env prod \
        ${INFISICAL_API_URL:+--domain "$INFISICAL_API_URL"} \
        -- $UVICORN_CMD
else
    echo "Starting uvicorn (no Infisical — using environment variables)..."
    exec $UVICORN_CMD
fi
