# MCPWorks LLM Agent Reference

> Structured reference for AI agents operating MCPWorks. Optimized for system-prompt consumption.

---

## Platform Summary

MCPWorks = serverless Python functions managed and executed via MCP protocol.
Two endpoints per namespace. Create endpoint for CRUD. Run endpoint for execution.
All code runs in nsjail sandboxes. 59 packages pre-installed. No pip at runtime.

---

## MCP Configuration

```json
{
  "mcpServers": {
    "{ns}-create": {
      "type": "http",
      "url": "https://{ns}.create.mcpworks.io/mcp",
      "headers": { "Authorization": "Bearer {API_KEY}" }
    },
    "{ns}-run": {
      "type": "http",
      "url": "https://{ns}.run.mcpworks.io/mcp",
      "headers": { "Authorization": "Bearer {API_KEY}" }
    }
  }
}
```

---

## Endpoints

| Endpoint | Pattern | Purpose | Metered |
|----------|---------|---------|---------|
| Create | `{ns}.create.mcpworks.io/mcp` | Namespace/service/function CRUD | No |
| Run (code mode) | `{ns}.run.mcpworks.io/mcp` | Single `execute` tool, write Python | Yes |
| Run (tool mode) | `{ns}.run.mcpworks.io/mcp?mode=tools` | One tool per function | Yes |

Default run mode is **code** (no query param needed).

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
| `make_function` | `service`, `name`, `backend` | `code`, `config`, `input_schema`, `output_schema`, `description`, `tags`, `requirements`, `template` | `template` overrides code/schemas/reqs as defaults |
| `update_function` | `service`, `name` | `backend`, `code`, `config`, `input_schema`, `output_schema`, `description`, `tags`, `requirements`, `restore_version` | Code/config/schema/req changes → new version |
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
| `code_sandbox` | Active | Secure Python execution (nsjail) |
| `activepieces` | Future | Workflow orchestration |
| `nanobot` | Future | — |
| `github_repo` | Future | — |

Always use `code_sandbox` for now.

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

## Tier Limits

### Execution Quotas (per month)

| Tier | Price | Executions |
|------|-------|------------|
| free | $0 | 100 |
| founder | $29 | 1,000 |
| founder_pro | $59 | 10,000 |
| enterprise | $129 | 100,000 |

### Sandbox Resources (per execution)

| Resource | free | founder | founder_pro | enterprise |
|----------|------|---------|-------------|------------|
| Timeout | 10s | 30s | 60s | 300s |
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
| Hardcode API keys in function code | Use environment variables (future) |
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
| `INVALID_HOST` | Wrong subdomain format | Use `{ns}.{create|run}.mcpworks.io` |

---

## Auth Flow

1. Register: `POST /v1/auth/register` (email, password, name, accept_tos)
2. Login: `POST /v1/auth/login` → JWT tokens
3. Create API key: `POST /v1/auth/api-keys` (requires JWT)
4. Use API key in MCP: `Authorization: Bearer {raw_key}`

API keys can also be exchanged for JWTs via `POST /v1/auth/token`.
