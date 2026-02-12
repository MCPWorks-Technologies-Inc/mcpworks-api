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

    # Create cgroup directory for nsjail
    CGDIR="/sys/fs/cgroup/mcpworks"
    if [ -d /sys/fs/cgroup ] && [ ! -d "${CGDIR}" ]; then
        mkdir -p "${CGDIR}" 2>/dev/null || echo "Warning: Could not create cgroup dir (cgroups v2 may not be available)"
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

    echo "Sandbox initialization complete"
fi

# Start the application
echo "Starting uvicorn..."
exec uvicorn mcpworks_api.main:app \
    --host 0.0.0.0 \
    --port ${APP_PORT:-8000} \
    --workers ${UVICORN_WORKERS:-1} \
    --log-level ${LOG_LEVEL:-info}
