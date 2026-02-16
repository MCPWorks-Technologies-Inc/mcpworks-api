#!/bin/bash
# setup-cgroups.sh — Create aggregate cgroup limits for sandbox executions.
#
# ORDER-002: Prevents 10 concurrent sandboxes from OOMing the 4GB host.
# Run once at container startup (before any sandbox execution).
#
# Creates /sys/fs/cgroup/mcpworks/ parent cgroup with:
#   memory.max = 3GB  (leaves 1GB for OS + API + DB + Redis)
#   pids.max   = 200  (total process limit across all sandboxes)
#   cpu.max    = 200000 100000  (200% of one CPU = 2 cores)

set -euo pipefail

CGROUP_BASE="/sys/fs/cgroup"
CGROUP_NAME="mcpworks"
CGROUP_PATH="${CGROUP_BASE}/${CGROUP_NAME}"

# Check for cgroup v2
if [ ! -f "${CGROUP_BASE}/cgroup.controllers" ]; then
    echo "WARNING: cgroup v2 not available, skipping aggregate limits"
    exit 0
fi

# Create parent cgroup if it doesn't exist
if [ ! -d "${CGROUP_PATH}" ]; then
    mkdir -p "${CGROUP_PATH}"
    echo "Created cgroup: ${CGROUP_PATH}"
fi

# Enable controllers in parent
AVAILABLE=$(cat "${CGROUP_BASE}/cgroup.subtree_control" 2>/dev/null || echo "")
for CTRL in memory pids cpu; do
    if ! echo "${AVAILABLE}" | grep -q "${CTRL}"; then
        echo "+${CTRL}" > "${CGROUP_BASE}/cgroup.subtree_control" 2>/dev/null || true
    fi
done

# Set aggregate limits
# Memory: 3GB (leaves ~1GB for OS + API + DB + Redis on 4GB host)
echo "3221225472" > "${CGROUP_PATH}/memory.max" 2>/dev/null || \
    echo "WARNING: Could not set memory.max"

# PIDs: 200 total across all sandboxes
echo "200" > "${CGROUP_PATH}/pids.max" 2>/dev/null || \
    echo "WARNING: Could not set pids.max"

# CPU: 200% of one CPU (2 cores max)
# Format: $MAX $PERIOD (microseconds)
echo "200000 100000" > "${CGROUP_PATH}/cpu.max" 2>/dev/null || \
    echo "WARNING: Could not set cpu.max"

echo "Aggregate cgroup limits configured:"
echo "  Path:       ${CGROUP_PATH}"
echo "  memory.max: $(cat ${CGROUP_PATH}/memory.max 2>/dev/null || echo 'N/A')"
echo "  pids.max:   $(cat ${CGROUP_PATH}/pids.max 2>/dev/null || echo 'N/A')"
echo "  cpu.max:    $(cat ${CGROUP_PATH}/cpu.max 2>/dev/null || echo 'N/A')"
