"""LLM instruction endpoint - machine-readable API guidance."""

from fastapi import APIRouter

router = APIRouter(tags=["llm"])


@router.get("/llm")
async def llm_instructions() -> dict:
    """Terse instructions for LLM consumption.

    No human niceties. Optimized for token efficiency and clarity.
    """
    return {
        "api": "mcpworks",
        "version": "0.1.0",
        "auth": {
            "method": "Bearer token",
            "header": "Authorization: Bearer <token>",
            "get_token": {
                "option_1": "POST /v1/auth/register {email, password, name} → access_token",
                "option_2": "POST /v1/auth/login {email, password} → access_token",
                "option_3": "POST /v1/auth/token {api_key} → access_token",
            },
        },
        "endpoints": {
            "account": {
                "register": "POST /v1/auth/register {email, password, name}",
                "login": "POST /v1/auth/login {email, password}",
                "api_keys": "POST /v1/auth/api-keys {name} → key (save, shown once)",
                "usage": "GET /v1/account/usage → executions_count, executions_limit",
            },
            "namespaces": {
                "list": "GET /v1/namespaces",
                "create": "POST /v1/namespaces {name, display_name}",
                "get": "GET /v1/namespaces/{name}",
            },
            "functions": {
                "list": "GET /v1/namespaces/{ns}/functions",
                "create": "POST /v1/namespaces/{ns}/functions {name, code, runtime}",
                "call": "POST /v1/namespaces/{ns}/functions/{name}/call {args}",
            },
        },
        "mcp": {
            "create_endpoint": "https://{namespace}.create.mcpworks.io/mcp",
            "run_endpoint": "https://{namespace}.run.mcpworks.io/mcp",
            "protocol": "JSON-RPC 2.0",
            "methods": ["tools/list", "tools/call"],
        },
        "errors": {
            "401": "Invalid/missing auth. Get token first.",
            "402": "Execution limit exceeded. Check usage or upgrade tier.",
            "403": "No access to resource. Check namespace ownership.",
            "404": "Resource not found.",
            "429": "Rate limited. Wait and retry.",
        },
        "quick_start": [
            "1. POST /v1/auth/register → get access_token",
            "2. POST /v1/namespaces {name} → create namespace",
            "3. Configure MCP: {namespace}.create.mcpworks.io/mcp",
            "4. Use tools/list and tools/call via MCP",
        ],
    }
