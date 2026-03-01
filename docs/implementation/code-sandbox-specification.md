# Code Execution Sandbox Specification

**Version:** 1.0.0
**Date:** 2026-02-09
**Status:** Draft
**Author:** sandbox-engineer, cto-architect
**Related Documents:**
- [mcpworks-internals: code-execution-sandbox-specification.md](../../../../mcpworks-internals/docs/implementation/code-execution-sandbox-specification.md)
- [mcpworks-internals: STRATEGY.md](../../../../mcpworks-internals/STRATEGY.md)
- [mcpworks-internals: PRICING.md](../../../../mcpworks-internals/PRICING.md)

---

## Executive Summary

This specification defines the complete implementation of the Code Execution Sandbox for MCPWorks A0. The sandbox executes LLM-authored Python code in a secure, isolated environment using nsjail with Linux kernel primitives (namespaces, cgroups v2, seccomp-bpf).

**Core Philosophy:** Simplify ruthlessly, secure completely. Use kernel primitives directly--no container orchestration, no external dependencies.

**Key Outcomes:**
- 70-98% token savings through architectural efficiency
- Defense-in-depth isolation against malicious code
- Per-tier resource limits enforced at kernel level
- Egress proxy for network allowlist enforcement

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [nsjail Configuration](#2-nsjail-configuration)
3. [Seccomp Policy (Allowlist)](#3-seccomp-policy-allowlist)
4. [Egress Proxy Architecture](#4-egress-proxy-architecture)
5. [Execution Wrapper](#5-execution-wrapper)
6. [Sandbox Root Filesystem](#6-sandbox-root-filesystem)
7. [Gateway Integration](#7-gateway-integration)
8. [Resource Limits by Tier](#8-resource-limits-by-tier)
9. [Security Threat Model](#9-security-threat-model)
10. [Monitoring and Observability](#10-monitoring-and-observability)
11. [Implementation Checklist](#11-implementation-checklist)

---

## 1. Architecture Overview

### Execution Flow

```
1. Request arrives at Gateway
   POST /v1/sandbox/execute
   { "code": "...", "input": {...}, "tier": "founder" }

2. Gateway validates request
   - Authentication (API key validation)
   - Rate limiting check
   - Tier-based resource allocation

3. Gateway creates execution directory
   /tmp/exec-{uuid}/
   ├── input.json         (input data, written by gateway)
   ├── user_code.py       (user's code, written by gateway)
   └── output.json        (result, written by wrapper)

4. Gateway spawns nsjail process
   nsjail --config /etc/mcpworks/sandbox.cfg \
          --env MCPWORKS_EXEC_ID={uuid} \
          --bindmount /tmp/exec-{uuid}:/sandbox:rw \
          -- /opt/mcpworks/bin/execute.py

5. nsjail creates isolated environment
   ├── New PID namespace (process sees itself as PID 1)
   ├── New network namespace (egress proxy only)
   ├── New mount namespace (read-only root, tmpfs scratch)
   ├── New user namespace (runs as nobody:nogroup)
   ├── cgroup limits applied (CPU, memory, PIDs)
   └── seccomp filter loaded (allowlist policy)

6. Execution wrapper runs
   - Reads input.json from /sandbox/input.json
   - Executes user_code.py with injected mcpworks SDK
   - Captures stdout/stderr
   - Writes structured result to /sandbox/output.json

7. nsjail terminates (timeout or completion)
   - Exit code captured
   - All processes killed
   - Namespace destroyed

8. Gateway reads result
   - Parses /tmp/exec-{uuid}/output.json
   - Returns response to client
   - Cleans up execution directory
```

### Isolation Layers

| Layer | Technology | Purpose | Configuration |
|-------|------------|---------|---------------|
| **PID namespace** | `CLONE_NEWPID` | Process isolation | Sandbox sees itself as PID 1 |
| **Network namespace** | `CLONE_NEWNET` | Network isolation | veth pair to egress proxy only |
| **Mount namespace** | `CLONE_NEWNS` | Filesystem isolation | Read-only root, minimal mounts |
| **User namespace** | `CLONE_NEWUSER` | Privilege isolation | Run as nobody (UID 65534) |
| **UTS namespace** | `CLONE_NEWUTS` | Hostname isolation | Fixed hostname "sandbox" |
| **IPC namespace** | `CLONE_NEWIPC` | IPC isolation | No shared memory with host |
| **cgroups v2** | `memory.max`, `cpu.max`, `pids.max` | Resource limits | Per-tier limits |
| **seccomp-bpf** | Syscall filter | Attack surface reduction | Allowlist policy |

---

## 2. nsjail Configuration

### Production Configuration File

```protobuf
# /etc/mcpworks/sandbox.cfg
# MCPWorks Code Execution Sandbox - Production Configuration
# Version: 1.0.0
#
# SECURITY NOTES:
# - This is a PRODUCTION configuration with defense-in-depth
# - All syscalls blocked by default (seccomp allowlist)
# - No network access except via egress proxy
# - Read-only filesystem except /sandbox and /tmp
# - Resource limits enforced by cgroups v2

name: "mcpworks-sandbox"
description: "Secure Python code execution sandbox for MCPWorks"

# Execution mode: ONCE = single execution, then exit
mode: ONCE

# Hostname inside sandbox (isolated by UTS namespace)
hostname: "sandbox"

# Working directory for user code
cwd: "/sandbox"

# =============================================================================
# NAMESPACE ISOLATION
# =============================================================================

# PID namespace: Process can only see itself
clone_newpid: true

# Network namespace: Isolated network stack
# Network setup handled by pre-execution script (veth pair to egress proxy)
clone_newnet: true

# Mount namespace: Isolated filesystem mounts
clone_newns: true

# User namespace: Run as unprivileged user
clone_newuser: true

# UTS namespace: Isolated hostname
clone_newuts: true

# IPC namespace: Isolated System V IPC
clone_newipc: true

# cgroup namespace: Isolated cgroup view
clone_newcgroup: true

# =============================================================================
# USER/GROUP MAPPING
# =============================================================================

# Map sandbox user to nobody (UID/GID 65534)
# This is the lowest-privilege user on Linux systems

uidmap {
    inside_id: "65534"    # nobody inside sandbox
    outside_id: "65534"   # nobody on host
    count: 1
}

gidmap {
    inside_id: "65534"    # nogroup inside sandbox
    outside_id: "65534"   # nogroup on host
    count: 1
}

# =============================================================================
# RESOURCE LIMITS (DEFAULT - OVERRIDDEN PER TIER)
# =============================================================================
# These are baseline limits; actual limits set via cgroup before nsjail spawn

# Wall-clock time limit (seconds) - CRITICAL for DoS prevention
# Overridden per-tier: Free=10s, Founder=30s, Pro=60s, Enterprise=300s
time_limit: 30

# Virtual memory limit (MB)
# Overridden per-tier: Free=128MB, Founder=256MB, Pro=512MB, Enterprise=2GB
rlimit_as_type: HARD
rlimit_as: 256

# CPU time limit (seconds) - total CPU time across all cores
# Overridden per-tier: Free=5s, Founder=15s, Pro=30s, Enterprise=120s
rlimit_cpu_type: HARD
rlimit_cpu: 15

# Max file size (MB) - prevent disk filling attacks
rlimit_fsize_type: HARD
rlimit_fsize: 10

# Max open file descriptors
rlimit_nofile_type: HARD
rlimit_nofile: 64

# Max processes/threads (within sandbox)
rlimit_nproc_type: HARD
rlimit_nproc: 32

# Core dump disabled
rlimit_core_type: HARD
rlimit_core: 0

# =============================================================================
# FILESYSTEM MOUNTS
# =============================================================================

# Mount /proc with hidepid for process isolation
# hidepid=invisible: process can only see its own /proc entries
mount {
    dst: "/proc"
    fstype: "proc"
    rw: false
    options: "hidepid=invisible"
}

# Mount /dev with minimal device nodes (pre-created static directory)
# Contains: null, zero, random, urandom, fd -> /proc/self/fd
mount {
    src: "/opt/mcpworks/rootfs/dev-static"
    dst: "/dev"
    is_bind: true
    rw: false
}

# Python interpreter and standard library (read-only)
mount {
    src: "/usr"
    dst: "/usr"
    is_bind: true
    rw: false
}

# System libraries (read-only)
mount {
    src: "/lib"
    dst: "/lib"
    is_bind: true
    rw: false
}

# 64-bit system libraries (read-only)
mount {
    src: "/lib64"
    dst: "/lib64"
    is_bind: true
    rw: false
    is_optional: true
}

# MCPWorks SDK and pre-installed packages (read-only)
mount {
    src: "/opt/mcpworks/sandbox-root/site-packages"
    dst: "/opt/mcpworks/site-packages"
    is_bind: true
    rw: false
}

# Execution wrapper script (read-only)
mount {
    src: "/opt/mcpworks/bin"
    dst: "/opt/mcpworks/bin"
    is_bind: true
    rw: false
}

# User's execution directory (read-write, bind-mounted per execution)
# Actual path set via --bindmount flag: /tmp/exec-{uuid}:/sandbox:rw
mount {
    dst: "/sandbox"
    fstype: "tmpfs"
    rw: true
    options: "size=50M,mode=0700"
}

# Temporary directory for Python (read-write)
mount {
    dst: "/tmp"
    fstype: "tmpfs"
    rw: true
    options: "size=50M,mode=1777"
}

# /etc/resolv.conf for DNS resolution (only if egress enabled)
mount {
    src: "/opt/mcpworks/rootfs/resolv.conf"
    dst: "/etc/resolv.conf"
    is_bind: true
    rw: false
}

# /etc/hosts for localhost resolution
mount {
    src: "/opt/mcpworks/rootfs/hosts"
    dst: "/etc/hosts"
    is_bind: true
    rw: false
}

# /etc/passwd and /etc/group for user lookup
mount {
    src: "/opt/mcpworks/rootfs/passwd"
    dst: "/etc/passwd"
    is_bind: true
    rw: false
}

mount {
    src: "/opt/mcpworks/rootfs/group"
    dst: "/etc/group"
    is_bind: true
    rw: false
}

# SSL certificates for HTTPS (egress proxy)
mount {
    src: "/etc/ssl/certs"
    dst: "/etc/ssl/certs"
    is_bind: true
    rw: false
}

mount {
    src: "/usr/share/ca-certificates"
    dst: "/usr/share/ca-certificates"
    is_bind: true
    rw: false
    is_optional: true
}

# =============================================================================
# SECURITY POLICIES
# =============================================================================

# Seccomp policy file (ALLOWLIST - critical for security)
seccomp_policy_file: "/etc/mcpworks/seccomp-allowlist.policy"

# Disable privileged operations
keep_caps: false
disable_no_new_privs: false

# Drop all capabilities
cap {
    # No capabilities granted
}

# =============================================================================
# ENVIRONMENT VARIABLES
# =============================================================================

# Set inside sandbox (additional env vars passed via --env flag)
envar: "HOME=/sandbox"
envar: "TMPDIR=/tmp"
envar: "PYTHONPATH=/opt/mcpworks/site-packages"
envar: "PYTHONUNBUFFERED=1"
envar: "PYTHONDONTWRITEBYTECODE=1"
envar: "LC_ALL=C.UTF-8"
envar: "LANG=C.UTF-8"

# =============================================================================
# EXECUTION
# =============================================================================

# Path to Python interpreter
exec_bin: "/usr/bin/python3"

# Command line arguments (wrapper script path)
# Actual execution: /usr/bin/python3 /opt/mcpworks/bin/execute.py
```

### Tier-Specific Configuration Overrides

The gateway generates tier-specific limits before spawning nsjail. These are applied via cgroup manipulation before the sandbox starts.

```bash
#!/bin/bash
# /opt/mcpworks/bin/spawn-sandbox.sh
# Spawns nsjail with tier-specific resource limits

set -euo pipefail

EXEC_ID="$1"
TIER="$2"
CODE_PATH="$3"
INPUT_PATH="$4"

# Tier-specific limits
declare -A MEMORY_LIMITS=(
    ["free"]="134217728"        # 128MB
    ["founder"]="268435456"     # 256MB
    ["founder_pro"]="536870912" # 512MB
    ["enterprise"]="2147483648" # 2GB
)

declare -A TIME_LIMITS=(
    ["free"]="10"
    ["founder"]="30"
    ["founder_pro"]="60"
    ["enterprise"]="300"
)

declare -A CPU_LIMITS=(
    ["free"]="5000 100000"      # 5% of one CPU
    ["founder"]="15000 100000"  # 15% of one CPU
    ["founder_pro"]="30000 100000" # 30% of one CPU
    ["enterprise"]="100000 100000" # 100% of one CPU
)

declare -A PID_LIMITS=(
    ["free"]="16"
    ["founder"]="32"
    ["founder_pro"]="64"
    ["enterprise"]="128"
)

declare -A NETWORK_HOSTS=(
    ["free"]="0"
    ["founder"]="5"
    ["founder_pro"]="25"
    ["enterprise"]="unlimited"
)

# Create cgroup for this execution
CGROUP_PATH="/sys/fs/cgroup/mcpworks/exec-${EXEC_ID}"
mkdir -p "$CGROUP_PATH"

# Apply resource limits
echo "${MEMORY_LIMITS[$TIER]}" > "$CGROUP_PATH/memory.max"
echo "${CPU_LIMITS[$TIER]}" > "$CGROUP_PATH/cpu.max"
echo "${PID_LIMITS[$TIER]}" > "$CGROUP_PATH/pids.max"

# Enable memory accounting
echo "+memory +cpu +pids" > "$CGROUP_PATH/cgroup.subtree_control"

# Create execution directory
EXEC_DIR="/tmp/exec-${EXEC_ID}"
mkdir -p "$EXEC_DIR"
chmod 700 "$EXEC_DIR"

# Copy code and input
cp "$CODE_PATH" "$EXEC_DIR/user_code.py"
cp "$INPUT_PATH" "$EXEC_DIR/input.json"

# Set up network namespace with egress proxy (if tier allows network)
if [[ "$TIER" != "free" ]]; then
    /opt/mcpworks/bin/setup-network.sh "$EXEC_ID" "$TIER" "${NETWORK_HOSTS[$TIER]}"
fi

# Spawn nsjail with cgroup
nsjail \
    --config /etc/mcpworks/sandbox.cfg \
    --cgroup_mem_mount "$CGROUP_PATH" \
    --cgroup_pids_mount "$CGROUP_PATH" \
    --cgroup_cpu_mount "$CGROUP_PATH" \
    --time_limit "${TIME_LIMITS[$TIER]}" \
    --rlimit_as "$((${MEMORY_LIMITS[$TIER]} / 1048576))" \
    --bindmount "$EXEC_DIR:/sandbox:rw" \
    --env "MCPWORKS_EXEC_ID=$EXEC_ID" \
    --env "MCPWORKS_TIER=$TIER" \
    -- /opt/mcpworks/bin/execute.py

EXIT_CODE=$?

# Cleanup
rm -rf "$CGROUP_PATH"
# Note: EXEC_DIR cleaned up by gateway after reading output

exit $EXIT_CODE
```

---

## 3. Seccomp Policy (Allowlist)

### Critical: Allowlist, Not Blocklist

A **blocklist** (blocking specific syscalls) is dangerous because new kernel syscalls are automatically allowed. We use an **allowlist** that denies everything by default and explicitly permits only required syscalls.

### Seccomp Allowlist Policy

```
# /etc/mcpworks/seccomp-allowlist.policy
#
# MCPWorks Code Execution Sandbox - Seccomp Allowlist Policy
# Version: 1.0.0
#
# PHILOSOPHY:
# - DEFAULT DENY: All syscalls blocked unless explicitly allowed
# - MINIMAL SURFACE: Only syscalls required for Python execution
# - DOCUMENTED: Each syscall has a rationale
#
# POLICY FORMAT: Kafel (used by nsjail)
# See: https://github.com/google/kafel

POLICY mcpworks_sandbox {
  # =========================================================================
  # FILE OPERATIONS (read-only access, controlled write to /sandbox and /tmp)
  # =========================================================================

  # File open - needed for reading Python files, libraries, input.json
  # SECURITY: Filesystem is mounted read-only except /sandbox, /tmp
  ALLOW {
    open,
    openat,
    openat2
  }

  # File close
  ALLOW { close, close_range }

  # File read
  ALLOW { read, pread64, readv, preadv, preadv2 }

  # File write - only succeeds on writable mounts (/sandbox, /tmp)
  ALLOW { write, pwrite64, writev, pwritev, pwritev2 }

  # File seek
  ALLOW { lseek, llseek }

  # File stat (metadata)
  ALLOW {
    stat, lstat, fstat,
    statx,
    newfstatat,
    fstatat64
  }

  # Directory operations
  ALLOW {
    getdents, getdents64,
    getcwd,
    chdir, fchdir
  }

  # File descriptor operations
  ALLOW {
    dup, dup2, dup3,
    fcntl, fcntl64,
    flock
  }

  # File access check
  ALLOW { access, faccessat, faccessat2 }

  # Symlink operations (read-only)
  ALLOW { readlink, readlinkat }

  # File truncate (only works on writable files)
  ALLOW { truncate, ftruncate }

  # Unlink/rename (only works in /sandbox, /tmp)
  ALLOW { unlink, unlinkat, rename, renameat, renameat2 }

  # Directory creation (only works in /sandbox, /tmp)
  ALLOW { mkdir, mkdirat, rmdir }

  # =========================================================================
  # MEMORY OPERATIONS
  # =========================================================================

  # Memory mapping - essential for Python/library loading
  ALLOW {
    mmap, mmap2,
    munmap,
    mprotect,
    mremap,
    msync,
    madvise,
    mlock, mlock2, munlock,
    mlockall, munlockall
  }

  # Memory allocation
  ALLOW { brk, sbrk }

  # =========================================================================
  # PROCESS OPERATIONS
  # =========================================================================

  # Get process/thread IDs
  ALLOW {
    getpid, gettid,
    getppid,
    getuid, geteuid,
    getgid, getegid,
    getgroups,
    getresuid, getresgid
  }

  # Process exit
  ALLOW { exit, exit_group }

  # Thread creation - needed for Python threading/asyncio
  # SECURITY: pids.max cgroup limits total threads
  ALLOW { clone, clone3 }

  # Wait for child processes
  ALLOW { wait4, waitid, waitpid }

  # Signals
  ALLOW {
    rt_sigaction, sigaction,
    rt_sigprocmask, sigprocmask,
    rt_sigreturn, sigreturn,
    rt_sigsuspend,
    rt_sigpending,
    rt_sigtimedwait,
    kill, tgkill, tkill,
    sigaltstack
  }

  # Futex - needed for Python threading primitives
  ALLOW { futex, futex_time64 }

  # Thread-local storage
  ALLOW { set_tid_address, set_robust_list, get_robust_list }

  # Arch-specific (x86_64)
  ALLOW { arch_prctl }

  # Process resource limits (read-only, enforced by nsjail)
  ALLOW { getrlimit, prlimit64 }

  # Scheduler operations (within cgroup limits)
  ALLOW {
    sched_yield,
    sched_getaffinity,
    sched_getscheduler,
    sched_getparam,
    sched_get_priority_min,
    sched_get_priority_max
  }

  # =========================================================================
  # TIME OPERATIONS
  # =========================================================================

  ALLOW {
    clock_gettime, clock_gettime64,
    clock_getres, clock_getres_time64,
    gettimeofday,
    time,
    nanosleep, clock_nanosleep, clock_nanosleep_time64
  }

  # Timers (for asyncio)
  ALLOW {
    timer_create,
    timer_settime, timer_settime64,
    timer_gettime, timer_gettime64,
    timer_getoverrun,
    timer_delete,
    timerfd_create,
    timerfd_settime, timerfd_settime64,
    timerfd_gettime, timerfd_gettime64
  }

  # =========================================================================
  # I/O MULTIPLEXING (for asyncio, httpx)
  # =========================================================================

  ALLOW {
    poll, ppoll, ppoll_time64,
    select, pselect6, pselect6_time64,
    epoll_create, epoll_create1,
    epoll_ctl,
    epoll_wait, epoll_pwait, epoll_pwait2,
    eventfd, eventfd2
  }

  # =========================================================================
  # NETWORK OPERATIONS (routed through egress proxy)
  # =========================================================================

  # Socket creation - only AF_INET, AF_INET6, AF_UNIX allowed by network namespace
  ALLOW { socket }

  # Socket operations
  ALLOW {
    bind, listen, accept, accept4,
    connect,
    send, sendto, sendmsg, sendmmsg,
    recv, recvfrom, recvmsg, recvmmsg,
    shutdown,
    getsockname, getpeername,
    getsockopt, setsockopt,
    socketpair
  }

  # =========================================================================
  # PIPE OPERATIONS
  # =========================================================================

  ALLOW { pipe, pipe2 }
  ALLOW { splice, tee }

  # =========================================================================
  # RANDOM NUMBER GENERATION (critical for TLS)
  # =========================================================================

  ALLOW { getrandom }

  # =========================================================================
  # MISC REQUIRED SYSCALLS
  # =========================================================================

  # System info (read-only)
  ALLOW { uname, sysinfo }

  # Resource usage
  ALLOW { getrusage }

  # File system info
  ALLOW { statfs, fstatfs, statfs64, fstatfs64 }

  # ioctl - limited to safe operations
  # SECURITY: Most ioctl commands will fail (no device access)
  ALLOW { ioctl }

  # prctl - for thread naming, etc.
  # SECURITY: Dangerous prctl options blocked separately
  ALLOW { prctl }

  # Read-only proc/sys access
  ALLOW { sysfs }

  # Misc
  ALLOW {
    umask,
    rseq,
    membarrier
  }

  # =========================================================================
  # EXPLICITLY DENIED (with rationale)
  # =========================================================================

  # --- NAMESPACE/CONTAINER ESCAPE ---
  DENY {
    unshare,          # Create new namespaces (escape)
    setns,            # Enter different namespace (escape)
    pivot_root,       # Change root filesystem (escape)
    chroot,           # Change root directory (escape)
    mount,            # Mount filesystems (escape)
    umount, umount2   # Unmount filesystems
  }

  # --- PRIVILEGE ESCALATION ---
  DENY {
    setuid, setgid,
    setreuid, setregid,
    setresuid, setresgid,
    setgroups,
    setfsuid, setfsgid,
    capget, capset    # Capability manipulation
  }

  # --- KERNEL MANIPULATION ---
  DENY {
    init_module, finit_module, delete_module,  # Kernel modules
    kexec_load, kexec_file_load,               # Kernel execution
    reboot,                                     # System reboot
    swapon, swapoff,                           # Swap manipulation
    sethostname, setdomainname,                # Network identity
    settimeofday, clock_settime, adjtimex      # Time manipulation
  }

  # --- DANGEROUS DEBUGGING/INTROSPECTION ---
  DENY {
    ptrace,                                    # Process tracing (escape)
    process_vm_readv, process_vm_writev,       # Cross-process memory access
    kcmp,                                      # Kernel object comparison
    lookup_dcookie                             # Kernel profiling
  }

  # --- BPF/PERFORMANCE (kernel attack surface) ---
  DENY {
    bpf,                                       # BPF programs
    perf_event_open,                           # Performance monitoring
    userfaultfd                                # User-space page fault handling
  }

  # --- SECURITY KEYS (keyring exploits) ---
  DENY {
    keyctl,
    request_key,
    add_key
  }

  # --- FILESYSTEM ESCAPE ---
  DENY {
    open_by_handle_at,   # CVE-2015-1335 container escape
    name_to_handle_at,   # Handle-based file access
    fanotify_init,       # File access notification (escape vector)
    inotify_init, inotify_init1  # File notification (resource exhaustion)
  }

  # --- QUOTA/ACCOUNTING ---
  DENY {
    quotactl,            # Disk quota manipulation
    acct                 # Process accounting
  }

  # --- IPC (isolated by namespace, explicitly deny) ---
  DENY {
    shmget, shmat, shmdt, shmctl,    # Shared memory
    msgget, msgsnd, msgrcv, msgctl,  # Message queues
    semget, semop, semtimedop, semctl # Semaphores
  }

  # --- PERSONALITY (disable ASLR, etc.) ---
  DENY { personality }

  # --- SECCOMP MANIPULATION ---
  DENY { seccomp }

  # --- VDSO/VSYSCALL ---
  # These are handled specially by the kernel and generally safe
  # but we don't need them

  # =========================================================================
  # DEFAULT: DENY ALL UNLISTED SYSCALLS
  # =========================================================================

  # Any syscall not explicitly ALLOW'd above is killed
  # This includes future syscalls added to the kernel
}

# Apply the policy
USE mcpworks_sandbox DEFAULT KILL
```

### Syscall Rationale Summary

| Category | Allowed | Rationale |
|----------|---------|-----------|
| **File I/O** | open, read, write, stat, etc. | Python needs filesystem access; mounts enforce read-only |
| **Memory** | mmap, mprotect, brk | Python VM requires memory management |
| **Process** | clone, exit, wait, signals | Python threading/multiprocessing (limited by pids.max) |
| **Time** | clock_gettime, nanosleep | Timekeeping, sleep operations |
| **Network** | socket, connect, send, recv | HTTP clients (routed through egress proxy) |
| **Random** | getrandom | Cryptographic operations, TLS |
| **I/O Multiplex** | epoll, poll, select | asyncio event loop |

| Category | Denied | Rationale |
|----------|--------|-----------|
| **Namespaces** | unshare, setns, pivot_root | Prevent namespace escape |
| **Privileges** | setuid, setgid, cap* | Prevent privilege escalation |
| **Kernel** | init_module, kexec_load | Prevent kernel manipulation |
| **Debug** | ptrace, process_vm_* | Prevent process introspection |
| **BPF** | bpf, perf_event_open | Reduce kernel attack surface |
| **Keys** | keyctl, request_key | Prevent keyring exploits |
| **Escape** | open_by_handle_at | CVE-2015-1335 container escape |

---

## 4. Egress Proxy Architecture

### Overview

The egress proxy controls all outbound network access from sandboxes. It enforces per-tier allowlist policies and logs all network activity.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  Host System                                                                 │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  Egress Proxy (mitmproxy or custom)                                  │   │
│  │  Listening on: 127.0.0.1:8888 (HTTP) / 127.0.0.1:8889 (SOCKS5)      │   │
│  │                                                                      │   │
│  │  Per-request enforcement:                                            │   │
│  │  1. Extract execution ID from X-MCPWorks-Exec-ID header             │   │
│  │  2. Look up tier and allowed hosts from Redis/file                  │   │
│  │  3. Check destination against allowlist                             │   │
│  │  4. Allow or reject with logging                                    │   │
│  │                                                                      │   │
│  │  Allowlist by tier:                                                  │   │
│  │  - Free: NONE (no network access)                                   │   │
│  │  - Founder: 5 user-configured hosts                                 │   │
│  │  - Founder Pro: 25 user-configured hosts                            │   │
│  │  - Enterprise: Unlimited (or blocklist mode)                        │   │
│  └────────────────────────────────────┬─────────────────────────────────┘   │
│                                       │                                     │
│  ┌────────────────────────────────────┴─────────────────────────────────┐   │
│  │  veth0 (host end)                                                    │   │
│  │  IP: 10.200.{exec_id}.1/30                                          │   │
│  └────────────────────────────────────┬─────────────────────────────────┘   │
│                                       │                                     │
│  ════════════════════════════════════════════════════════════════════════   │
│                                       │                                     │
│  ┌────────────────────────────────────┴─────────────────────────────────┐   │
│  │  Sandbox Network Namespace                                           │   │
│  │                                                                      │   │
│  │  veth1 (sandbox end)                                                 │   │
│  │  IP: 10.200.{exec_id}.2/30                                          │   │
│  │  Default route: 10.200.{exec_id}.1 (host)                           │   │
│  │                                                                      │   │
│  │  iptables (inside sandbox):                                         │   │
│  │  - OUTPUT -p tcp --dport 80 -j REDIRECT --to-port 8888              │   │
│  │  - OUTPUT -p tcp --dport 443 -j REDIRECT --to-port 8888             │   │
│  │  - OUTPUT -j DROP (everything else)                                 │   │
│  │                                                                      │   │
│  │  User code sees: Normal HTTPS access to allowlisted hosts           │   │
│  │  Actually routes through: Egress proxy on host                      │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Network Setup Script

```bash
#!/bin/bash
# /opt/mcpworks/bin/setup-network.sh
# Sets up network namespace with egress proxy routing

set -euo pipefail

EXEC_ID="$1"
TIER="$2"
MAX_HOSTS="$3"

# Calculate unique IP range for this execution
# Using last 2 bytes of exec_id hash for uniqueness
EXEC_HASH=$(echo -n "$EXEC_ID" | md5sum | head -c 4)
SUBNET_ID=$((16#$EXEC_HASH % 65536))
SUBNET_A=$((SUBNET_ID / 256))
SUBNET_B=$((SUBNET_ID % 256))

VETH_HOST="veth-${EXEC_ID:0:8}-h"
VETH_SANDBOX="veth-${EXEC_ID:0:8}-s"
HOST_IP="10.${SUBNET_A}.${SUBNET_B}.1"
SANDBOX_IP="10.${SUBNET_A}.${SUBNET_B}.2"

# Create veth pair
ip link add "$VETH_HOST" type veth peer name "$VETH_SANDBOX"

# Configure host end
ip addr add "${HOST_IP}/30" dev "$VETH_HOST"
ip link set "$VETH_HOST" up

# Move sandbox end to sandbox's network namespace
# (nsjail will handle this via --macvlan_iface or we pre-create netns)

# Enable forwarding for this interface
echo 1 > /proc/sys/net/ipv4/conf/$VETH_HOST/forwarding

# NAT for outbound traffic (through egress proxy)
iptables -t nat -A POSTROUTING -s "${SANDBOX_IP}/32" -o eth0 -j MASQUERADE

# Route sandbox traffic to egress proxy
# All HTTP(S) traffic redirected to mitmproxy
iptables -t nat -A PREROUTING -i "$VETH_HOST" -p tcp --dport 80 -j REDIRECT --to-port 8888
iptables -t nat -A PREROUTING -i "$VETH_HOST" -p tcp --dport 443 -j REDIRECT --to-port 8889

# Block all other traffic from sandbox
iptables -A FORWARD -i "$VETH_HOST" -p tcp --dport 80 -j ACCEPT
iptables -A FORWARD -i "$VETH_HOST" -p tcp --dport 443 -j ACCEPT
iptables -A FORWARD -i "$VETH_HOST" -j DROP

# Register this execution's allowed hosts
if [[ "$MAX_HOSTS" != "0" && "$MAX_HOSTS" != "unlimited" ]]; then
    redis-cli SET "egress:${EXEC_ID}:tier" "$TIER"
    redis-cli SET "egress:${EXEC_ID}:max_hosts" "$MAX_HOSTS"
    redis-cli EXPIRE "egress:${EXEC_ID}:tier" 3600
    redis-cli EXPIRE "egress:${EXEC_ID}:max_hosts" 3600
fi

echo "Network setup complete for $EXEC_ID"
echo "  Sandbox IP: $SANDBOX_IP"
echo "  Host IP: $HOST_IP"
echo "  Max hosts: $MAX_HOSTS"
```

### Egress Proxy Implementation (mitmproxy addon)

```python
# /opt/mcpworks/egress-proxy/allowlist_addon.py
"""
MCPWorks Egress Proxy - Allowlist Enforcement Addon for mitmproxy

This addon intercepts all HTTP/HTTPS traffic from sandboxes and enforces
per-tier allowlist policies.
"""

import logging
import redis
from mitmproxy import http, ctx
from typing import Optional, Set

logger = logging.getLogger("mcpworks.egress")

# Redis connection for allowlist lookup
redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

# Tier-based host limits
TIER_LIMITS = {
    "free": 0,
    "founder": 5,
    "founder_pro": 25,
    "enterprise": -1,  # Unlimited
}

# Always-allowed hosts (MCPWorks internal services)
INTERNAL_HOSTS = {
    "127.0.0.1",
    "localhost",
    "gateway.mcpworks.internal",
}

# Always-blocked hosts (security)
BLOCKED_HOSTS = {
    "169.254.169.254",      # AWS/GCP metadata service
    "metadata.google.internal",
    "metadata.azure.internal",
    "100.100.100.200",      # Alibaba metadata
    "fd00:ec2::254",        # AWS IPv6 metadata
}


class AllowlistAddon:
    def __init__(self):
        self.cached_allowlists: dict[str, Set[str]] = {}

    def get_exec_id(self, flow: http.HTTPFlow) -> Optional[str]:
        """Extract execution ID from request headers or source IP."""
        # Method 1: X-MCPWorks-Exec-ID header (injected by SDK)
        exec_id = flow.request.headers.get("X-MCPWorks-Exec-ID")
        if exec_id:
            return exec_id

        # Method 2: Lookup by source IP
        src_ip = flow.client_conn.peername[0]
        exec_id = redis_client.get(f"egress:ip:{src_ip}")
        return exec_id

    def get_tier(self, exec_id: str) -> str:
        """Get execution tier from Redis."""
        tier = redis_client.get(f"egress:{exec_id}:tier")
        return tier or "free"

    def get_allowlist(self, exec_id: str) -> Set[str]:
        """Get allowed hosts for this execution."""
        # Check cache first
        if exec_id in self.cached_allowlists:
            return self.cached_allowlists[exec_id]

        # Load from Redis
        hosts = redis_client.smembers(f"egress:{exec_id}:hosts")
        allowlist = set(hosts) | INTERNAL_HOSTS

        # Cache for this execution
        self.cached_allowlists[exec_id] = allowlist
        return allowlist

    def is_host_allowed(self, exec_id: str, host: str, tier: str) -> tuple[bool, str]:
        """Check if host is allowed for this execution."""
        # Always block dangerous hosts
        if host in BLOCKED_HOSTS or any(host.endswith(f".{blocked}") for blocked in BLOCKED_HOSTS):
            return False, f"Host {host} is blocked (security)"

        # Always allow internal hosts
        if host in INTERNAL_HOSTS:
            return True, "internal"

        # Free tier: no network access
        if tier == "free":
            return False, "Free tier has no network access"

        # Get allowlist
        allowlist = self.get_allowlist(exec_id)

        # Check against allowlist
        if host in allowlist:
            return True, "allowlisted"

        # Check wildcard (*.example.com)
        for allowed in allowlist:
            if allowed.startswith("*.") and host.endswith(allowed[1:]):
                return True, f"wildcard match {allowed}"

        # Enterprise tier: allow all (unless explicitly blocked)
        if tier == "enterprise":
            return True, "enterprise (all allowed)"

        # Not in allowlist
        return False, f"Host {host} not in allowlist"

    def request(self, flow: http.HTTPFlow) -> None:
        """Intercept and validate each request."""
        host = flow.request.host

        # Get execution context
        exec_id = self.get_exec_id(flow)
        if not exec_id:
            logger.warning(f"Request without exec_id from {flow.client_conn.peername}")
            flow.response = http.Response.make(
                403,
                b'{"error": "Missing execution context"}',
                {"Content-Type": "application/json"}
            )
            return

        tier = self.get_tier(exec_id)
        allowed, reason = self.is_host_allowed(exec_id, host, tier)

        # Log all requests
        logger.info(f"[{exec_id}] {flow.request.method} {host}{flow.request.path} "
                   f"- tier={tier} allowed={allowed} reason={reason}")

        if not allowed:
            # Block the request
            flow.response = http.Response.make(
                403,
                f'{{"error": "Network access denied", "reason": "{reason}"}}'.encode(),
                {"Content-Type": "application/json"}
            )

            # Log security event
            redis_client.rpush(
                f"security:blocked_requests",
                f"{exec_id}|{host}|{tier}|{reason}"
            )


addons = [AllowlistAddon()]
```

### User Host Configuration API

Users configure their allowed hosts via the Gateway API:

```http
POST /v1/account/network-allowlist
Authorization: Bearer {api_key}
Content-Type: application/json

{
    "hosts": [
        "api.stripe.com",
        "api.openai.com",
        "*.shopify.com",
        "hooks.slack.com"
    ]
}

Response:
{
    "status": "ok",
    "hosts": ["api.stripe.com", "api.openai.com", "*.shopify.com", "hooks.slack.com"],
    "tier": "founder_pro",
    "max_hosts": 25,
    "used": 4
}
```

---

## 5. Execution Wrapper

The execution wrapper is a Python script that runs inside the sandbox. It:
1. Reads input from `/sandbox/input.json`
2. Injects the MCPWorks SDK
3. Executes user code with timeout handling
4. Captures stdout/stderr
5. Writes structured output to `/sandbox/output.json`

### Execution Wrapper Script

```python
#!/usr/bin/env python3
# /opt/mcpworks/bin/execute.py
"""
MCPWorks Execution Wrapper

Runs inside the nsjail sandbox. Executes user code with:
- Input injection from input.json
- MCPWorks SDK available as 'mcpworks' module
- Captured stdout/stderr
- Structured output to output.json

SECURITY NOTES:
- This script runs as nobody:nogroup
- Filesystem is read-only except /sandbox and /tmp
- Network is isolated (egress proxy only)
- Resource limits enforced by cgroups
"""

import sys
import os
import json
import traceback
import io
import signal
from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime
from typing import Any, Optional

# Ensure our SDK is importable
sys.path.insert(0, '/opt/mcpworks/site-packages')

# Constants
SANDBOX_DIR = '/sandbox'
INPUT_FILE = os.path.join(SANDBOX_DIR, 'input.json')
CODE_FILE = os.path.join(SANDBOX_DIR, 'user_code.py')
OUTPUT_FILE = os.path.join(SANDBOX_DIR, 'output.json')
MAX_OUTPUT_SIZE = 1024 * 1024  # 1MB max output


class TimeoutError(Exception):
    """Raised when execution exceeds time limit."""
    pass


def timeout_handler(signum, frame):
    """Signal handler for SIGALRM timeout."""
    raise TimeoutError("Execution timed out")


def truncate_output(output: str, max_size: int = MAX_OUTPUT_SIZE) -> str:
    """Truncate output to prevent memory exhaustion."""
    if len(output) > max_size:
        return output[:max_size] + f"\n... (truncated, {len(output) - max_size} bytes omitted)"
    return output


def safe_json_serialize(obj: Any) -> Any:
    """Convert non-serializable objects to strings."""
    if isinstance(obj, (str, int, float, bool, type(None))):
        return obj
    if isinstance(obj, (list, tuple)):
        return [safe_json_serialize(item) for item in obj]
    if isinstance(obj, dict):
        return {str(k): safe_json_serialize(v) for k, v in obj.items()}
    if isinstance(obj, bytes):
        try:
            return obj.decode('utf-8')
        except UnicodeDecodeError:
            return f"<bytes: {len(obj)} bytes>"
    if isinstance(obj, datetime):
        return obj.isoformat()
    # Fallback: convert to string
    return str(obj)


def write_output(
    success: bool,
    result: Optional[Any] = None,
    stdout: str = "",
    stderr: str = "",
    error: Optional[str] = None,
    error_type: Optional[str] = None,
    traceback_str: Optional[str] = None,
    execution_time_ms: Optional[int] = None
):
    """Write structured output to output.json."""
    output = {
        "success": success,
        "result": safe_json_serialize(result) if result is not None else None,
        "stdout": truncate_output(stdout),
        "stderr": truncate_output(stderr),
        "error": error,
        "error_type": error_type,
        "traceback": traceback_str,
        "execution_time_ms": execution_time_ms,
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }

    with open(OUTPUT_FILE, 'w') as f:
        json.dump(output, f, indent=2)


def main():
    start_time = datetime.utcnow()
    stdout_capture = io.StringIO()
    stderr_capture = io.StringIO()

    try:
        # Read input data
        if os.path.exists(INPUT_FILE):
            with open(INPUT_FILE, 'r') as f:
                input_data = json.load(f)
        else:
            input_data = {}

        # Read user code
        if not os.path.exists(CODE_FILE):
            write_output(
                success=False,
                error="User code file not found",
                error_type="FileNotFoundError"
            )
            return 1

        with open(CODE_FILE, 'r') as f:
            user_code = f.read()

        # Validate code doesn't import dangerous modules
        # (This is defense-in-depth; seccomp is the real protection)
        dangerous_imports = ['os.system', 'subprocess', 'ctypes', 'cffi']
        for dangerous in dangerous_imports:
            if dangerous in user_code:
                write_output(
                    success=False,
                    error=f"Disallowed import/call: {dangerous}",
                    error_type="SecurityError"
                )
                return 1

        # Prepare execution environment
        exec_globals = {
            '__builtins__': __builtins__,
            '__name__': '__main__',
            '__file__': CODE_FILE,
            'input_data': input_data,
        }

        # Import MCPWorks SDK
        try:
            import mcpworks
            exec_globals['mcpworks'] = mcpworks
        except ImportError as e:
            stderr_capture.write(f"Warning: MCPWorks SDK not available: {e}\n")

        # Set up timeout handler
        # Note: This is backup; nsjail enforces the real time limit
        timeout_seconds = int(os.environ.get('MCPWORKS_TIMEOUT', 30))
        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(timeout_seconds)

        # Execute user code with captured stdout/stderr
        with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
            # Compile first to get better error messages
            compiled = compile(user_code, CODE_FILE, 'exec')

            # Execute
            exec(compiled, exec_globals)

        # Cancel timeout
        signal.alarm(0)

        # Extract result (look for 'result' variable or last expression)
        result = exec_globals.get('result', None)

        # Calculate execution time
        execution_time_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)

        write_output(
            success=True,
            result=result,
            stdout=stdout_capture.getvalue(),
            stderr=stderr_capture.getvalue(),
            execution_time_ms=execution_time_ms
        )
        return 0

    except TimeoutError as e:
        write_output(
            success=False,
            stdout=stdout_capture.getvalue(),
            stderr=stderr_capture.getvalue(),
            error="Execution timed out",
            error_type="TimeoutError"
        )
        return 1

    except SyntaxError as e:
        write_output(
            success=False,
            stdout=stdout_capture.getvalue(),
            stderr=stderr_capture.getvalue(),
            error=str(e),
            error_type="SyntaxError",
            traceback_str=traceback.format_exc()
        )
        return 1

    except Exception as e:
        write_output(
            success=False,
            stdout=stdout_capture.getvalue(),
            stderr=stderr_capture.getvalue(),
            error=str(e),
            error_type=type(e).__name__,
            traceback_str=traceback.format_exc()
        )
        return 1


if __name__ == '__main__':
    sys.exit(main())
```

### MCPWorks SDK (Injected into Sandbox)

```python
# /opt/mcpworks/sandbox-root/site-packages/mcpworks/__init__.py
"""
MCPWorks SDK - Available inside Code Execution Sandbox

Provides access to:
- mcpworks.workflows.{workflow_name}.run() - Execute Activepieces workflows
- mcpworks.services.{service_name}.run() - Call services
- mcpworks.http.get/post() - Make HTTP requests (through egress proxy)

All external communication routes through the internal gateway at
http://gateway.mcpworks.internal:9999
"""

import os
import json
import urllib.request
import urllib.error
from typing import Any, Optional, Dict
from dataclasses import dataclass


# Internal gateway endpoint (not internet-accessible)
GATEWAY_URL = os.environ.get("MCPWORKS_GATEWAY_URL", "http://gateway.mcpworks.internal:9999")
EXEC_ID = os.environ.get("MCPWORKS_EXEC_ID", "unknown")
EXEC_TOKEN = os.environ.get("MCPWORKS_EXEC_TOKEN", "")


@dataclass
class SDKResponse:
    """Response from an SDK call."""
    success: bool
    data: Any
    error: Optional[str] = None
    status_code: int = 200


class GatewayClient:
    """HTTP client for internal gateway communication."""

    def __init__(self, base_url: str, exec_id: str, token: str):
        self.base_url = base_url
        self.exec_id = exec_id
        self.token = token

    def _request(
        self,
        method: str,
        path: str,
        data: Optional[Dict] = None
    ) -> SDKResponse:
        """Make a request to the internal gateway."""
        url = f"{self.base_url}{path}"

        headers = {
            "Content-Type": "application/json",
            "X-MCPWorks-Exec-ID": self.exec_id,
            "Authorization": f"Bearer {self.token}" if self.token else "",
        }

        body = json.dumps(data).encode() if data else None

        try:
            req = urllib.request.Request(
                url,
                data=body,
                headers=headers,
                method=method
            )

            with urllib.request.urlopen(req, timeout=30) as response:
                response_data = json.loads(response.read().decode())
                return SDKResponse(
                    success=True,
                    data=response_data,
                    status_code=response.status
                )

        except urllib.error.HTTPError as e:
            error_body = e.read().decode() if e.fp else str(e)
            return SDKResponse(
                success=False,
                data=None,
                error=error_body,
                status_code=e.code
            )
        except urllib.error.URLError as e:
            return SDKResponse(
                success=False,
                data=None,
                error=f"Network error: {e.reason}",
                status_code=0
            )
        except Exception as e:
            return SDKResponse(
                success=False,
                data=None,
                error=str(e),
                status_code=0
            )

    def post(self, path: str, data: Dict) -> SDKResponse:
        return self._request("POST", path, data)

    def get(self, path: str) -> SDKResponse:
        return self._request("GET", path)


class WorkflowProxy:
    """Proxy for accessing user workflows."""

    def __init__(self, client: GatewayClient, workflow_name: str):
        self.client = client
        self.workflow_name = workflow_name

    def run(self, **kwargs) -> Any:
        """Execute this workflow with the given parameters."""
        response = self.client.post(
            f"/internal/workflows/{self.workflow_name}/execute",
            {"params": kwargs}
        )

        if not response.success:
            raise RuntimeError(f"Workflow {self.workflow_name} failed: {response.error}")

        return response.data


class WorkflowsNamespace:
    """Namespace for accessing workflows."""

    def __init__(self, client: GatewayClient):
        self.client = client
        self._cache: Dict[str, WorkflowProxy] = {}

    def __getattr__(self, workflow_name: str) -> WorkflowProxy:
        if workflow_name.startswith('_'):
            raise AttributeError(workflow_name)

        if workflow_name not in self._cache:
            self._cache[workflow_name] = WorkflowProxy(self.client, workflow_name)

        return self._cache[workflow_name]

    def list(self) -> list:
        """List available workflows."""
        response = self.client.get("/internal/workflows")
        if not response.success:
            raise RuntimeError(f"Failed to list workflows: {response.error}")
        return response.data


class ServiceProxy:
    """Proxy for accessing services."""

    def __init__(self, client: GatewayClient, service_name: str):
        self.client = client
        self.service_name = service_name

    def run(self, **kwargs) -> Any:
        """Call this service with the given parameters."""
        response = self.client.post(
            f"/internal/services/{self.service_name}/invoke",
            {"params": kwargs}
        )

        if not response.success:
            raise RuntimeError(f"Service {self.service_name} failed: {response.error}")

        return response.data


class ServicesNamespace:
    """Namespace for accessing services."""

    def __init__(self, client: GatewayClient):
        self.client = client
        self._cache: Dict[str, ServiceProxy] = {}

    def __getattr__(self, service_name: str) -> ServiceProxy:
        if service_name.startswith('_'):
            raise AttributeError(service_name)

        if service_name not in self._cache:
            self._cache[service_name] = ServiceProxy(self.client, service_name)

        return self._cache[service_name]

    def list(self) -> list:
        """List available services."""
        response = self.client.get("/internal/services")
        if not response.success:
            raise RuntimeError(f"Failed to list services: {response.error}")
        return response.data


class HttpClient:
    """HTTP client for external requests (through egress proxy)."""

    def __init__(self, exec_id: str):
        self.exec_id = exec_id

    def _request(self, method: str, url: str, **kwargs) -> Any:
        """Make an HTTP request through the egress proxy."""
        headers = kwargs.get("headers", {})
        headers["X-MCPWorks-Exec-ID"] = self.exec_id

        data = kwargs.get("data") or kwargs.get("json")
        if kwargs.get("json"):
            headers["Content-Type"] = "application/json"
            data = json.dumps(data).encode()
        elif isinstance(data, str):
            data = data.encode()

        timeout = kwargs.get("timeout", 30)

        try:
            req = urllib.request.Request(url, data=data, headers=headers, method=method)
            with urllib.request.urlopen(req, timeout=timeout) as response:
                content = response.read()
                try:
                    return json.loads(content)
                except json.JSONDecodeError:
                    return content.decode()
        except urllib.error.HTTPError as e:
            error_body = e.read().decode() if e.fp else ""
            raise RuntimeError(f"HTTP {e.code}: {error_body}")
        except urllib.error.URLError as e:
            if "403" in str(e.reason) or "denied" in str(e.reason).lower():
                raise RuntimeError(f"Network access denied. Add this host to your allowlist.")
            raise RuntimeError(f"Network error: {e.reason}")

    def get(self, url: str, **kwargs) -> Any:
        return self._request("GET", url, **kwargs)

    def post(self, url: str, **kwargs) -> Any:
        return self._request("POST", url, **kwargs)

    def put(self, url: str, **kwargs) -> Any:
        return self._request("PUT", url, **kwargs)

    def delete(self, url: str, **kwargs) -> Any:
        return self._request("DELETE", url, **kwargs)


class MCPWorks:
    """Main MCPWorks SDK class."""

    def __init__(self):
        self._client = GatewayClient(GATEWAY_URL, EXEC_ID, EXEC_TOKEN)
        self._workflows: Optional[WorkflowsNamespace] = None
        self._services: Optional[ServicesNamespace] = None
        self._http: Optional[HttpClient] = None

    @property
    def workflows(self) -> WorkflowsNamespace:
        """Access to user workflows."""
        if self._workflows is None:
            self._workflows = WorkflowsNamespace(self._client)
        return self._workflows

    @property
    def services(self) -> ServicesNamespace:
        """Access to services."""
        if self._services is None:
            self._services = ServicesNamespace(self._client)
        return self._services

    @property
    def http(self) -> HttpClient:
        """HTTP client for external requests."""
        if self._http is None:
            self._http = HttpClient(EXEC_ID)
        return self._http


# Global instance
mcpworks = MCPWorks()

# Convenience exports
workflows = mcpworks.workflows
services = mcpworks.services
http = mcpworks.http
```

---

## 6. Sandbox Root Filesystem

### Directory Structure

```
/opt/mcpworks/
├── bin/
│   ├── execute.py              # Execution wrapper script
│   ├── spawn-sandbox.sh        # Sandbox spawning script
│   └── setup-network.sh        # Network namespace setup
│
├── rootfs/
│   ├── dev-static/             # Static device nodes
│   │   ├── null                # /dev/null
│   │   ├── zero                # /dev/zero
│   │   ├── random              # /dev/random (symlink to urandom)
│   │   ├── urandom             # /dev/urandom
│   │   ├── fd -> /proc/self/fd # File descriptor directory
│   │   ├── stdin -> fd/0
│   │   ├── stdout -> fd/1
│   │   └── stderr -> fd/2
│   │
│   ├── passwd                  # Minimal passwd file
│   ├── group                   # Minimal group file
│   ├── hosts                   # Minimal hosts file
│   └── resolv.conf             # DNS configuration
│
├── sandbox-root/
│   └── site-packages/          # Pre-installed Python packages
│       ├── mcpworks/           # MCPWorks SDK
│       │   ├── __init__.py
│       │   └── ...
│       ├── requests/           # HTTP library
│       ├── httpx/              # Async HTTP library
│       ├── pandas/             # Data analysis
│       ├── numpy/              # Numerical computing
│       ├── pyyaml/             # YAML parsing
│       └── ...
│
└── egress-proxy/
    ├── allowlist_addon.py      # mitmproxy addon
    └── config.yaml             # Proxy configuration
```

### Static Files

#### /opt/mcpworks/rootfs/passwd

```
root:x:0:0:root:/root:/bin/false
nobody:x:65534:65534:nobody:/nonexistent:/bin/false
```

#### /opt/mcpworks/rootfs/group

```
root:x:0:
nogroup:x:65534:
```

#### /opt/mcpworks/rootfs/hosts

```
127.0.0.1   localhost
::1         localhost
10.0.0.1    gateway.mcpworks.internal
```

#### /opt/mcpworks/rootfs/resolv.conf

```
# DNS resolution through host
nameserver 127.0.0.53
options ndots:0
```

### Creating Static Device Nodes

```bash
#!/bin/bash
# /opt/mcpworks/scripts/create-dev-static.sh

set -euo pipefail

DEV_DIR="/opt/mcpworks/rootfs/dev-static"

# Create directory
mkdir -p "$DEV_DIR"

# Create device nodes (requires root)
mknod -m 666 "$DEV_DIR/null" c 1 3
mknod -m 666 "$DEV_DIR/zero" c 1 5
mknod -m 444 "$DEV_DIR/urandom" c 1 9

# Symlinks
ln -sf urandom "$DEV_DIR/random"
ln -sf /proc/self/fd "$DEV_DIR/fd"
ln -sf fd/0 "$DEV_DIR/stdin"
ln -sf fd/1 "$DEV_DIR/stdout"
ln -sf fd/2 "$DEV_DIR/stderr"

# Set ownership
chown -R root:root "$DEV_DIR"

echo "Device nodes created in $DEV_DIR"
```

### Pre-installed Python Packages

```
# /opt/mcpworks/sandbox-root/requirements.txt
# Pre-installed packages available in all sandboxes

# HTTP clients
requests==2.31.0
httpx==0.27.0

# Data processing
pandas==2.2.0
numpy==1.26.0

# Serialization
pyyaml==6.0.1
orjson==3.9.0

# Date/time
python-dateutil==2.8.2
pytz==2024.1

# Utilities
typing-extensions==4.9.0
pydantic==2.5.0

# Note: These are installed at image build time, not runtime
# Additional packages cannot be installed by user code (pip blocked)
```

---

## 7. Gateway Integration

### Gateway Sandbox Backend

```python
# src/mcpworks_api/backends/sandbox.py
"""
Gateway backend for Code Execution Sandbox.

Handles:
- Request validation
- Sandbox spawning
- Result retrieval
- Cleanup
"""

import asyncio
import json
import os
import shutil
import subprocess
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from ..config import settings
from ..models import Account, ExecutionTier
from ..exceptions import SandboxError, RateLimitError, ValidationError


@dataclass
class ExecutionRequest:
    """Request to execute code in sandbox."""
    code: str
    input_data: Dict[str, Any]
    account: Account
    execution_id: Optional[str] = None

    def __post_init__(self):
        if self.execution_id is None:
            self.execution_id = str(uuid.uuid4())


@dataclass
class ExecutionResult:
    """Result from sandbox execution."""
    success: bool
    result: Optional[Any]
    stdout: str
    stderr: str
    error: Optional[str]
    error_type: Optional[str]
    traceback: Optional[str]
    execution_time_ms: int
    execution_id: str


class SandboxBackend:
    """Backend for Code Execution Sandbox."""

    # Tier configuration
    TIER_CONFIG = {
        ExecutionTier.FREE: {
            "timeout": 10,
            "memory_mb": 128,
            "cpu_percent": 5,
            "max_pids": 16,
            "network_hosts": 0,
        },
        ExecutionTier.FOUNDER: {
            "timeout": 30,
            "memory_mb": 256,
            "cpu_percent": 15,
            "max_pids": 32,
            "network_hosts": 5,
        },
        ExecutionTier.FOUNDER_PRO: {
            "timeout": 60,
            "memory_mb": 512,
            "cpu_percent": 30,
            "max_pids": 64,
            "network_hosts": 25,
        },
        ExecutionTier.ENTERPRISE: {
            "timeout": 300,
            "memory_mb": 2048,
            "cpu_percent": 100,
            "max_pids": 128,
            "network_hosts": -1,  # Unlimited
        },
    }

    def __init__(self):
        self.sandbox_config = Path("/etc/mcpworks/sandbox.cfg")
        self.spawn_script = Path("/opt/mcpworks/bin/spawn-sandbox.sh")
        self.exec_dir = Path(tempfile.gettempdir())

    async def execute(self, request: ExecutionRequest) -> ExecutionResult:
        """Execute code in sandbox."""
        start_time = datetime.utcnow()
        exec_id = request.execution_id
        tier = request.account.tier
        tier_config = self.TIER_CONFIG[tier]

        # Create execution directory
        exec_dir = self.exec_dir / f"exec-{exec_id}"
        exec_dir.mkdir(mode=0o700, exist_ok=True)

        try:
            # Write input and code files
            (exec_dir / "input.json").write_text(
                json.dumps(request.input_data, default=str)
            )
            (exec_dir / "user_code.py").write_text(request.code)

            # Spawn sandbox process
            process = await asyncio.create_subprocess_exec(
                str(self.spawn_script),
                exec_id,
                tier.value,
                str(exec_dir / "user_code.py"),
                str(exec_dir / "input.json"),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            # Wait for completion with timeout
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=tier_config["timeout"] + 5  # Grace period
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                return ExecutionResult(
                    success=False,
                    result=None,
                    stdout="",
                    stderr="",
                    error="Execution timed out",
                    error_type="TimeoutError",
                    traceback=None,
                    execution_time_ms=tier_config["timeout"] * 1000,
                    execution_id=exec_id,
                )

            # Read output file
            output_file = exec_dir / "output.json"
            if output_file.exists():
                output_data = json.loads(output_file.read_text())
            else:
                output_data = {
                    "success": False,
                    "result": None,
                    "stdout": stdout.decode() if stdout else "",
                    "stderr": stderr.decode() if stderr else "",
                    "error": "No output produced",
                    "error_type": "ExecutionError",
                    "traceback": None,
                }

            execution_time_ms = int(
                (datetime.utcnow() - start_time).total_seconds() * 1000
            )

            return ExecutionResult(
                success=output_data.get("success", False),
                result=output_data.get("result"),
                stdout=output_data.get("stdout", ""),
                stderr=output_data.get("stderr", ""),
                error=output_data.get("error"),
                error_type=output_data.get("error_type"),
                traceback=output_data.get("traceback"),
                execution_time_ms=execution_time_ms,
                execution_id=exec_id,
            )

        finally:
            # Cleanup execution directory
            shutil.rmtree(exec_dir, ignore_errors=True)

    async def validate_code(self, code: str) -> None:
        """Validate user code before execution."""
        # Check code size
        if len(code) > 1024 * 1024:  # 1MB limit
            raise ValidationError("Code exceeds maximum size (1MB)")

        # Check for obviously malicious patterns
        # (Defense-in-depth; seccomp is the real protection)
        dangerous_patterns = [
            "os.system(",
            "subprocess.",
            "ctypes.",
            "__import__('os')",
            "eval(input",
            "exec(input",
        ]

        for pattern in dangerous_patterns:
            if pattern in code:
                raise ValidationError(
                    f"Potentially dangerous code pattern detected: {pattern}"
                )


# Singleton instance
sandbox_backend = SandboxBackend()
```

### API Endpoint

```python
# src/mcpworks_api/routers/sandbox.py
"""
API endpoint for Code Execution Sandbox.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from typing import Any, Dict, Optional

from ..auth import get_current_account
from ..backends.sandbox import sandbox_backend, ExecutionRequest
from ..models import Account
from ..rate_limiting import check_rate_limit


router = APIRouter(prefix="/v1/sandbox", tags=["sandbox"])


class ExecuteCodeRequest(BaseModel):
    """Request to execute code."""
    code: str = Field(..., description="Python code to execute")
    input_data: Dict[str, Any] = Field(
        default_factory=dict,
        description="Input data available as 'input_data' variable"
    )


class ExecuteCodeResponse(BaseModel):
    """Response from code execution."""
    success: bool
    result: Optional[Any]
    stdout: str
    stderr: str
    error: Optional[str]
    error_type: Optional[str]
    execution_time_ms: int
    execution_id: str


@router.post("/execute", response_model=ExecuteCodeResponse)
async def execute_code(
    request: ExecuteCodeRequest,
    account: Account = Depends(get_current_account),
):
    """
    Execute Python code in a secure sandbox.

    The sandbox provides:
    - Process isolation (PID namespace)
    - Network isolation (egress proxy only)
    - Filesystem isolation (read-only root)
    - Resource limits (CPU, memory, time)

    Available in sandbox:
    - `input_data`: Dict with input parameters
    - `mcpworks.workflows`: Access to user workflows
    - `mcpworks.services`: Access to services
    - `mcpworks.http`: HTTP client (allowlisted hosts only)
    - Pre-installed packages: requests, httpx, pandas, numpy, pyyaml

    Set `result` variable to return data from execution.
    """
    # Rate limiting
    await check_rate_limit(account, "sandbox_execute")

    # Validate code
    try:
        await sandbox_backend.validate_code(request.code)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

    # Execute in sandbox
    execution_request = ExecutionRequest(
        code=request.code,
        input_data=request.input_data,
        account=account,
    )

    result = await sandbox_backend.execute(execution_request)

    return ExecuteCodeResponse(
        success=result.success,
        result=result.result,
        stdout=result.stdout,
        stderr=result.stderr,
        error=result.error,
        error_type=result.error_type,
        execution_time_ms=result.execution_time_ms,
        execution_id=result.execution_id,
    )
```

---

## 8. Resource Limits by Tier

### Complete Tier Comparison

| Resource | Free | Founder | Founder Pro | Enterprise |
|----------|------|---------|-------------|------------|
| **Execution time (wall)** | 10s | 30s | 60s | 300s |
| **CPU time** | 5s | 15s | 30s | 120s |
| **Memory** | 128MB | 256MB | 512MB | 2GB |
| **Max PIDs** | 16 | 32 | 64 | 128 |
| **Max file size** | 10MB | 10MB | 10MB | 10MB |
| **Max open files** | 64 | 64 | 64 | 128 |
| **Network hosts** | None | 5 | 25 | Unlimited |
| **Concurrent executions** | 1 | 3 | 10 | 50 |
| **Executions/month** | 100 | 1,000 | 10,000 | Unlimited |

### Aggregate Host Limits

To prevent resource exhaustion at the host level, aggregate cgroups limit total resources across all sandboxes:

```bash
# /sys/fs/cgroup/mcpworks/
# Parent cgroup for all sandbox executions

# Total memory for all sandboxes (4GB)
echo "4294967296" > /sys/fs/cgroup/mcpworks/memory.max

# Total PIDs (200 processes)
echo "200" > /sys/fs/cgroup/mcpworks/pids.max

# Total CPU (200% = 2 cores equivalent)
echo "200000 100000" > /sys/fs/cgroup/mcpworks/cpu.max

# Enable controllers
echo "+memory +cpu +pids" > /sys/fs/cgroup/mcpworks/cgroup.subtree_control
```

---

## 9. Security Threat Model

### Threats and Mitigations

| Threat | Attack Vector | Mitigation | Confidence |
|--------|---------------|------------|------------|
| **Process escape** | Kill host processes | PID namespace (sandbox is PID 1) | High |
| **Filesystem access** | Read /etc/shadow, credentials | Mount namespace (read-only, minimal mounts) | High |
| **Network exfiltration** | Send data to attacker | Network namespace + egress proxy allowlist | High |
| **Privilege escalation** | setuid, capabilities | User namespace (nobody, no capabilities) | High |
| **Resource exhaustion** | Fork bomb, memory bomb | cgroups v2 (CPU, memory, PIDs) | High |
| **Kernel exploits** | Dangerous syscalls | seccomp allowlist (200 syscalls blocked) | High |
| **Container escape (CVE-2015-1335)** | open_by_handle_at | Blocked by seccomp | High |
| **Metadata service** | 169.254.169.254 access | Egress proxy blocks metadata IPs | High |
| **DNS exfiltration** | Encode data in DNS queries | DNS through host resolver only | Medium |
| **Timing attacks** | Covert channels | Isolated execution, no shared resources | Medium |
| **Spectre/Meltdown** | CPU side channels | Kernel mitigations (host responsibility) | Medium |

### Defense-in-Depth Layers

```
Layer 1: API Gateway
├── Authentication (API key validation)
├── Rate limiting (per-tier)
└── Input validation (code size, patterns)

Layer 2: Process Isolation
├── PID namespace (isolated process tree)
├── User namespace (unprivileged user)
├── IPC namespace (isolated IPC)
└── UTS namespace (isolated hostname)

Layer 3: Filesystem Isolation
├── Mount namespace (isolated mounts)
├── Read-only root filesystem
├── tmpfs for writable areas
└── No access to host paths

Layer 4: Network Isolation
├── Network namespace (isolated network)
├── Egress proxy (allowlist enforcement)
├── No direct internet access
└── Blocked metadata services

Layer 5: Resource Limits
├── cgroups v2 memory limits
├── cgroups v2 CPU limits
├── cgroups v2 PID limits
└── Aggregate host limits

Layer 6: Syscall Filtering
├── seccomp-bpf allowlist
├── 200+ dangerous syscalls blocked
└── Default deny for new syscalls

Layer 7: Monitoring
├── Execution logging
├── Security event alerts
├── Anomaly detection
└── Audit trail
```

### Blast Radius Analysis

| Component Compromised | Impact | Recovery Time |
|-----------------------|--------|---------------|
| Single sandbox | One user's current request | Immediate (sandbox destroyed) |
| Egress proxy | Network allowlist bypassed | 5-10 minutes (restart proxy) |
| Gateway process | All active requests | 1-5 minutes (auto-restart) |
| Host machine | All users, all data | 30-60 minutes (restore from backup) |
| Database credentials | CRITICAL | Days (rotate all credentials) |

**Critical Mitigation:** Database credentials NEVER exist on the execution host. The Gateway handles auth; the sandbox is isolated from persistent data stores.

---

## 10. Monitoring and Observability

### Metrics to Collect

| Metric | Type | Alert Threshold |
|--------|------|-----------------|
| `sandbox_execution_total` | Counter | - |
| `sandbox_execution_duration_ms` | Histogram | p99 > 10s |
| `sandbox_execution_success_rate` | Gauge | < 95% |
| `sandbox_memory_usage_bytes` | Gauge | > 80% of limit |
| `sandbox_cpu_usage_percent` | Gauge | > 90% sustained |
| `sandbox_concurrent_executions` | Gauge | > 80% of capacity |
| `sandbox_spawn_time_ms` | Histogram | p99 > 500ms |
| `egress_requests_total` | Counter | - |
| `egress_requests_blocked` | Counter | > 100/min |
| `seccomp_violations_total` | Counter | > 0 (alert immediately) |

### Logging

```python
# Execution log format
{
    "timestamp": "2026-02-09T12:00:00.000Z",
    "execution_id": "exec-abc123",
    "account_id": "acct-xyz789",
    "tier": "founder",
    "action": "execute_complete",
    "success": true,
    "duration_ms": 1234,
    "memory_peak_mb": 45,
    "stdout_size": 256,
    "stderr_size": 0,
    "network_requests": 2,
    "exit_code": 0
}

# Security event log format
{
    "timestamp": "2026-02-09T12:00:00.000Z",
    "execution_id": "exec-abc123",
    "event_type": "seccomp_violation",
    "syscall": "ptrace",
    "action": "killed",
    "severity": "high"
}
```

### Alerting Rules

```yaml
# alerts/sandbox.yml

groups:
  - name: sandbox_alerts
    rules:
      - alert: SandboxSeccompViolation
        expr: increase(seccomp_violations_total[5m]) > 0
        for: 0m
        labels:
          severity: critical
        annotations:
          summary: "Seccomp violation detected"
          description: "A sandbox attempted a blocked syscall. Investigate immediately."

      - alert: SandboxHighFailureRate
        expr: sandbox_execution_success_rate < 0.95
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Sandbox failure rate above 5%"

      - alert: SandboxSlowSpawn
        expr: histogram_quantile(0.99, sandbox_spawn_time_ms) > 500
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Sandbox spawn time p99 > 500ms"

      - alert: EgressBlockedSpike
        expr: increase(egress_requests_blocked[5m]) > 100
        for: 0m
        labels:
          severity: info
        annotations:
          summary: "High rate of blocked egress requests"
```

---

## 11. Implementation Checklist

### Phase 1: Basic Sandbox (Week 1-2)

- [ ] Install nsjail on development machine
  - [ ] Build from source (latest)
  - [ ] Verify kernel support for namespaces, cgroups v2
- [ ] Create /etc/mcpworks/sandbox.cfg
  - [ ] All namespace flags
  - [ ] Resource limits
  - [ ] Filesystem mounts
- [ ] Create /etc/mcpworks/seccomp-allowlist.policy
  - [ ] Allowlist (not blocklist)
  - [ ] Test with Python stdlib
- [ ] Create /opt/mcpworks/rootfs/
  - [ ] dev-static/ with device nodes
  - [ ] passwd, group, hosts, resolv.conf
- [ ] Create execution wrapper (/opt/mcpworks/bin/execute.py)
  - [ ] Input/output handling
  - [ ] Error capture
  - [ ] Timeout handling
- [ ] Test basic Python execution
  - [ ] Hello world
  - [ ] File I/O in /sandbox
  - [ ] Import standard library
- [ ] Measure execution overhead
  - [ ] Target: < 100ms spawn time

### Phase 2: SDK Integration (Week 2-3)

- [ ] Create MCPWorks SDK package
  - [ ] /opt/mcpworks/sandbox-root/site-packages/mcpworks/
  - [ ] Workflows namespace
  - [ ] Services namespace
  - [ ] HTTP client
- [ ] Set up internal gateway routing
  - [ ] gateway.mcpworks.internal:9999
  - [ ] Token-based auth for sandbox calls
- [ ] Install pre-installed packages
  - [ ] requests, httpx
  - [ ] pandas, numpy
  - [ ] pyyaml
- [ ] Test SDK calls from sandbox
  - [ ] Workflow invocation
  - [ ] Service invocation
  - [ ] Error handling

### Phase 3: Egress Proxy (Week 3-4)

- [ ] Set up mitmproxy with allowlist addon
  - [ ] Per-tier allowlist enforcement
  - [ ] Logging all requests
  - [ ] Blocking metadata services
- [ ] Create network setup script
  - [ ] veth pair creation
  - [ ] iptables rules
  - [ ] Per-execution cleanup
- [ ] Test network isolation
  - [ ] Verify no direct internet access
  - [ ] Verify egress proxy routing
  - [ ] Test allowlist enforcement
- [ ] Implement user allowlist API
  - [ ] Add/remove hosts
  - [ ] Tier-based limits

### Phase 4: Gateway Integration (Week 4)

- [ ] Implement SandboxBackend class
  - [ ] Execution request handling
  - [ ] Tier-based limits
  - [ ] Result parsing
- [ ] Create /v1/sandbox/execute endpoint
  - [ ] Authentication
  - [ ] Rate limiting
  - [ ] Input validation
- [ ] Test end-to-end execution
  - [ ] From API request to result
  - [ ] Error handling
  - [ ] Timeout handling

### Phase 5: Production Hardening (Week 5)

- [ ] Security audit
  - [ ] Seccomp policy review
  - [ ] Escape attempt testing
  - [ ] Penetration testing
- [ ] Resource limit tuning
  - [ ] Based on real usage
  - [ ] Aggregate limits
- [ ] Monitoring setup
  - [ ] Metrics collection
  - [ ] Alerting rules
  - [ ] Dashboard
- [ ] Documentation
  - [ ] User guide
  - [ ] Security model
  - [ ] Troubleshooting

---

## Appendix A: Security Testing

### Escape Attempt Tests

Run these tests to verify sandbox isolation:

```python
# tests/security/test_sandbox_escape.py
"""
Security tests for sandbox isolation.
These tests attempt various escape vectors and should all fail safely.
"""

import pytest

ESCAPE_ATTEMPTS = [
    # Process escape
    ("import os; os.kill(1, 9)", "kill init"),
    ("import os; os.system('whoami')", "os.system"),
    ("import subprocess; subprocess.run(['ls', '/'])", "subprocess"),

    # Filesystem escape
    ("open('/etc/shadow').read()", "read shadow"),
    ("open('/etc/passwd', 'w').write('x')", "write passwd"),
    ("import os; os.listdir('/home')", "list home"),

    # Network escape
    ("import socket; s=socket.socket(); s.connect(('8.8.8.8', 53))", "direct socket"),
    ("import urllib.request; urllib.request.urlopen('http://169.254.169.254/')", "metadata"),

    # Privilege escalation
    ("import os; os.setuid(0)", "setuid root"),
    ("import ctypes; ctypes.CDLL(None)", "ctypes"),

    # Kernel manipulation
    ("import os; os.execve('/bin/sh', [], {})", "execve shell"),
]

@pytest.mark.parametrize("code,description", ESCAPE_ATTEMPTS)
def test_escape_blocked(sandbox, code, description):
    """Verify that escape attempts are blocked."""
    result = sandbox.execute(code)

    # Should fail with security error, not succeed
    assert not result.success or "denied" in result.stderr.lower() or \
           "error" in result.error_type.lower(), \
           f"Escape attempt '{description}' should have failed but succeeded"
```

---

## Appendix B: Performance Benchmarks

### Target Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Sandbox spawn time | < 100ms | Time from request to first instruction |
| Hello world execution | < 200ms | Total time for `print("hello")` |
| SDK call overhead | < 50ms | Time for mcpworks.workflows.list() |
| Memory overhead | < 10MB | Memory used by sandbox infrastructure |
| Concurrent capacity | 100 sandboxes | On 4 vCPU, 8GB RAM droplet |

### Benchmark Script

```python
#!/usr/bin/env python3
# benchmarks/sandbox_perf.py
"""Sandbox performance benchmarks."""

import time
import statistics
from sandbox import SandboxBackend

def benchmark_spawn_time(n=100):
    """Measure sandbox spawn time."""
    backend = SandboxBackend()
    times = []

    for i in range(n):
        start = time.perf_counter()
        result = backend.execute("pass")  # Minimal code
        elapsed = (time.perf_counter() - start) * 1000
        times.append(elapsed)

    print(f"Spawn time (n={n}):")
    print(f"  Mean:   {statistics.mean(times):.1f}ms")
    print(f"  Median: {statistics.median(times):.1f}ms")
    print(f"  p95:    {statistics.quantiles(times, n=20)[18]:.1f}ms")
    print(f"  p99:    {statistics.quantiles(times, n=100)[98]:.1f}ms")

if __name__ == "__main__":
    benchmark_spawn_time()
```

---

## Changelog

**v1.0.0 (2026-02-09):**
- Initial specification
- Complete nsjail configuration with all isolation layers
- Seccomp allowlist policy (not blocklist) with rationale
- Egress proxy architecture with per-tier allowlist
- Execution wrapper with SDK injection
- Sandbox root filesystem structure
- Gateway integration with SandboxBackend
- Complete threat model and security analysis
- Monitoring and observability requirements
- Implementation checklist
