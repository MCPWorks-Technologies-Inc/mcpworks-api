"""Documentation endpoints.

ORDER-012: Getting-started quickstart page.
Platform guide and LLM reference served as rendered markdown.
"""

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(prefix="/docs", tags=["docs"])

_QUICKSTART_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>MCPWorks — Quick Start Guide</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,100..1000;1,9..40,100..1000&family=Space+Grotesk:wght@300..700&display=swap" rel="stylesheet">
<style>
  body { font-family: 'DM Sans', ui-sans-serif, system-ui, sans-serif; max-width: 760px; margin: 2rem auto; padding: 0 1rem; color: #d1d5db; background: #111827; line-height: 1.6; }
  h1 { font-family: 'Space Grotesk', ui-sans-serif, system-ui, sans-serif; color: #3b82f6; border-bottom: 2px solid #3b82f6; padding-bottom: 0.5rem; font-weight: 700; }
  h2 { font-family: 'Space Grotesk', ui-sans-serif, system-ui, sans-serif; color: #60a5fa; margin-top: 2rem; font-weight: 700; }
  code { background: #1f2937; padding: 2px 6px; border-radius: 4px; font-size: 0.9em; color: #60a5fa; }
  pre { background: #1f2937; padding: 1rem; border-radius: 8px; overflow-x: auto; border: 1px solid #374151; }
  pre code { background: none; padding: 0; color: #d1d5db; }
  a { color: #60a5fa; transition: color 0.15s; }
  a:hover { color: #d1d5db; }
  .step { background: #1f2937; border-left: 3px solid #3b82f6; padding: 1rem 1.5rem; margin: 1rem 0; border-radius: 0 8px 8px 0; }
  .step-num { font-family: 'Space Grotesk', ui-sans-serif, system-ui, sans-serif; color: #3b82f6; font-weight: bold; font-size: 1.1em; }
  .time { color: #6b7280; font-size: 0.85em; }
  .tip { background: rgba(37, 99, 235, 0.1); border: 1px solid #2563eb; padding: 1rem; border-radius: 8px; margin: 1rem 0; }
</style>
</head>
<body>

<h1>From Zero to First Function in 5 Minutes</h1>
<p class="time">Estimated time: 5 minutes</p>

<h2>What You'll Do</h2>
<p>Register an account, connect your AI assistant (Claude Code, Codex, etc.), and create + execute your first serverless function — all through natural language.</p>

<div class="step">
<p><span class="step-num">Step 1:</span> Create your account <span class="time">(1 min)</span></p>
<p>Go to <a href="/register">/register</a> and sign up with your email. You'll get the Builder plan free — 25,000 executions/month.</p>
</div>

<div class="step">
<p><span class="step-num">Step 2:</span> Copy your <code>.mcp.json</code> config <span class="time">(30 sec)</span></p>
<p>After login, the dashboard shows your namespace and API key. Copy the generated config:</p>
<pre><code>{
  "mcpServers": {
    "myns-create": {
      "type": "http",
      "url": "https://myns.create.mcpworks.io/mcp",
      "headers": { "Authorization": "Bearer YOUR_API_KEY" }
    },
    "myns-run": {
      "type": "http",
      "url": "https://myns.run.mcpworks.io/mcp",
      "headers": { "Authorization": "Bearer YOUR_API_KEY" }
    }
  }
}</code></pre>
<p>Paste this into your project's <code>.mcp.json</code> file (or <code>~/.claude/settings.json</code> for global access).</p>
</div>

<div class="step">
<p><span class="step-num">Step 3:</span> Create a service <span class="time">(30 sec)</span></p>
<p>Ask your AI assistant:</p>
<pre><code>"Create a service called 'utils' in my MCPWorks namespace"</code></pre>
<p>The AI will call <code>make_service</code> automatically.</p>
</div>

<div class="step">
<p><span class="step-num">Step 4:</span> Create your first function <span class="time">(1 min)</span></p>
<p>Ask your AI assistant:</p>
<pre><code>"Create a hello-world function in my utils service using the hello-world template"</code></pre>
<p>Or create something custom:</p>
<pre><code>"Create a function called 'word-count' that takes text and returns the word count"</code></pre>
<p>The AI will write the code and call <code>make_function</code> with backend <code>code_sandbox</code>.</p>
</div>

<div class="step">
<p><span class="step-num">Step 5:</span> Execute it <span class="time">(30 sec)</span></p>
<p>Ask your AI assistant:</p>
<pre><code>"Execute hello-world with name 'MCPWorks'"</code></pre>
<p>The function runs in a secure sandbox. You'll see the result immediately.</p>
</div>

<div class="tip">
<strong>Available templates:</strong> <code>hello-world</code>, <code>csv-analyzer</code>, <code>api-connector</code>, <code>slack-notifier</code>, <code>scheduled-report</code>.
Use <code>list_templates</code> to see all options, or <code>describe_template</code> for full details.
</div>

<h2>Passing API Keys &amp; Secrets to Functions</h2>
<p>Functions that call external APIs (OpenAI, Stripe, Twilio, etc.) need credentials. MCPWorks lets you pass environment variables securely via a header — <strong>nothing is stored on our servers</strong>.</p>

<div class="step">
<p><span class="step-num">Step A:</span> Declare env vars when creating the function</p>
<p>When you create or update a function, specify which env vars it needs:</p>
<pre><code>"Create a function called 'summarize' that calls OpenAI to summarize text.
It requires OPENAI_API_KEY."</code></pre>
<p>The AI will set <code>required_env: ["OPENAI_API_KEY"]</code> on the function automatically.</p>
</div>

<div class="step">
<p><span class="step-num">Step B:</span> Add the header to your <code>.mcp.json</code></p>
<p>Base64-encode your env vars as JSON, then add the <code>X-MCPWorks-Env</code> header to your <strong>run</strong> server:</p>
<pre><code>{
  "mcpServers": {
    "myns-run": {
      "type": "http",
      "url": "https://myns.run.mcpworks.io/mcp",
      "headers": {
        "Authorization": "Bearer YOUR_API_KEY",
        "X-MCPWorks-Env": "base64:eyJPUEVOQUlfQVBJX0tFWSI6InNrLXh4eCJ9"
      }
    }
  }
}</code></pre>
<p>To encode: <code>echo -n '{"OPENAI_API_KEY":"sk-xxx"}' | base64</code></p>
</div>

<div class="step">
<p><span class="step-num">Step C:</span> Check what's configured</p>
<p>Ask your AI assistant to call the <code>_env_status</code> tool — it shows which variables are configured and which are missing across all your functions.</p>
</div>

<div class="tip">
<strong>Security:</strong> Env vars are never stored, logged, or persisted. They travel encrypted (HTTPS), are injected into the sandbox for the duration of execution, and are destroyed immediately after. Each function only receives the specific variables it declared — not the full set.
</div>

<h2>What's Happening Behind the Scenes</h2>
<ul>
<li><strong>create endpoint</strong> (<code>*.create.mcpworks.io</code>) — manages your namespaces, services, and functions</li>
<li><strong>run endpoint</strong> (<code>*.run.mcpworks.io</code>) — executes functions in a secure nsjail sandbox</li>
<li>Each function runs in an isolated container with no network access to your database or secrets</li>
<li>60+ Python packages pre-installed (numpy, pandas, httpx, etc.) — use <code>list_packages</code> to see all</li>
<li>Environment variables are passed per-request via header — never stored server-side</li>
</ul>

<h2>Next Steps</h2>
<ul>
<li>Browse templates: ask your AI to <code>list_templates</code></li>
<li>See available packages: ask your AI to <code>list_packages</code></li>
<li>Pass secrets to functions: add <code>X-MCPWorks-Env</code> header to your run config</li>
<li>Check usage: visit <a href="/dashboard">/dashboard</a></li>
<li>Read the API docs: <a href="/docs">/docs</a> (development mode only)</li>
</ul>

<p style="margin-top: 3rem; color: #4b5563; font-size: 0.85em; border-top: 1px solid #374151; padding-top: 1rem;">
MCPWorks — Code Sandbox for AI Assistants &middot;
<a href="/legal/terms">Terms</a> &middot;
<a href="/legal/privacy">Privacy</a> &middot;
<a href="/legal/aup">AUP</a>
</p>

</body>
</html>
"""


@router.get("/quickstart", response_class=HTMLResponse, include_in_schema=False)
async def quickstart() -> HTMLResponse:
    """Serve the getting-started guide."""
    return HTMLResponse(content=_QUICKSTART_HTML)


# ---------------------------------------------------------------------------
# Markdown-based docs (guide + LLM reference)
# ---------------------------------------------------------------------------

_DOCS_DIR = Path(__file__).resolve().parents[4] / "docs"

_MD_CSS = """\
<style>
  body { font-family: 'DM Sans', ui-sans-serif, system-ui, sans-serif; max-width: 860px; margin: 2rem auto; padding: 0 1.5rem; color: #d1d5db; background: #111827; line-height: 1.7; }
  h1, h2, h3, h4 { font-family: 'Space Grotesk', ui-sans-serif, system-ui, sans-serif; color: #60a5fa; font-weight: 700; }
  h1 { color: #3b82f6; border-bottom: 2px solid #3b82f6; padding-bottom: 0.5rem; }
  code { background: #1f2937; padding: 2px 6px; border-radius: 4px; font-size: 0.9em; color: #60a5fa; }
  pre { background: #1f2937; padding: 1rem; border-radius: 8px; overflow-x: auto; border: 1px solid #374151; }
  pre code { background: none; padding: 0; color: #d1d5db; }
  a { color: #60a5fa; transition: color 0.15s; }
  a:hover { color: #d1d5db; }
  table { border-collapse: collapse; width: 100%; margin: 1rem 0; }
  th, td { border: 1px solid #374151; padding: 0.5rem 0.75rem; text-align: left; }
  th { background: #1f2937; color: #60a5fa; }
  tr:nth-child(even) { background: rgba(31, 41, 55, 0.5); }
  blockquote { border-left: 3px solid #3b82f6; margin: 1rem 0; padding: 0.5rem 1rem; background: rgba(31, 41, 55, 0.5); }
  hr { border: none; border-top: 1px solid #374151; margin: 2rem 0; }
  ul, ol { padding-left: 1.5rem; }
  li { margin: 0.25rem 0; }
</style>
"""

_MD_HEAD = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,100..1000;1,9..40,100..1000&family=Space+Grotesk:wght@300..700&display=swap" rel="stylesheet">
{css}
</head>
<body>
{body}
<p style="margin-top: 3rem; color: #4b5563; font-size: 0.85em; border-top: 1px solid #374151; padding-top: 1rem;">
MCPWorks &middot;
<a href="/v1/docs/quickstart">Quick Start</a> &middot;
<a href="/v1/docs/guide">Platform Guide</a> &middot;
<a href="/v1/docs/llm-reference">LLM Reference</a>
</p>
</body>
</html>
"""


def _render_md(filename: str, title: str) -> str:
    """Read a markdown file from docs/ and render to HTML."""
    import markdown as md

    md_path = _DOCS_DIR / filename
    md_text = md_path.read_text(encoding="utf-8")
    body = md.markdown(md_text, extensions=["tables", "fenced_code", "toc"])
    return _MD_HEAD.format(title=title, css=_MD_CSS, body=body)


@router.get("/guide", response_class=HTMLResponse, include_in_schema=False)
async def guide() -> HTMLResponse:
    """Serve the platform guide (rendered from docs/guide.md)."""
    return HTMLResponse(content=_render_md("guide.md", "MCPWorks Platform Guide"))


@router.get("/llm-reference", response_class=HTMLResponse, include_in_schema=False)
async def llm_reference() -> HTMLResponse:
    """Serve the LLM agent reference (rendered from docs/llm-reference.md)."""
    return HTMLResponse(content=_render_md("llm-reference.md", "MCPWorks LLM Agent Reference"))
