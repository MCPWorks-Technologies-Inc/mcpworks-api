#!/usr/bin/env python3
"""MCP Test Client - Test MCP endpoints without restarting Claude.

Usage:
    # Against local dev server
    python scripts/test-mcp.py --base-url http://localhost:8000

    # Against production
    python scripts/test-mcp.py --base-url https://api.mcpworks.io --token $TOKEN

    # Interactive mode
    python scripts/test-mcp.py -i
"""

import argparse
import json
import sys
from typing import Any

import httpx


class MCPTestClient:
    """Simple MCP test client for HTTP-based MCP servers."""

    def __init__(self, base_url: str, token: str | None = None, namespace: str = "default"):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.namespace = namespace
        self.request_id = 0

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _next_id(self) -> int:
        self.request_id += 1
        return self.request_id

    def _mcp_url(self, endpoint_type: str = "create") -> str:
        """Get MCP endpoint URL."""
        # Local dev uses query params
        if "localhost" in self.base_url or "127.0.0.1" in self.base_url:
            return f"{self.base_url}/mcp?namespace={self.namespace}&endpoint={endpoint_type}"
        # Production uses subdomains (but we hit the API directly for testing)
        return f"{self.base_url}/mcp"

    def call(self, method: str, params: dict[str, Any] | None = None) -> dict:
        """Make JSON-RPC call to MCP endpoint."""
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "id": self._next_id(),
        }
        if params:
            payload["params"] = params

        url = self._mcp_url()
        print(f"\n→ POST {url}")
        print(f"  Method: {method}")
        if params:
            print(f"  Params: {json.dumps(params, indent=2)}")

        try:
            response = httpx.post(url, json=payload, headers=self._headers(), timeout=30)
            result = response.json()

            print(f"\n← Status: {response.status_code}")
            print(f"  Response: {json.dumps(result, indent=2)}")

            return result
        except Exception as e:
            print(f"\n✗ Error: {e}")
            return {"error": str(e)}

    def initialize(self) -> dict:
        """Send initialize request."""
        return self.call("initialize")

    def tools_list(self) -> dict:
        """List available tools."""
        return self.call("tools/list")

    def tools_call(self, name: str, arguments: dict[str, Any] | None = None) -> dict:
        """Call a tool."""
        return self.call("tools/call", {"name": name, "arguments": arguments or {}})

    def health(self) -> dict:
        """Check health endpoint."""
        url = f"{self.base_url}/v1/health/ready"
        print(f"\n→ GET {url}")
        try:
            response = httpx.get(url, timeout=10)
            result = response.json()
            print(f"← {response.status_code}: {json.dumps(result)}")
            return result
        except Exception as e:
            print(f"✗ Error: {e}")
            return {"error": str(e)}


def interactive_mode(client: MCPTestClient):
    """Run interactive REPL."""
    print("\nMCP Test Client - Interactive Mode")
    print("=" * 40)
    print("Commands:")
    print("  init          - Send initialize")
    print("  list          - List tools")
    print("  call <name>   - Call tool (prompts for args)")
    print("  health        - Check health")
    print("  raw           - Send raw JSON-RPC")
    print("  quit          - Exit")
    print()

    while True:
        try:
            cmd = input("mcp> ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break

        if not cmd:
            continue
        elif cmd == "quit" or cmd == "exit":
            break
        elif cmd == "init":
            client.initialize()
        elif cmd == "list":
            client.tools_list()
        elif cmd == "health":
            client.health()
        elif cmd.startswith("call "):
            tool_name = cmd[5:].strip()
            args_str = input("  Arguments (JSON or empty): ").strip()
            args = json.loads(args_str) if args_str else {}
            client.tools_call(tool_name, args)
        elif cmd == "raw":
            method = input("  Method: ").strip()
            params_str = input("  Params (JSON or empty): ").strip()
            params = json.loads(params_str) if params_str else None
            client.call(method, params)
        else:
            print(f"Unknown command: {cmd}")


def run_smoke_tests(client: MCPTestClient):
    """Run basic smoke tests."""
    print("\n" + "=" * 50)
    print("MCP Smoke Tests")
    print("=" * 50)

    # Health check
    print("\n[1/3] Health Check")
    health = client.health()
    if health.get("status") == "ready":
        print("  ✓ Health OK")
    else:
        print("  ✗ Health check failed")
        return False

    # Initialize
    print("\n[2/3] Initialize")
    init = client.initialize()
    if "result" in init:
        print(f"  ✓ Protocol: {init['result'].get('protocolVersion')}")
    else:
        print(f"  ✗ Initialize failed: {init.get('error')}")

    # Tools list
    print("\n[3/3] Tools List")
    tools = client.tools_list()
    if "result" in tools:
        tool_count = len(tools["result"].get("tools", []))
        print(f"  ✓ Found {tool_count} tools")
        for tool in tools["result"].get("tools", [])[:5]:
            print(f"    - {tool['name']}")
        if tool_count > 5:
            print(f"    ... and {tool_count - 5} more")
    else:
        print(f"  ✗ Tools list failed: {tools.get('error')}")

    print("\n" + "=" * 50)
    return True


def main():
    parser = argparse.ArgumentParser(description="MCP Test Client")
    parser.add_argument(
        "--base-url", "-u", default="http://localhost:8000", help="Base URL of the API"
    )
    parser.add_argument("--token", "-t", help="Bearer token for auth")
    parser.add_argument("--namespace", "-n", default="default", help="Namespace for local testing")
    parser.add_argument("--interactive", "-i", action="store_true", help="Run in interactive mode")
    parser.add_argument("--smoke", "-s", action="store_true", help="Run smoke tests")

    args = parser.parse_args()

    client = MCPTestClient(
        base_url=args.base_url,
        token=args.token,
        namespace=args.namespace,
    )

    if args.interactive:
        interactive_mode(client)
    elif args.smoke:
        success = run_smoke_tests(client)
        sys.exit(0 if success else 1)
    else:
        # Default: run smoke tests
        run_smoke_tests(client)


if __name__ == "__main__":
    main()
