"""MCP Protocol Router - Routes JSON-RPC requests to handlers.

This module provides FastAPI router for MCP endpoints, routing to either
CreateMCPHandler or RunMCPHandler based on subdomain endpoint type.
"""

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from mcpworks_api.core.database import get_db
from mcpworks_api.core.exceptions import ForbiddenError, NotFoundError
from mcpworks_api.mcp.create_handler import CreateMCPHandler
from mcpworks_api.mcp.protocol import (
    JSONRPCRequest,
    MCPErrorCodes,
    make_error_response,
)
from mcpworks_api.mcp.run_handler import RunMCPHandler
from mcpworks_api.models import Account, APIKey, Namespace, User
from mcpworks_api.services.namespace import NamespaceServiceManager

router = APIRouter(tags=["mcp"])


async def get_account_from_api_key(
    request: Request,
    db: AsyncSession,
) -> Account:
    """Extract and validate API key, return associated account.

    Args:
        request: FastAPI request object.
        db: Database session.

    Returns:
        The account associated with the API key.

    Raises:
        HTTPException: If API key is missing, invalid, or revoked.
    """
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from mcpworks_api.core.security import verify_api_key

    # Get API key from Authorization header
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid Authorization header",
        )

    raw_key = auth_header[7:]  # Remove "Bearer " prefix

    # Extract prefix for lookup (first 12 chars)
    if len(raw_key) < 12:
        raise HTTPException(status_code=401, detail="Invalid API key format")

    key_prefix = raw_key[:12]

    # Look up API keys with matching prefix
    result = await db.execute(
        select(APIKey)
        .where(APIKey.key_prefix == key_prefix)
        .where(APIKey.revoked_at.is_(None))  # Not revoked
        .options(selectinload(APIKey.user).selectinload(User.account))
    )
    api_keys = result.scalars().all()

    if not api_keys:
        raise HTTPException(status_code=401, detail="Invalid API key")

    # Verify against each matching key's hash
    valid_key: APIKey | None = None
    for api_key in api_keys:
        if verify_api_key(raw_key, api_key.key_hash):
            valid_key = api_key
            break

    if not valid_key:
        raise HTTPException(status_code=401, detail="Invalid API key")

    # Get account from user
    if not valid_key.user or not valid_key.user.account:
        raise HTTPException(
            status_code=403,
            detail="API key not associated with an account",
        )

    return valid_key.user.account


async def validate_namespace_access(
    namespace_name: str,
    account: Account,
    db: AsyncSession,
) -> Namespace:
    """Validate the account has access to the namespace.

    Args:
        namespace_name: Namespace from subdomain.
        account: Authenticated account.
        db: Database session.

    Returns:
        The namespace.

    Raises:
        HTTPException: If namespace not found or access denied.
    """
    namespace_service = NamespaceServiceManager(db)
    try:
        return await namespace_service.get_by_name(
            namespace_name,
            account.id,
        )
    except NotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Namespace '{namespace_name}' not found",
        )
    except ForbiddenError:
        raise HTTPException(
            status_code=403,
            detail=f"Access denied to namespace '{namespace_name}'",
        )


def parse_json_rpc_request(body: bytes) -> JSONRPCRequest:
    """Parse and validate JSON-RPC request.

    Args:
        body: Raw request body.

    Returns:
        Validated JSONRPCRequest.

    Raises:
        ValueError: If body is not valid JSON-RPC.
    """
    try:
        data = json.loads(body)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON: {e}")

    try:
        return JSONRPCRequest(**data)
    except ValidationError as e:
        raise ValueError(f"Invalid JSON-RPC request: {e}")


@router.post("/mcp")
async def handle_mcp_request(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Handle MCP JSON-RPC requests.

    This endpoint:
    1. Extracts namespace and endpoint type from request.state (set by SubdomainMiddleware)
    2. Authenticates via API key
    3. Routes to CreateMCPHandler or RunMCPHandler based on endpoint type
    4. Returns JSON-RPC response

    Returns:
        JSON-RPC response dict.
    """
    # Get subdomain info from middleware
    namespace_name = getattr(request.state, "namespace", None)
    endpoint_type = getattr(request.state, "endpoint_type", None)

    if not namespace_name:
        return make_error_response(
            MCPErrorCodes.INVALID_REQUEST,
            "Missing namespace. Use {namespace}.create.mcpworks.io or {namespace}.run.mcpworks.io",
        ).model_dump()

    if endpoint_type not in ("create", "run"):
        return make_error_response(
            MCPErrorCodes.INVALID_REQUEST,
            f"Invalid endpoint type: {endpoint_type}. Must be 'create' or 'run'",
        ).model_dump()

    # Parse JSON-RPC request
    try:
        body = await request.body()
        rpc_request = parse_json_rpc_request(body)
    except ValueError as e:
        return make_error_response(
            MCPErrorCodes.PARSE_ERROR,
            str(e),
        ).model_dump()

    # Authenticate
    try:
        account = await get_account_from_api_key(request, db)
    except HTTPException as e:
        return make_error_response(
            MCPErrorCodes.UNAUTHORIZED,
            e.detail,
            request_id=rpc_request.id,
        ).model_dump()

    # Validate namespace access
    try:
        await validate_namespace_access(namespace_name, account, db)
    except HTTPException as e:
        code = MCPErrorCodes.NOT_FOUND if e.status_code == 404 else MCPErrorCodes.FORBIDDEN
        return make_error_response(
            code,
            e.detail,
            request_id=rpc_request.id,
        ).model_dump()

    # Route to appropriate handler
    if endpoint_type == "create":
        handler = CreateMCPHandler(
            namespace=namespace_name,
            account=account,
            db=db,
        )
    else:  # endpoint_type == "run"
        handler = RunMCPHandler(
            namespace=namespace_name,
            account=account,
            db=db,
        )

    # Handle request
    response = await handler.handle(rpc_request)
    return response.model_dump()


@router.get("/mcp")
async def mcp_info(request: Request) -> dict[str, Any]:
    """Return MCP endpoint information.

    Used for discovery and health checks.
    """
    namespace_name = getattr(request.state, "namespace", None)
    endpoint_type = getattr(request.state, "endpoint_type", None)

    return {
        "protocol": "mcp",
        "version": "2024-11-05",
        "namespace": namespace_name,
        "endpoint_type": endpoint_type,
        "supported_methods": [
            "initialize",
            "tools/list",
            "tools/call",
        ],
    }
