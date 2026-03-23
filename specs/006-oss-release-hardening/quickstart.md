# Quickstart: OSS Release Hardening Verification

**Branch**: `006-oss-release-hardening`

## Verification Procedures

### After Implementation — Run These Checks

**V1: No production IP in tracked files**
```bash
git ls-files | xargs grep -l "159\.203\.30\.199" 2>/dev/null
# Expected: zero results
```

**V2: No personal emails in tracked files**
```bash
git ls-files | xargs grep -l "simon\.carr@" 2>/dev/null
# Expected: zero results
```

**V3: No internal docs tracked**
```bash
for f in ORDERS.md BILLING-PLAN.md PROBLEMS.md SECURITY_AUDIT.md MCP_SECURITY_AUDIT.md PRODUCT-SPEC.md CLAUDE.md "SUPPORT-REPORT-*.md"; do
  git ls-files "$f" 2>/dev/null
done
# Expected: zero results
```

**V4: Community files exist**
```bash
for f in AGENTS.md CONTRIBUTING.md CODE_OF_CONDUCT.md SECURITY.md LICENSE README.md; do
  test -f "$f" && echo "OK: $f" || echo "MISSING: $f"
done
test -f .github/ISSUE_TEMPLATE/bug_report.yml && echo "OK: bug template" || echo "MISSING: bug template"
test -f .github/ISSUE_TEMPLATE/feature_request.yml && echo "OK: feature template" || echo "MISSING: feature template"
```

**V5: No embedded keys in docker-compose.yml**
```bash
grep -c "BEGIN EC" docker-compose.yml
# Expected: 0
```

**V6: No broken internal repo references**
```bash
git ls-files | xargs grep -l "\.\./mcpworks-internals" 2>/dev/null
# Expected: zero results (or only in archive/ files)
```

**V7: Git history clean**
```bash
for f in ORDERS.md BILLING-PLAN.md PROBLEMS.md SECURITY_AUDIT.md MCP_SECURITY_AUDIT.md; do
  git log --all --diff-filter=A -- "$f" | head -1
done
# Review: if any output, those files were committed at some point — verify content was not sensitive
```

**V8: Credential rotation verified**
```bash
ssh root@$PROD_IP "cd /opt/mcpworks && docker compose -f docker-compose.prod.yml exec api python -c \"import httpx; r = httpx.get('http://localhost:8000/v1/health'); print(r.status_code, r.json())\""
# Expected: 200 {"status": "ok", ...}
```

## Implementation Order

1. **Remove internal docs** (FR-001, FR-002) — gitignore + git rm --cached
2. **Move CLAUDE.md** (FR-003) — mv + gitignore + create AGENTS.md
3. **Scrub IPs** (FR-005) — 3 scripts
4. **Scrub emails** (FR-006) — config defaults + legal docs
5. **Fix docker-compose keys** (FR-007) — remove embedded keys
6. **Fix discord localhost** (FR-008) — url_builder call
7. **Create community files** (FR-011 to FR-015) — 5 new files + README expansion
8. **Add docstrings** (FR-016) — 15 functions
9. **Remove dead code** (FR-017) — metrics.py
10. **Scrub internal refs** (FR-018, FR-019) — grep + remove
11. **Verify** — run V1-V7 checks
12. **Credential rotation** (FR-009, FR-010) — operational, done last
