# Quickstart: Third-Party MCP Server Integration

## Add an MCP Server

> "Add the Slack MCP server to my namespace at `https://slack-mcp.example.com/mcp` with token `xoxb-...`"

MCPWorks connects, discovers tools, encrypts the token, and stores the config.

## Call MCP Tools from Code

Write a function that uses Slack tools:

```python
from functions import mcp__slack__list_channels, mcp__slack__send_message

channels = mcp__slack__list_channels()
private = [c for c in channels if c.get('is_private')]
mcp__slack__send_message(channel="C01234", text=f"Found {len(private)} private channels")
result = {"private_channel_count": len(private)}
```

The AI sends ~80 tokens of code. Slack's full channel list stays in the sandbox. Only the result returns.

## Tune Settings

> "Set the response limit for the google-workspace MCP server to 2MB"

> "Set the timeout for slack to 60 seconds"

> "Disable the github MCP server temporarily"

## Add Environment Variables

> "Set SLACK_WORKSPACE=mcpworks on the slack MCP server"

> "Set GOOGLE_PROJECT_ID=my-project on the google-workspace MCP server"

## Give an Agent Access

> "Configure the assistantpam agent to use the slack and google-workspace MCP servers"

The agent can now call Slack and Google Workspace tools during its runs.

## Discover Available Tools

From sandbox code:
```python
import functions
print(functions.__doc__)
```

Output:
```
Available functions in the 'assistantpam' namespace:

  [Services]
    [email-tools]
      check_email(account) — Check inbox
      format_report(data) — Format report

  [RemoteMCP]
    [slack]
      mcp__slack__send_message(channel, text) — Send a Slack message
      mcp__slack__list_channels() — List all channels
    [google-workspace]
      mcp__google_workspace__read_sheet_values(spreadsheet_id, range) — Read from Sheets
```

## Implementation Order

1. Database: `namespace_mcp_servers` table + `mcp_server_names` on agents
2. Model: `NamespaceMcpServer` + relationship on Namespace
3. Service: `McpServerService` — CRUD, discovery, settings, env vars
4. Proxy: `/v1/internal/mcp-proxy` endpoint + execution token registry
5. Connection pool: refactor `McpServerPool` to read from DB
6. Sandbox integration: MCP tool wrappers in `code_mode.py` + `_mcp_bridge.py`
7. MCP tools: 11 tool handlers on create endpoint + tool registry
8. Agent integration: orchestrator reads `mcp_server_names` from namespace registry
9. Console: Remote MCP Servers section in `console.html`
10. Deprecate: stop reading `agent.mcp_servers` JSONB
11. Tests: unit + integration
