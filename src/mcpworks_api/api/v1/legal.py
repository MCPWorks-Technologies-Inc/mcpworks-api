"""Legal document endpoints - Privacy Policy, Terms of Service, AUP.

ORDER-007: Serve legal documents or redirect to www.mcpworks.io.
"""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(prefix="/legal", tags=["legal"])

# Placeholder legal documents until www.mcpworks.io hosts the full versions.
# Replace these with RedirectResponse to www.mcpworks.io/privacy etc. when ready.

_PLACEHOLDER_STYLE = """
<style>
  body { font-family: system-ui, sans-serif; max-width: 720px; margin: 2rem auto; padding: 0 1rem; color: #222; }
  h1 { border-bottom: 2px solid #333; padding-bottom: 0.5rem; }
  .draft { background: #fff3cd; padding: 1rem; border-radius: 8px; margin-bottom: 2rem; }
</style>
"""


@router.get("/privacy", response_class=HTMLResponse)
async def privacy_policy() -> HTMLResponse:
    """Serve the Privacy Policy."""
    return HTMLResponse(
        content=f"""<!DOCTYPE html>
<html><head><title>MCPWorks - Privacy Policy</title>{_PLACEHOLDER_STYLE}</head>
<body>
<h1>Privacy Policy</h1>
<div class="draft">This is a placeholder. The final Privacy Policy is being drafted
by legal counsel and will be published at <code>www.mcpworks.io/privacy</code>.</div>

<h2>What We Collect</h2>
<ul>
  <li>Email address (for account creation and communication)</li>
  <li>Hashed password (never stored in plaintext)</li>
  <li>API usage data (execution counts, timestamps)</li>
  <li>IP addresses (for rate limiting and security)</li>
</ul>

<h2>What We Don't Collect</h2>
<ul>
  <li>We do not sell your data to third parties</li>
  <li>We do not store your code after execution completes</li>
  <li>We do not access your sandbox execution results</li>
</ul>

<h2>Contact</h2>
<p>Questions? Email <a href="mailto:privacy@mcpworks.io">privacy@mcpworks.io</a></p>

<p><em>Last updated: February 2026</em></p>
</body></html>"""
    )


@router.get("/terms", response_class=HTMLResponse)
async def terms_of_service() -> HTMLResponse:
    """Serve the Terms of Service."""
    return HTMLResponse(
        content=f"""<!DOCTYPE html>
<html><head><title>MCPWorks - Terms of Service</title>{_PLACEHOLDER_STYLE}</head>
<body>
<h1>Terms of Service</h1>
<div class="draft">This is a placeholder. The final Terms of Service are being drafted
by legal counsel and will be published at <code>www.mcpworks.io/terms</code>.</div>

<h2>Acceptable Use</h2>
<ul>
  <li>Do not use the sandbox to attack other systems</li>
  <li>Do not attempt to escape the sandbox or access other users' data</li>
  <li>Do not use the service for illegal activities</li>
  <li>Do not exceed your subscription tier's execution limits</li>
</ul>

<h2>Service Availability</h2>
<p>MCPWorks is provided "as is" during the beta period. We target 99.5% uptime
but do not guarantee it during early access.</p>

<h2>Data Retention</h2>
<p>Execution results are retained for 30 days. Code submitted for execution is
deleted immediately after execution completes.</p>

<h2>Contact</h2>
<p>Questions? Email <a href="mailto:legal@mcpworks.io">legal@mcpworks.io</a></p>

<p><em>Last updated: February 2026</em></p>
</body></html>"""
    )


@router.get("/aup", response_class=HTMLResponse)
async def acceptable_use_policy() -> HTMLResponse:
    """Serve the Acceptable Use Policy."""
    return HTMLResponse(
        content=f"""<!DOCTYPE html>
<html><head><title>MCPWorks - Acceptable Use Policy</title>{_PLACEHOLDER_STYLE}</head>
<body>
<h1>Acceptable Use Policy</h1>
<div class="draft">This is a placeholder. The final AUP is being drafted
by legal counsel and will be published at <code>www.mcpworks.io/aup</code>.</div>

<h2>Prohibited Activities</h2>
<ul>
  <li>Cryptocurrency mining</li>
  <li>Distributed denial-of-service (DDoS) attacks</li>
  <li>Port scanning or network reconnaissance</li>
  <li>Spam or unsolicited bulk messaging</li>
  <li>Hosting malware or phishing pages</li>
  <li>Attempting sandbox escape or privilege escalation</li>
  <li>Accessing or modifying other users' data</li>
  <li>Automated credential stuffing or brute force attacks</li>
</ul>

<h2>Resource Limits</h2>
<p>Each subscription tier has defined execution limits. Circumventing these limits
(e.g., creating multiple free accounts) is a violation of this policy.</p>

<h2>Enforcement</h2>
<p>Violations may result in immediate account suspension. Repeated violations
will result in permanent account termination.</p>

<h2>Reporting</h2>
<p>Report abuse to <a href="mailto:abuse@mcpworks.io">abuse@mcpworks.io</a></p>

<p><em>Last updated: February 2026</em></p>
</body></html>"""
    )
