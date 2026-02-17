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
case "${TIER}" in
    free)
        TIMEOUT=10
        MEMORY=128
        PIDS=16
        TMPFS_SIZE=5
        ;;
    founder)
        TIMEOUT=30
        MEMORY=256
        PIDS=32
        TMPFS_SIZE=20
        ;;
    founder_pro)
        TIMEOUT=60
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
        # Default to founder tier
        TIMEOUT=30
        MEMORY=256
        PIDS=32
        TMPFS_SIZE=20
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

# Chown workspace to UID 65534 (required for outside_id: 65534 mapping)
chown -R 65534:65534 "${WORKSPACE}"

# Build nsjail arguments
NSJAIL_ARGS=(
    --config "${CONFIG}"
    --seccomp_policy "${SECCOMP_POLICY}"
    --bindmount "${WORKSPACE}:/sandbox"
    --time_limit "${TIMEOUT}"
    --rlimit_as "${MEMORY}"
    --rlimit_nproc "${PIDS}"
    --hostname "${NAMESPACE}"
)

# ORDER-002: Run under aggregate cgroup if available
if [ -d "${CGROUP_PARENT}" ]; then
    NSJAIL_ARGS+=(--cgroup_mem_parent "${CGROUP_PARENT}")
    NSJAIL_ARGS+=(--cgroup_pids_parent "${CGROUP_PARENT}")
    NSJAIL_ARGS+=(--cgroup_cpu_parent "${CGROUP_PARENT}")
fi

# Execute nsjail with tier-specific overrides
"${NSJAIL}" \
    "${NSJAIL_ARGS[@]}" \
    -- \
    /usr/local/bin/python3 -S /opt/mcpworks/bin/execute.py

NSJAIL_EXIT=$?

# Copy output.json back to exec_dir (so sandbox.py can read it)
if [ -f "${WORKSPACE}/output.json" ]; then
    cp "${WORKSPACE}/output.json" "${EXEC_DIR}/output.json"
fi

exit ${NSJAIL_EXIT}
