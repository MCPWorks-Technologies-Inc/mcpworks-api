# Research: OSS Release Hardening

**Date**: 2026-03-23
**Branch**: `006-oss-release-hardening`

## R1: Internal Documents to Remove

**Decision**: Add 8 files to `.gitignore` and `git rm --cached` to untrack without deleting locally.

**Files:**
| File | Size | Reason |
|------|------|--------|
| `ORDERS.md` | 18KB | Board meeting refs, internal governance |
| `BILLING-PLAN.md` | 13KB | Stripe config, pricing strategy, migration plans |
| `PROBLEMS.md` | 39KB | Beta tester names/emails, support tickets |
| `SUPPORT-REPORT-2026-03-11.md` | 6KB | User PII, internal triage |
| `SUPPORT-REPORT-2026-03-12.md` | 9KB | User PII, internal triage |
| `SECURITY_AUDIT.md` | 88KB | Specific vulnerability disclosures |
| `MCP_SECURITY_AUDIT.md` | 70KB | Specific vulnerability disclosures |
| `PRODUCT-SPEC.md` | 32KB | SAFE tranche refs, personal email, funding status |

**Rationale**: These contain PII, vulnerability details, or internal strategy that would be harmful or embarrassing if public. Files are preserved locally and can be moved to mcpworks-internals.

## R2: CLAUDE.md → .claude/CLAUDE.md + AGENTS.md

**Decision**: Move CLAUDE.md unchanged to `.claude/CLAUDE.md` (gitignored). Create `AGENTS.md` at root with LLM-agnostic content.

**AGENTS.md content** (extracted from CLAUDE.md):
- Project overview (what mcpworks-api is)
- Technology stack
- Code style conventions (formatting, linting, type hints)
- Testing commands and conventions
- Git workflow (branching, commit messages)
- Project structure overview
- Common mistakes to avoid (token efficiency, provider abstraction)

**Excluded from AGENTS.md** (stays only in .claude/CLAUDE.md):
- Production infrastructure details (IPs, SSH, server specs)
- Deployment procedures (manual rsync, CI/CD secrets)
- Admin email addresses
- Internal strategic context
- Managed service connection details

## R3: Production IP Scrubbing

**Decision**: Replace `159.203.30.199` with `${PROD_IP:-<your-server-ip>}` in scripts, remove from docs.

**Files to scrub:**
- `infra/prod/deploy-exporters.sh` line 4 — `PROD_IP="${1:-159.203.30.199}"`
- `scripts/backup-db-local.sh` line 17 — `REMOTE_HOST="root@159.203.30.199"`
- `infra/scripts/migrate-secrets.sh` line 5 — `PROD_IP="${2:-159.203.30.199}"`

**Rationale**: Hardcoded IPs let attackers target infrastructure immediately upon repo going public.

## R4: Personal Email Scrubbing

**Decision**: Replace `simon.carr@mcpworks.io` with role-based addresses.

**Mapping:**
- Config `admin_emails` default → `["admin@mcpworks.io"]`
- Privacy policy Privacy Officer → `privacy@mcpworks.io`
- Security contact → `security@mcpworks.io`
- Support contact → `support@mcpworks.io`

## R5: Docker Compose JWT Keys

**Decision**: Remove hardcoded keys from `docker-compose.yml`, use file mount pattern matching prod/self-hosted compose files.

**Current** (lines 48-49): PEM keys embedded as environment variables
**Target**: Mount from `./keys/` directory with `JWT_PRIVATE_KEY_PATH` and `JWT_PUBLIC_KEY_PATH`

## R6: Community Files

**Decision**: Create standard OSS community files.

| File | Source/Template |
|------|----------------|
| `CONTRIBUTING.md` | Custom — extract dev workflow from CLAUDE.md |
| `CODE_OF_CONDUCT.md` | Contributor Covenant v2.1 (standard text) |
| `SECURITY.md` | Custom — security@mcpworks.io, 72h response target |
| `.github/ISSUE_TEMPLATE/bug_report.yml` | GitHub YAML template format |
| `.github/ISSUE_TEMPLATE/feature_request.yml` | GitHub YAML template format |

## R7: Credential Rotation Checklist

**Decision**: Create and execute a credential rotation checklist as part of implementation.

**Credentials to rotate:**
1. PostgreSQL password (DO Managed Database)
2. Redis/Valkey password (DO Managed Valkey)
3. JWT signing keys (ES256 keypair)
4. SECRET_KEY (application secret)
5. Google OAuth client secret
6. GitHub OAuth client secret
7. Resend API key
8. Discord webhook URL
9. ADMIN_API_KEY

**Process**: Regenerate each credential, update prod `.env`, restart services, verify health.
