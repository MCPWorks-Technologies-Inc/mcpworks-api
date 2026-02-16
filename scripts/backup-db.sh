#!/bin/bash
# backup-db.sh — Daily PostgreSQL backup with 7-day retention.
#
# ORDER-014: Run via cron on production server.
# Setup: crontab -e → 0 3 * * * /opt/mcpworks/scripts/backup-db.sh
#
# Usage: ./scripts/backup-db.sh [backup_dir]

set -euo pipefail

BACKUP_DIR="${1:-/opt/mcpworks/backups}"
CONTAINER="mcpworks-postgres"
DB_USER="mcpworks"
DB_NAME="mcpworks"
RETAIN_DAYS=7
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/mcpworks_${TIMESTAMP}.sql.gz"

# Create backup directory
mkdir -p "${BACKUP_DIR}"

echo "[$(date -Iseconds)] Starting database backup..."

# Run pg_dump inside the postgres container, pipe through gzip
docker exec "${CONTAINER}" pg_dump -U "${DB_USER}" -d "${DB_NAME}" --no-owner --no-acl \
    | gzip > "${BACKUP_FILE}"

BACKUP_SIZE=$(du -h "${BACKUP_FILE}" | cut -f1)
echo "[$(date -Iseconds)] Backup created: ${BACKUP_FILE} (${BACKUP_SIZE})"

# Remove backups older than retention period
DELETED=$(find "${BACKUP_DIR}" -name "mcpworks_*.sql.gz" -mtime +${RETAIN_DAYS} -print -delete | wc -l)
if [ "${DELETED}" -gt 0 ]; then
    echo "[$(date -Iseconds)] Cleaned up ${DELETED} backup(s) older than ${RETAIN_DAYS} days"
fi

# List current backups
echo "[$(date -Iseconds)] Current backups:"
ls -lh "${BACKUP_DIR}"/mcpworks_*.sql.gz 2>/dev/null || echo "  (none)"

echo "[$(date -Iseconds)] Backup complete."
