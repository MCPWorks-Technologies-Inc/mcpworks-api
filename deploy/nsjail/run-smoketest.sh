#!/bin/bash
# run-smoketest.sh — Run sandbox smoke test via nsjail.
#
# Launches smoketest.py through nsjail using the SAME config + seccomp policy
# as production, with generous resource limits to allow all packages to init.
#
# Usage:
#   ./run-smoketest.sh                          # Human-readable output
#   JSON_OUTPUT=1 ./run-smoketest.sh            # JSON output for CI
#   SECCOMP_POLICY=new.policy ./run-smoketest.sh  # Test alternate policy
#
# Exit codes:
#   0 = all packages passed
#   1 = one or more packages failed or nsjail error

set -euo pipefail

CONFIG="${SANDBOX_CONFIG:-/etc/mcpworks/sandbox.cfg}"
SECCOMP_POLICY="${SECCOMP_POLICY:-/etc/mcpworks/seccomp.policy}"
NSJAIL="${NSJAIL:-/usr/local/bin/nsjail}"
SMOKETEST="/opt/mcpworks/bin/smoketest.py"
WORKSPACE_BASE="/tmp/mcpworks-smoketest"

# Generous limits for smoke testing (all 57 packages need to initialize)
TIMEOUT=120
MEMORY=1024
PIDS=64

# Create tmpfs-backed workspace
WORKSPACE="${WORKSPACE_BASE}/ws-$$"
mkdir -p "${WORKSPACE}"
mount -t tmpfs -o "size=50m,mode=0755" tmpfs "${WORKSPACE}"

# Cleanup
cleanup() {
    umount "${WORKSPACE}" 2>/dev/null || true
    rmdir "${WORKSPACE}" 2>/dev/null || true
    rmdir "${WORKSPACE_BASE}" 2>/dev/null || true
}
trap cleanup EXIT

# Chown workspace to UID 65534 (matches sandbox uidmap)
chown -R 65534:65534 "${WORKSPACE}"

# Build python args
PYTHON_ARGS=("-S" "${SMOKETEST}")
if [ "${JSON_OUTPUT:-0}" = "1" ]; then
    PYTHON_ARGS+=("--json")
fi

# Build nsjail arguments (mirrors spawn-sandbox.sh structure)
NSJAIL_ARGS=(
    --config "${CONFIG}"
    --seccomp_policy "${SECCOMP_POLICY}"
    --bindmount "${WORKSPACE}:/sandbox"
    --time_limit "${TIMEOUT}"
    --rlimit_as "${MEMORY}"
    --rlimit_nproc "${PIDS}"
    --rlimit_nofile 64
    --hostname "smoketest"
)

# Run under aggregate cgroup if available
CGROUP_PARENT="/sys/fs/cgroup/mcpworks"
if [ -d "${CGROUP_PARENT}" ]; then
    NSJAIL_ARGS+=(--cgroup_mem_parent "${CGROUP_PARENT}")
    NSJAIL_ARGS+=(--cgroup_pids_parent "${CGROUP_PARENT}")
    NSJAIL_ARGS+=(--cgroup_cpu_parent "${CGROUP_PARENT}")
fi

# Execute
"${NSJAIL}" \
    "${NSJAIL_ARGS[@]}" \
    -- \
    /usr/local/bin/python3 "${PYTHON_ARGS[@]}"
