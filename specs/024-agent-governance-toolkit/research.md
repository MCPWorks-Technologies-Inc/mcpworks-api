# Research: Agent Governance Toolkit Integration

**Date**: 2026-04-08
**Branch**: `024-agent-governance-toolkit`

## R1: Agent OS SDK API (Policy Engine)

**Decision**: Use `agent-os-kernel` package with `StatelessKernel` for per-request policy evaluation.

**API Surface**:
```python
from agent_os import StatelessKernel, ExecutionContext

kernel = StatelessKernel()
ctx = ExecutionContext(agent_id="agent-001", policies=["policy_name"])
result = await kernel.execute(action="tool_call", params={...}, context=ctx)
```

Policy loading supports YAML inline:
```python
kernel.load_policy_yaml("""
version: "1.0"
name: custom-policy
rules:
  - name: block-dangerous
    condition: "action == 'database_query'"
    action: deny
    pattern: "DROP|TRUNCATE"
""")
```

Cedar and Rego are also supported via the `[full]` extra which pulls in `cedarpy` and OPA CLI.

**Rationale**: `StatelessKernel` is the right fit — request-scoped, no persistent state, async-native. `KernelSpace` (full control plane with VFS and signals) is overkill for scanner pipeline integration.

**Alternatives Rejected**:
- `KernelSpace`: Too heavy; manages agent lifecycle, flight recorder, VFS — we already have these
- Direct `cedarpy`/OPA calls: Loses the unified policy abstraction

**Install**: `pip install agent-os-kernel` (base) or `pip install agent-os-kernel[full]` (Cedar + Rego)

## R2: Agent Mesh Trust Scoring

**Decision**: Implement trust scoring natively in MCPWorks rather than importing Agent Mesh's trust system.

**Rationale**: Agent Mesh's trust scoring is designed for inter-agent mesh communication with DID identity and peer verification (`verify_peer(did:mesh:agent-b, min_trust=700)`). MCPWorks has a simpler model: platform → agent trust, not agent ↔ agent trust. The score arithmetic is straightforward (delta on events, cap at bounds) and doesn't warrant an external dependency.

We adopt Agent Mesh's **0-1000 scale** and **behavioral tier concept** for compatibility, but implement the scoring logic in ~50 lines of Python rather than pulling in the full mesh package.

**Trust Score Deltas** (from Agent Mesh docs, adapted):
- Security event (prompt injection): -50
- Security event (secret leak): -100
- Security event (other): -25
- Successful execution: +1 (capped at 500)

**Alternatives Rejected**:
- Full Agent Mesh integration: Requires DID identity, IATP protocol, registry — massive scope creep
- No trust scoring: Spec requires it (REQ-AGT-020 through REQ-AGT-024)

## R3: Agent Compliance SDK

**Decision**: Use `agent-compliance` `GovernanceVerifier` for attestation generation, with a custom config-to-controls mapper.

**API Surface**:
```python
from agent_compliance.verify import GovernanceVerifier

verifier = GovernanceVerifier()
attestation = verifier.verify()
attestation.compliance_grade()   # "A", "B", "C", "D", "F"
attestation.coverage_pct()       # 0-100
attestation.badge_markdown()     # "![badge](url)"
```

**OWASP Agentic Top 10 Mapping** (MCPWorks controls → OWASP risks):

| OWASP Risk | MCPWorks Control | Detection Method |
|------------|-----------------|------------------|
| 1. Goal Hijack | scanner_pipeline (pattern_scanner) | Check pipeline has input scanner |
| 2. Tool Misuse | agent_access rules | Check function_rules exist |
| 3. Identity Abuse | API key auth + namespace isolation | Check auth config |
| 4. Supply Chain | pip audit + locked dependencies | Check sandbox config |
| 5. Code Execution | nsjail sandbox (seccomp allowlist) | Check sandbox tier |
| 6. Memory Poisoning | output_trust + trust_boundary_scanner | Check output trust setting |
| 7. Inter-Agent Comms | namespace isolation | Check agent isolation |
| 8. Cascading Failures | rate limiting + execution limits | Check rate limit config |
| 9. Trust Exploitation | agent access rules + approval workflows | Check access rules |
| 10. Rogue Agents | trust scoring + kill switch | Check trust_score enabled |

**Rationale**: The verifier handles the scoring/grading algorithm. We provide the control evidence by mapping namespace config to OWASP risk categories. This avoids reimplementing the compliance grading logic.

**Alternatives Rejected**:
- Pure native implementation: Would need to track OWASP risk definitions ourselves; Microsoft will maintain these
- Full toolkit compliance: Requires Agent Runtime, Agent SRE — out of scope per spec

## R4: Dependency Strategy

**Decision**: All three packages are **optional** extras in `requirements.txt`.

```
# Optional: Agent Governance Toolkit
# agent-os-kernel[full]    # Cedar + Rego policy evaluation
# agent-compliance          # OWASP attestation
```

**Lazy Import Pattern** (matches existing webhook_scanner.py):
```python
if scanner_type == "agent_os":
    try:
        from mcpworks_api.core.scanners.agent_os_scanner import AgentOSScanner
    except ImportError:
        logger.warning("scanner_unavailable", type="agent_os",
                       hint="pip install agent-os-kernel[full]")
        return None
    return AgentOSScanner(config=entry.get("config", {}))
```

**Rationale**: Self-hosted community edition may not want these dependencies. Core MCPWorks must run without them.

## R5: Migration Strategy

**Decision**: Single migration adding two columns to `agents` table.

```sql
ALTER TABLE agents ADD COLUMN trust_score INTEGER NOT NULL DEFAULT 500;
ALTER TABLE agents ADD COLUMN trust_score_updated_at TIMESTAMPTZ;
```

No new tables. Trust score updates use atomic SQL: `UPDATE agents SET trust_score = GREATEST(0, LEAST(1000, trust_score + :delta))`.

**Rationale**: Minimal schema change. No new tables reduces migration risk. Atomic update prevents race conditions per spec edge case 6.4.
