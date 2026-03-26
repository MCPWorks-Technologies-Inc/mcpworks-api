# Quickstart: Prompt Injection Defense

## Set Function Trust Level

When creating a function, you must declare its trust level:

```
"Create a function called fetch-rss in the news service with output_trust=data"
```

- `prompt` — output is trusted (computed results, summaries). No wrapping.
- `data` — output contains untrusted external content (emails, APIs, web scrapes). Wrapped with trust markers.

If you forget, you'll get a helpful error:
```
output_trust is required. Suggested: 'data' (function imports mcp__google_workspace tools).
Set output_trust='data' or output_trust='prompt'.
```

## Change Trust Level

```
"Update fetch-rss in the news service to output_trust=prompt"
```

## See Trust Markers in Action

When a `data` function returns a result, the AI sees:
```
[UNTRUSTED_OUTPUT function="news.fetch-rss" trust="data"]
{"articles": [{"title": "...", "body": "..."}]}
[/UNTRUSTED_OUTPUT]
```

The AI knows not to execute instructions found within the markers.

## MCP Server Rules

New MCP servers get default rules automatically:
- All responses wrapped with trust boundary markers
- All responses scanned for prompt injection (warn mode)

### Add a Custom Rule

```
"Add a rule to the slack server: block the delete_channel tool"
```

```
"Add a response rule to google-workspace: scan for injection with strictness=flag"
```

```
"Add a request rule to slack: always limit list_channels to 50 results"
```

### See Active Rules

```
"List the rules on the slack MCP server"
```

### Remove a Rule

```
"Remove rule r-abc123 from the slack server"
```

## Strictness Levels

| Level | Behavior |
|-------|----------|
| `warn` | Log security event, pass data unchanged (default) |
| `flag` | Log event, add `[INJECTION_WARNING]` markers around flagged text |
| `block` | Log event, redact flagged content with explanation |

## Implementation Order

1. Injection scanner module (`sandbox/injection_scan.py`)
2. Trust boundary wrapping functions (`core/trust_boundary.py`)
3. Migration: `output_trust` on functions + `rules` on namespace_mcp_servers
4. Modify `make_function` / `update_function` for mandatory output_trust
5. Modify run handler: wrap results for `output_trust: data` functions
6. Modify MCP proxy: apply response rules (wrap, scan, strip, redact)
7. Modify MCP proxy: apply request rules (inject, block, require, cap)
8. Add rule management tools (add/remove/list)
9. Default rules on `add_mcp_server`
10. Tests: scanner patterns, marker format, rule engine, adversarial corpus
