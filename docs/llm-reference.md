# MCPWorks LLM Agent Reference

> Structured reference for AI agents operating MCPWorks. Optimized for system-prompt consumption.

---

## Platform Summary

MCPWorks = self-hosted Python/TypeScript function platform managed and executed via MCP protocol.
Two endpoints per namespace. Create endpoint for CRUD. Run endpoint for execution.
All code runs in nsjail sandboxes. 59 Python packages + Node.js packages pre-installed. No pip/npm at runtime.

---

## MCP Configuration

### Path-based routing (default, recommended)

```json
{
  "mcpServers": {
    "{ns}-create": {
      "type": "http",
      "url": "https://api.{BASE_DOMAIN}/mcp/create/{ns}",
      "headers": { "Authorization": "Bearer {API_KEY}" }
    },
    "{ns}-run": {
      "type": "http",
      "url": "https://api.{BASE_DOMAIN}/mcp/run/{ns}",
      "headers": {
        "Authorization": "Bearer {API_KEY}",
        "X-MCPWorks-Env": "base64:{base64-encoded JSON of env vars}"
      }
    },
    "{ns}-agent": {
      "type": "http",
      "url": "https://api.{BASE_DOMAIN}/mcp/agent/{ns}",
      "headers": { "Authorization": "Bearer {API_KEY}" }
    }
  }
}
```

### Subdomain routing (alternative)

```json
{
  "mcpServers": {
    "{ns}-create": {
      "type": "http",
      "url": "https://{ns}.create.{BASE_DOMAIN}/mcp",
      "headers": { "Authorization": "Bearer {API_KEY}" }
    },
    "{ns}-run": {
      "type": "http",
      "url": "https://{ns}.run.{BASE_DOMAIN}/mcp",
      "headers": {
        "Authorization": "Bearer {API_KEY}",
        "X-MCPWorks-Env": "base64:{base64-encoded JSON of env vars}"
      }
    },
    "{ns}-agent": {
      "type": "http",
      "url": "https://{ns}.agent.{BASE_DOMAIN}/mcp",
      "headers": { "Authorization": "Bearer {API_KEY}" }
    }
  }
}
```

The `{ns}-agent` entry is only needed for namespaces with a running agent.

---

## Endpoints

| Endpoint | Path Pattern | Subdomain Pattern | Purpose | Metered |
|----------|-------------|-------------------|---------|---------|
| Create | `api.{DOMAIN}/mcp/create/{ns}` | `{ns}.create.{DOMAIN}/mcp` | Namespace/service/function CRUD | No |
| Run (code) | `api.{DOMAIN}/mcp/run/{ns}` | `{ns}.run.{DOMAIN}/mcp` | Single `execute` tool, write Python/TS | Yes |
| Run (tools) | `api.{DOMAIN}/mcp/run/{ns}?mode=tools` | `{ns}.run.{DOMAIN}/mcp?mode=tools` | One tool per function | Yes |
| Agent | `api.{DOMAIN}/mcp/agent/{ns}` | `{ns}.agent.{DOMAIN}/mcp` | Webhook delivery to agent containers | No |

Default run mode is **code** (no query param needed). Agent endpoint is only active for namespaces with a running agent.

---

## Create Endpoint — 13 Tools

### Namespace

| Tool | Required Params | Optional Params | Notes |
|------|----------------|-----------------|-------|
| `make_namespace` | `name` | `description` | Name: `^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$` |
| `list_namespaces` | — | — | Returns all namespaces for account |

### Service

| Tool | Required Params | Optional Params | Notes |
|------|----------------|-----------------|-------|
| `make_service` | `name` | `description` | Created in current namespace |
| `list_services` | — | — | Returns name, description, function_count, call_count |
| `delete_service` | `name` | — | Deletes all functions in service |

### Function

| Tool | Required Params | Optional Params | Notes |
|------|----------------|-----------------|-------|
| `make_function` | `service`, `name`, `backend`, `output_trust` | `language`, `code`, `config`, `input_schema`, `output_schema`, `description`, `tags`, `requirements`, `required_env`, `optional_env`, `template` | `output_trust`: `prompt` or `data`. `language`: `python` (default) or `typescript`. `template` overrides code/schemas/reqs |
| `update_function` | `service`, `name` | `backend`, `code`, `config`, `input_schema`, `output_schema`, `description`, `tags`, `requirements`, `required_env`, `optional_env`, `restore_version` | Code/config/schema/req/env changes → new version |
| `delete_function` | `service`, `name` | — | Permanent |
| `list_functions` | `service` | `tag` | Returns qualified names (`service.function`) |
| `describe_function` | `service`, `name` | — | Full details + version history |

### Discovery

| Tool | Required Params | Notes |
|------|----------------|-------|
| `list_packages` | — | 59 packages grouped by category |
| `list_templates` | — | 5 templates: hello-world, csv-analyzer, api-connector, slack-notifier, scheduled-report |
| `describe_template` | `name` | Returns code, schemas, requirements |

---

## Run Endpoint

### Tool Mode (`?mode=tools`)

Each function → one MCP tool named `service.function`.
Input schema comes from function's `input_schema`.
AI calls functions directly.

### Code Mode (default)

Single tool: `execute(code: str)`.
Platform generates `functions/` package from namespace functions.

**Discover functions:**
```python
import functions
print(functions.__doc__)
```

**Call a function:**
```python
from functions import my_func
result = my_func(param="value")
```

**Return data:** Set `result = ...` (or `output = ...`).

---

## Environment Variable Passthrough

Functions can receive secrets (API keys, tokens) via the `X-MCPWorks-Env` header. Nothing is stored server-side.

### Declaring Env Vars

```
make_function(service="ai", name="summarize", backend="code_sandbox",
  required_env=["OPENAI_API_KEY"], optional_env=["OPENAI_ORG_ID"], ...)
```

### Passing Env Vars

Add `X-MCPWorks-Env` header to the **run** server in `.mcp.json`:

```json
"headers": {
  "Authorization": "Bearer {API_KEY}",
  "X-MCPWorks-Env": "base64:{base64 of JSON object}"
}
```

Encode: `echo -n '{"OPENAI_API_KEY":"sk-xxx"}' | base64`

### Reading in Function Code

```python
import os
api_key = os.environ["OPENAI_API_KEY"]
```

### Diagnostics

Call `_env_status` tool (run endpoint, tool mode) to check which vars are configured vs missing.

### Rules

- Max 64 vars, 32 KB header
- Names: `^[A-Z][A-Z0-9_]*$`
- Blocked: `PATH`, `HOME`, `LD_*`, `PYTHON*`, `NSJAIL*`, `MCPWORKS_*`
- Each function receives only its declared vars (least-privilege)

---

## Function Code Conventions

Three ways to return output (checked in order):

1. Set `result` variable
2. Set `output` variable
3. Define `main(input_data)` that returns a value

`input_data` dict is always available as a global.

---

## Backend Values

| Backend | Status | Description |
|---------|--------|-------------|
| `code_sandbox` | Active | Secure Python/TypeScript execution (nsjail) |

Always use `code_sandbox`.

---

## Templates

| Name | Description | Requirements |
|------|-------------|-------------|
| `hello-world` | Greet by name, prove system works | — |
| `csv-analyzer` | Parse CSV, return summary stats | — |
| `api-connector` | Call external API, return response | `httpx` |
| `slack-notifier` | Post to Slack webhook | `httpx` |
| `scheduled-report` | Generate markdown/JSON report | — |

Usage: `make_function(service="x", name="y", backend="code_sandbox", template="hello-world")`

---

## Versioning Rules

- `make_function` → v1
- `update_function` with code/config/schema/requirements → new version (v2, v3, ...)
- `update_function` with only description/tags → metadata update, no new version
- `update_function` with `restore_version=N` → copies vN into a new version
- Versions are immutable

---

## Agents

Agents = long-running containers with AI engine, schedules, webhooks, state, and channels. Require agent-enabled tier (admin-provisioned).

### Agent MCP Tools (on create endpoint, agent tier required)

| Tool | Required Params | Notes |
|------|----------------|-------|
| `make_agent` | `name` | Creates container + namespace |
| `list_agents` | — | All agents for account |
| `describe_agent` | `name` | Full details: status, AI, schedules, webhooks, state |
| `start_agent` | `name` | Start stopped container |
| `stop_agent` | `name` | Stop running container |
| `destroy_agent` | `name` | Remove container and resources |
| `clone_agent` | `source_name`, `new_name` | Copy namespace, functions, state, schedules |
| `scale_agent` | `name`, `replicas` | Scale to N replicas (each counts as 1 agent slot) |
| `configure_ai` | `name`, `engine`, `model`, `api_key` | Set AI engine (restart agent to apply) |
| `add_schedule` | `name`, `function_name`, `cron_expression` | Optional `mode`: `single` (default, round-robin) or `cluster` (all replicas) |
| `add_webhook` | `name`, `path` | Register webhook path |
| `chat_with_agent` | `name`, `message` | Optional `replica` for session affinity (verb-animal name) |
| `set_state` | `name`, `key`, `value` | Encrypted K/V store |
| `get_state` | `name`, `key` | Retrieve state value |

### AI Engines

| Engine | Provider | API Style |
|--------|----------|-----------|
| `anthropic` | Anthropic (Claude) | Native SDK |
| `openai` | OpenAI | OpenAI-compatible |
| `google` | Google (Gemini) | Native SDK |
| `grok` | xAI | OpenAI-compatible |
| `deepseek` | DeepSeek | OpenAI-compatible |
| `kimi` | Moonshot (Kimi) | OpenAI-compatible |
| `openrouter` | OpenRouter | OpenAI-compatible |
| `ollama` | Self-hosted | OpenAI-compatible |

### Agent Resources (per replica)

Each replica gets full tier resources. Each replica counts as 1 agent slot.

| Resource | builder-agent | pro-agent | enterprise-agent |
|----------|--------------|-----------|-----------------|
| Agent slots | 1 | 5 | 20 |
| RAM | 256 MB | 512 MB | 1 GB |
| CPU | 0.25 vCPU | 0.5 vCPU | 1.0 vCPU |
| Min schedule | 5 min | 30 sec | 15 sec |
| State storage | 10 MB | 100 MB | 1 GB |

### Agent Security

Agents cannot call function management tools (`make_function`, `update_function`, `delete_function`, `make_service`, `delete_service`, `lock_function`, `unlock_function`) during orchestration. All function output is scanned for leaked secrets (API keys, JWTs, connection URIs, private keys, env var values) before reaching the AI context. Detected secrets are replaced with `[REDACTED_*]` markers.

---

## Tier Limits

### Execution Quotas (per month)

| Tier | Price | Executions | Agents |
|------|-------|------------|--------|
| free | $0 | 1,000 | — |
| builder | $29 | 25,000 | — |
| pro | $149 | 250,000 | — |
| enterprise | $499 | 1,000,000 | — |
| builder-agent | $29 | 25,000 | 1 |
| pro-agent | $179 | 250,000 | 5 |
| enterprise-agent | $599 | 1,000,000 | 20 |

Agent tiers include full access to the corresponding Functions tier.

### Sandbox Resources (per execution)

| Resource | free | builder | pro | enterprise |
|----------|------|---------|-----|------------|
| Timeout | 10s | 30s | 90s | 300s |
| Memory | 128 MB | 256 MB | 512 MB | 2048 MB |
| Max PIDs | 16 | 32 | 64 | 128 |
| Network hosts | 0 | 5 | 25 | unlimited |

Quota exceeded → HTTP 429 `QUOTA_EXCEEDED`.

---

## Naming Constraints

| Entity | Rules |
|--------|-------|
| Namespace | `^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$` — DNS-compliant, 1-63 chars |
| Service | String, no special constraints beyond non-empty |
| Function | String, hyphens converted to underscores in code-mode imports |

---

## Package Categories

| Category | Packages |
|----------|----------|
| http | requests, httpx, urllib3, aiohttp, websockets |
| data_formats | pyyaml, orjson, tomli, tomli-w, xmltodict, msgpack |
| validation | pydantic, attrs, jsonschema |
| text | beautifulsoup4, lxml, markdownify, markdown, html2text, chardet, python-slugify, jinja2, regex |
| datetime | python-dateutil, pytz, arrow |
| data_science | numpy, pandas, scipy, scikit-learn, sympy, statsmodels |
| visualization | matplotlib, pillow |
| ai | openai, anthropic, tiktoken, cohere |
| cloud | boto3, stripe, sendgrid, twilio, google-cloud-storage |
| file_formats | openpyxl, xlsxwriter, tabulate, feedparser, python-docx, pypdf |
| security | cryptography, pyjwt, bcrypt |
| database | psycopg2-binary, pymongo, redis |
| utilities | humanize, tqdm, rich, typing-extensions |

**Aliases:** bs4→beautifulsoup4, yaml→pyyaml, dateutil→python-dateutil, slugify→python-slugify, sklearn→scikit-learn, PIL→pillow, jwt→pyjwt, psycopg2→psycopg2-binary

---

## Decision Tree: Code Mode vs Tool Mode

```
Is the AI chaining multiple functions or doing data transformation?
  YES → code mode (default)
  NO →
    Does the AI need to call a single function with structured params?
      YES → tool mode (?mode=tools)
      NO → code mode (default)
```

Code mode is the default and handles all use cases. Tool mode is useful when the AI should call functions one-at-a-time with schema-validated inputs.

---

## Common Patterns

### Create namespace → service → function → execute

```
1. make_namespace(name="acme")
2. make_service(name="tools")
3. make_function(service="tools", name="hello", backend="code_sandbox", template="hello-world")
4. (switch to run endpoint)
5. execute(code='from functions import hello; result = hello(name="World")')
```

### Update function code

```
update_function(service="tools", name="hello", code="def main(input_data): ...")
```

### Roll back a function

```
describe_function(service="tools", name="hello")  # check version history
update_function(service="tools", name="hello", restore_version=1)
```

### Use packages

```
make_function(
  service="data", name="analyze",
  backend="code_sandbox",
  requirements=["pandas", "numpy"],
  code="import pandas as pd\nimport numpy as np\ndef main(input_data): ...",
  input_schema={...}
)
```

---

## Anti-Patterns

| Don't | Do Instead |
|-------|-----------|
| `pip install` in function code | Declare in `requirements` field |
| Use `os.system` / `subprocess` | These are blocked by seccomp |
| Return large binary data | Return references or summaries |
| Hardcode API keys in function code | Declare `required_env` and pass via `X-MCPWorks-Env` header |
| Create functions without `input_schema` | Always define schemas for better AI discovery |

---

## Error Reference

| Error | Cause | Fix |
|-------|-------|-----|
| `QUOTA_EXCEEDED` (429) | Monthly execution limit hit | Upgrade tier or wait for reset |
| `Unknown template: X` | Invalid template name | Use `list_templates` to see valid names |
| `Package 'X' is not in the allowed list` | Invalid requirement | Use `list_packages` to see allowed packages |
| `Execution timed out` | Code exceeded tier timeout | Optimize code or upgrade tier |
| `No code provided` | Empty code in execute/make_function | Provide code or use a template |
| `Invalid tool name format` | Tool mode name missing `.` | Use `service.function` format |
| `Authentication failed` | Bad or missing API key | Check Authorization header |
| `INVALID_ENDPOINT` | Invalid endpoint type | Use `/mcp/{create|run|agent}/{namespace}` |

---

## Auth Flow

1. Create admin account: `seed_admin.py` script (see [Getting Started](GETTING-STARTED.md#5-create-your-admin-account))
2. Login: `POST /v1/auth/login` → JWT tokens
3. Create API key: `POST /v1/auth/api-keys` (requires JWT) or use the console
4. Use API key in MCP: `Authorization: Bearer {raw_key}`

Public registration is disabled by default. Set `ALLOW_REGISTRATION=true` in `.env` to enable `POST /v1/auth/register`.

API keys can also be exchanged for JWTs via `POST /v1/auth/token`.

## Observability

Prometheus metrics at `GET /metrics`. Health checks at `/v1/health`, `/v1/health/live`, `/v1/health/ready`. Security audit log at `GET /v1/audit/logs` (admin only). All logs are structured JSON with `X-Request-ID` correlation.

Key metric families: `http_requests_total`, `sandbox_executions_total`, `mcpworks_agent_runs_total`, `mcpworks_agent_tool_calls_total`, `mcpworks_mcp_proxy_calls_total`, `mcpworks_function_calls_total`, `mcpworks_auth_attempts_total`, `mcpworks_security_events_total`. Full list in [SELF-HOSTING.md](SELF-HOSTING.md#available-metrics).
