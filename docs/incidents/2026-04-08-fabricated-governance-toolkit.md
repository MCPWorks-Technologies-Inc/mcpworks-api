# Incident Report: Botched Agent Governance Toolkit Integration

**Date:** 2026-04-08
**Severity:** High
**Duration:** ~11 hours (12:44 spec committed -> 23:33 code removed)
**Affected repos:** mcpworks-api, www.mcpworks.io
**Root cause:** LLM hallucination blending real and fabricated API details
**Report revised:** 2026-04-09 (v3 — see "Note on this report" at bottom)

---

## Summary

On 2026-04-08, a Claude Code session was asked to research and integrate
Microsoft's Agent Governance Toolkit into the mcpworks platform. The toolkit
is a real, substantial MIT-licensed Microsoft project
(github.com/microsoft/agent-governance-toolkit, 869 stars, 12 packages). A
450-line spec was written, 2,268 lines were implemented, 29 tests were added,
a blog post was published, and a PR was merged — all in one day.

The integration was then removed after discovering that the code was written
against incorrect API assumptions. The removal commit and subsequent sessions
overstated the problem, claiming the toolkit and its packages "were
hallucinated" and "do not exist." In fact, most of what was described was real.
The actual errors were narrow: one package not published to PyPI
(`agent-compliance`), one wrong attribute name (`result.allowed` vs
`result.success`), and one fabricated method (`load_policy_yaml()`).

This incident is notable not just for the original hallucination, but for how
the overcorrection itself became a second hallucination that persisted through
multiple sessions and even into the first two drafts of this report.

---

## Claim-by-claim verification

Every claim below was verified on 2026-04-09 against primary sources (GitHub
API, PyPI, actual source code). Claims marked "OUR CODE" show what the
integration assumed; "REALITY" shows what actually exists.

### What's real in the toolkit

| Claim | Verified | Source |
|-------|----------|--------|
| `microsoft/agent-governance-toolkit` exists on GitHub | YES | `gh api repos/microsoft/agent-governance-toolkit` — 869 stars, MIT, created 2026-03-02 |
| Monorepo contains 12 packages | YES | `gh api .../contents/packages` — agent-os, agent-mesh, agent-compliance, agent-runtime, agent-sre, agent-lightning, agent-marketplace, agent-hypervisor, agent-mcp-governance, agent-os-vscode, agent-governance-dotnet, agentmesh-integrations |
| `agent-os-kernel` on PyPI | YES | `pip index versions agent-os-kernel` — versions 2.0.0 through 3.0.2 |
| `agent-governance-toolkit` on PyPI | YES | `pip index versions agent-governance-toolkit` — versions 2.1.0 through 3.0.2 |
| `StatelessKernel` class exists | YES | `packages/agent-os/src/agent_os/stateless.py:373` |
| `ExecutionContext` dataclass exists | YES | `packages/agent-os/src/agent_os/stateless.py:284` — fields: `agent_id`, `policies`, `history`, `state_ref`, `metadata` |
| `ExecutionResult` dataclass exists | YES | `packages/agent-os/src/agent_os/stateless.py:341` — fields: `success`, `data`, `error`, `signal`, `updated_context`, `metadata` |
| `execute(action, params, context)` method | YES | `packages/agent-os/src/agent_os/stateless.py:426` — exact signature matches our code |
| Cedar policy support | YES | `packages/agent-os/src/agent_os/policies/backends.py` — `CedarBackend` class |
| OPA/Rego policy support | YES | `packages/agent-os/src/agent_os/policies/backends.py` — `OPABackend` class |
| YAML policy support | YES | Native `PolicyDocument` engine alongside external backends |
| `GovernanceVerifier` class exists | YES | `packages/agent-compliance/src/agent_compliance/verify.py:252` |
| `GovernanceVerifier.verify()` method | YES | Returns `GovernanceAttestation` with OWASP controls |
| `GovernanceAttestation.compliance_grade()` | YES | `verify.py:159` — returns letter grade |
| `agent-compliance` source in monorepo | YES | Full package at `packages/agent-compliance/` |
| MIT license | YES | `gh api` confirms `spdx_id: "MIT"` |

### What was actually wrong in our code

| Our code | Reality | Severity |
|----------|---------|----------|
| `pip install agent-compliance` | Not published to PyPI as standalone package. Source exists in monorepo but isn't a separate PyPI distribution. | Medium — would fail at install time |
| `result.allowed` | Real field is `result.success` (bool). Same semantics, wrong name. | Low — trivial fix |
| `kernel.load_policy_yaml(self._policy)` | This method does not exist on `StatelessKernel`. Policy loading uses `OPABackend`/`CedarBackend` classes added to a policy evaluator, not a kernel method. | Medium — wrong API pattern |
| `governance` optional extra in pyproject.toml listing `agent-os-kernel[full]` and `agent-compliance` | `agent-os-kernel[full]` is valid; `agent-compliance` is not installable from PyPI | Low — half correct |

### What the removal commit got wrong

The commit `abe085a` stated:

> "The 'Microsoft Agent Governance Toolkit' monorepo, blog post, and
> agent-compliance package were hallucinated by web search."

This is incorrect. The monorepo is real (869 stars, MIT, 12 packages). The
`agent-compliance` package exists as source in the monorepo — it's just not
published to PyPI as a standalone package. The blog post contained real
information mixed with unverified claims.

---

## Timeline

All times PDT (UTC-7).

### Phase 1: Spec (12:44)

| Time | Commit | Repo | Event |
|------|--------|------|-------|
| 12:44 | `de3f1cb` | mcpworks-api | **Spec committed.** 450-line specification for "Microsoft Agent Governance Toolkit integration (#62)." Describes Agent OS, Agent Compliance, Agent Mesh. Most high-level claims are accurate; specific API details contain errors. |

### Phase 2: Parallel legitimate work (13:05 - 14:08)

| Time | Commit | Event |
|------|--------|-------|
| 13:05 | `b543847` | Analytics token savings spec (#53) |
| 13:16 | `e47a9c6` | Analytics token savings implementation |
| 13:42 | `513ea25` | Analytics token savings PR merged (#63) |
| 13:50 | `ef8628f` | Telemetry webhook spec (#46) |
| 14:02 | `82c196c` | Telemetry webhook implementation |
| 14:08 | `db7af86` | Telemetry webhook PR merged (#64) |

These features are real and remain in the codebase.

### Phase 3: Implementation (15:48 - 15:49)

| Time | Commit | Event |
|------|--------|-------|
| 15:48 | `f735ad8` | **Implementation committed.** 27 files changed, +2,268 lines. The `agent_os_scanner.py` called real classes (`StatelessKernel`, `ExecutionContext`) with mostly-correct signatures, but used a non-existent method (`load_policy_yaml`) and wrong attribute (`result.allowed` vs `result.success`). |
| 15:49 | `b2db7dc` | **PR merged (#65).** Same diff, merge commit to main. |

### Phase 4: Discovery and overcorrection (23:21 - 23:33)

| Time | Commit | Repo | Event |
|------|--------|------|-------|
| 23:21 | `a7819f9` | www.mcpworks.io | **Blog post published.** Announced governance toolkit integration. |
| 23:25 | `b8e50f2` | www.mcpworks.io | **First correction.** Removed false claims about enterprise demand. |
| 23:27 | `deeebfa` | www.mcpworks.io | **Blog post deleted.** Commit message: "agent-compliance doesn't exist on PyPI, and agent-os-kernel 3.x has a different API than what our code assumes." |
| 23:33 | `abe085a` | mcpworks-api | **Code removed with incorrect framing.** Commit message claims toolkit "was hallucinated by web search." Actually: toolkit is real, but specific API calls were wrong. Deleted `agent_os_scanner.py`, its tests, pipeline case, and optional deps. Kept native features. |

### Phase 5: Overcorrection propagates (2026-04-09)

During a codebase reality audit, the LLM sessions inherited the "hallucinated"
framing from the removal commit and continued to describe the toolkit as
fabricated:

- Audit report v1 stated `StatelessKernel` was "hallucinated" (it's real)
- Audit report v1 stated `GovernanceVerifier` "does not exist" (it exists)
- Audit report v1 stated the toolkit "does not exist" (it has 869 stars)
- Spec artifacts were deleted based on the assumption everything was fabricated
- Implementation spec was rewritten describing features as "native" rather
  than acknowledging the real upstream toolkit they were inspired by

The user caught the error by pointing to the real GitHub repo.

### Phase 6: Cleanup (2026-04-09)

| Action | Accurate? |
|--------|-----------|
| `specs/024-agent-governance-toolkit/` directory deleted | Overbroad — specs contained mostly accurate high-level descriptions mixed with some wrong API details |
| Implementation spec rewritten | Overcorrected — removed all toolkit references instead of correcting the specific wrong claims |
| CLAUDE.md reference updated | Fine |

---

## What was kept (native, no external deps)

| Feature | Files | Status |
|---------|-------|--------|
| Trust scoring (0-1000, degrade/recover) | `services/trust_score.py`, `models/agent.py`, migration | Native implementation, works correctly |
| Trust-gated access control | `core/agent_access.py`, `mcp/tool_registry.py` | Native, extends existing access system |
| OWASP compliance endpoint | `api/v1/compliance.py`, `services/compliance.py` | Native evaluation logic |
| 24 unit tests (trust, compliance, access) | `tests/unit/test_trust_score.py`, etc. | All passing |

---

## Impact

- **Code merged to main:** ~200 lines of scanner code with wrong API calls
  reached production. The scanner was lazy-imported and would only activate if
  a namespace explicitly configured `type: agent_os`, which none had.
- **Blog post published and retracted:** ~6 minutes of public visibility.
- **Overcorrection:** Removal commit and subsequent sessions propagated a
  false narrative that the toolkit doesn't exist, leading to deletion of spec
  artifacts and documentation that were mostly accurate.
- **Production impact:** None. The scanner was never invoked.
- **Trust impact:** High. Required a full codebase audit, and the audit itself
  initially repeated incorrect claims.

---

## Root cause analysis

### Primary: LLM filled in API details it didn't actually know

The toolkit is real. The high-level description (policy engine, compliance,
trust scoring, Cedar/Rego support) is accurate. The LLM correctly identified
the project and its purpose, but then fabricated specific implementation
details: a method name that doesn't exist (`load_policy_yaml`), an attribute
name that's close but wrong (`allowed` vs `success`), and a PyPI publication
status that's incorrect (`agent-compliance` isn't on PyPI).

### Secondary: Overcorrection compounded the error

When the API mismatches were discovered, the response was to declare the entire
toolkit "hallucinated." This overcorrection was itself a hallucination —
anchored on the discovery of specific errors, the LLM (and the session)
generalized to "everything about this is fake." The removal commit's framing
then became authoritative context for subsequent sessions, which repeated and
amplified it.

### Contributing: No verification step in the workflow

Neither the spec phase nor the implementation phase included `pip install` and
`python -c "import agent_os; help(agent_os.StatelessKernel)"`. A 30-second
check would have caught the wrong method name before 2,268 lines were written.

### Contributing: Mocked tests couldn't catch API mismatches

The 29 unit tests mocked `agent_os` entirely, validating the scanner against
its own assumptions. A single test that imported the real package would have
revealed `load_policy_yaml` doesn't exist and `result.allowed` should be
`result.success`.

---

## Lessons

### 1. Install and import before writing integration code

Before writing code that wraps an external package, `pip install` it and
`help()` the actual classes. 30 seconds of verification prevents 2,268 lines
of rework.

### 2. Never mock the thing you're integrating

At least one test must import the real package. Mocking an external dependency
proves your code works against your assumptions, not reality.

### 3. When you find errors, scope the correction precisely

Finding that `result.allowed` should be `result.success` does not mean the
entire toolkit is fabricated. Overcorrection is itself a form of hallucination
— pattern-matching from "some details are wrong" to "everything is fake."

### 4. Don't trust commit messages as ground truth

The removal commit said "hallucinated by web search." Subsequent sessions
treated this as verified fact. Commit messages reflect the author's
understanding at commit time, which may be wrong.

### 5. Verify before repeating

This report itself went through three drafts because each version repeated
claims from previous sessions without re-verifying them. The rule for memory
applies to incident reports too: a claim from a prior session is not a fact
until you check it against a primary source.

---

## Remediation completed

| Action | Date | Commit | Assessment |
|--------|------|--------|------------|
| Removed scanner code with wrong API calls + tests | 2026-04-08 | `abe085a` | Correct action, incorrect framing in commit message |
| Removed blog post | 2026-04-08 | `deeebfa` | Correct — contained unverified claims |
| Full codebase reality audit | 2026-04-09 | -- | Correct action, audit results reliable (no other issues found) |
| Deleted spec artifacts | 2026-04-09 | pending | Overbroad — specs were mostly accurate |
| Rewrote implementation spec | 2026-04-09 | pending | Overcorrected — removed all toolkit references |
| This report: claim-by-claim verification | 2026-04-09 | pending | v3 — corrected false claims from v1 and v2 |

---

## Audit result

The full codebase audit on 2026-04-09 verified:
- 31 SQLAlchemy models, all with matching Alembic migrations
- 25 router files, all with real endpoint implementations
- 23 service files, all with real business logic and DB queries
- 45 test files (649 passing), all testing real code
- All infrastructure (Dockerfile, CI/CD, docker-compose) consistent
- **No other issues found.** The governance integration was an isolated incident.

---

## Note on this report

This report went through three versions, each correcting errors from the
previous one:

**v1 (2026-04-09, first draft):** Stated the Microsoft Agent Governance
Toolkit "does not exist," `StatelessKernel` was "hallucinated," and
`GovernanceVerifier` was "fabricated." All three claims were wrong. The report
inherited the incorrect framing from the removal commit (`abe085a`) without
verifying any claims against primary sources.

**v2 (2026-04-09, after user correction):** User pointed to the real GitHub
repo. Report was rewritten acknowledging the toolkit exists, but still claimed
`GovernanceVerifier` was fabricated and Cedar/Rego support was hallucinated.
Both claims were wrong — `GovernanceVerifier` exists at
`agent_compliance/verify.py:252` with a real `verify()` method, and Cedar/Rego
support exists via `OPABackend` and `CedarBackend` in
`agent_os/policies/backends.py`.

**v3 (2026-04-09, after full verification):** Every claim verified against
GitHub API and actual source code. The actual errors in the integration were
narrow: one method that doesn't exist (`load_policy_yaml`), one wrong attribute
name (`allowed` vs `success`), one package not on PyPI (`agent-compliance`).
The overcorrection — declaring everything fabricated — was a bigger deviation
from truth than the original errors.

This progression demonstrates compounding hallucination: the original LLM
session got specific API details wrong. The removal session overcorrected to
"everything is fake." The audit session inherited that framing. The report
session repeated it. Each layer of LLM processing amplified the error rather
than correcting it, because each session trusted the previous session's
conclusions as ground truth.

---

## Epilogue: Verification of this report (2026-04-09)

After v2 of this report was written, the user requested that every claim in
the report be substantiated against primary sources. The verification was
performed by the same Claude Code session that wrote v2, using:

- `gh api repos/microsoft/agent-governance-toolkit/...` to read actual source
  files from the upstream repo
- `pip index versions <package>` to check PyPI publication status
- `git show <commit>` to read the deleted integration code and compare it
  against the real API

This verification revealed that v2 still contained false claims inherited from
v1: `GovernanceVerifier` was described as fabricated (it's real, with a working
`verify()` method and `compliance_grade()` on the attestation), and Cedar/Rego
support was described as hallucinated (real `CedarBackend` and `OPABackend`
classes exist in the policies module).

The narrowing across versions:
- **v1:** "The entire toolkit is fabricated" (wrong — toolkit has 869 stars)
- **v2:** "Toolkit is real but GovernanceVerifier and Cedar/Rego are fabricated" (wrong — both exist)
- **v3:** "Toolkit is real, classes are real, the actual errors were: one wrong method name, one wrong attribute name, one package not on PyPI"

Each correction required going to the primary source (actual source code in the
GitHub repo) rather than trusting any prior session's characterization.
