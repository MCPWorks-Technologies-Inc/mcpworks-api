# Token Efficiency Requirements

**Target:** 200-1000 tokens per operation (80%+ operations under 500 tokens)

## Critical Optimization Patterns

### 1. Progressive Disclosure

```json
// Bad: Return full service details (2000+ tokens)
{
  "service_id": "svc_123",
  "full_config": {...},
  "all_metrics": {...},
  "complete_history": [...]
}

// Good: Return reference with expansion option (200 tokens)
{
  "service_id": "svc_123",
  "status": "running",
  "url": "https://api.mcpworks.io/v1/services/svc_123"
}
```

### 2. Semantic Compression

```json
// Bad: Verbose error message (150 tokens)
"The deployment failed because the Git repository could not be cloned due to invalid credentials. Please check that..."

// Good: Structured error (50 tokens)
{
  "error": "git_clone_failed",
  "reason": "invalid_credentials",
  "action": "verify_ssh_key"
}
```

### 3. References Over Full Data

```json
// Return resource URLs, not full objects
{
  "services": [
    {"id": "svc_1", "url": "/v1/services/svc_1"},
    {"id": "svc_2", "url": "/v1/services/svc_2"}
  ]
}
```

**Deep dive:** [docs/implementation/guidance/mcp-token-optimization.md](../implementation/guidance/mcp-token-optimization.md)
