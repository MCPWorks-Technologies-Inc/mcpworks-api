#!/bin/bash
# spawn-sandbox.sh — Launch an nsjail sandbox for code execution.
#
# Called by sandbox.py._execute_nsjail()
# Usage: spawn-sandbox.sh <exec_id> <tier> <code_path> <input_path>
#
# The script:
#   1. Maps tier to resource limits (memory, PIDs, timeout)
#   2. Prepares the execution directory
#   3. Calls nsjail with the config and bind mounts

set -euo pipefail

EXEC_ID="${1:?exec_id required}"
TIER="${2:?tier required}"
CODE_PATH="${3:?code_path required}"
INPUT_PATH="${4:?input_path required}"

CONFIG="/etc/mcpworks/sandbox.cfg"
NSJAIL="/usr/local/bin/nsjail"

# Derive exec_dir from code_path (parent directory)
EXEC_DIR="$(dirname "${CODE_PATH}")"

# Tier resource limits: timeout_sec memory_mb max_pids
case "${TIER}" in
    free)
        TIMEOUT=10
        MEMORY=128
        PIDS=16
        ;;
    founder)
        TIMEOUT=30
        MEMORY=256
        PIDS=32
        ;;
    founder_pro)
        TIMEOUT=60
        MEMORY=512
        PIDS=64
        ;;
    enterprise)
        TIMEOUT=300
        MEMORY=2048
        PIDS=128
        ;;
    *)
        # Default to founder tier
        TIMEOUT=30
        MEMORY=256
        PIDS=32
        ;;
esac

# Execute nsjail with tier-specific overrides
exec "${NSJAIL}" \
    --config "${CONFIG}" \
    --bindmount "${EXEC_DIR}:/sandbox" \
    --time_limit "${TIMEOUT}" \
    --rlimit_as "${MEMORY}" \
    --rlimit_nproc "${PIDS}" \
    -- \
    /usr/bin/python3 -S /opt/mcpworks/bin/execute.py
