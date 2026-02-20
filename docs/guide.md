# MCPWorks Platform Guide

MCPWorks is a code execution platform for AI assistants. You create Python functions through the MCP protocol, and AI agents (Claude Code, Codex, GitHub Copilot) can discover and execute them in secure sandboxes.

No servers to manage. No containers to configure. Write a function, and it runs.

---

## Table of Contents

- [Core Concepts](#core-concepts)
- [Getting Started](#getting-started)
- [Two Endpoints](#two-endpoints)
- [Create Endpoint Tools](#create-endpoint-tools)
- [Run Endpoint](#run-endpoint)
- [Writing Function Code](#writing-function-code)
- [Available Packages](#available-packages)
- [Templates](#templates)
- [Versioning](#versioning)
- [Environment Variables](#environment-variables)
- [Billing & Tiers](#billing--tiers)
- [Sandbox Limits](#sandbox-limits)
- [Code Mode Deep Dive](#code-mode-deep-dive)
- [End-to-End Examples](#end-to-end-examples)

---

## Core Concepts

### Namespaces

A namespace is your top-level organizational unit. It maps to a subdomain pair:

- `myns.create.mcpworks.io` — management
- `myns.run.mcpworks.io` — execution

Namespace names must be DNS-compliant: lowercase alphanumeric with hyphens, 1–63 characters, must start and end with an alphanumeric character.

### Services

Services group related functions within a namespace. Think of them as folders. A namespace can have many services, each with many functions.

### Functions

A function is a unit of executable Python code with:

- **Code** — the Python source
- **Input schema** — JSON Schema describing expected parameters
- **Output schema** — JSON Schema describing the return value
- **Backend** — execution engine (`code_sandbox` for Python)
- **Requirements** — Python packages needed (from the allow-list)
- **Tags** — optional labels for filtering

### Versions

Every code change creates a new immutable version. You can restore any previous version. The active version is always the latest.

### Backends

Currently supported: `code_sandbox` (secure Python execution via nsjail). Future backends include `activepieces` (workflow orchestration), `nanobot`, and `github_repo`.

---

## Getting Started

### 1. Create Your Account

Register at `https://api.mcpworks.io/register` with your email. You get 100 free function executions per month.

### 2. Get Your API Key

After registration, log in at `https://api.mcpworks.io/login`. From the dashboard, create an API key. The raw key is shown only once — save it.

### 3. Connect Your AI Assistant

Add this to your project's `.mcp.json` (or `~/.claude/settings.json` for global access):

```json
{
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
}
```

Replace `myns` with your namespace name and `YOUR_API_KEY` with your actual key.

### 4. Create a Service and Function

Ask your AI assistant:

> "Create a service called 'utils' in my MCPWorks namespace, then create a hello-world function using the hello-world template."

### 5. Execute It

> "Run hello-world with name 'MCPWorks'"

---

## Two Endpoints

Every namespace gets two MCP endpoints, each serving a different purpose:

### Create Endpoint — `{namespace}.create.mcpworks.io/mcp`

Management operations. Use this to:

- Create/list/delete namespaces, services, and functions
- Browse available packages and templates
- Inspect function details and version history

**Not metered.** Management calls don't count against your execution quota.

### Run Endpoint — `{namespace}.run.mcpworks.io/mcp`

Function execution. Operates in two modes:

| Mode | URL | Tools Exposed | Use Case |
|------|-----|---------------|----------|
| **Code mode** (default) | `.../mcp` or `.../mcp?mode=code` | Single `execute` tool | Write Python that imports and calls your functions |
| **Tool mode** | `.../mcp?mode=tools` | One tool per function | AI calls functions directly by name |

**Metered.** Each execution counts against your monthly quota.

---

## Create Endpoint Tools

The create endpoint exposes 13 tools:

### Namespace Management

#### `make_namespace`

Create a new namespace.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `name` | string | Yes | Namespace name (lowercase, alphanumeric, hyphens, 1-63 chars) |
| `description` | string | No | Optional description |

Returns the namespace ID, name, and both endpoint URLs.

#### `list_namespaces`

List all namespaces for your account. No parameters.

Returns array of namespaces with name, description, call_count, and endpoint URLs.

### Service Management

#### `make_service`

Create a new service in the current namespace.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `name` | string | Yes | Service name |
| `description` | string | No | Optional description |

#### `list_services`

List all services in the current namespace. No parameters.

Returns array of services with name, description, function_count, and call_count.

#### `delete_service`

Delete a service and all its functions.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `name` | string | Yes | Service name to delete |

### Function CRUD

#### `make_function`

Create a new function in a service.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `service` | string | Yes | Service name |
| `name` | string | Yes | Function name |
| `backend` | string | Yes | Execution backend: `code_sandbox`, `activepieces`, `nanobot`, `github_repo` |
| `code` | string | No | Python source code |
| `config` | object | No | Backend-specific configuration |
| `input_schema` | object | No | JSON Schema for input parameters |
| `output_schema` | object | No | JSON Schema for output |
| `description` | string | No | Human-readable description |
| `tags` | string[] | No | Tags for filtering |
| `requirements` | string[] | No | Python packages from the allow-list |
| `required_env` | string[] | No | Environment variables required for execution (e.g., `["OPENAI_API_KEY"]`) |
| `optional_env` | string[] | No | Optional environment variables the function can use |
| `template` | string | No | Clone from a template (overrides code/schemas/requirements) |

If `template` is provided, it fills in code, schemas, description, tags, and requirements as defaults. Explicit arguments override template values.

Requirements are validated against the allow-list. Use `list_packages` to see what's available.

#### `update_function`

Update a function. Creates a new version if code, config, schemas, or requirements change.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `service` | string | Yes | Service name |
| `name` | string | Yes | Function name |
| `backend` | string | No | New execution backend |
| `code` | string | No | New Python source code |
| `config` | object | No | New backend configuration |
| `input_schema` | object | No | New input schema |
| `output_schema` | object | No | New output schema |
| `description` | string | No | New description |
| `tags` | string[] | No | New tags |
| `requirements` | string[] | No | New package requirements |
| `required_env` | string[] | No | New required environment variables |
| `optional_env` | string[] | No | New optional environment variables |
| `restore_version` | integer | No | Restore code from a previous version number |

#### `delete_function`

Delete a function permanently.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `service` | string | Yes | Service name |
| `name` | string | Yes | Function name |

#### `list_functions`

List functions in a service.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `service` | string | Yes | Service name |
| `tag` | string | No | Filter by tag |

Returns array of functions with qualified name (`service.function`), description, version, tags, and call_count.

#### `describe_function`

Get detailed function info including version history.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `service` | string | Yes | Service name |
| `name` | string | Yes | Function name |

Returns full details: code, schemas, all versions, backend, requirements, and metadata.

### Discovery

#### `list_packages`

List all available Python packages for sandbox functions, grouped by category. No parameters.

Returns packages organized by category (http, data_formats, validation, text, datetime, data_science, visualization, ai, cloud, file_formats, security, database, utilities).

#### `list_templates`

List available function templates for quick-start. No parameters.

Returns summary of each template: name, description, tags, requirements.

#### `describe_template`

Get full template details including code and schemas.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `name` | string | Yes | Template name (e.g., `hello-world`, `csv-analyzer`) |

Returns complete template: name, description, code, input_schema, output_schema, tags, requirements.

---

## Run Endpoint

### Tool Mode (`?mode=tools`)

Each function in your namespace becomes an individual MCP tool. The tool name is `service.function` (e.g., `utils.hello`). The AI calls them directly with the function's input_schema as parameters.

Best for: AI agents that need to call specific functions by name with structured parameters.

### Code Mode (default, `?mode=code`)

A single `execute` tool is exposed. The AI writes Python code that imports and calls your functions from a generated `functions` package.

**The `execute` tool:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `code` | string | Yes | Python code to execute |

Best for: Complex workflows, chaining multiple functions, data transformation between calls.

See [Code Mode Deep Dive](#code-mode-deep-dive) for details.

---

## Writing Function Code

Functions run in a Python sandbox. Your code receives input and must produce output using one of three conventions:

### Convention 1: `main(input_data)` function (recommended)

```python
def main(input_data):
    name = input_data.get("name", "World")
    return {"greeting": f"Hello, {name}!"}
```

### Convention 2: `result` variable

```python
name = input_data.get("name", "World")
result = {"greeting": f"Hello, {name}!"}
```

### Convention 3: `output` variable

```python
name = input_data.get("name", "World")
output = {"greeting": f"Hello, {name}!"}
```

The sandbox checks for these in order: `result` variable → `output` variable → `main()` callable. The first one found is used as the function's return value.

### Input

`input_data` is a dict populated from the function's input_schema. It's always available as a global variable.

### Schemas

Define `input_schema` and `output_schema` as JSON Schema objects when creating a function. These are used to:

- Generate tool parameter descriptions for the AI
- Validate inputs (future)
- Document expected behavior

Example:

```json
{
  "type": "object",
  "properties": {
    "url": { "type": "string", "description": "URL to fetch" },
    "method": { "type": "string", "enum": ["GET", "POST"], "default": "GET" }
  },
  "required": ["url"]
}
```

---

## Available Packages

All packages are pre-installed in the sandbox image. No `pip install` at runtime — this gives instant cold starts and prevents supply-chain attacks.

Specify required packages in the `requirements` field when creating a function. Use `list_packages` to see the full list.

### HTTP & Networking
| Package | Description |
|---------|-------------|
| `requests` | Simple HTTP client library |
| `httpx` | Modern async/sync HTTP client |
| `urllib3` | Low-level HTTP client |
| `aiohttp` | Async HTTP client/server framework |
| `websockets` | WebSocket client and server library |

### Data Formats & Serialization
| Package | Description |
|---------|-------------|
| `pyyaml` | YAML parser and emitter (alias: `yaml`) |
| `orjson` | Fast JSON library (10x faster than stdlib json) |
| `tomli` | TOML parser |
| `tomli-w` | TOML writer |
| `xmltodict` | XML to Python dict and back |
| `msgpack` | MessagePack binary serialization |

### Data Validation
| Package | Description |
|---------|-------------|
| `pydantic` | Data validation using Python type hints |
| `attrs` | Classes without boilerplate |
| `jsonschema` | JSON Schema validation |

### Text & Content Processing
| Package | Description |
|---------|-------------|
| `beautifulsoup4` | HTML and XML parser (alias: `bs4`) |
| `lxml` | Fast XML and HTML processing |
| `markdownify` | Convert HTML to Markdown |
| `markdown` | Markdown to HTML converter |
| `html2text` | Convert HTML to plain text |
| `chardet` | Character encoding detection |
| `python-slugify` | URL slug generator (alias: `slugify`) |
| `jinja2` | Template engine |
| `regex` | Extended regular expressions (superset of stdlib re) |

### Date & Time
| Package | Description |
|---------|-------------|
| `python-dateutil` | Powerful date parsing and manipulation (alias: `dateutil`) |
| `pytz` | Timezone definitions |
| `arrow` | Better dates and times for Python |

### Data Science
| Package | Description |
|---------|-------------|
| `numpy` | Numerical computing with arrays |
| `pandas` | Data manipulation and analysis |
| `scipy` | Scientific computing (optimization, stats, signal) |
| `scikit-learn` | Machine learning (alias: `sklearn`) |
| `sympy` | Symbolic mathematics |
| `statsmodels` | Statistical models and tests |

### Visualization
| Package | Description |
|---------|-------------|
| `matplotlib` | Plotting and visualization |
| `pillow` | Image processing (alias: `PIL`) |

### AI & LLM
| Package | Description |
|---------|-------------|
| `openai` | OpenAI API client (GPT, embeddings, assistants) |
| `anthropic` | Anthropic Claude API client |
| `tiktoken` | OpenAI tokenizer for token counting |
| `cohere` | Cohere API client (embeddings, rerank, generate) |

### Cloud & SaaS APIs
| Package | Description |
|---------|-------------|
| `boto3` | AWS SDK (S3, DynamoDB, Lambda, SES, etc.) |
| `stripe` | Stripe payment processing API |
| `sendgrid` | SendGrid email delivery API |
| `twilio` | Twilio SMS and voice API |
| `google-cloud-storage` | Google Cloud Storage client |

### File Formats
| Package | Description |
|---------|-------------|
| `openpyxl` | Read/write Excel .xlsx files |
| `xlsxwriter` | Write Excel .xlsx files with formatting |
| `tabulate` | Pretty-print tabular data |
| `feedparser` | Parse RSS and Atom feeds |
| `python-docx` | Read/write Word .docx files |
| `pypdf` | Read and manipulate PDF files |

### Crypto & Security
| Package | Description |
|---------|-------------|
| `cryptography` | Cryptographic primitives and recipes |
| `pyjwt` | JSON Web Token encoding/decoding (alias: `jwt`) |
| `bcrypt` | Password hashing |

### Database Clients
| Package | Description |
|---------|-------------|
| `psycopg2-binary` | PostgreSQL database client (alias: `psycopg2`) |
| `pymongo` | MongoDB client |
| `redis` | Redis client |

### Utilities
| Package | Description |
|---------|-------------|
| `humanize` | Human-friendly data formatting |
| `tqdm` | Progress bars for loops |
| `rich` | Rich text and formatting for terminal output |
| `typing-extensions` | Backported typing features |

Package aliases are automatically resolved (e.g., `bs4` → `beautifulsoup4`). Duplicates are silently deduplicated.

---

## Templates

Templates provide working starter code. Use `template` in `make_function` to clone one.

### `hello-world`

Simple input/output function — proves the system works.

- **Tags:** `starter`, `example`
- **Requirements:** none
- **Input:** `name` (string, optional)
- **Output:** `greeting`, `message`

### `csv-analyzer`

Parse CSV data and return summary statistics.

- **Tags:** `data`, `analytics`
- **Requirements:** none (uses stdlib `csv`, `statistics`)
- **Input:** `csv_data` (string, required — raw CSV with header)
- **Output:** `row_count`, `columns`, `stats` (per-column min/max/mean/median or unique values)

### `api-connector`

Call an external API and transform the response.

- **Tags:** `http`, `integration`
- **Requirements:** `httpx`
- **Input:** `url` (required), `method` (GET/POST/PUT/DELETE/PATCH), `headers`, `body`
- **Output:** `status_code`, `headers`, `body`, `ok`

### `slack-notifier`

Send a formatted message to a Slack webhook.

- **Tags:** `notification`, `slack`, `integration`
- **Requirements:** `httpx`
- **Input:** `webhook_url` (required), `text` (required), `channel` (optional)
- **Output:** `sent`, `status_code`, `response`

### `scheduled-report`

Generate and format a structured report from data.

- **Tags:** `reporting`, `formatting`
- **Requirements:** none
- **Input:** `title` (required), `sections` (required — array of `{heading, content}`), `format` (`markdown` or `json`)
- **Output:** `report`, `format`, `generated_at`

---

## Versioning

Functions use immutable versioning:

- **Creating a function** starts at version 1
- **Updating code, config, schemas, requirements, or env declarations** creates a new version (version number increments)
- **Updating only metadata** (description, tags) does not create a new version
- **Restoring** copies a previous version's code/config/schemas/requirements into a new version

Use `describe_function` to see version history. Use `update_function` with `restore_version` to roll back.

---

## Environment Variables

Functions that call external APIs (OpenAI, Stripe, Twilio, etc.) need credentials. MCPWorks supports **stateless environment variable passthrough** — secrets travel with each request and are never stored on our servers.

### How It Works

1. **Declare** which env vars a function needs when you create it
2. **Encode** your secrets as a base64 JSON header
3. **Execute** — the sandbox receives only the declared variables, then they're destroyed

### Step 1: Declare Env Vars

When creating or updating a function, specify `required_env` and/or `optional_env`:

```
make_function(
  service="ai",
  name="summarize",
  backend="code_sandbox",
  required_env=["OPENAI_API_KEY"],
  optional_env=["OPENAI_ORG_ID"],
  code="import openai\ndef main(input_data):\n    import os\n    client = openai.OpenAI(api_key=os.environ['OPENAI_API_KEY'])\n    ...",
  requirements=["openai"]
)
```

### Step 2: Add the Header to `.mcp.json`

Base64-encode a JSON object of key-value pairs and add the `X-MCPWorks-Env` header to your **run** server config:

```json
{
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
}
```

To encode your variables:

```bash
echo -n '{"OPENAI_API_KEY":"sk-xxx","STRIPE_KEY":"sk_live_xxx"}' | base64
```

### Step 3: Check Configuration

Call the `_env_status` tool (available on run endpoints in tool mode via `?mode=tools`) to see which variables are configured and which are missing across all your functions.

### Security Properties

- **Never stored** — values exist only in memory during request processing
- **Never logged** — structlog processors strip env values from all log output
- **Least-privilege** — each function receives only its declared variables, not the full set
- **Destroyed after execution** — env file is unlinked before code runs, dict is cleared after file write
- **Blocked names** — `PATH`, `HOME`, `LD_*`, `PYTHON*`, `NSJAIL*`, `MCPWORKS_*` are rejected to prevent sandbox escape

### Limits

- Maximum 64 variables per request
- Maximum 32 KB total header size
- Variable names must match `^[A-Z][A-Z0-9_]*$`

---

## Billing & Tiers

### Subscription Tiers

| Tier | Price | Executions/Month |
|------|-------|------------------|
| **Free** | $0 | 100 |
| **Founder** | $29/mo | 1,000 |
| **Founder Pro** | $59/mo | 10,000 |
| **Enterprise** | $129/mo | 100,000 |

New accounts start on the free tier.

### What Counts as an Execution

Each successful `tools/call` request to the **run endpoint** counts as one execution. Management operations on the create endpoint are free and unlimited.

### Quota Enforcement

When you hit your monthly limit, run endpoint calls return HTTP 429 with:

```json
{
  "code": "QUOTA_EXCEEDED",
  "message": "Monthly execution limit (100) exceeded",
  "usage": 100,
  "limit": 100,
  "tier": "free"
}
```

Usage resets at the start of each calendar month.

---

## Sandbox Limits

Resource limits vary by tier:

| Resource | Free | Founder | Founder Pro | Enterprise |
|----------|------|---------|-------------|------------|
| **Timeout** | 10 sec | 30 sec | 60 sec | 300 sec |
| **Memory** | 128 MB | 256 MB | 512 MB | 2048 MB |
| **Max PIDs** | 16 | 32 | 64 | 128 |
| **Network hosts** | 0 (none) | 5 | 25 | Unlimited |

The production sandbox uses nsjail with Linux namespaces, cgroups v2, and seccomp-bpf for isolation. Code size is limited to 1 MB.

---

## Code Mode Deep Dive

Code mode is the default run mode. Instead of exposing each function as a separate MCP tool, it exposes a single `execute` tool that accepts arbitrary Python code.

### How It Works

1. The platform generates a `functions/` Python package from your namespace's functions
2. Your code can `import` from this package
3. Each function wrapper calls the actual function code internally
4. Return data by setting `result = ...` in your code

### Discovering Functions

```python
import functions
print(functions.__doc__)
```

This prints a catalog of all functions in the namespace with their signatures and descriptions.

### Calling Functions

```python
from functions import hello
result = hello(name="World")
```

Or import from a specific service module:

```python
from functions.utils import hello, word_count
```

Function names with hyphens are converted to underscores (`my-func` → `my_func`).

### Returning Data

Set `result` to whatever you want returned to the conversation:

```python
from functions import analyze_csv, format_report

data = analyze_csv(csv_data="name,age\nAlice,30\nBob,25")
result = format_report(title="Analysis", sections=[{"heading": "Data", "content": str(data)}])
```

### Call Tracking

The platform tracks which functions your code actually calls. This is used for per-function analytics (call_count) and appears in execution metadata as `called_functions`.

---

## End-to-End Examples

### Example 1: Create and Execute a Simple Function

**Step 1: Create a namespace** (if you don't have one)

> "Create a namespace called 'demo'"

The AI calls `make_namespace(name="demo")`.

**Step 2: Create a service**

> "Create a service called 'math' in my namespace"

The AI calls `make_service(name="math")`.

**Step 3: Create a function**

> "Create a function called 'is-prime' that checks if a number is prime"

The AI calls:
```
make_function(
  service="math",
  name="is-prime",
  backend="code_sandbox",
  code="def main(input_data):\n    n = input_data.get('number', 2)\n    if n < 2:\n        return {'is_prime': False, 'number': n}\n    for i in range(2, int(n**0.5) + 1):\n        if n % i == 0:\n            return {'is_prime': False, 'number': n}\n    return {'is_prime': True, 'number': n}",
  input_schema={
    "type": "object",
    "properties": {
      "number": {"type": "integer", "description": "Number to check"}
    },
    "required": ["number"]
  }
)
```

**Step 4: Execute it (tool mode)**

Connect with `?mode=tools` and call `math.is-prime(number=17)`.

**Step 5: Execute it (code mode)**

Connect with default mode and use the `execute` tool:
```python
from functions import is_prime
result = is_prime(number=17)
```

### Example 2: Using a Template

> "Create a function called 'fetch' in my 'utils' service using the api-connector template"

The AI calls:
```
make_function(
  service="utils",
  name="fetch",
  backend="code_sandbox",
  template="api-connector"
)
```

This clones the template's code, schemas, tags, and requirements (`httpx`).

### Example 3: Code Mode with Multiple Functions

Using the `execute` tool on the run endpoint:

```python
from functions import fetch, analyze_csv

# Fetch CSV from a URL
response = fetch(url="https://example.com/data.csv")

# Analyze it
stats = analyze_csv(csv_data=response["body"])

result = {
    "url": "https://example.com/data.csv",
    "rows": stats["row_count"],
    "columns": stats["columns"],
    "statistics": stats["stats"]
}
```

### Example 4: Updating a Function

> "Update my is-prime function to also return the factors if not prime"

The AI calls `update_function(service="math", name="is-prime", code="...")` which creates version 2.

> "Actually, restore the original version"

The AI calls `update_function(service="math", name="is-prime", restore_version=1)` which creates version 3 with v1's code.
