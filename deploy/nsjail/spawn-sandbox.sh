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
# Language: python (default) or typescript
LANGUAGE="${7:-python}"

CONFIG="/etc/mcpworks/sandbox.cfg"
SECCOMP_POLICY="/etc/mcpworks/seccomp.policy"
NSJAIL="/usr/local/bin/nsjail"
WORKSPACE_BASE="/tmp/mcpworks-sandbox"

# ORDER-002: Aggregate cgroup parent — all sandboxes run under this
CGROUP_PARENT="/sys/fs/cgroup/mcpworks"

# Derive exec_dir from code_path (parent directory)
EXEC_DIR="$(dirname "${CODE_PATH}")"

# Tier resource limits: timeout_sec memory_mb max_pids tmpfs_size_mb
# Names must match Python ExecutionTier enum or agent tier variants.
# Agent tiers (builder-agent, pro-agent, enterprise-agent) map to their
# base tier resource limits.
case "${TIER}" in
    free)
        TIMEOUT=10
        MEMORY=128
        PIDS=16
        TMPFS_SIZE=5
        ;;
    builder|builder-agent)
        TIMEOUT=30
        MEMORY=256
        PIDS=32
        TMPFS_SIZE=20
        ;;
    pro|pro-agent)
        TIMEOUT=90
        MEMORY=512
        PIDS=64
        TMPFS_SIZE=50
        ;;
    enterprise|enterprise-agent)
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

# Cleanup function: unmount tmpfs, remove network namespace, clean iptables
cleanup() {
    if [ -n "${NETNS:-}" ]; then
        local _iface="${DEFAULT_IFACE:-eth0}"
        iptables -D INPUT -i "${VETH_HOST}" -j DROP 2>/dev/null || true
        iptables -t nat -D POSTROUTING -s "${SANDBOX_IP}/32" -o "${_iface}" -j MASQUERADE 2>/dev/null || true
        iptables -D FORWARD -i "${VETH_HOST}" -o "${_iface}" -j ACCEPT 2>/dev/null || true
        iptables -D FORWARD -i "${_iface}" -o "${VETH_HOST}" -m state --state RELATED,ESTABLISHED -j ACCEPT 2>/dev/null || true
        iptables -D FORWARD -i "${VETH_HOST}" -p udp --dport 53 -j ACCEPT 2>/dev/null || true
        iptables -D FORWARD -i "${VETH_HOST}" -p udp -j DROP 2>/dev/null || true
        iptables -D FORWARD -i "${VETH_HOST}" -d 169.254.169.254/32 -j DROP 2>/dev/null || true
        iptables -D FORWARD -i "${VETH_HOST}" -d 172.16.0.0/12 -j DROP 2>/dev/null || true
        iptables -D FORWARD -i "${VETH_HOST}" -d 10.0.0.0/8 -j DROP 2>/dev/null || true
        iptables -D FORWARD -i "${VETH_HOST}" -d 192.168.0.0/16 -j DROP 2>/dev/null || true
        ip netns del "${NETNS}" 2>/dev/null || true
    fi
    umount "${WORKSPACE}" 2>/dev/null || true
    rmdir "${WORKSPACE}" 2>/dev/null || true
}
trap cleanup EXIT

# Copy input files into tmpfs workspace
cp "${INPUT_PATH}" "${WORKSPACE}/input.json"

if [ "${LANGUAGE}" = "typescript" ]; then
    # TypeScript: code is already transpiled to JS by the API host
    cp "${CODE_PATH}" "${WORKSPACE}/user_code.js"
    cp /opt/mcpworks/bin/execute.js "${WORKSPACE}/.e.js"
else
    # Python
    cp "${CODE_PATH}" "${WORKSPACE}/user_code.py"
    # F-36: Copy execute.pyc into writable workspace (deleted by execute.py
    # before user code runs — prevents .pyc decompilation via marshal.loads).
    cp /opt/mcpworks/bin/execute.pyc "${WORKSPACE}/.e"
fi

# Copy functions/ package if it exists (code-mode, Python only)
if [ -d "${EXEC_DIR}/functions" ] && [ "${LANGUAGE}" != "typescript" ]; then
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

# CONTEXT: Copy agent state/context if present (read by execute.py, passed to handler).
if [ -f "${EXEC_DIR}/context.json" ]; then
    cp "${EXEC_DIR}/context.json" "${WORKSPACE}/context.json"
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

# Network isolation:
# Free tier: nsjail creates empty network namespace (clone_newnet) = zero connectivity.
# Paid tiers: Pre-configured network namespace with veth pair for internet access.
#   nsjail runs inside this namespace with clone_newnet DISABLED.
#
# Architecture (paid tiers):
#   sandbox (10.X.Y.2) --[veth]--> container (10.X.Y.1) --[NAT/eth0]--> internet
#
# Why veth instead of MACVLAN: MACVLAN on Docker veth pairs is unreliable.
# Docker bridges filter unknown MAC addresses created by MACVLAN child
# interfaces, causing zero connectivity (PROBLEM-016). Veth pairs with NAT
# is how Docker itself does networking — proven on all kernel versions.

SANDBOX_UID=65534

chown -R "${SANDBOX_UID}:${SANDBOX_UID}" "${WORKSPACE}"

# Derive unique subnet octets from exec_id hash for veth pair addressing.
# Each sandbox gets its own /24 subnet: 10.{octet3}.{octet4}.0/24
_exec_hash=$(echo -n "${EXEC_ID}" | md5sum | cut -c1-4)
_hex3=$(echo "${_exec_hash}" | cut -c1-2)
_hex4=$(echo "${_exec_hash}" | cut -c3-4)
_octet3=$(( 16#${_hex3} ))
_octet4=$(( 16#${_hex4} ))
# Clamp to 1-254 to avoid network/broadcast addresses
_octet3=$(( (_octet3 % 254) + 1 ))
[ "${_octet4}" -eq 0 ] && _octet4=1
[ "${_octet4}" -eq 255 ] && _octet4=254

NETNS=""
VETH_HOST=""
SANDBOX_IP=""
if [ "${TIER}" != "free" ]; then
    SHORT_ID="${EXEC_ID:0:8}"
    NETNS="mcpw-${SHORT_ID}"
    VETH_HOST="vh${SHORT_ID}"
    VETH_SANDBOX="vs${SHORT_ID}"
    VETH_GW="10.${_octet3}.${_octet4}.1"
    SANDBOX_IP="10.${_octet3}.${_octet4}.2"

    # Detect the container's default outbound interface (may not be eth0 when
    # the container is on multiple Docker networks).
    DEFAULT_IFACE=$(ip route show default | awk '{print $5}' | head -1)
    DEFAULT_IFACE="${DEFAULT_IFACE:-eth0}"

    echo 1 > /proc/sys/net/ipv4/ip_forward 2>/dev/null || true

    ip netns add "${NETNS}"

    ip link add "${VETH_HOST}" type veth peer name "${VETH_SANDBOX}"
    ip link set "${VETH_SANDBOX}" netns "${NETNS}"

    ip netns exec "${NETNS}" ip link set lo up
    ip netns exec "${NETNS}" ip addr add "${SANDBOX_IP}/24" dev "${VETH_SANDBOX}"
    ip netns exec "${NETNS}" ip link set "${VETH_SANDBOX}" up
    ip netns exec "${NETNS}" ip route add default via "${VETH_GW}"

    ip addr add "${VETH_GW}/24" dev "${VETH_HOST}"
    ip link set "${VETH_HOST}" up

    # Block sandbox from reaching container services (API on :8000, etc).
    # Without this, traffic to the gateway IP (10.X.Y.1) is locally delivered
    # and bypasses the FORWARD chain entirely. MACVLAN had inherent parent-child
    # isolation; veth does not — INPUT DROP is the equivalent.
    iptables -I INPUT -i "${VETH_HOST}" -j DROP

    iptables -I FORWARD -i "${VETH_HOST}" -d 169.254.169.254/32 -j DROP
    iptables -I FORWARD -i "${VETH_HOST}" -d 172.16.0.0/12 -j DROP
    iptables -I FORWARD -i "${VETH_HOST}" -d 10.0.0.0/8 -j DROP
    iptables -I FORWARD -i "${VETH_HOST}" -d 192.168.0.0/16 -j DROP
    iptables -A FORWARD -i "${VETH_HOST}" -p udp --dport 53 -j ACCEPT
    iptables -A FORWARD -i "${VETH_HOST}" -p udp -j DROP
    iptables -A FORWARD -i "${VETH_HOST}" -o "${DEFAULT_IFACE}" -j ACCEPT
    iptables -A FORWARD -i "${DEFAULT_IFACE}" -o "${VETH_HOST}" -m state --state RELATED,ESTABLISHED -j ACCEPT
    iptables -t nat -A POSTROUTING -s "${SANDBOX_IP}/32" -o "${DEFAULT_IFACE}" -j MASQUERADE
fi

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

# Python-specific: Hide _ctypes C extension .so files from sandbox.
# Not needed for TypeScript — Node.js doesn't have Python's ctypes surface.
touch "${WORKSPACE}/.empty"
if [ "${LANGUAGE}" != "typescript" ]; then
    # FINDING-25: sys.modules poisoning is bypassed via importlib.util.spec_from_file_location.
    # Bind-mounting empty files over the .so makes the C extension un-importable.
    NSJAIL_ARGS+=(--bindmount_ro "${WORKSPACE}/.empty:/usr/local/lib/python3.11/lib-dynload/_ctypes.cpython-311-x86_64-linux-gnu.so")
    NSJAIL_ARGS+=(--bindmount_ro "${WORKSPACE}/.empty:/usr/local/lib/python3.11/lib-dynload/_ctypes_test.cpython-311-x86_64-linux-gnu.so")
    # F-32: Hollow _posixsubprocess .so — defense-in-depth (execve blocked by seccomp,
    # but prevents C-level fork_exec even if sys.modules poison is bypassed).
    NSJAIL_ARGS+=(--bindmount_ro "${WORKSPACE}/.empty:/usr/local/lib/python3.11/lib-dynload/_posixsubprocess.cpython-311-x86_64-linux-gnu.so")
fi

# ORDER-002: Run under aggregate cgroup if available
if [ -d "${CGROUP_PARENT}" ]; then
    NSJAIL_ARGS+=(--cgroup_mem_parent "${CGROUP_PARENT}")
    NSJAIL_ARGS+=(--cgroup_pids_parent "${CGROUP_PARENT}")
    NSJAIL_ARGS+=(--cgroup_cpu_parent "${CGROUP_PARENT}")
fi

# Network: paid tiers use pre-configured namespace (veth pair).
# nsjail must NOT create a new network namespace for paid tiers.
NSJAIL_PREFIX=""
if [ -n "${NETNS}" ]; then
    NSJAIL_ARGS+=(--disable_clone_newnet)
    NSJAIL_PREFIX="ip netns exec ${NETNS}"
fi

# Execute nsjail with tier-specific overrides.
# --execute_fd: use execveat(fd) instead of execve(path), required because
# seccomp blocks execve. This prevents any shell execution (posix.system,
# subprocess, /bin/sh) at the kernel level after the runtime starts.
# Paid tiers: run inside pre-configured network namespace via ip netns exec.
if [ "${LANGUAGE}" = "typescript" ]; then
    # Node.js: bind mount node binary and packages into sandbox.
    # Use --bindmount_ro to mount into paths within /sandbox (which is writable
    # tmpfs), avoiding the mount target creation permission issue with nsjail chroot.
    NSJAIL_ARGS+=(--env "NODE_PATH=/sandbox/.node_modules")
    NSJAIL_ARGS+=(--bindmount_ro "/opt/mcpworks/sandbox-root/usr/local/bin/node:/sandbox/.node_bin")
    NSJAIL_ARGS+=(--bindmount_ro "/opt/mcpworks/sandbox-root/node_modules:/sandbox/.node_modules")
    ${NSJAIL_PREFIX} "${NSJAIL}" \
        "${NSJAIL_ARGS[@]}" \
        --exec_file /opt/mcpworks/sandbox-root/usr/local/bin/node \
        --execute_fd \
        -- \
        /sandbox/.node_bin --max-old-space-size="${MEMORY}" /sandbox/.e.js
else
    # Python
    ${NSJAIL_PREFIX} "${NSJAIL}" \
        "${NSJAIL_ARGS[@]}" \
        --execute_fd \
        -- \
        /usr/local/bin/python3 -S /sandbox/.e
fi

NSJAIL_EXIT=$?

# Copy output.json back to exec_dir (so sandbox.py can read it)
if [ -f "${WORKSPACE}/output.json" ]; then
    cp "${WORKSPACE}/output.json" "${EXEC_DIR}/output.json"
fi

exit ${NSJAIL_EXIT}
