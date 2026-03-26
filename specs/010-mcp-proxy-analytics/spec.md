# MCP Proxy Analytics & AI Self-Optimization - Specification

**Version:** 0.1.0 (Draft)
**Created:** 2026-03-26
**Status:** Captured (not yet spec'd)
**Feature Branch:** `010-mcp-proxy-analytics`

---

## Idea Capture

Since the MCPWorks proxy sits in the middle of every RemoteMCP call, it can gather per-server, per-tool performance and utilization statistics — then expose those stats to the AI so it can optimize its own token usage.

### What the proxy can measure

- Response size (bytes + estimated tokens) per tool per server
- Latency per call
- Call frequency (which tools get called most, by which functions)
- Error and timeout rates
- Truncation rate (how often response_limit_bytes is hit)
- Tokens saved (data processed in sandbox minus result returned to AI)
- MCP calls per execution per function

### The self-optimization loop

The AI queries stats via MCP tools and makes decisions:

- "list_channels returns 200KB avg but functions only use name + id. Add a redact_fields rule."
- "search_gmail times out 15% of the time. Increase timeout to 60s."
- "process_leads makes 47 MCP calls per execution. Raise the cap."
- "The google-workspace server has 40 tools but only 3 are ever called. Suggest removing unused tool wrappers to reduce functions package size."

No other platform can do this — the proxy path gives us the data, the MCP tools give the AI the interface, and the rules system (009) gives it the levers to act.

### Key MCP tools (draft)

- `get_mcp_server_stats(name, period)` — per-tool call counts, avg latency, avg response size, error rate
- `get_function_mcp_stats(service, function)` — MCP calls per execution, tokens consumed vs returned
- `get_token_savings_report(period)` — namespace-wide: tokens that stayed in sandbox vs tokens returned to AI
- `suggest_optimizations(name)` — AI-readable optimization suggestions based on stats (e.g., "add redact_fields rule for tool X")

### Why this matters

This is the AI optimizing its own infrastructure costs based on real telemetry. The proxy is the moat — no direct MCP connection gives you this observability.

---

## Status

Captured for future spec work. Depends on 008 (MCP server plugins) and 009 (prompt injection defense / rules system).
