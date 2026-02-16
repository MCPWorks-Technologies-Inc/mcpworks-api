#!/bin/bash
# restore-db.sh — Restore PostgreSQL from a backup file.
#
# ORDER-014: Test restore procedure.
#
# Usage: ./scripts/restore-db.sh <backup_file.sql.gz>
#
# WARNING: This will DROP and recreate the database!

set -euo pipefail

BACKUP_FILE="${1:?Usage: restore-db.sh <backup_file.sql.gz>}"
CONTAINER="mcpworks-postgres"
DB_USER="mcpworks"
DB_NAME="mcpworks"

if [ ! -f "${BACKUP_FILE}" ]; then
    echo "ERROR: Backup file not found: ${BACKUP_FILE}"
    exit 1
fi

echo "WARNING: This will DROP and recreate the '${DB_NAME}' database!"
echo "Backup file: ${BACKUP_FILE}"
echo ""
read -p "Are you sure? (yes/no): " CONFIRM

if [ "${CONFIRM}" != "yes" ]; then
    echo "Aborted."
    exit 0
fi

echo "[$(date -Iseconds)] Stopping API container..."
docker stop mcpworks-api 2>/dev/null || true

echo "[$(date -Iseconds)] Dropping and recreating database..."
docker exec "${CONTAINER}" psql -U "${DB_USER}" -d postgres \
    -c "DROP DATABASE IF EXISTS ${DB_NAME};" \
    -c "CREATE DATABASE ${DB_NAME} OWNER ${DB_USER};"

echo "[$(date -Iseconds)] Restoring from backup..."
gunzip -c "${BACKUP_FILE}" | docker exec -i "${CONTAINER}" psql -U "${DB_USER}" -d "${DB_NAME}" --quiet

echo "[$(date -Iseconds)] Running migrations..."
docker exec mcpworks-api alembic upgrade head 2>/dev/null || \
    echo "Note: API container not running, run migrations manually after restart"

echo "[$(date -Iseconds)] Starting API container..."
docker start mcpworks-api 2>/dev/null || true

echo "[$(date -Iseconds)] Restore complete."
