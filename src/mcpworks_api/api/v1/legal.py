"""Legal document endpoints - Privacy Policy, Terms of Service, AUP.

Serves legal documents as rendered HTML via markdown.
When www.mcpworks.io is live, these can become 302 redirects.
"""

from pathlib import Path

import markdown
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(prefix="/legal", tags=["legal"])

# Current legal document version
LEGAL_VERSION = "1.0.0"

# Load and render legal documents once at import time
_LEGAL_DIR = Path(__file__).parent.parent.parent / "static" / "legal"

_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title} — MCPWorks</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,100..1000;1,9..40,100..1000&family=Space+Grotesk:wght@300..700&display=swap" rel="stylesheet">
<style>
  body {{ font-family: 'DM Sans', ui-sans-serif, system-ui, sans-serif; max-width: 760px; margin: 2rem auto; padding: 0 1rem; color: #d1d5db; background: #111827; line-height: 1.7; }}
  h1 {{ font-family: 'Space Grotesk', ui-sans-serif, system-ui, sans-serif; color: #3b82f6; border-bottom: 2px solid #3b82f6; padding-bottom: 0.5rem; font-weight: 700; }}
  h2 {{ font-family: 'Space Grotesk', ui-sans-serif, system-ui, sans-serif; color: #60a5fa; margin-top: 2rem; font-weight: 700; }}
  h3 {{ font-family: 'Space Grotesk', ui-sans-serif, system-ui, sans-serif; color: #93c5fd; font-weight: 600; }}
  a {{ color: #60a5fa; transition: color 0.15s; }}
  a:hover {{ color: #d1d5db; }}
  code {{ background: #1f2937; padding: 2px 6px; border-radius: 4px; color: #60a5fa; }}
  hr {{ border: none; border-top: 1px solid #374151; margin: 2rem 0; }}
  table {{ border-collapse: collapse; width: 100%; margin: 1rem 0; }}
  th, td {{ border: 1px solid #374151; padding: 0.5rem 0.75rem; text-align: left; }}
  th {{ background: #1f2937; }}
  ul, ol {{ padding-left: 1.5rem; }}
  li {{ margin-bottom: 0.3rem; color: #d1d5db; }}
  strong {{ color: #ffffff; }}
  .footer {{ margin-top: 3rem; padding-top: 1rem; border-top: 1px solid #374151; color: #4b5563; font-size: 0.85em; }}
</style>
</head>
<body>
{content}
<div class="footer">
  <a href="/v1/legal/terms">Terms</a> &middot;
  <a href="/v1/legal/privacy">Privacy</a> &middot;
  <a href="/v1/legal/aup">AUP</a> &middot;
  Version {version}
</div>
</body>
</html>
"""


def _render_legal_doc(filename: str, title: str) -> str:
    """Read a markdown file and render to styled HTML."""
    md_path = _LEGAL_DIR / filename
    md_content = md_path.read_text(encoding="utf-8")
    html_content = markdown.markdown(md_content, extensions=["tables", "toc"])
    return _HTML_TEMPLATE.format(title=title, content=html_content, version=LEGAL_VERSION)


# Pre-render at import time (these are static documents)
_PRIVACY_HTML = _render_legal_doc("privacy-policy.md", "Privacy Policy")
_TERMS_HTML = _render_legal_doc("terms-of-service.md", "Terms of Service")
_AUP_HTML = _render_legal_doc("acceptable-use-policy.md", "Acceptable Use Policy")


@router.get("/privacy", response_class=HTMLResponse)
async def privacy_policy() -> HTMLResponse:
    """Serve the Privacy Policy (v1.0.0)."""
    return HTMLResponse(content=_PRIVACY_HTML)


@router.get("/terms", response_class=HTMLResponse)
async def terms_of_service() -> HTMLResponse:
    """Serve the Terms of Service (v1.0.0)."""
    return HTMLResponse(content=_TERMS_HTML)


@router.get("/aup", response_class=HTMLResponse)
async def acceptable_use_policy() -> HTMLResponse:
    """Serve the Acceptable Use Policy (v1.0.0)."""
    return HTMLResponse(content=_AUP_HTML)
