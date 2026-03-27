# Getting Started with MCPWorks

From zero to running your first function. This guide covers deploying MCPWorks on your own infrastructure and creating your first function.

## Prerequisites

| Requirement | Minimum | Notes |
|-------------|---------|-------|
| OS | Linux (kernel 5.10+) | macOS/Windows for evaluation only |
| Docker | 24.0+ | With Docker Compose v2 |
| RAM | 2 GB | 4 GB recommended |
| Disk | 20 GB | SSD recommended |
| Domain | Wildcard DNS | Required for namespace subdomains |
| Ports | 80, 443 | Must be open for Let's Encrypt |

## 1. Clone and Configure

```bash
git clone https://github.com/MCPWorks-Technologies-Inc/mcpworks-api.git
cd mcpworks-api

# Create environment file
cp .env.self-hosted.example .env
```

Edit `.env` and set:

- **`BASE_DOMAIN`** — your domain (e.g. `example.com`)
- **`ADMIN_EMAILS`** — JSON list of admin email addresses (e.g. `["admin@example.com"]`)

## 2. Generate Keys

```bash
# JWT signing keys (ES256)
mkdir -p keys
openssl ecparam -genkey -name prime256v1 -noout -out keys/private.pem
openssl ec -in keys/private.pem -pubout -out keys/public.pem

# Encryption key — copy the output into ENCRYPTION_KEK_B64 in .env
python3 -c "import secrets, base64; print(base64.b64encode(secrets.token_bytes(32)).decode())"
```

## 3. Configure DNS

Set up these DNS records pointing to your server:

| Record | Type | Value |
|--------|------|-------|
| `api.yourdomain.com` | A | Your server IP |
| `*.create.yourdomain.com` | A | Your server IP |
| `*.run.yourdomain.com` | A | Your server IP |
| `*.agent.yourdomain.com` | A | Your server IP |

Caddy automatically provisions TLS certificates via Let's Encrypt on first access.

## 4. Start the Server

```bash
docker compose -f docker-compose.self-hosted.yml up -d
```

Wait for the health check to pass:

```bash
curl https://api.yourdomain.com/v1/health
```

## 5. Create Your Admin Account

```bash
docker compose -f docker-compose.self-hosted.yml exec \
  -e ADMIN_EMAIL=you@example.com \
  -e ADMIN_PASSWORD=your-password \
  api python3 scripts/seed_admin.py
```

Replace `you@example.com` and `your-password` with your desired credentials. The email must match an entry in `ADMIN_EMAILS` in your `.env` for admin access.

## 6. Open the Console

Open `https://api.<your-domain>/console` in your browser and log in.

The console walks you through three setup steps:

1. **Create a namespace** — this becomes your subdomain prefix (e.g. `demo.create.<your-domain>`)
2. **Create an API key** — starts with `sk_live_`, shown only once — copy it
3. **Connect your AI assistant** — the console generates the `.mcp.json` config for Claude Code, Cursor, and other clients, pre-filled with your namespace URLs and API key

Once your AI assistant is connected, come back here.

## 7. Create Your First Function

Ask your AI assistant:

> "Create a service called 'utils', then create a function called 'hello' using the hello-world template with output_trust=prompt."

Or use the MCP tools directly:

1. **`make_service`** — name: `utils`
2. **`make_function`** — name: `hello`, service: `utils`, template: `hello-world`, output_trust: `prompt`

Every function requires `output_trust`: use `prompt` for trusted computed output, or `data` for functions that process external content (emails, APIs, web scrapes).

## 8. Run It

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

## 9. Write a Real Function

Create a function that does something useful. Here's an example that processes data without sending it through the AI:

> "Create a function called 'analyze-csv' in the utils service. It should accept a CSV string as input, parse it, and return summary statistics (row count, column names, numeric column means). Use the pandas package."

The AI will create the function through the `make_function` tool. When you run it, pandas processes the CSV inside the sandbox — only the summary comes back to the AI. If the CSV has 10,000 rows, you save thousands of tokens.

## 10. Back Up Your Namespace to Git

Once you have functions worth keeping, export them to a Git repository:

> "Configure my namespace to push to `https://github.com/youruser/demo-functions.git` with token `ghp_...`"

> "Export my namespace to Git"

Your functions, schemas, and agent configs are now version-controlled. See the [Git Export & Import](guide.md#git-export--import) section in the platform guide for the full reference.

## 11. Connect a Third-Party MCP Server

Add external tools to your namespace — Slack, Google Workspace, GitHub, or any MCP server:

> "Add the Slack MCP server to my namespace at `https://slack-mcp.example.com/mcp` with token `xoxb-...`"

Now your sandbox code can call Slack tools directly:

```python
from functions import mcp__slack__send_message
mcp__slack__send_message(channel="C01234", text="Hello from MCPWorks!")
result = {"sent": True}
```

The AI writes code, the sandbox calls Slack via the proxy, and only the result comes back. See [Remote MCP Servers](guide.md#remote-mcp-servers) for the full reference.

---

## Configuration Reference

### Required Settings

| Variable | Description | Example |
|----------|-------------|---------|
| `BASE_DOMAIN` | Your domain name | `example.com` |
| `JWT_PRIVATE_KEY_PATH` | Path to ES256 private key file | `/app/keys/private.pem` |
| `JWT_PUBLIC_KEY_PATH` | Path to ES256 public key file | `/app/keys/public.pem` |
| `ENCRYPTION_KEK_B64` | 32-byte key (base64) | Output of keygen command |

### Optional Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `BASE_SCHEME` | `https` | Use `http` for local dev without TLS |
| `ALLOW_REGISTRATION` | `false` | Set `true` to allow public signup |
| `ADMIN_EMAIL` | - | Email for seed admin account |
| `ADMIN_PASSWORD` | - | Password for seed admin account |
| `STRIPE_SECRET_KEY` | (empty) | Enable billing when set |
| `RESEND_API_KEY` | (empty) | Enable Resend email when set |
| `SMTP_HOST` | (empty) | Enable SMTP email when set |
| `SANDBOX_DEV_MODE` | `true` | Set `false` for production (requires Linux) |

See `.env.self-hosted.example` for the complete list with descriptions.

## Sandbox Security Modes

MCPWorks uses nsjail to isolate user code execution. There are two modes:

### Production Mode (`SANDBOX_DEV_MODE=false`)

- Uses nsjail with Linux namespaces, cgroups v2, and seccomp-bpf
- Full process isolation — user code cannot access the host
- **Requires Linux** with kernel 5.10+ and privileged Docker container
- Recommended for any deployment running untrusted code

### Dev Mode (`SANDBOX_DEV_MODE=true`)

- Uses Python subprocess — **no isolation**
- User code runs with the same permissions as the API process
- Works on macOS, Windows (WSL2), and Linux
- **Only use for evaluation or trusted code**

## Billing

By default, self-hosted instances run without billing. All users get unlimited executions.

To enable billing:
1. Create a Stripe account
2. Set `STRIPE_SECRET_KEY` and `STRIPE_WEBHOOK_SECRET` in `.env`
3. Configure Stripe price IDs for each tier
4. Restart the API container

## Email

Email is optional. Without it, users won't receive welcome emails or notifications, but all other functionality works.

**Option 1: Resend** — Set `RESEND_API_KEY` in `.env`

**Option 2: SMTP** — Set `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM_EMAIL` in `.env`

**Option 3: Disabled** — Leave all email settings empty (emails are silently skipped)

## Using External Databases

The self-hosted compose file includes PostgreSQL and Redis. To use your own:

1. Set `DATABASE_URL` to your PostgreSQL connection string
2. Set `REDIS_URL` to your Redis connection string
3. Remove the `postgres` and `redis` services from `docker-compose.self-hosted.yml`

## Upgrading

```bash
cd mcpworks-api
git pull origin main
docker compose -f docker-compose.self-hosted.yml build api
docker compose -f docker-compose.self-hosted.yml up -d api
```

Migrations run automatically on container startup.

## Troubleshooting

### Health check fails

```bash
docker logs mcpworks-api --tail 50
```

Common causes:
- Database not ready (wait for postgres healthcheck)
- JWT keys not set or malformed
- Port 8000 not accessible from Caddy

### Caddy certificate errors

- Ensure ports 80 and 443 are open to the internet
- Ensure DNS records are pointing to your server
- Check Caddy logs: `docker logs mcpworks-caddy --tail 50`

### nsjail errors

- Ensure `SANDBOX_DEV_MODE=false` is set
- Container must run with `privileged: true`
- Host kernel must support namespaces and cgroups v2
- Check: `docker exec mcpworks-api nsjail --help`

### Registration disabled

Self-hosted instances default to closed registration. To enable:
- Set `ALLOW_REGISTRATION=true` in `.env`
- Or create accounts manually via the seed script

## Architecture

```
Internet → Caddy (TLS) → MCPWorks API → PostgreSQL
                                       → Redis
                                       → nsjail (code sandbox)
```

All services run in Docker containers on a single machine. For high-availability deployments, see the project documentation.

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
