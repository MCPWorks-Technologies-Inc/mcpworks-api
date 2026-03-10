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

    # Network isolation via clone_newnet (per-sandbox network namespaces).
    #
    # Free tier:  empty network namespace = zero connectivity (no setup needed).
    # Paid tiers: MACVLAN on container's eth0, unique IP per sandbox.
    #
    # MACVLAN traffic bypasses the container's network namespace entirely,
    # so iptables rules must be on the HOST, not here.
    # See: scripts/setup-sandbox-network.sh (run on host after deployment).
    echo "Network isolation: clone_newnet (per-sandbox network namespaces)"
    echo "  Free tier:  empty netns (zero connectivity)"
    echo "  Paid tiers: MACVLAN on eth0 (host iptables required)"

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
