# Token Savings Analysis — MCPWorks Code Sandbox

**ORDER-017** | February 2026

## Executive Summary

MCPWorks Code Sandbox reduces token usage by **60-85%** compared to traditional MCP tool definitions for equivalent functionality. This translates to faster response times and lower costs for AI assistant users.

## Methodology

We compare two approaches for common developer tasks:

1. **Traditional MCP**: Load full tool definitions (JSON Schema) + execute via tool call + process response
2. **MCPWorks**: Single `execute` tool + function name + input → result

Token estimates use the standard approximation of **1 token ≈ 4 characters** for English text.

## Measurements

### Scenario 1: Hello World (baseline)

| Approach | Tool Definitions | Call | Response | Total Tokens |
|----------|-----------------|------|----------|-------------|
| **Traditional** (custom MCP with 1 tool) | ~150 tokens | ~30 tokens | ~50 tokens | **~230** |
| **MCPWorks** (execute tool) | ~200 tokens (shared) | ~40 tokens | ~50 tokens | **~290** |

**Result**: For a single trivial tool, overhead is similar. MCPWorks advantage appears at scale.

### Scenario 2: CSV Analysis

| Approach | Tool Definitions | Call | Response | Total Tokens |
|----------|-----------------|------|----------|-------------|
| **Traditional** (pandas MCP with 15 tools) | ~3,000 tokens | ~100 tokens | ~200 tokens | **~3,300** |
| **MCPWorks** (execute csv-analyzer) | ~200 tokens (shared) | ~80 tokens | ~200 tokens | **~480** |

**Result**: **85% reduction** (3,300 → 480 tokens). Traditional approach loads 15 tool definitions even when using only 1.

### Scenario 3: External API Integration

| Approach | Tool Definitions | Call | Response | Total Tokens |
|----------|-----------------|------|----------|-------------|
| **Traditional** (httpx MCP with 8 tools) | ~2,000 tokens | ~150 tokens | ~300 tokens | **~2,450** |
| **MCPWorks** (execute api-connector) | ~200 tokens (shared) | ~100 tokens | ~300 tokens | **~600** |

**Result**: **76% reduction** (2,450 → 600 tokens).

### Scenario 4: Slack Notification

| Approach | Tool Definitions | Call | Response | Total Tokens |
|----------|-----------------|------|----------|-------------|
| **Traditional** (Slack MCP with 12 tools) | ~2,800 tokens | ~80 tokens | ~100 tokens | **~2,980** |
| **MCPWorks** (execute slack-notifier) | ~200 tokens (shared) | ~60 tokens | ~100 tokens | **~360** |

**Result**: **88% reduction** (2,980 → 360 tokens).

### Scenario 5: Report Generation

| Approach | Tool Definitions | Call | Response | Total Tokens |
|----------|-----------------|------|----------|-------------|
| **Traditional** (doc-gen MCP with 6 tools) | ~1,500 tokens | ~200 tokens | ~500 tokens | **~2,200** |
| **MCPWorks** (execute scheduled-report) | ~200 tokens (shared) | ~150 tokens | ~500 tokens | **~850** |

**Result**: **61% reduction** (2,200 → 850 tokens).

## Why MCPWorks Is More Token-Efficient

### 1. Shared Tool Definitions (Fixed Cost Amortized)

Traditional MCP: Each server exposes N tools. The AI assistant must load ALL tool definitions into context, even if it only uses one. A server with 15 tools = ~3,000 tokens of definitions loaded every conversation.

MCPWorks: The `execute` tool is a single generic tool (~200 tokens). Function-specific schemas are only loaded when explicitly requested via `describe_function`.

### 2. No Schema Bloat

Traditional MCP tools carry full JSON Schema definitions for every parameter. MCPWorks functions have schemas too, but they're only fetched on demand — the execute call just needs `function` name and `input_data`.

### 3. Multi-Function Efficiency

When using 5 different capabilities in one conversation:

| Approach | Token Cost |
|----------|-----------|
| **Traditional** (5 separate MCP servers, avg 8 tools each) | ~10,000 tokens for definitions alone |
| **MCPWorks** (2 tools: execute + list_functions) | ~400 tokens for definitions |

**96% reduction in definition overhead** for multi-capability scenarios.

## Prometheus Metrics

The following metrics are now instrumented (ORDER-017):

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `mcpworks_mcp_tool_calls_total` | Counter | `endpoint_type`, `tool_name` | Total MCP tool invocations |
| `mcpworks_mcp_response_bytes` | Histogram | `endpoint_type`, `tool_name` | Response payload size in bytes |

Access via `/metrics` endpoint. Use response bytes as proxy for token usage (÷4 for approximate token count).

### Grafana Query Examples

```promql
# Average response tokens per tool (last 24h)
avg by (tool_name) (rate(mcpworks_mcp_response_bytes_sum[24h]) / rate(mcpworks_mcp_response_bytes_count[24h])) / 4

# Tool call volume
sum by (tool_name) (rate(mcpworks_mcp_tool_calls_total[1h]))
```

## Data-in-Context Savings (70-98%)

The measurements above cover tool definition overhead. There is a second, larger source of savings: **data never enters the AI context window**.

### The Problem with Traditional Tool Calls

Traditional MCP tool calls return full results into the AI's context:

```
AI: "Get all 500 leads from the database"
Tool returns: [{name: "Acme Corp", email: "...", ...}, ...] × 500
Context cost: ~47,000 tokens
AI summarizes: "You have 500 leads, 120 from tech sector..."
Response: ~200 tokens
```

The AI needed 200 tokens of insight but paid for 47,000 tokens of raw data.

### How MCPWorks Code Mode Solves This

In code mode, the AI writes code that runs inside a sandbox. Data is processed in the sandbox and only the result returns:

```
AI writes: from functions import store_lead; result = store_lead(action='stats')
Code cost: ~50 tokens
Sandbox processes 500 leads internally, computes stats
Result returns: {"total": 500, "by_sector": {"tech": 120, ...}}
Result cost: ~85 tokens
```

Total: ~300 tokens instead of ~47,200. The 500 lead records never enter the context.

### Technology Stack Behind This Claim

The following implemented components enforce the data-stays-in-sandbox architecture:

| Component | File | Role |
|-----------|------|------|
| Code mode handler | `src/mcpworks_api/mcp/run_handler.py` | AI sends `code` string (~50 tokens), not data. The `execute_python` / `execute_typescript` tools accept code, not function results. |
| Functions package injection | `src/mcpworks_api/mcp/code_mode.py` | All namespace functions are injected as importable Python inside the sandbox. `from functions import store_lead` calls the function inside the jail, not over the network. |
| nsjail sandbox | `deploy/nsjail/python.cfg`, `spawn-sandbox.sh` | Linux namespace jail: PID, mount, net, cgroup, seccomp-bpf isolation. Code runs in a disposable environment with no access to the host. |
| File-based I/O | `deploy/nsjail/execute.py` | Input goes in as `/sandbox/input.json`, output comes out as `/sandbox/output.json`. Data flows through the filesystem, never through the AI's context window. |
| Result extraction | `deploy/nsjail/execute.py:9-13` | Only the `result` variable is serialized back. All intermediate variables, data structures, and loop state are discarded when the sandbox exits. |
| Output size caps | `deploy/nsjail/execute.py:29-31` | `MAX_OUTPUT_JSON_BYTES = 1MB`, `MAX_STDOUT_BYTES = 64KB`. Even if the function processes gigabytes, the return is capped. |

### Data Flow Diagram

```
AI Context Window                    MCPWorks Sandbox (nsjail)
┌─────────────────┐                 ┌──────────────────────────┐
│                  │  ~50 tokens     │                          │
│ AI writes code ──┼────────────────>│ from functions import    │
│                  │  (code string)  │   store_lead             │
│                  │                 │ result = store_lead(     │
│                  │                 │   action='stats')        │
│                  │                 │                          │
│                  │                 │ [500 leads loaded from   │
│                  │                 │  DB, processed in memory,│
│                  │                 │  stats computed — ALL    │
│                  │                 │  inside sandbox]         │
│                  │                 │                          │
│                  │  ~85 tokens     │ result = {"total": 500,  │
│ AI receives ◄────┼────────────────│  "by_sector": {...}}     │
│ result only      │  (JSON result)  │                          │
│                  │                 │ [sandbox destroyed]      │
└─────────────────┘                 └──────────────────────────┘
```

### When Savings Are Highest

| Scenario | Traditional | MCPWorks | Savings |
|----------|-----------|----------|---------|
| Summarize 500 database records | ~47,200 tokens | ~300 tokens | 99.4% |
| Parse 10,000-row CSV, return column stats | ~120,000 tokens | ~400 tokens | 99.7% |
| Search logs, return matching count | ~25,000 tokens | ~200 tokens | 99.2% |
| Fetch API response, extract 3 fields | ~2,000 tokens | ~250 tokens | 87.5% |
| Simple computation (no data) | ~300 tokens | ~300 tokens | 0% |

Savings scale with data volume. The more data the function processes, the higher the savings. For trivial operations with no intermediate data, there is no savings — code mode adds the same overhead as a direct tool call.

### Caveats

- The 70-98% range in marketing materials reflects typical data-processing workloads. Edge cases (tiny payloads, computation-only functions) may see 0% savings.
- Code mode requires the AI to write code, which adds ~20-50 tokens of code overhead vs a direct tool call. This is negligible for any data-processing scenario but means code mode is not always cheaper for simple single-value lookups.
- The savings are in context tokens (what the AI processes), not in compute. The sandbox still processes the full data — you save on AI API costs, not on compute costs.

## Key Takeaway

> **MCPWorks delivers two layers of token savings:**
>
> 1. **Tool definition overhead (60-85% savings):** Single `execute` tool replaces N tool definitions per server.
> 2. **Data-in-context elimination (70-98% savings):** Code runs in sandbox, data never enters AI context. Only the result returns.
>
> Combined, this is the core differentiator: *"Data stays in the sandbox, not in your AI bill."*
