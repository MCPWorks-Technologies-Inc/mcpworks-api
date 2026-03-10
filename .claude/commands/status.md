Run a full MCPWorks platform status check using the admin function suite via `mcp__mcpworks-run__execute`.

Execute these three batches sequentially. Each batch is a single `mcp__mcpworks-run__execute` call.

**Batch 1 — Core health:**
```python
from functions import admin
result = {
    "stats": admin.stats(),
    "health": admin.system_health(),
    "resources": admin.system_resources(),
}
```

**Batch 2 — Issues and diagnostics:**
```python
from functions import admin
result = {
    "errors": admin.errors(since="24h"),
    "security_events": admin.security_events(since="24h", limit=10),
    "rate_limits": admin.rate_limits(),
}
```

**Batch 3 — Infrastructure:**
```python
from functions import admin
result = {
    "database": admin.system_database(),
    "redis": admin.system_redis(),
    "usage": admin.usage(),
}
```

After collecting all data, present a concise dashboard:

```
## MCPWorks Status

**Platform:** X users | X namespaces | X functions | X total calls
**Uptime:** Xd Xh | CPU: X | Memory: X% | Disk: X%
**Database:** [healthy/unhealthy] | Pool: X/X | Size: X MB | Active: X connections
**Redis:** [healthy/unhealthy] | Memory: X | Clients: X | Commands: X
**Errors (24h):** X failures / X total (X% failure rate)
**Security (24h):** X events — breakdown by severity
**Rate Limits:** X currently throttled
**Usage:** X accounts at risk (>=80% of limit)
```

If any section shows problems (errors, security events with severity >= warning, rate-limited users, at-risk usage accounts), expand with details below the summary.

Flag anything that needs immediate attention.
