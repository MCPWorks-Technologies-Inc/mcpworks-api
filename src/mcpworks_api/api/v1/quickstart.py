"""Getting-started documentation endpoint.

ORDER-012: Single page — "From zero to first function in 5 minutes."
Served at GET /v1/docs/quickstart as HTML.
"""

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
<p>Go to <a href="/register">/register</a> and sign up with your email. You'll get 100 free executions/month.</p>
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

<h2>What's Happening Behind the Scenes</h2>
<ul>
<li><strong>create endpoint</strong> (<code>*.create.mcpworks.io</code>) — manages your namespaces, services, and functions</li>
<li><strong>run endpoint</strong> (<code>*.run.mcpworks.io</code>) — executes functions in a secure nsjail sandbox</li>
<li>Each function runs in an isolated container with no network access to your database or secrets</li>
<li>60+ Python packages pre-installed (numpy, pandas, httpx, etc.) — use <code>list_packages</code> to see all</li>
</ul>

<h2>Next Steps</h2>
<ul>
<li>Browse templates: ask your AI to <code>list_templates</code></li>
<li>See available packages: ask your AI to <code>list_packages</code></li>
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
