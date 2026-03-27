# Getting Started with MCPWorks

From zero to running your first function in 5 minutes. This tutorial assumes you have a running MCPWorks instance — see [Self-Hosting](SELF-HOSTING.md) if you haven't set one up yet.

## 1. Create an Account

Run the seed script to create your admin account:

```bash
docker compose -f docker-compose.self-hosted.yml exec \
  -e ADMIN_EMAIL=you@example.com \
  -e ADMIN_PASSWORD=your-password \
  api python3 scripts/seed_admin.py
```

Replace `you@example.com` and `your-password` with your desired credentials. The email must match an entry in `ADMIN_EMAILS` in your `.env` for admin access.

## 2. Open the Console

Open `https://api.<your-domain>/console` in your browser and log in with the credentials you just created.

The console walks you through three setup steps:

1. **Create a namespace** — this becomes your subdomain prefix (e.g. `demo.create.<your-domain>`)
2. **Create an API key** — starts with `sk_live_`, shown only once — copy it
3. **Connect your AI assistant** — the console generates the `.mcp.json` config for Claude Code, Cursor, and other clients, pre-filled with your namespace URLs and API key

Once your AI assistant is connected, come back here.

## 3. Create Your First Function

Ask your AI assistant:

> "Create a service called 'utils', then create a function called 'hello' using the hello-world template with output_trust=prompt."

Or use the MCP tools directly:

1. **`make_service`** — name: `utils`
2. **`make_function`** — name: `hello`, service: `utils`, template: `hello-world`, output_trust: `prompt`

Every function requires `output_trust`: use `prompt` for trusted computed output, or `data` for functions that process external content (emails, APIs, web scrapes).

## 4. Run It

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

## 5. Write a Real Function

Create a function that does something useful. Here's an example that processes data without sending it through the AI:

> "Create a function called 'analyze-csv' in the utils service. It should accept a CSV string as input, parse it, and return summary statistics (row count, column names, numeric column means). Use the pandas package."

The AI will create the function through the `make_function` tool. When you run it, pandas processes the CSV inside the sandbox — only the summary comes back to the AI. If the CSV has 10,000 rows, you save thousands of tokens.

## 6. Back Up Your Namespace to Git

Once you have functions worth keeping, export them to a Git repository:

> "Configure my namespace to push to `https://github.com/youruser/demo-functions.git` with token `ghp_...`"

> "Export my namespace to Git"

Your functions, schemas, and agent configs are now version-controlled. See the [Git Export & Import](guide.md#git-export--import) section in the platform guide for the full reference.

## 7. Connect a Third-Party MCP Server

Add external tools to your namespace — Slack, Google Workspace, GitHub, or any MCP server:

> "Add the Slack MCP server to my namespace at `https://slack-mcp.example.com/mcp` with token `xoxb-...`"

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
