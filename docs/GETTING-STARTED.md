# Getting Started with MCPWorks

From zero to running your first function in 5 minutes. This tutorial assumes you have a running MCPWorks instance — either [self-hosted](SELF-HOSTING.md) or on [MCPWorks Cloud](https://mcpworks.io).

## 1. Create an Account

**Self-hosted:** Run the seed script to create your admin account:

```bash
docker compose -f docker-compose.self-hosted.yml exec api \
  python3 scripts/seed_admin.py
```

Set `ADMIN_EMAIL` and `ADMIN_PASSWORD` in your `.env` first, or the script uses defaults.

**MCPWorks Cloud:** Register at `https://api.mcpworks.io/register`.

## 2. Get an API Key

```bash
# Log in (replace with your URL for self-hosted)
API=https://api.mcpworks.io

# Get an access token
TOKEN=$(curl -s -X POST $API/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "you@example.com", "password": "your-password"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# Create an API key
curl -s -X POST $API/v1/keys \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "my-first-key"}' | python3 -m json.tool
```

Save the `raw_key` from the response. It starts with `sk_live_` and is shown only once.

## 3. Connect Your AI Assistant

Add this to your project's `.mcp.json` (Claude Code, Codex, Copilot, etc.):

```json
{
  "mcpServers": {
    "myns-create": {
      "type": "http",
      "url": "https://myns.create.mcpworks.io/mcp",
      "headers": { "Authorization": "Bearer sk_live_..." }
    },
    "myns-run": {
      "type": "http",
      "url": "https://myns.run.mcpworks.io/mcp",
      "headers": { "Authorization": "Bearer sk_live_..." }
    }
  }
}
```

Replace `myns` with the namespace you want to use and `sk_live_...` with your API key.

**Self-hosted:** Replace `mcpworks.io` with your `BASE_DOMAIN`.

## 4. Create Your First Function

Ask your AI assistant:

> "Create a namespace called 'demo', then a service called 'utils', then create a function called 'hello' using the hello-world template."

Or do it manually through the MCP tools:

1. **`make_namespace`** — name: `demo`
2. **`make_service`** — name: `utils`
3. **`make_function`** — name: `hello`, service: `utils`, template: `hello-world`

## 5. Run It

Ask your AI assistant:

> "Run the hello function with name 'World'"

The function executes inside a secure sandbox. Your AI assistant gets back only the result — the data never enters the context window.

### What Just Happened?

```
Your AI assistant                    MCPWorks
      |                                  |
      |-- "Run hello with name World" -->|
      |                                  |-- [sandbox: nsjail]
      |                                  |   def handler(params):
      |                                  |     return {"greeting": f"Hello, {params['name']}!"}
      |                                  |-- [sandbox exits]
      |                                  |
      |<---- {"greeting": "Hello, World!"} --|
```

The sandbox ran the code, returned the result, and destroyed itself. No data leaked into the AI context.

## 6. Write a Real Function

Create a function that does something useful. Here's an example that processes data without sending it through the AI:

> "Create a function called 'analyze-csv' in the utils service. It should accept a CSV string as input, parse it, and return summary statistics (row count, column names, numeric column means). Use the pandas package."

The AI will create the function through the `make_function` tool. When you run it, pandas processes the CSV inside the sandbox — only the summary comes back to the AI. If the CSV has 10,000 rows, you save thousands of tokens.

## 7. Back Up Your Namespace to Git

Once you have functions worth keeping, export them to a Git repository:

> "Configure my demo namespace to push to `https://github.com/youruser/demo-functions.git` with token `ghp_...`"

> "Export my demo namespace to Git"

Your functions, schemas, and agent configs are now version-controlled. See the [Git Export & Import](guide.md#git-export--import) section in the platform guide for the full reference.

## 8. Connect a Third-Party MCP Server

Add external tools to your namespace — Slack, Google Workspace, GitHub, or any MCP server:

> "Add the Slack MCP server to my demo namespace at `https://slack-mcp.example.com/mcp` with token `xoxb-...`"

Now your sandbox code can call Slack tools directly:

```python
from functions import mcp__slack__send_message
mcp__slack__send_message(channel="C01234", text="Hello from MCPWorks!")
result = {"sent": True}
```

The AI writes code, the sandbox calls Slack via the proxy, and only the result comes back. See [Remote MCP Servers](guide.md#remote-mcp-servers) for the full reference.

## What's Next?

- **[Platform Guide](guide.md)** — Full reference for all MCP tools, code mode, templates, and agents
- **[API Contract](implementation/specs/api-contract.md)** — REST API reference
- **[Token Savings Analysis](token-savings-analysis.md)** — How sandbox execution reduces token costs

### Key Concepts

| Concept | What it does |
|---------|-------------|
| **Namespace** | Top-level container, maps to `{ns}.create.` and `{ns}.run.` subdomains |
| **Service** | Groups related functions (like a folder) |
| **Function** | Executable code with input/output schemas |
| **Code mode** | AI writes Python that calls your functions inside the sandbox |
| **Tool mode** | AI calls functions directly (one MCP tool per function) |
| **BYOAI** | Agents use your own AI provider key — no vendor lock-in |
