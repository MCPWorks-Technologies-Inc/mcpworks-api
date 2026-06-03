"""Full sandbox-callback loop e2e for API → MCP (019).

Proves the one link unit/integration tests can't: REAL generated bridge code,
running in a REAL separate subprocess (the "sandbox", as in SANDBOX_DEV_MODE),
calling back over loopback HTTP to the api-proxy endpoint (same process → shared
in-memory exec-token registry), which proxies to a REAL upstream (httpbin) and
returns the result to the sandbox.

    subprocess sandbox → functions/_api_bridge.py (generated) → HTTP POST
    /v1/internal/api-proxy → resolve_execution(token) [shared registry] →
    proxy_api_call → httpbin → response back to the sandbox

Requires Postgres + outbound network + a free TCP port. SKIPPED by default:

    RUN_LIVE_TESTS=1 ENCRYPTION_KEK_B64=$(python -c \
      "import os,base64;print(base64.b64encode(os.urandom(32)).decode())") \
      pytest tests/e2e/test_sandbox_callback.py -m network
"""

import asyncio
import contextlib
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import uuid
from pathlib import Path

import pytest
import uvicorn
from fastapi import FastAPI, Header
from fastapi.responses import JSONResponse
from sqlalchemy import NullPool
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from mcpworks_api.core.api_proxy import proxy_api_call
from mcpworks_api.core.exec_token_registry import (
    register_execution,
    resolve_execution,
    unregister_execution,
)
from mcpworks_api.mcp.code_mode import generate_functions_package
from mcpworks_api.models import Account, Base, Namespace, User
from mcpworks_api.schemas.api_server import ApiProxyRequest
from mcpworks_api.services.api_server import ApiServerService

pytestmark = [
    pytest.mark.network,
    pytest.mark.skipif(
        not (os.getenv("RUN_LIVE_TESTS") and os.getenv("ENCRYPTION_KEK_B64")),
        reason="live e2e; set RUN_LIVE_TESTS=1 and ENCRYPTION_KEK_B64 to run",
    ),
]

DB_URL = os.getenv(
    "DATABASE_URL", "postgresql+asyncpg://mcpworks:mcpworks_dev@localhost:5432/mcpworks"
)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _build_app() -> FastAPI:
    """Minimal app serving only the api-proxy route (mirrors api/v1/api_proxy.py)."""
    app = FastAPI()

    @app.on_event("startup")
    async def _startup() -> None:
        engine = create_async_engine(DB_URL, echo=False, poolclass=NullPool)
        app.state.sm = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    @app.post("/v1/internal/api-proxy")
    async def api_proxy(body: ApiProxyRequest, authorization: str = Header(...)):
        ctx = resolve_execution(authorization.removeprefix("Bearer ").strip())
        if not ctx:
            return JSONResponse(status_code=403, content={"error": "auth_error"})
        async with app.state.sm() as db:
            r = await proxy_api_call(
                ctx,
                body.server,
                body.operation_id,
                body.path,
                body.query,
                body.body,
                body.headers,
                db,
            )
        if r.error:
            return JSONResponse(status_code=502, content={"error": r.error, "reason": r.reason})
        out = {
            "status_code": r.status_code,
            "truncated": r.truncated,
            "content_type": r.content_type,
        }
        if r.json_body is not None:
            out["json"] = r.json_body
        if r.text is not None:
            out["text"] = r.text
        return JSONResponse(content=out)

    return app


async def _seed() -> tuple[uuid.UUID, str, str]:
    engine = create_async_engine(DB_URL, echo=False, poolclass=NullPool)
    sm = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with sm() as db:
        user = User(
            email=f"e2e-{uuid.uuid4().hex[:8]}@x.io",
            password_hash="x",
            name="E2E",
            tier="builder",
            status="active",
        )
        db.add(user)
        await db.flush()
        acct = Account(user_id=user.id, name="E2E")
        db.add(acct)
        await db.flush()
        ns = Namespace(account_id=acct.id, name=f"e2e-{uuid.uuid4().hex[:8]}")
        db.add(ns)
        await db.flush()
        svc = ApiServerService(db)
        await svc.add_server(
            namespace_id=ns.id,
            name="httpbin",
            base_url="https://httpbin.org",
            spec_source="openapi_url",
            openapi_url="https://httpbin.org/spec.json",
        )
        eps = await svc.list_endpoints(ns.id, "httpbin")
        anything = next(e for e in eps if e.method == "GET" and e.path == "/anything")
        await svc.set_enabled(ns.id, "httpbin", [anything.operation_id], enabled=True)
        await db.commit()
        return ns.id, ns.name, anything.operation_id


async def test_sandbox_callback_loop() -> None:
    ns_id, ns_name, op_id = await _seed()
    port = _free_port()

    server = uvicorn.Server(
        uvicorn.Config(_build_app(), host="127.0.0.1", port=port, log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        await asyncio.sleep(2.0)  # let the server bind + run startup

        token = "bridge_" + uuid.uuid4().hex
        register_execution(
            token=token, namespace_id=ns_id, namespace_name=ns_name, execution_id=str(uuid.uuid4())
        )

        files = generate_functions_package(
            functions=[],
            namespace=ns_name,
            api_servers=[
                {
                    "name": "httpbin",
                    "endpoints": [
                        {
                            "operation_id": op_id,
                            "method": "GET",
                            "path": "/anything",
                            "summary": "echo",
                        }
                    ],
                }
            ],
        )
        tmp = Path(tempfile.mkdtemp())
        baked_url = files["functions/_api_bridge.py"].split('_PROXY_URL = "')[1].split('"')[0]
        for rel, content in files.items():
            if rel == "functions/_api_bridge.py":
                content = content.replace(
                    baked_url, f"http://127.0.0.1:{port}/v1/internal/api-proxy"
                )
            path = tmp / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)

        code = (
            f"import sys, json; sys.path.insert(0, {str(tmp)!r}); "
            f"from functions import api__httpbin__{op_id} as call; "
            "print(json.dumps(call(query={'hello': 'world'}, path={})))"
        )
        env = {**os.environ, "__MCPWORKS_BRIDGE_KEY__": token, "PYTHONPATH": str(tmp)}
        proc = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True, env=env, timeout=60
        )
        assert proc.returncode == 0, proc.stderr[-2000:]

        out = json.loads(proc.stdout.strip().splitlines()[-1])
        assert out["status_code"] == 200, out
        assert out["json"]["args"] == {"hello": "world"}
        assert out["json"]["url"].endswith("/anything?hello=world")
    finally:
        unregister_execution(token)
        server.should_exit = True
        with contextlib.suppress(Exception):
            thread.join(timeout=5)
