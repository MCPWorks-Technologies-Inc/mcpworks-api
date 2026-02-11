# MCP Token Optimization Strategies

**Version:** 1.0
**Created:** 2025-10-30
**Status:** Implementation Guidance
**Purpose:** Token efficiency patterns for production MCP server

---

## Overview

Token efficiency is crucial for MCP viability, especially at scale. This document outlines strategies to minimize token consumption while maintaining functionality.

**Key Principle:** MCPs should act like smart indexes, not data dumps. They should help the LLM locate and retrieve exactly what's needed, when it's needed, in the most compact form possible.

---

## 1. Smart Tool Definition Design

### Minimize Schema Verbosity

**Bad - Verbose descriptions (50+ tokens):**
```python
{
  "name": "search_database",
  "description": "This tool searches through our company database to find records matching your query. It can search across multiple tables including customers, orders, products, and inventory...",
}
```

**Good - Concise but clear (6 tokens):**
```python
{
  "name": "search_database",
  "description": "Search company records by query",
  "tables": ["customers", "orders", "products"]  # metadata separate
}
```

### Progressive Disclosure of Capabilities

- Start with a single "router" tool that determines what's needed
- Only expose specialized tools when relevant to the conversation
- Use tool grouping/namespacing to reduce initial load

**Example:**
```python
# Instead of exposing 19 tools immediately:
tools = [
    "provision_service",
    "get_service_status",
    "scale_service",
    "deprovision_service",
    "deploy_application",
    # ... 14 more tools
]

# Start with router:
tools = [
    {
        "name": "multisphere_router",
        "description": "Route to infrastructure, deployment, or integration tools",
        "categories": ["infra", "deploy", "domain", "integrations"]
    }
]

# Expose detailed tools only when category selected
```

---

## 2. Response Data Optimization

### Smart Truncation with Token Awareness

```python
def fetch_records(query, max_tokens=500):
    results = database.search(query)

    # Token-aware pagination
    included_results = []
    token_count = 0

    for result in results:
        result_tokens = estimate_tokens(result)
        if token_count + result_tokens > max_tokens:
            return {
                "data": included_results,
                "has_more": True,
                "continue_token": result.id
            }
        included_results.append(result)
        token_count += result_tokens

    return {"data": included_results, "has_more": False}
```

### Return References, Not Full Data

**Bad - Full documents:**
```python
return {"document": "Here's the entire 10,000 word document..."}
```

**Good - Summaries + retrieval handles:**
```python
return {
    "summary": "Q3 report showing 15% growth",
    "key_points": ["Revenue: $2.1M", "Costs: $1.8M"],
    "doc_id": "doc_q3_2024",
    "fetch_sections": ["exec_summary", "financials", "forecast"]
}
```

**mcpworks Application:**
```python
# Don't return full deployment logs
return {
    "status": "deploying",
    "progress": "Installing dependencies (3/12)",
    "stream_url": "https://logs.multisphere.ca/deploy/abc123",
    "key_events": [
        "✓ Repository cloned",
        "✓ Dependencies cached",
        "→ Installing packages..."
    ]
}
```

---

## 3. Intelligent Caching & State Management

### Conversation-Aware Caching

```python
class MCPCache:
    def __init__(self):
        self.conversation_cache = {}
        self.ttl = 300  # 5 minutes

    def get_or_fetch(self, key, fetch_fn):
        if key in self.conversation_cache:
            return {"ref": f"cached_{key}", "tokens": 10}

        data = fetch_fn()
        self.conversation_cache[key] = data
        return data
```

### Incremental Updates

- Don't re-send entire datasets on each query
- Send deltas/changes only
- Reference previously sent data by ID

**Example:**
```python
# First query
{
    "service_id": "srv_abc123",
    "status": "running",
    "metrics": {"cpu": 45, "mem": 62, "disk": 30}
}

# Subsequent queries - delta only
{
    "service_id": "srv_abc123",
    "changes": {"metrics.cpu": 52}  # Only what changed
}
```

---

## 4. Query Result Optimization

### Semantic Compression

```python
def compress_for_llm(data):
    """
    Remove redundant fields
    Flatten nested structures
    Use abbreviations for common terms
    Strip unnecessary whitespace/formatting
    """

    return {
        "custId": data["customer_identifier"],  # Shortened keys
        "ord": data["orders"][:5],  # Limit arrays
        "tot": data["total_revenue"],  # Abbreviate
        # Skip fields like created_at, updated_by, etc.
    }
```

### Dynamic Field Selection

```python
def fetch_customer(id, fields=None):
    """Let the LLM request only needed fields"""
    if not fields:
        fields = ["name", "status", "balance"]  # Minimal default

    customer = database.get_customer(id)
    return {k: v for k, v in customer.items() if k in fields}
```

**mcpworks Application:**
```python
def get_service_status(service_id, detail_level="summary"):
    """
    summary: name, status, region (20 tokens)
    standard: + resources, costs (50 tokens)
    detailed: + metrics, logs preview (200 tokens)
    full: + complete logs, history (1000+ tokens)
    """
    service = services.get(service_id)

    if detail_level == "summary":
        return {
            "id": service.id,
            "status": service.status,
            "region": service.region
        }
    # ... other detail levels
```

---

## 5. Tool Response Strategies

### Implement "Zoom Levels"

```python
class DataProvider:
    def search(self, query, detail_level="summary"):
        """
        summary: 50 tokens
        standard: 200 tokens
        detailed: 1000 tokens
        full: unlimited
        """
        results = self._search(query)
        return self._format_by_level(results, detail_level)
```

### Streaming for Large Responses

- Stream chunks as needed rather than loading everything upfront
- Allow LLM to stop retrieval when sufficient information is found
- Use Server-Sent Events (SSE) for real-time progress updates

**mcpworks Deployment Streaming:**
```python
def deploy_application(repo_url, branch="main"):
    """Stream deployment progress via SSE"""
    deployment = create_deployment(repo_url, branch)

    return {
        "deployment_id": deployment.id,
        "stream_url": f"/v1/deployments/{deployment.id}/stream",
        "initial_status": "queued",
        # LLM subscribes to stream_url for updates
    }
```

---

## 6. MCP-Level Optimizations

### Batch Operations

**Bad - Multiple tool calls:**
```python
get_customer(123)  # 100 tokens
get_orders(123)    # 200 tokens
get_invoices(123)  # 150 tokens
# Total: 450 tokens + 3 round trips
```

**Good - Single batched call:**
```python
get_customer_context(123, include=["orders", "invoices"])  # 300 tokens total, 1 round trip
```

**mcpworks Application:**
```python
def provision_complete_stack(config):
    """Single tool call to provision service + domain + SSL + integrations"""
    return {
        "service": provision_service(config.service),
        "domain": register_domain(config.domain),
        "ssl": provision_ssl(config.domain),
        "stripe": setup_stripe_account(config.stripe) if config.stripe else None,
        # All in one response, ~500 tokens vs 4 separate calls
    }
```

### Token Budgets

```python
class TokenAwareMCP:
    def __init__(self, max_tokens_per_turn=2000):
        self.token_budget = max_tokens_per_turn

    def execute_tool(self, tool, params):
        result = tool.execute(params)
        tokens_used = estimate_tokens(result)

        if tokens_used > self.token_budget:
            return self.summarize_result(result, self.token_budget)

        self.token_budget -= tokens_used
        return result
```

---

## 7. Architecture Patterns

### Two-Tier Approach

**Tier 1: Lightweight MCP** (runs in LLM context)
- Routing and minimal tools
- Token-efficient tool definitions
- Caching layer

**Tier 2: Heavy MCP** (remote service)
- Actual data processing
- Returns compressed results
- Handles streaming

```
┌─────────────────────────────────────────┐
│           AI Assistant (Claude)         │
│  ┌───────────────────────────────────┐  │
│  │   Lightweight MCP Client (Tier 1) │  │
│  │   - Tool routing (~100 tools)     │  │
│  │   - Result caching                │  │
│  │   - Token budget tracking         │  │
│  └──────────────┬────────────────────┘  │
└─────────────────┼───────────────────────┘
                  │ HTTPS
                  ▼
┌─────────────────────────────────────────┐
│    mcpworks Infrastructure MCP Server (Tier 2)     │
│  ┌───────────────────────────────────┐  │
│  │   FastAPI + Compression Layer     │  │
│  │   - Data processing               │  │
│  │   - Semantic compression          │  │
│  │   - Streaming responses (SSE)     │  │
│  └───────────────────────────────────┘  │
└─────────────────────────────────────────┘
```

### Specialized Compression Models

- Run a smaller model to pre-summarize data before sending to main LLM
- Implement semantic search to retrieve only relevant chunks
- Use embeddings to find most relevant sections of large documents

**Example:**
```python
def compress_logs(logs, max_tokens=500):
    """Use small model to extract key information"""
    # Run logs through summarization model
    summary = summarization_model.summarize(logs, max_length=max_tokens)

    return {
        "summary": summary,
        "error_count": count_errors(logs),
        "warnings": extract_warnings(logs)[:5],
        "full_logs_url": upload_to_s3(logs)  # Reference for deep dive
    }
```

---

## 8. mcpworks-Specific Optimizations

### Usage Tracking Optimization

**Instead of:**
```python
{
    "service_id": "srv_abc123",
    "plan": "standard-4gb",
    "region": "tor1",
    "os": "ubuntu-22-04",
    "cpu": "2 vCPUs",
    "memory": "4 GB",
    "disk": "80 GB SSD",
    "bandwidth": "4 TB transfer",
    "ipv4": "1 IPv4 address",
    "ipv6": "Yes",
    "backups": "Weekly automated backups",
    "monitoring": "Basic monitoring included",
    "tier": "founder_pro",
    "executions_count": 1500,
    "executions_limit": 10000,
    "executions_remaining": 8500
}
```

**Use:**
```python
{
    "svc": "srv_abc123",
    "plan": "std-4gb",
    "exec_left": 8500,  # executions remaining
    "tier": "pro",
    "region": "tor1"
    # Full details available via get_service_details(id)
}
```

### Deployment Log Streaming

**Instead of returning full logs:**
```python
{
    "deployment_logs": """
    [2024-10-30 10:00:00] Cloning repository...
    [2024-10-30 10:00:02] Repository cloned successfully
    [2024-10-30 10:00:03] Installing dependencies...
    [2024-10-30 10:00:15] Dependency installation complete
    ... (500 more lines)
    """
}
```

**Stream via SSE with progress markers:**
```python
{
    "id": "deploy_xyz789",
    "status": "deploying",
    "progress": 60,  # percentage
    "stage": "installing_deps",
    "last_event": "✓ Dependencies cached (3/12 complete)",
    "stream": "https://mcp.multisphere.ca/v1/deployments/xyz789/stream",
    "errors": []  # Only if errors occur
}
```

### Integration Status Compression

```python
# Compressed integration status
{
    "integrations": {
        "stripe": {"ok": True, "acct": "acct_abc123"},
        "shopify": {"ok": True, "store": "mystore.myshopify.com"},
        "sendgrid": {"ok": False, "err": "API key invalid"},
        "twilio": None  # Not configured
    }
}
```

---

## 9. Token Estimation Utilities

### Simple Token Estimator

```python
def estimate_tokens(text):
    """
    Rough estimate: 1 token ≈ 4 characters for English
    More accurate: use tiktoken library
    """
    if isinstance(text, dict):
        text = json.dumps(text)
    return len(text) // 4

# Better - use tiktoken
import tiktoken

def estimate_tokens_accurate(text, model="gpt-4"):
    encoding = tiktoken.encoding_for_model(model)
    return len(encoding.encode(text))
```

### Budget Tracking Decorator

```python
def token_budget(max_tokens):
    def decorator(func):
        def wrapper(*args, **kwargs):
            result = func(*args, **kwargs)
            tokens = estimate_tokens(result)

            if tokens > max_tokens:
                logging.warning(f"{func.__name__} exceeded budget: {tokens}/{max_tokens}")
                return compress_result(result, max_tokens)

            return result
        return wrapper
    return decorator

@token_budget(max_tokens=500)
def get_service_status(service_id):
    # Function automatically compressed if over budget
    return service_data
```

---

## 10. Testing & Monitoring

### Token Usage Metrics

```python
class TokenMetrics:
    def __init__(self):
        self.tool_token_usage = defaultdict(list)

    def record(self, tool_name, tokens):
        self.tool_token_usage[tool_name].append(tokens)

    def report(self):
        return {
            tool: {
                "avg": mean(tokens),
                "max": max(tokens),
                "p95": percentile(tokens, 95)
            }
            for tool, tokens in self.tool_token_usage.items()
        }
```

### A/B Testing Compression Strategies

```python
def deploy_application(repo_url, compression_strategy="v2"):
    """Test different response compression strategies"""
    deployment = create_deployment(repo_url)

    if compression_strategy == "v1":
        return format_v1(deployment)  # Baseline
    elif compression_strategy == "v2":
        return format_v2(deployment)  # Optimized

    # Track: success rate, token savings, LLM satisfaction
```

---

## Implementation Priority

**Phase 1: MVP (Must Have)**
1. Concise tool descriptions (<20 tokens each)
2. Smart truncation with `has_more` pagination
3. Return references instead of full data
4. Basic token estimation

**Phase 2: Optimization (Month 3-6)**
5. Conversation-aware caching
6. Zoom levels (summary/standard/detailed)
7. Batch operations
8. Incremental updates (deltas only)

**Phase 3: Advanced (Month 6-12)**
9. Two-tier architecture with compression layer
10. Specialized compression models
11. Token budget tracking per conversation
12. Automated compression optimization

---

## Success Metrics

**Target Token Efficiency:**
- Tool definitions: <500 tokens total (19 tools × ~25 tokens each)
- Average tool response: <200 tokens
- Complex operation (e.g., full stack deployment): <1000 tokens
- Streaming responses: <50 tokens per update

**Comparison to Competitors:**
- AWS MCP (hypothetical): 2000-5000 tokens per operation
- GCP MCP (hypothetical): 1500-4000 tokens per operation
- mcpworks target: 200-1000 tokens per operation (2-5x more efficient)

---

## References

- [MCP Protocol Specification](https://spec.modelcontextprotocol.io/)
- [tiktoken - OpenAI's tokenizer](https://github.com/openai/tiktoken)
- [Anthropic Claude token limits](https://docs.anthropic.com/claude/docs/models-overview)

---

## Changelog

**v1.0 (2025-10-30):**
- Initial token optimization guidance
- 10 core optimization strategies
- mcpworks-specific patterns
- Implementation priority framework
