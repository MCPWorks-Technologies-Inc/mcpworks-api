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

# Generate fake /proc files (same as spawn-sandbox.sh)
cat > "${WORKSPACE}/.fake_cpuinfo" <<'CPUINFO'
processor	: 0
vendor_id	: MCPWorks
model name	: Virtual CPU
cpu MHz		: 2000.000
cache size	: 4096 KB
cpu cores	: 1
flags		: fpu sse sse2 ssse3 sse4_1 sse4_2 avx
CPUINFO

MEMORY_KB=$(( MEMORY * 1024 ))
cat > "${WORKSPACE}/.fake_meminfo" <<MEMINFO
MemTotal:       ${MEMORY_KB} kB
MemFree:        ${MEMORY_KB} kB
MemAvailable:   ${MEMORY_KB} kB
MEMINFO

cat > "${WORKSPACE}/.fake_version" <<'VERSION'
Linux version 0.0.0 (sandbox)
VERSION


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
    --rlimit_as "$((MEMORY * 4))"
    --rlimit_nproc "${PIDS}"
    --rlimit_nofile 64
    --cgroup_mem_max "$((MEMORY * 1024 * 1024))"
    --hostname "smoketest"
)

# Overlay fake /proc files (matches spawn-sandbox.sh)
NSJAIL_ARGS+=(--bindmount_ro "${WORKSPACE}/.fake_cpuinfo:/proc/cpuinfo")
NSJAIL_ARGS+=(--bindmount_ro "${WORKSPACE}/.fake_meminfo:/proc/meminfo")
NSJAIL_ARGS+=(--bindmount_ro "${WORKSPACE}/.fake_version:/proc/version")

# Run under aggregate cgroup if available
CGROUP_PARENT="/sys/fs/cgroup/mcpworks"
if [ -d "${CGROUP_PARENT}" ]; then
    NSJAIL_ARGS+=(--cgroup_mem_parent "${CGROUP_PARENT}")
    NSJAIL_ARGS+=(--cgroup_pids_parent "${CGROUP_PARENT}")
    NSJAIL_ARGS+=(--cgroup_cpu_parent "${CGROUP_PARENT}")
fi

# Execute (--execute_fd needed because seccomp blocks execve;
# nsjail uses execveat(fd) instead, matching exec_fd:true in config)
"${NSJAIL}" \
    "${NSJAIL_ARGS[@]}" \
    --execute_fd \
    -- \
    /usr/local/bin/python3 "${PYTHON_ARGS[@]}"
