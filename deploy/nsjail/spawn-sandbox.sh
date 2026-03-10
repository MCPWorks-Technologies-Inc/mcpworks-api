#!/bin/bash
# spawn-sandbox.sh — Launch an nsjail sandbox for code execution.
#
# Called by sandbox.py._execute_nsjail()
# Usage: spawn-sandbox.sh <exec_id> <tier> <code_path> <input_path> [namespace]
#
# The script:
#   1. Maps tier to resource limits (memory, PIDs, timeout)
#   2. Creates a tmpfs-backed workspace with tier-specific size cap
#   3. Copies input files into the workspace and chowns to UID 65534
#   4. Calls nsjail with the config and bind mounts
#   5. Copies output.json back to the original exec_dir
#   6. Unmounts + cleans up the tmpfs workspace

set -euo pipefail

EXEC_ID="${1:?exec_id required}"
TIER="${2:?tier required}"
CODE_PATH="${3:?code_path required}"
INPUT_PATH="${4:?input_path required}"
NAMESPACE="${5:-sandbox}"
# ORDER-003: Optional execution token passed via file descriptor (not env var).
# Token file is read by execute.py via stdin, then deleted.
EXEC_TOKEN_FILE="${6:-}"

CONFIG="/etc/mcpworks/sandbox.cfg"
SECCOMP_POLICY="/etc/mcpworks/seccomp.policy"
NSJAIL="/usr/local/bin/nsjail"
WORKSPACE_BASE="/tmp/mcpworks-sandbox"

# ORDER-002: Aggregate cgroup parent — all sandboxes run under this
CGROUP_PARENT="/sys/fs/cgroup/mcpworks"

# Derive exec_dir from code_path (parent directory)
EXEC_DIR="$(dirname "${CODE_PATH}")"

# Tier resource limits: timeout_sec memory_mb max_pids tmpfs_size_mb
# Names must match Python ExecutionTier enum: free, builder, pro, enterprise
case "${TIER}" in
    free)
        TIMEOUT=10
        MEMORY=128
        PIDS=16
        TMPFS_SIZE=5
        ;;
    builder)
        TIMEOUT=30
        MEMORY=256
        PIDS=32
        TMPFS_SIZE=20
        ;;
    pro)
        TIMEOUT=90
        MEMORY=512
        PIDS=64
        TMPFS_SIZE=50
        ;;
    enterprise)
        TIMEOUT=300
        MEMORY=2048
        PIDS=128
        TMPFS_SIZE=200
        ;;
    *)
        # Unknown tier — fall back to free (most restrictive)
        TIMEOUT=10
        MEMORY=128
        PIDS=16
        TMPFS_SIZE=5
        ;;
esac

# Create tmpfs-backed workspace
WORKSPACE="${WORKSPACE_BASE}/ws-${EXEC_ID}"
mkdir -p "${WORKSPACE}"
mount -t tmpfs -o "size=${TMPFS_SIZE}m,mode=0755" tmpfs "${WORKSPACE}"

# Cleanup function: unmount tmpfs and remove directory
cleanup() {
    umount "${WORKSPACE}" 2>/dev/null || true
    rmdir "${WORKSPACE}" 2>/dev/null || true
}
trap cleanup EXIT

# Copy input files into tmpfs workspace
cp "${CODE_PATH}" "${WORKSPACE}/user_code.py"
cp "${INPUT_PATH}" "${WORKSPACE}/input.json"

# F-36: Copy execute.pyc into writable workspace (deleted by execute.py
# before user code runs — prevents .pyc decompilation via marshal.loads).
cp /opt/mcpworks/bin/execute.pyc "${WORKSPACE}/.e"

# Copy functions/ package if it exists (code-mode)
if [ -d "${EXEC_DIR}/functions" ]; then
    cp -r "${EXEC_DIR}/functions" "${WORKSPACE}/functions"
fi

# ORDER-003: If execution token provided, write to workspace for stdin piping.
# Token is passed as a file path, read once by execute.py, never in env vars.
if [ -n "${EXEC_TOKEN_FILE}" ] && [ -f "${EXEC_TOKEN_FILE}" ]; then
    cp "${EXEC_TOKEN_FILE}" "${WORKSPACE}/.exec_token"
    rm -f "${EXEC_TOKEN_FILE}"
fi

# ENV PASSTHROUGH: Copy env vars file into workspace if present.
# Read once by execute.py, then deleted. Never in nsjail --env (avoids /proc leak).
if [ -f "${EXEC_DIR}/.sandbox_env.json" ]; then
    cp "${EXEC_DIR}/.sandbox_env.json" "${WORKSPACE}/.sandbox_env.json"
    rm -f "${EXEC_DIR}/.sandbox_env.json"
fi

# Generate fake /proc files to hide host details (SECURITY_AUDIT.md FINDING-02)
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

# clone_newnet: each sandbox gets its own network namespace.
# /proc/net is automatically empty (no host network info visible).
# Free tier: empty network namespace = zero connectivity (no MACVLAN).
# Paid tiers: MACVLAN on eth0 gives outbound internet access.

# All tiers use UID 65534 (nobody). Network isolation is per-namespace
# via clone_newnet, not per-UID via iptables.
SANDBOX_UID=65534

chown -R "${SANDBOX_UID}:${SANDBOX_UID}" "${WORKSPACE}"

# Derive unique MACVLAN IP from exec_id for paid tiers.
# Must be on the same subnet as the container (172.18.0.0/16) so the
# gateway (172.18.0.1) is directly reachable from the MACVLAN interface.
# Use 172.18.128-254.1-254 range to avoid conflicts with Docker-assigned IPs
# (Docker assigns from the low end of the subnet).
_exec_hash=$(echo -n "${EXEC_ID}" | md5sum | cut -c1-4)
_hex3=$(echo "${_exec_hash}" | cut -c1-2)
_hex4=$(echo "${_exec_hash}" | cut -c3-4)
_octet3=$(( 16#${_hex3} ))
_octet4=$(( 16#${_hex4} ))
# Clamp octet3 to 128-254 (high range, away from Docker's low-range allocations)
_octet3=$(( (_octet3 % 127) + 128 ))
# Clamp octet4 to 1-254
[ "${_octet4}" -eq 0 ] && _octet4=1
[ "${_octet4}" -eq 255 ] && _octet4=254
MACVLAN_IP="172.18.${_octet3}.${_octet4}"

# Build nsjail arguments
NSJAIL_ARGS=(
    --config "${CONFIG}"
    --seccomp_policy "${SECCOMP_POLICY}"
    --bindmount "${WORKSPACE}:/sandbox"
    --time_limit "${TIMEOUT}"
    --rlimit_as "$((MEMORY * 4))"
    --rlimit_nproc "${PIDS}"
    --hostname "${NAMESPACE}"
)

# UID/GID mapping: all tiers use 65534 (nobody) inside and outside.
NSJAIL_ARGS+=(--uid_mapping "65534:65534:1")
NSJAIL_ARGS+=(--gid_mapping "65534:65534:1")

# Overlay fake /proc files to hide host details
NSJAIL_ARGS+=(--bindmount_ro "${WORKSPACE}/.fake_cpuinfo:/proc/cpuinfo")
NSJAIL_ARGS+=(--bindmount_ro "${WORKSPACE}/.fake_meminfo:/proc/meminfo")
NSJAIL_ARGS+=(--bindmount_ro "${WORKSPACE}/.fake_version:/proc/version")

# clone_newnet isolates /proc/net natively (each sandbox sees only its own
# network namespace). /proc/self (mountinfo, maps, status) is low-risk.

# FINDING-25: Hide _ctypes C extension .so files from sandbox.
# sys.modules poisoning is bypassed via importlib.util.spec_from_file_location.
# Bind-mounting empty files over the .so makes the C extension un-importable.
touch "${WORKSPACE}/.empty"
NSJAIL_ARGS+=(--bindmount_ro "${WORKSPACE}/.empty:/usr/local/lib/python3.11/lib-dynload/_ctypes.cpython-311-x86_64-linux-gnu.so")
NSJAIL_ARGS+=(--bindmount_ro "${WORKSPACE}/.empty:/usr/local/lib/python3.11/lib-dynload/_ctypes_test.cpython-311-x86_64-linux-gnu.so")
# F-32: Hollow _posixsubprocess .so — defense-in-depth (execve blocked by seccomp,
# but prevents C-level fork_exec even if sys.modules poison is bypassed).
NSJAIL_ARGS+=(--bindmount_ro "${WORKSPACE}/.empty:/usr/local/lib/python3.11/lib-dynload/_posixsubprocess.cpython-311-x86_64-linux-gnu.so")

# ORDER-002: Run under aggregate cgroup if available
if [ -d "${CGROUP_PARENT}" ]; then
    NSJAIL_ARGS+=(--cgroup_mem_parent "${CGROUP_PARENT}")
    NSJAIL_ARGS+=(--cgroup_pids_parent "${CGROUP_PARENT}")
    NSJAIL_ARGS+=(--cgroup_cpu_parent "${CGROUP_PARENT}")
fi

# Network isolation via clone_newnet:
# Free tier: empty network namespace (no MACVLAN) = zero connectivity.
# Paid tiers: MACVLAN on eth0 gives internet access via container gateway.
if [ "${TIER}" != "free" ]; then
    NSJAIL_ARGS+=(--macvlan_iface eth0)
    NSJAIL_ARGS+=(--macvlan_vs_ip "${MACVLAN_IP}")
    NSJAIL_ARGS+=(--macvlan_vs_nm "255.255.0.0")
    NSJAIL_ARGS+=(--macvlan_vs_gw "172.18.0.1")
fi

# Execute nsjail with tier-specific overrides.
# --execute_fd: use execveat(fd) instead of execve(path), required because
# seccomp blocks execve. This prevents any shell execution (posix.system,
# subprocess, /bin/sh) at the kernel level after Python starts.
"${NSJAIL}" \
    "${NSJAIL_ARGS[@]}" \
    --execute_fd \
    -- \
    /usr/local/bin/python3 -S /sandbox/.e

NSJAIL_EXIT=$?

# Copy output.json back to exec_dir (so sandbox.py can read it)
if [ -f "${WORKSPACE}/output.json" ]; then
    cp "${WORKSPACE}/output.json" "${EXEC_DIR}/output.json"
fi

exit ${NSJAIL_EXIT}
