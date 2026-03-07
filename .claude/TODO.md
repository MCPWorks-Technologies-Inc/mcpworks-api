# Internal TODOs

## [DONE] Sandbox: Host Information Obfuscation (FINDING-02)

**Implemented:** 2026-03-07
**Source:** SECURITY_AUDIT.md FINDING-02

Resolved by overlaying fake/empty mounts on sensitive /proc entries:
- `/proc/net` → empty tmpfs (hides network topology)
- `/proc/cpuinfo` → fake "Virtual CPU" (hides provider/hardware)
- `/proc/meminfo` → tier-specific memory limit (hides host RAM)
- `/proc/version` → generic string (hides kernel version)

`/proc/self` preserved for Python runtime. No impact on outbound networking.

**Files changed:** `deploy/nsjail/python.cfg`, `deploy/nsjail/spawn-sandbox.sh`
**Docs:** `infra/prod/SANDBOX-NETWORK-ISOLATION.md`

---

## Remaining: /proc/net and /proc/mounts leakage

**Priority:** Low

- `/proc/net` cannot be overlaid — nsjail `move_mount()` rejects overlays on
  procfs subdirectories (both tmpfs and bind-mount). Mitigated by iptables
  UID-based rules. Full fix requires `clone_newnet: true` + veth pair.
- `/proc/mounts` still shows the full mount table including overlay layer paths
  and volume mounts. Low information value but could reveal directory structure.
  Consider overlaying with a fake mounts file showing only `/sandbox` and `/tmp`.

## Remaining: Full network namespace isolation

**Priority:** Medium (future)

`clone_newnet: true` would eliminate all network-level leakage at the namespace
level (no `/proc/net` even without the tmpfs overlay, no visibility into host
sockets). Requires veth pair or slirp4netns for outbound internet access.
Would be the cleanest long-term solution but more infrastructure work.
