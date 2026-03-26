# Quickstart: Namespace Git Export

## Prerequisites

- A MCPWorks namespace with at least one service and function
- A Git repository (GitHub, GitLab, Gitea, etc.) with HTTPS access
- A personal access token (PAT) with push permissions to the repo

## Export a Namespace

### 1. Configure the Git remote

> "Configure my analytics namespace to push to `https://github.com/user/analytics-functions.git` with token `ghp_abc123...`"

The tool verifies the credentials with a test `git ls-remote` before saving.

### 2. Export

> "Export my analytics namespace to Git"

MCPWorks serializes all services, functions, and agents, then commits and pushes.

### 3. Verify

Check your repo — you'll see:

```
analytics/
  namespace.yaml
  services/
    utils/
      service.yaml
      functions/
        hello/
          function.yaml
          handler.py
        analyze-csv/
          function.yaml
          handler.py
  agents/
    leadgenerator/
      agent.yaml
```

## Import a Namespace

### From a public repo:

> "Import the namespace from `https://github.com/user/analytics-functions.git`"

### From a private repo:

> "Import the namespace from `https://github.com/user/analytics-functions.git` with token `ghp_abc123...`"

### Into an existing namespace (overwrite):

> "Import the utils service from `https://github.com/user/analytics-functions.git` into my production namespace, overwrite if exists"

## What Gets Exported

| Included | Not Included |
|----------|-------------|
| Function code (active version) | Env var values |
| Function schemas + requirements | Agent AI API keys |
| Agent config + system prompts | Channel credentials (bot tokens) |
| Agent schedules + webhooks | Agent state |
| Service metadata | Execution history |

After importing, you'll need to:
1. Set environment variable values for any functions declaring `required_env`
2. Configure AI API keys for agents (`configure_agent_ai`)
3. Re-add channel credentials for agents (`add_channel`)

## Implementation Order

1. Database migration (`namespace_git_remotes` table)
2. Git remote service (subprocess wrapper: clone, commit, push, ls-remote)
3. Export serializer (namespace → YAML + code directory)
4. Import deserializer (YAML + code directory → DB entities)
5. MCP tool handlers (6 tools on create endpoint)
6. Dockerfile: add `git` binary
7. Tests (unit + integration)
