# Feature Specification: OSS Release Hardening

**Feature Branch**: `006-oss-release-hardening`
**Created**: 2026-03-23
**Status**: Draft
**Input**: User description: "Prepare mcpworks-api for public GitHub release — remove internal docs, scrub secrets/IPs, add community files, harden for public scrutiny."

## Clarifications

### Session 2026-03-23

- Q: What to do with CLAUDE.md for public release? → A: Move to `.claude/CLAUDE.md` unchanged and add to `.gitignore`. Create a public `AGENTS.md` at root with LLM-agnostic coding practices and standards extracted from CLAUDE.md.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - No Secrets or Internal Data Exposed (Priority: P1)

A security researcher forks the public repository and searches for credentials, internal IP addresses, personal email addresses, and internal governance documents. They find nothing exploitable — no production IPs, no real credentials, no internal strategy documents, no personal contact information.

**Why this priority**: A single exposed secret or internal document on a public repo can be found within minutes by automated scanners. This is the highest-risk category and must be resolved before any public visibility.

**Independent Test**: Clone the repo, run `grep -r` for known patterns (IP addresses, email addresses, key formats, internal doc names), and verify zero matches in tracked files.

**Acceptance Scenarios**:

1. **Given** the public repository, **When** a user searches for the production server IP address, **Then** zero matches are found in any tracked file (scripts, docs, or source code).
2. **Given** the public repository, **When** a user searches for personal email addresses (e.g., firstname.lastname@domain), **Then** only generic role-based addresses appear (security@, support@, privacy@).
3. **Given** the public repository, **When** a user lists all files, **Then** no internal governance documents are present (no board meeting references, no acquisition strategy, no support tickets, no security audit reports with vulnerability details).
4. **Given** the public repository, **When** a user examines docker-compose files, **Then** no real cryptographic keys are embedded — only references to file mounts or environment variables.
5. **Given** the public repository, **When** a user examines the git history, **Then** no secrets or internal documents were ever committed (clean history).

---

### User Story 2 - Professional Community Presence (Priority: P1)

A developer evaluating MCPWorks lands on the GitHub repository page. They immediately find a compelling README explaining what the project does and why it matters, clear contribution guidelines, a code of conduct, a security reporting policy, and issue templates. The project looks maintained, professional, and welcoming to contributors.

**Why this priority**: First impressions determine adoption. An open-source project without community files signals abandonment or immaturity. This is table stakes for any serious OSS project launch.

**Independent Test**: Visit the repository on GitHub and verify all standard community files render correctly and link to each other.

**Acceptance Scenarios**:

1. **Given** a developer visits the GitHub repo, **When** they read the README, **Then** they understand what MCPWorks is, why it exists, how to get started (self-host or cloud), and how to contribute — within 2 minutes of reading.
2. **Given** a developer wants to contribute, **When** they look for guidelines, **Then** they find a CONTRIBUTING file covering development setup, branching conventions, PR process, and code style expectations.
3. **Given** a developer discovers a security vulnerability, **When** they look for reporting instructions, **Then** they find a SECURITY file with a clear private disclosure process and expected response timeline.
4. **Given** a developer wants to report a bug, **When** they click "New Issue" on GitHub, **Then** they see structured templates for bug reports and feature requests with guided fields.
5. **Given** a developer reads any community document, **When** they look for a code of conduct, **Then** they find one that establishes behavioral expectations for the community.

---

### User Story 3 - Clean Codebase for Public Review (Priority: P2)

A developer browsing the source code finds well-documented public functions, no dead code, no TODO markers that reveal incomplete work, and no broken references to internal repositories. The code reads like a project that's ready for production use and community contribution.

**Why this priority**: Code quality signals trustworthiness. Dead code, missing docstrings, and broken links make the project look unfinished. This is less urgent than security but important for adoption.

**Independent Test**: Run a documentation coverage check on public functions and grep for broken internal references.

**Acceptance Scenarios**:

1. **Given** the public repository, **When** a developer reads any public function in the core modules, **Then** it has a docstring explaining its purpose and parameters.
2. **Given** the public repository, **When** a developer searches for commented-out code blocks, **Then** none are found (dead code has been removed).
3. **Given** the public repository, **When** a developer follows any documentation link, **Then** the link resolves (no broken references to private/internal repositories).

---

### User Story 4 - Credential Rotation Plan (Priority: P1)

Before the repository goes public, all production credentials that were ever present on the development machine (even if never committed) are rotated. This includes database passwords, API keys, OAuth secrets, JWT signing keys, and webhook URLs.

**Why this priority**: Even though credentials were never committed to git, the development machine has had access to them. Going public increases the attack surface — rotating credentials is defense in depth.

**Independent Test**: Verify each credential has been regenerated and the old values no longer work.

**Acceptance Scenarios**:

1. **Given** the decision to go public, **When** the credential rotation checklist is executed, **Then** every production credential (database, cache, JWT, OAuth, email API, webhooks) has been rotated.
2. **Given** rotated credentials, **When** the old credential values are used, **Then** they are rejected (no longer valid).
3. **Given** rotated credentials, **When** the production system restarts with new credentials, **Then** all services pass health checks.

---

### Edge Cases

- What happens if git history contains a file that was later gitignored? The file content persists in history. Verify with `git log --all --diff-filter=A -- <file>` for each sensitive file.
- What happens if a developer's fork preserves internal docs that were removed? Forks are independent — we can only control the upstream repo. Document this risk.
- What happens if CLAUDE.md is removed but Claude Code needs it to work? CLAUDE.md is moved to `.claude/CLAUDE.md` (gitignored) — Claude Code reads from this path natively. Public contributors using any LLM get `AGENTS.md` instead.
- What happens if references to mcpworks-internals are removed but specs still need that context? Remove the file path references but keep the conceptual content inline where needed.

## Requirements *(mandatory)*

### Functional Requirements

**Internal Document Removal (CRITICAL):**
- **FR-001**: The following files MUST be added to `.gitignore` and removed from git tracking: `ORDERS.md`, `BILLING-PLAN.md`, `PROBLEMS.md`, `SUPPORT-REPORT-*.md`, `SECURITY_AUDIT.md`, `MCP_SECURITY_AUDIT.md`.
- **FR-002**: `PRODUCT-SPEC.md` MUST be either removed from tracking or stripped of funding references, personal emails, and internal strategy details.
- **FR-003**: `CLAUDE.md` MUST be moved unchanged to `.claude/CLAUDE.md` and added to `.gitignore`. A new public `AGENTS.md` MUST be created at the repository root containing LLM-agnostic coding practices, standards, and development guidance extracted from CLAUDE.md (no infrastructure details, no IPs, no deployment commands).
- **FR-004**: Git history MUST be verified clean — no sensitive files were ever committed. If any were, the repository history must be rewritten before public release.

**Infrastructure Scrubbing (CRITICAL):**
- **FR-005**: All references to the production server IP address MUST be replaced with environment variable references or placeholders in scripts and documentation.
- **FR-006**: All personal email addresses in configuration defaults and documentation MUST be replaced with generic role-based addresses (security@, support@, privacy@).
- **FR-007**: Development docker-compose MUST NOT contain embedded cryptographic keys — keys MUST be loaded from files or environment variables.
- **FR-008**: The hardcoded localhost URL in the Discord gateway module MUST be replaced with a configurable URL.

**Credential Rotation (CRITICAL):**
- **FR-009**: A credential rotation checklist MUST be created and executed covering: database passwords, cache passwords, JWT signing keys, OAuth client secrets, email API keys, webhook URLs, and application secrets.
- **FR-010**: Production services MUST be verified healthy after credential rotation.

**Community Files (HIGH):**
- **FR-011**: A CONTRIBUTING file MUST exist covering: development environment setup, branching conventions, pull request process, commit message format, and code style expectations.
- **FR-012**: A CODE_OF_CONDUCT file MUST exist (Contributor Covenant v2.1 or equivalent).
- **FR-013**: A SECURITY file MUST exist covering: how to report vulnerabilities privately, expected response timeline, and disclosure policy.
- **FR-014**: Issue templates MUST exist for bug reports and feature requests with structured fields.
- **FR-015**: README MUST be expanded to serve as a compelling project landing page: what MCPWorks is, key features, architecture overview, quick start for both self-hosted and cloud, badges (license, CI, version), and links to documentation.

**Code Cleanup (HIGH):**
- **FR-016**: All public functions in core utility modules MUST have docstrings.
- **FR-017**: Commented-out code blocks MUST be removed from production source files.
- **FR-018**: All references to internal repository paths (e.g., `../mcpworks-internals/`) MUST be removed or replaced with public-facing alternatives.

**Broken Link Cleanup (MEDIUM):**
- **FR-019**: All documentation links that reference private repositories or non-existent paths MUST be removed or updated.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Zero matches when searching tracked files for the production server IP address pattern.
- **SC-002**: Zero personal email addresses in any tracked file — only generic role-based addresses remain.
- **SC-003**: Zero internal governance documents (board meetings, support tickets, security audit details) present in tracked files.
- **SC-004**: All 5 community files present and rendering correctly on GitHub (README, CONTRIBUTING, CODE_OF_CONDUCT, SECURITY, issue templates).
- **SC-005**: 100% of public functions in core utility modules have docstrings.
- **SC-006**: Zero commented-out code blocks in production source files.
- **SC-007**: Zero broken links to private/internal repositories in documentation.
- **SC-008**: All production credentials rotated and verified working before public release.
- **SC-009**: A first-time visitor to the GitHub page can understand what the project does within 2 minutes of reading the README.

## Assumptions

- Internal documents (ORDERS.md, etc.) will be preserved locally or moved to the private `mcpworks-internals` repo — they are not being deleted, just removed from the public repo.
- CLAUDE.md is moved unchanged to `.claude/CLAUDE.md` (gitignored, private to developers using Claude Code). A public LLM-agnostic `AGENTS.md` replaces it at root with coding standards only.
- Git history is believed to be clean (verified in the audit), but a final verification pass is required before going public.
- Credential rotation is a one-time operational task that will be executed as part of this feature, not an ongoing automated process.
- The Contributor Covenant v2.1 is the standard code of conduct for open-source projects and does not require customization.
- Issue templates should follow GitHub's standard YAML-based template format.

## Scope Boundaries

**In scope:**
- Removing/relocating internal documents from git tracking
- Scrubbing production IPs, personal emails, embedded keys
- Creating community files (CONTRIBUTING, CODE_OF_CONDUCT, SECURITY, issue templates)
- Expanding README into a project landing page
- Adding docstrings to public functions missing them
- Removing dead/commented-out code
- Removing broken internal repo references
- Credential rotation checklist and execution
- Final git history verification

**Out of scope:**
- Rewriting git history (only if audit finds committed secrets — believed clean)
- Refactoring large files (admin.py at 2852 lines — tracked separately)
- Adding new features or changing functionality
- Setting up GitHub Discussions, wiki, or project boards
- Creating a CHANGELOG (can be generated from git tags at launch)
- Marketing website updates for the launch announcement
