#!/bin/bash
# backup-db-local.sh — Pull PostgreSQL dump from production to local machine.
#
# Runs pg_dump on the prod server via SSH, pipes compressed output locally.
# Intended for cron: 0 */4 * * * /home/user/dev/mcpworks.io/mcpworks-api/scripts/backup-db-local.sh
#
# Retention policy:
#   - Today: keep all backups (4hr granularity for tight restores)
#   - Past 7 days: keep one per day (closest to midnight)
#   - Older than 7 days: delete
#
# Usage: ./scripts/backup-db-local.sh [backup_dir]

set -euo pipefail

BACKUP_DIR="${1:-$HOME/backups/mcpworks}"
REMOTE_HOST="${MCPWORKS_PROD_HOST:?Set MCPWORKS_PROD_HOST (e.g. root@your-server-ip)}"
CONTAINER="mcpworks-postgres"
DB_USER="mcpworks"
DB_NAME="mcpworks"
RETAIN_DAYS=7
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/mcpworks_${TIMESTAMP}.sql.gz"

mkdir -p "${BACKUP_DIR}"

echo "[$(date -Iseconds)] Starting remote database backup..."

ssh "${REMOTE_HOST}" "docker exec ${CONTAINER} pg_dump -U ${DB_USER} -d ${DB_NAME} --no-owner --no-acl" \
    | gzip > "${BACKUP_FILE}"

BACKUP_SIZE=$(du -h "${BACKUP_FILE}" | cut -f1)
echo "[$(date -Iseconds)] Backup saved: ${BACKUP_FILE} (${BACKUP_SIZE})"

# ── Two-tier retention ────────────────────────────────────────────────────
TODAY=$(date +%Y%m%d)
CUTOFF=$(date -d "${RETAIN_DAYS} days ago" +%Y%m%d)

declare -A KEEP

for f in "${BACKUP_DIR}"/mcpworks_*.sql.gz; do
    [ -f "$f" ] || continue
    FNAME=$(basename "$f")
    FILE_DATE="${FNAME:9:8}"
    FILE_TIME="${FNAME:18:6}"

    if [ "${FILE_DATE}" = "${TODAY}" ]; then
        continue
    fi

    if [ "${FILE_DATE}" -lt "${CUTOFF}" ]; then
        rm "$f"
        echo "[$(date -Iseconds)] Expired: ${FNAME}"
        continue
    fi

    PREV="${KEEP[${FILE_DATE}]:-}"
    if [ -z "${PREV}" ] || [ "${FILE_TIME}" -lt "${PREV##*:}" ]; then
        KEEP[${FILE_DATE}]="${f}:${FILE_TIME}"
    fi
done

for FILE_DATE in "${!KEEP[@]}"; do
    BEST="${KEEP[${FILE_DATE}]%%:*}"
    for f in "${BACKUP_DIR}"/mcpworks_"${FILE_DATE}"_*.sql.gz; do
        [ -f "$f" ] || continue
        if [ "$f" != "${BEST}" ]; then
            echo "[$(date -Iseconds)] Consolidated: $(basename "$f") (keeping $(basename "${BEST}"))"
            rm "$f"
        fi
    done
done

echo "[$(date -Iseconds)] Backup complete."
