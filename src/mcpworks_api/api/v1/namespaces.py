"""Namespace management REST API endpoints.

Provides REST endpoints for managing namespaces, services, and functions.
Complements the MCP interface for use by the web dashboard and CLI.
"""

from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mcpworks_api.core.database import get_db
from mcpworks_api.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from mcpworks_api.dependencies import require_active_status, require_scope
from mcpworks_api.models import Account
from mcpworks_api.models.api_key import APIKey
from mcpworks_api.models.function import Function
from mcpworks_api.models.namespace_service import NamespaceService as NamespaceServiceModel
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
    description: str | None = Field(None, max_length=500)
    network_allowlist: list[str] | None = Field(None, description="List of allowed IPs/CIDRs")

    @field_validator("name")
    @classmethod
    def reject_reserved_names(cls, v: str) -> str:
        from mcpworks_api.schemas.namespace import RESERVED_NAMESPACE_NAMES

        v = v.lower()
        if v in RESERVED_NAMESPACE_NAMES:
            raise ValueError(f"Namespace name '{v}' is reserved")
        return v


class UpdateNamespaceRequest(BaseModel):
    """Request to update a namespace."""

    description: str | None = Field(None, max_length=500)
    network_allowlist: list[str] | None = Field(None, description="List of allowed IPs/CIDRs")


class NamespaceResponse(BaseModel):
    """Namespace response."""

    id: str
    name: str
    description: str | None
    create_endpoint: str
    run_endpoint: str
    network_allowlist: list[str] | None
    call_count: int = 0
    created_at: str
    updated_at: str | None


class NamespaceListResponse(BaseModel):
    """List of namespaces."""

    namespaces: list[NamespaceResponse]
    total: int
    page: int
    page_size: int


class NamespaceDeletedResponse(BaseModel):
    """Response after soft-deleting a namespace."""

    name: str
    deleted_at: str
    recovery_until: str
    affected_services: int
    affected_functions: int
    affected_api_keys: int


class CreateServiceRequest(BaseModel):
    """Request to create a service."""

    name: str = Field(..., min_length=1, max_length=63)
    description: str | None = Field(None, max_length=500)


class ServiceResponse(BaseModel):
    """Service response."""

    id: str
    name: str
    description: str | None
    namespace_id: str
    function_count: int
    call_count: int = 0
    created_at: str


class ServiceListResponse(BaseModel):
    """List of services."""

    services: list[ServiceResponse]
    namespace: str


class CreateFunctionRequest(BaseModel):
    """Request to create a function."""

    name: str = Field(..., min_length=1, max_length=63)
    backend: str = Field(
        ..., description="Execution backend (code_sandbox, activepieces, nanobot, github_repo)"
    )
    description: str | None = Field(None, max_length=500)
    tags: list[str] | None = None
    code: str | None = Field(None, description="Function code (for code_sandbox)")
    config: dict[str, Any] | None = Field(None, description="Backend-specific configuration")
    input_schema: dict[str, Any] | None = Field(None, description="JSON Schema for input")
    output_schema: dict[str, Any] | None = Field(None, description="JSON Schema for output")


class FunctionResponse(BaseModel):
    """Function response."""

    id: str
    name: str
    description: str | None
    tags: list[str] | None
    active_version: int
    call_count: int
    service_id: str
    created_at: str


class FunctionDetailResponse(BaseModel):
    """Detailed function response."""

    id: str
    name: str
    description: str | None
    tags: list[str] | None
    active_version: int
    call_count: int
    active_version_details: dict[str, Any] | None
    versions: list[dict[str, Any]]
    created_at: str
    updated_at: str | None


class FunctionVersionDetailResponse(BaseModel):
    """Detailed response for a specific function version."""

    id: str
    version: int
    backend: str
    code: str | None
    config: dict[str, Any] | None
    input_schema: dict[str, Any] | None
    output_schema: dict[str, Any] | None
    requirements: list[str] | None
    required_env: list[str] | None
    optional_env: list[str] | None
    created_by: str | None = None
    is_active: bool
    created_at: str


class FunctionListResponse(BaseModel):
    """List of functions."""

    functions: list[FunctionResponse]
    total: int
    service: str


# Dependency to get authenticated account
async def get_current_account(
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(require_active_status),
) -> Account:
    """Get current account from authenticated user.

    Validates JWT token, enforces active status (blocks unverified/suspended),
    and retrieves the associated account.
    """
    from sqlalchemy import select

    result = await db.execute(select(Account).where(Account.user_id == user_id))
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=401, detail="Account not found for user")
    return account


# Namespace Endpoints
@router.post(
    "",
    response_model=NamespaceResponse,
    status_code=201,
    dependencies=[Depends(require_scope("write"))],
)
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
            network_allowlist=request.network_allowlist,
        )
        await db.commit()

        return NamespaceResponse(
            id=str(namespace.id),
            name=namespace.name,
            description=namespace.description,
            create_endpoint=namespace.create_endpoint,
            run_endpoint=namespace.run_endpoint,
            network_allowlist=namespace.network_allowlist,
            call_count=namespace.call_count,
            created_at=namespace.created_at.isoformat(),
            updated_at=namespace.updated_at.isoformat() if namespace.updated_at else None,
        )
    except ConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get("", response_model=NamespaceListResponse, dependencies=[Depends(require_scope("read"))])
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
        user_id=account.user_id,
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
                network_allowlist=ns.network_allowlist,
                call_count=ns.call_count,
                created_at=ns.created_at.isoformat(),
                updated_at=ns.updated_at.isoformat() if ns.updated_at else None,
            )
            for ns in namespaces
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/{namespace_name}",
    response_model=NamespaceResponse,
    dependencies=[Depends(require_scope("read"))],
)
async def get_namespace(
    namespace_name: str,
    db: AsyncSession = Depends(get_db),
    account: Account = Depends(get_current_account),
) -> NamespaceResponse:
    """Get a namespace by name."""
    service = NamespaceServiceManager(db)

    try:
        namespace = await service.get_by_name(
            namespace_name,
            account.id,
            user_id=account.user_id,
            required_permission="read",
        )
        return NamespaceResponse(
            id=str(namespace.id),
            name=namespace.name,
            description=namespace.description,
            create_endpoint=namespace.create_endpoint,
            run_endpoint=namespace.run_endpoint,
            network_allowlist=namespace.network_allowlist,
            call_count=namespace.call_count,
            created_at=namespace.created_at.isoformat(),
            updated_at=namespace.updated_at.isoformat() if namespace.updated_at else None,
        )
    except NotFoundError:
        raise HTTPException(status_code=404, detail=f"Namespace '{namespace_name}' not found")
    except ForbiddenError:
        raise HTTPException(status_code=403, detail="Access denied")


@router.patch(
    "/{namespace_name}",
    response_model=NamespaceResponse,
    dependencies=[Depends(require_scope("write"))],
)
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
            network_allowlist=request.network_allowlist,
        )
        await db.commit()

        return NamespaceResponse(
            id=str(namespace.id),
            name=namespace.name,
            description=namespace.description,
            create_endpoint=namespace.create_endpoint,
            run_endpoint=namespace.run_endpoint,
            network_allowlist=namespace.network_allowlist,
            call_count=namespace.call_count,
            created_at=namespace.created_at.isoformat(),
            updated_at=namespace.updated_at.isoformat() if namespace.updated_at else None,
        )
    except NotFoundError:
        raise HTTPException(status_code=404, detail=f"Namespace '{namespace_name}' not found")
    except ForbiddenError:
        raise HTTPException(status_code=403, detail="Access denied")


@router.delete(
    "/{namespace_name}",
    response_model=NamespaceDeletedResponse,
    status_code=200,
    dependencies=[Depends(require_scope("write"))],
)
async def delete_namespace(
    namespace_name: str,
    db: AsyncSession = Depends(get_db),
    account: Account = Depends(get_current_account),
) -> NamespaceDeletedResponse:
    """Soft-delete a namespace (recoverable for 30 days)."""
    service = NamespaceServiceManager(db)

    try:
        namespace = await service.get_by_name(namespace_name, account.id)

        svc_count = (
            await db.execute(
                select(func.count())
                .select_from(NamespaceServiceModel)
                .where(NamespaceServiceModel.namespace_id == namespace.id)
            )
        ).scalar() or 0

        fn_count = (
            await db.execute(
                select(func.count())
                .select_from(Function)
                .join(NamespaceServiceModel, Function.service_id == NamespaceServiceModel.id)
                .where(NamespaceServiceModel.namespace_id == namespace.id)
            )
        ).scalar() or 0

        key_count = (
            await db.execute(
                select(func.count()).select_from(APIKey).where(APIKey.namespace_id == namespace.id)
            )
        ).scalar() or 0

        deleted_ns = await service.delete(namespace.id, account.id)
        await db.commit()

        recovery_until = deleted_ns.deleted_at + timedelta(days=30)

        return NamespaceDeletedResponse(
            name=deleted_ns.name,
            deleted_at=deleted_ns.deleted_at.isoformat(),
            recovery_until=recovery_until.isoformat(),
            affected_services=svc_count,
            affected_functions=fn_count,
            affected_api_keys=key_count,
        )
    except NotFoundError:
        raise HTTPException(status_code=404, detail=f"Namespace '{namespace_name}' not found")
    except ForbiddenError:
        raise HTTPException(status_code=403, detail="Access denied")


# Service Endpoints
@router.post(
    "/{namespace_name}/services",
    response_model=ServiceResponse,
    status_code=201,
    dependencies=[Depends(require_scope("write"))],
)
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
            call_count=service.call_count,
            created_at=service.created_at.isoformat(),
        )
    except NotFoundError:
        raise HTTPException(status_code=404, detail=f"Namespace '{namespace_name}' not found")
    except ConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get(
    "/{namespace_name}/services",
    response_model=ServiceListResponse,
    dependencies=[Depends(require_scope("read"))],
)
async def list_services(
    namespace_name: str,
    db: AsyncSession = Depends(get_db),
    account: Account = Depends(get_current_account),
) -> ServiceListResponse:
    """List all services in a namespace."""
    ns_service = NamespaceServiceManager(db)
    svc_service = NamespaceServiceService(db)

    try:
        namespace = await ns_service.get_by_name(
            namespace_name,
            account.id,
            user_id=account.user_id,
            required_permission="read",
        )
        services = await svc_service.list(namespace.id)

        return ServiceListResponse(
            services=[
                ServiceResponse(
                    id=str(s.id),
                    name=s.name,
                    description=s.description,
                    namespace_id=str(s.namespace_id),
                    function_count=s.function_count,
                    call_count=s.call_count,
                    created_at=s.created_at.isoformat(),
                )
                for s in services
            ],
            namespace=namespace_name,
        )
    except NotFoundError:
        raise HTTPException(status_code=404, detail=f"Namespace '{namespace_name}' not found")


@router.delete(
    "/{namespace_name}/services/{service_name}",
    status_code=204,
    dependencies=[Depends(require_scope("write"))],
)
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
    dependencies=[Depends(require_scope("write"))],
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
            call_count=function.call_count,
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
    dependencies=[Depends(require_scope("read"))],
)
async def list_functions(
    namespace_name: str,
    service_name: str,
    tag: str | None = None,
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
        namespace = await ns_service.get_by_name(
            namespace_name,
            account.id,
            user_id=account.user_id,
            required_permission="read",
        )
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
                    call_count=f.call_count,
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
    dependencies=[Depends(require_scope("read"))],
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
        namespace = await ns_service.get_by_name(
            namespace_name,
            account.id,
            user_id=account.user_id,
            required_permission="read",
        )
        service = await svc_service.get_by_name(namespace.id, service_name)
        function = await func_service.get_by_name(service.id, function_name)
        details = await func_service.describe(function.id)

        return FunctionDetailResponse(
            id=details["id"],
            name=details["name"],
            description=details["description"],
            tags=details["tags"],
            active_version=details["active_version"],
            call_count=details.get("call_count", 0),
            active_version_details=details["active_version_details"],
            versions=details["versions"],
            created_at=details["created_at"],
            updated_at=details["updated_at"],
        )
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get(
    "/{namespace_name}/services/{service_name}/functions/{function_name}/versions/{version_num}",
    response_model=FunctionVersionDetailResponse,
    dependencies=[Depends(require_scope("read"))],
)
async def get_function_version(
    namespace_name: str,
    service_name: str,
    function_name: str,
    version_num: int,
    db: AsyncSession = Depends(get_db),
    account: Account = Depends(get_current_account),
) -> FunctionVersionDetailResponse:
    """Get detailed information for a specific function version."""
    ns_service = NamespaceServiceManager(db)
    svc_service = NamespaceServiceService(db)
    func_service = FunctionService(db)

    try:
        namespace = await ns_service.get_by_name(
            namespace_name,
            account.id,
            user_id=account.user_id,
            required_permission="read",
        )
        service = await svc_service.get_by_name(namespace.id, service_name)
        function = await func_service.get_by_name(service.id, function_name)
        detail = await func_service.get_version_detail(function.id, version_num)

        return FunctionVersionDetailResponse(**detail)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete(
    "/{namespace_name}/services/{service_name}/functions/{function_name}",
    status_code=204,
    dependencies=[Depends(require_scope("write"))],
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
