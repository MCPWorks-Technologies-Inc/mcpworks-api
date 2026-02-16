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

    # Block sandbox processes from reaching internal Docker services.
    # Sandbox shares the container network (clone_newnet: false) so it
    # can reach the internet, but we block access to postgres and redis.
    if command -v iptables >/dev/null 2>&1; then
        # Resolve internal service IPs from Docker DNS
        POSTGRES_IP=$(getent hosts postgres 2>/dev/null | awk '{print $1}')
        REDIS_IP=$(getent hosts redis 2>/dev/null | awk '{print $1}')

        if [ -n "${POSTGRES_IP}" ]; then
            iptables -C OUTPUT -d "${POSTGRES_IP}" -p tcp --dport 5432 -m owner --uid-owner 65534 -j REJECT 2>/dev/null || \
            iptables -A OUTPUT -d "${POSTGRES_IP}" -p tcp --dport 5432 -m owner --uid-owner 65534 -j REJECT
            echo "Blocked sandbox (uid 65534) → postgres (${POSTGRES_IP}:5432)"
        fi

        if [ -n "${REDIS_IP}" ]; then
            iptables -C OUTPUT -d "${REDIS_IP}" -p tcp --dport 6379 -m owner --uid-owner 65534 -j REJECT 2>/dev/null || \
            iptables -A OUTPUT -d "${REDIS_IP}" -p tcp --dport 6379 -m owner --uid-owner 65534 -j REJECT
            echo "Blocked sandbox (uid 65534) → redis (${REDIS_IP}:6379)"
        fi

        # Block cloud metadata endpoint (DO/AWS/GCP SSRF vector)
        iptables -C OUTPUT -d 169.254.169.254 -m owner --uid-owner 65534 -j REJECT 2>/dev/null || \
        iptables -A OUTPUT -d 169.254.169.254 -m owner --uid-owner 65534 -j REJECT
        echo "Blocked sandbox (uid 65534) → metadata (169.254.169.254)"

        # Block localhost (prevents SSRF to API on :8000)
        iptables -C OUTPUT -d 127.0.0.0/8 -m owner --uid-owner 65534 -j REJECT 2>/dev/null || \
        iptables -A OUTPUT -d 127.0.0.0/8 -m owner --uid-owner 65534 -j REJECT
        echo "Blocked sandbox (uid 65534) → localhost (127.0.0.0/8)"

        # Rate limit outbound TCP connections (20/sec burst 50)
        iptables -C OUTPUT -m owner --uid-owner 65534 -p tcp --syn \
            -m hashlimit --hashlimit-above 20/sec --hashlimit-burst 50 \
            --hashlimit-name sandbox_rate --hashlimit-mode srcip -j REJECT 2>/dev/null || \
        iptables -A OUTPUT -m owner --uid-owner 65534 -p tcp --syn \
            -m hashlimit --hashlimit-above 20/sec --hashlimit-burst 50 \
            --hashlimit-name sandbox_rate --hashlimit-mode srcip -j REJECT
        echo "Rate limited sandbox (uid 65534) outbound TCP (20/sec burst 50)"

        # Allow DNS (UDP 53) but block other UDP
        iptables -C OUTPUT -m owner --uid-owner 65534 -p udp --dport 53 -j ACCEPT 2>/dev/null || \
        iptables -A OUTPUT -m owner --uid-owner 65534 -p udp --dport 53 -j ACCEPT
        iptables -C OUTPUT -m owner --uid-owner 65534 -p udp -j REJECT 2>/dev/null || \
        iptables -A OUTPUT -m owner --uid-owner 65534 -p udp -j REJECT
        echo "Allowed sandbox (uid 65534) DNS, blocked other UDP"
    else
        echo "Warning: iptables not available, sandbox can reach internal services"
    fi

    echo "Sandbox initialization complete"
fi

# Start the application
echo "Starting uvicorn..."
exec uvicorn mcpworks_api.main:app \
    --host 0.0.0.0 \
    --port ${APP_PORT:-8000} \
    --workers ${UVICORN_WORKERS:-1} \
    --log-level ${LOG_LEVEL:-info}
