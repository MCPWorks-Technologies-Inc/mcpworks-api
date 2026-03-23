# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in MCPWorks, please report it responsibly.

**Do NOT open a public GitHub issue for security vulnerabilities.**

### How to Report

Email: **security@mcpworks.io**

Include:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

### Response Timeline

- **Acknowledgment**: Within 72 hours
- **Initial assessment**: Within 1 week
- **Fix timeline**: Depends on severity, typically 1-4 weeks
- **Disclosure**: Coordinated with reporter after fix is released

### Scope

In scope:
- mcpworks-api (this repository)
- MCPWorks Cloud (api.mcpworks.io)
- Authentication and authorization flaws
- Sandbox escape vulnerabilities
- Data exposure or leakage
- Injection vulnerabilities (SQL, command, etc.)

Out of scope:
- Denial of service attacks
- Social engineering
- Issues in third-party dependencies (report upstream)
- Self-hosted instances configured insecurely

### Recognition

We appreciate responsible disclosure and will credit reporters (with permission) in release notes.

## Supported Versions

| Version | Supported |
|---------|-----------|
| Latest release | Yes |
| Previous minor | Security fixes only |
| Older | No |

## Security Design

MCPWorks is designed with security as a core principle:

- **Sandbox isolation**: All user code runs in nsjail with namespace, cgroup, and seccomp isolation
- **No credential storage**: BYOAI model — user API keys are encrypted at rest and never logged
- **Architectural compliance**: GDPR/SOX compliance by design, not bolt-on
- **Rate limiting**: Per-account rate limits on all endpoints
- **Input validation**: Pydantic schema validation on all API inputs
