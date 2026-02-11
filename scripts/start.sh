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

# Start the application
echo "Starting uvicorn..."
exec uvicorn mcpworks_api.main:app \
    --host 0.0.0.0 \
    --port ${APP_PORT:-8000} \
    --workers ${UVICORN_WORKERS:-1} \
    --log-level ${LOG_LEVEL:-info}
