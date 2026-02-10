"""Namespace management REST API endpoints.

Provides REST endpoints for managing namespaces, services, and functions.
Complements the MCP interface for use by the web dashboard and CLI.
"""

import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from mcpworks_api.core.database import get_db
from mcpworks_api.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from mcpworks_api.models import Account
from mcpworks_api.services.function import FunctionService
from mcpworks_api.services.namespace import (
    NamespaceServiceManager,
    NamespaceServiceService,
)

router = APIRouter(prefix="/namespaces", tags=["namespaces"])


# Request/Response Models
class CreateNamespaceRequest(BaseModel):
    """Request to create a namespace."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=63,
        pattern=r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$",
        description="DNS-compliant namespace name",
    )
    description: Optional[str] = Field(None, max_length=500)
    network_whitelist: Optional[List[str]] = Field(
        None, description="List of allowed IPs/CIDRs"
    )


class UpdateNamespaceRequest(BaseModel):
    """Request to update a namespace."""

    description: Optional[str] = Field(None, max_length=500)
    network_whitelist: Optional[List[str]] = Field(
        None, description="List of allowed IPs/CIDRs"
    )


class NamespaceResponse(BaseModel):
    """Namespace response."""

    id: str
    name: str
    description: Optional[str]
    create_endpoint: str
    run_endpoint: str
    network_whitelist: Optional[List[str]]
    created_at: str
    updated_at: Optional[str]


class NamespaceListResponse(BaseModel):
    """List of namespaces."""

    namespaces: List[NamespaceResponse]
    total: int
    page: int
    page_size: int


class CreateServiceRequest(BaseModel):
    """Request to create a service."""

    name: str = Field(..., min_length=1, max_length=63)
    description: Optional[str] = Field(None, max_length=500)


class ServiceResponse(BaseModel):
    """Service response."""

    id: str
    name: str
    description: Optional[str]
    namespace_id: str
    function_count: int
    created_at: str


class ServiceListResponse(BaseModel):
    """List of services."""

    services: List[ServiceResponse]
    namespace: str


class CreateFunctionRequest(BaseModel):
    """Request to create a function."""

    name: str = Field(..., min_length=1, max_length=63)
    backend: str = Field(
        ..., description="Execution backend (code_sandbox, activepieces, nanobot, github_repo)"
    )
    description: Optional[str] = Field(None, max_length=500)
    tags: Optional[List[str]] = None
    code: Optional[str] = Field(None, description="Function code (for code_sandbox)")
    config: Optional[Dict[str, Any]] = Field(
        None, description="Backend-specific configuration"
    )
    input_schema: Optional[Dict[str, Any]] = Field(
        None, description="JSON Schema for input"
    )
    output_schema: Optional[Dict[str, Any]] = Field(
        None, description="JSON Schema for output"
    )


class FunctionResponse(BaseModel):
    """Function response."""

    id: str
    name: str
    description: Optional[str]
    tags: Optional[List[str]]
    active_version: int
    service_id: str
    created_at: str


class FunctionDetailResponse(BaseModel):
    """Detailed function response."""

    id: str
    name: str
    description: Optional[str]
    tags: Optional[List[str]]
    active_version: int
    active_version_details: Optional[Dict[str, Any]]
    versions: List[Dict[str, Any]]
    created_at: str
    updated_at: Optional[str]


class FunctionListResponse(BaseModel):
    """List of functions."""

    functions: List[FunctionResponse]
    total: int
    service: str


# Dependency to get account (placeholder - should use actual auth)
async def get_current_account(db: AsyncSession = Depends(get_db)) -> Account:
    """Get current account from request context.

    TODO: Implement actual authentication.
    For now, returns first account or raises 401.
    """
    from sqlalchemy import select

    result = await db.execute(select(Account).limit(1))
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return account


# Namespace Endpoints
@router.post("", response_model=NamespaceResponse, status_code=201)
async def create_namespace(
    request: CreateNamespaceRequest,
    db: AsyncSession = Depends(get_db),
    account: Account = Depends(get_current_account),
) -> NamespaceResponse:
    """Create a new namespace."""
    service = NamespaceServiceManager(db)

    try:
        namespace = await service.create(
            account_id=account.id,
            name=request.name,
            description=request.description,
            network_whitelist=request.network_whitelist,
        )
        await db.commit()

        return NamespaceResponse(
            id=str(namespace.id),
            name=namespace.name,
            description=namespace.description,
            create_endpoint=namespace.create_endpoint,
            run_endpoint=namespace.run_endpoint,
            network_whitelist=namespace.network_whitelist,
            created_at=namespace.created_at.isoformat(),
            updated_at=namespace.updated_at.isoformat() if namespace.updated_at else None,
        )
    except ConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get("", response_model=NamespaceListResponse)
async def list_namespaces(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    account: Account = Depends(get_current_account),
) -> NamespaceListResponse:
    """List all namespaces for the current account."""
    service = NamespaceServiceManager(db)
    namespaces, total = await service.list(
        account_id=account.id,
        page=page,
        page_size=page_size,
    )

    return NamespaceListResponse(
        namespaces=[
            NamespaceResponse(
                id=str(ns.id),
                name=ns.name,
                description=ns.description,
                create_endpoint=ns.create_endpoint,
                run_endpoint=ns.run_endpoint,
                network_whitelist=ns.network_whitelist,
                created_at=ns.created_at.isoformat(),
                updated_at=ns.updated_at.isoformat() if ns.updated_at else None,
            )
            for ns in namespaces
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{namespace_name}", response_model=NamespaceResponse)
async def get_namespace(
    namespace_name: str,
    db: AsyncSession = Depends(get_db),
    account: Account = Depends(get_current_account),
) -> NamespaceResponse:
    """Get a namespace by name."""
    service = NamespaceServiceManager(db)

    try:
        namespace = await service.get_by_name(namespace_name, account.id)
        return NamespaceResponse(
            id=str(namespace.id),
            name=namespace.name,
            description=namespace.description,
            create_endpoint=namespace.create_endpoint,
            run_endpoint=namespace.run_endpoint,
            network_whitelist=namespace.network_whitelist,
            created_at=namespace.created_at.isoformat(),
            updated_at=namespace.updated_at.isoformat() if namespace.updated_at else None,
        )
    except NotFoundError:
        raise HTTPException(status_code=404, detail=f"Namespace '{namespace_name}' not found")
    except ForbiddenError:
        raise HTTPException(status_code=403, detail="Access denied")


@router.patch("/{namespace_name}", response_model=NamespaceResponse)
async def update_namespace(
    namespace_name: str,
    request: UpdateNamespaceRequest,
    db: AsyncSession = Depends(get_db),
    account: Account = Depends(get_current_account),
) -> NamespaceResponse:
    """Update a namespace."""
    service = NamespaceServiceManager(db)

    try:
        namespace = await service.get_by_name(namespace_name, account.id)
        namespace = await service.update(
            namespace_id=namespace.id,
            account_id=account.id,
            description=request.description,
            network_whitelist=request.network_whitelist,
        )
        await db.commit()

        return NamespaceResponse(
            id=str(namespace.id),
            name=namespace.name,
            description=namespace.description,
            create_endpoint=namespace.create_endpoint,
            run_endpoint=namespace.run_endpoint,
            network_whitelist=namespace.network_whitelist,
            created_at=namespace.created_at.isoformat(),
            updated_at=namespace.updated_at.isoformat() if namespace.updated_at else None,
        )
    except NotFoundError:
        raise HTTPException(status_code=404, detail=f"Namespace '{namespace_name}' not found")
    except ForbiddenError:
        raise HTTPException(status_code=403, detail="Access denied")


@router.delete("/{namespace_name}", status_code=204)
async def delete_namespace(
    namespace_name: str,
    db: AsyncSession = Depends(get_db),
    account: Account = Depends(get_current_account),
) -> None:
    """Delete a namespace and all its services/functions."""
    service = NamespaceServiceManager(db)

    try:
        namespace = await service.get_by_name(namespace_name, account.id)
        await service.delete(namespace.id, account.id)
        await db.commit()
    except NotFoundError:
        raise HTTPException(status_code=404, detail=f"Namespace '{namespace_name}' not found")
    except ForbiddenError:
        raise HTTPException(status_code=403, detail="Access denied")


# Service Endpoints
@router.post("/{namespace_name}/services", response_model=ServiceResponse, status_code=201)
async def create_service(
    namespace_name: str,
    request: CreateServiceRequest,
    db: AsyncSession = Depends(get_db),
    account: Account = Depends(get_current_account),
) -> ServiceResponse:
    """Create a new service in a namespace."""
    ns_service = NamespaceServiceManager(db)
    svc_service = NamespaceServiceService(db)

    try:
        namespace = await ns_service.get_by_name(namespace_name, account.id)
        service = await svc_service.create(
            namespace_id=namespace.id,
            name=request.name,
            description=request.description,
        )
        await db.commit()

        return ServiceResponse(
            id=str(service.id),
            name=service.name,
            description=service.description,
            namespace_id=str(service.namespace_id),
            function_count=service.function_count,
            created_at=service.created_at.isoformat(),
        )
    except NotFoundError:
        raise HTTPException(status_code=404, detail=f"Namespace '{namespace_name}' not found")
    except ConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get("/{namespace_name}/services", response_model=ServiceListResponse)
async def list_services(
    namespace_name: str,
    db: AsyncSession = Depends(get_db),
    account: Account = Depends(get_current_account),
) -> ServiceListResponse:
    """List all services in a namespace."""
    ns_service = NamespaceServiceManager(db)
    svc_service = NamespaceServiceService(db)

    try:
        namespace = await ns_service.get_by_name(namespace_name, account.id)
        services = await svc_service.list(namespace.id)

        return ServiceListResponse(
            services=[
                ServiceResponse(
                    id=str(s.id),
                    name=s.name,
                    description=s.description,
                    namespace_id=str(s.namespace_id),
                    function_count=s.function_count,
                    created_at=s.created_at.isoformat(),
                )
                for s in services
            ],
            namespace=namespace_name,
        )
    except NotFoundError:
        raise HTTPException(status_code=404, detail=f"Namespace '{namespace_name}' not found")


@router.delete("/{namespace_name}/services/{service_name}", status_code=204)
async def delete_service(
    namespace_name: str,
    service_name: str,
    db: AsyncSession = Depends(get_db),
    account: Account = Depends(get_current_account),
) -> None:
    """Delete a service and all its functions."""
    ns_service = NamespaceServiceManager(db)
    svc_service = NamespaceServiceService(db)

    try:
        namespace = await ns_service.get_by_name(namespace_name, account.id)
        service = await svc_service.get_by_name(namespace.id, service_name)
        await svc_service.delete(service.id)
        await db.commit()
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


# Function Endpoints
@router.post(
    "/{namespace_name}/services/{service_name}/functions",
    response_model=FunctionResponse,
    status_code=201,
)
async def create_function(
    namespace_name: str,
    service_name: str,
    request: CreateFunctionRequest,
    db: AsyncSession = Depends(get_db),
    account: Account = Depends(get_current_account),
) -> FunctionResponse:
    """Create a new function in a service."""
    ns_service = NamespaceServiceManager(db)
    svc_service = NamespaceServiceService(db)
    func_service = FunctionService(db)

    try:
        namespace = await ns_service.get_by_name(namespace_name, account.id)
        service = await svc_service.get_by_name(namespace.id, service_name)

        function = await func_service.create(
            service_id=service.id,
            name=request.name,
            backend=request.backend,
            description=request.description,
            tags=request.tags,
            code=request.code,
            config=request.config,
            input_schema=request.input_schema,
            output_schema=request.output_schema,
        )
        await db.commit()

        return FunctionResponse(
            id=str(function.id),
            name=function.name,
            description=function.description,
            tags=function.tags,
            active_version=function.active_version,
            service_id=str(function.service_id),
            created_at=function.created_at.isoformat(),
        )
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get(
    "/{namespace_name}/services/{service_name}/functions",
    response_model=FunctionListResponse,
)
async def list_functions(
    namespace_name: str,
    service_name: str,
    tag: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    account: Account = Depends(get_current_account),
) -> FunctionListResponse:
    """List all functions in a service."""
    ns_service = NamespaceServiceManager(db)
    svc_service = NamespaceServiceService(db)
    func_service = FunctionService(db)

    try:
        namespace = await ns_service.get_by_name(namespace_name, account.id)
        service = await svc_service.get_by_name(namespace.id, service_name)

        tags = [tag] if tag else None
        functions, total = await func_service.list(
            service_id=service.id,
            page=page,
            page_size=page_size,
            tags=tags,
        )

        return FunctionListResponse(
            functions=[
                FunctionResponse(
                    id=str(f.id),
                    name=f.name,
                    description=f.description,
                    tags=f.tags,
                    active_version=f.active_version,
                    service_id=str(f.service_id),
                    created_at=f.created_at.isoformat(),
                )
                for f in functions
            ],
            total=total,
            service=service_name,
        )
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get(
    "/{namespace_name}/services/{service_name}/functions/{function_name}",
    response_model=FunctionDetailResponse,
)
async def get_function(
    namespace_name: str,
    service_name: str,
    function_name: str,
    db: AsyncSession = Depends(get_db),
    account: Account = Depends(get_current_account),
) -> FunctionDetailResponse:
    """Get detailed function information."""
    ns_service = NamespaceServiceManager(db)
    svc_service = NamespaceServiceService(db)
    func_service = FunctionService(db)

    try:
        namespace = await ns_service.get_by_name(namespace_name, account.id)
        service = await svc_service.get_by_name(namespace.id, service_name)
        function = await func_service.get_by_name(service.id, function_name)
        details = await func_service.describe(function.id)

        return FunctionDetailResponse(
            id=details["id"],
            name=details["name"],
            description=details["description"],
            tags=details["tags"],
            active_version=details["active_version"],
            active_version_details=details["active_version_details"],
            versions=details["versions"],
            created_at=details["created_at"],
            updated_at=details["updated_at"],
        )
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete(
    "/{namespace_name}/services/{service_name}/functions/{function_name}",
    status_code=204,
)
async def delete_function(
    namespace_name: str,
    service_name: str,
    function_name: str,
    db: AsyncSession = Depends(get_db),
    account: Account = Depends(get_current_account),
) -> None:
    """Delete a function."""
    ns_service = NamespaceServiceManager(db)
    svc_service = NamespaceServiceService(db)
    func_service = FunctionService(db)

    try:
        namespace = await ns_service.get_by_name(namespace_name, account.id)
        service = await svc_service.get_by_name(namespace.id, service_name)
        function = await func_service.get_by_name(service.id, function_name)
        await func_service.delete(function.id)
        await db.commit()
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
