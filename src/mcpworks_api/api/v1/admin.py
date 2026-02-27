"""Admin API endpoints - superadmin cross-user visibility."""

import asyncio
import uuid as uuid_module
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from mcpworks_api.core.database import get_db
from mcpworks_api.dependencies import AdminUserId
from mcpworks_api.models import (
    Account,
    AuditLog,
    Execution,
    Function,
    FunctionVersion,
    Namespace,
    NamespaceService,
    User,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/stats")
async def get_stats(
    _admin: AdminUserId,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Dashboard stats: total users, namespaces, services, functions, executions."""
    users_count = (await db.execute(select(func.count(User.id)))).scalar() or 0
    namespaces_count = (await db.execute(select(func.count(Namespace.id)))).scalar() or 0
    services_count = (await db.execute(select(func.count(NamespaceService.id)))).scalar() or 0
    functions_count = (await db.execute(select(func.count(Function.id)))).scalar() or 0
    executions_count = (await db.execute(select(func.count(Execution.id)))).scalar() or 0

    total_calls = (
        await db.execute(select(func.coalesce(func.sum(Namespace.call_count), 0)))
    ).scalar() or 0

    return {
        "users": users_count,
        "namespaces": namespaces_count,
        "services": services_count,
        "functions": functions_count,
        "executions": executions_count,
        "total_calls": total_calls,
    }


@router.get("/namespaces")
async def list_namespaces(
    _admin: AdminUserId,
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """All namespaces with owner email, account name, service count."""
    result = await db.execute(
        select(Namespace)
        .options(
            selectinload(Namespace.account).selectinload(Account.user),
            selectinload(Namespace.services),
        )
        .order_by(Namespace.created_at.desc())
    )
    namespaces = result.scalars().all()

    return [
        {
            "name": ns.name,
            "description": ns.description,
            "owner_email": ns.account.user.email if ns.account and ns.account.user else None,
            "account_name": ns.account.name if ns.account else None,
            "service_count": len(ns.services) if ns.services else 0,
            "call_count": ns.call_count,
            "created_at": ns.created_at.isoformat() if ns.created_at else None,
        }
        for ns in namespaces
    ]


@router.get("/namespaces/{ns_name}")
async def get_namespace(
    ns_name: str,
    _admin: AdminUserId,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Namespace detail: services list with function counts."""
    result = await db.execute(
        select(Namespace)
        .where(Namespace.name == ns_name)
        .options(
            selectinload(Namespace.account).selectinload(Account.user),
            selectinload(Namespace.services).selectinload(NamespaceService.functions),
        )
    )
    ns = result.scalar_one_or_none()

    if not ns:
        raise HTTPException(status_code=404, detail=f"Namespace '{ns_name}' not found")

    return {
        "name": ns.name,
        "description": ns.description,
        "owner_email": ns.account.user.email if ns.account and ns.account.user else None,
        "account_name": ns.account.name if ns.account else None,
        "network_whitelist": ns.network_whitelist,
        "call_count": ns.call_count,
        "created_at": ns.created_at.isoformat() if ns.created_at else None,
        "services": [
            {
                "name": svc.name,
                "description": svc.description,
                "function_count": len(svc.functions) if svc.functions else 0,
                "call_count": svc.call_count,
                "created_at": svc.created_at.isoformat() if svc.created_at else None,
            }
            for svc in (ns.services or [])
        ],
    }


@router.get("/namespaces/{ns_name}/services/{svc_name}/functions")
async def list_functions(
    ns_name: str,
    svc_name: str,
    _admin: AdminUserId,
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """Functions in a service."""
    result = await db.execute(
        select(Function)
        .join(NamespaceService, Function.service_id == NamespaceService.id)
        .join(Namespace, NamespaceService.namespace_id == Namespace.id)
        .where(Namespace.name == ns_name, NamespaceService.name == svc_name)
        .order_by(Function.name)
    )
    functions = result.scalars().all()

    return [
        {
            "name": fn.name,
            "description": fn.description,
            "tags": fn.tags,
            "active_version": fn.active_version,
            "call_count": fn.call_count,
            "created_at": fn.created_at.isoformat() if fn.created_at else None,
        }
        for fn in functions
    ]


@router.get("/namespaces/{ns_name}/services/{svc_name}/functions/{fn_name}")
async def get_function(
    ns_name: str,
    svc_name: str,
    fn_name: str,
    _admin: AdminUserId,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Full function detail: code, versions, config, schemas."""
    result = await db.execute(
        select(Function)
        .join(NamespaceService, Function.service_id == NamespaceService.id)
        .join(Namespace, NamespaceService.namespace_id == Namespace.id)
        .where(
            Namespace.name == ns_name,
            NamespaceService.name == svc_name,
            Function.name == fn_name,
        )
        .options(selectinload(Function.versions))
    )
    fn = result.scalar_one_or_none()

    if not fn:
        raise HTTPException(
            status_code=404,
            detail=f"Function '{fn_name}' not found in {ns_name}/{svc_name}",
        )

    versions = sorted(fn.versions or [], key=lambda v: v.version, reverse=True)
    active_ver = next((v for v in versions if v.version == fn.active_version), None)

    return {
        "name": fn.name,
        "description": fn.description,
        "tags": fn.tags,
        "active_version": fn.active_version,
        "call_count": fn.call_count,
        "created_at": fn.created_at.isoformat() if fn.created_at else None,
        "updated_at": fn.updated_at.isoformat() if fn.updated_at else None,
        "active_version_details": _version_to_dict(active_ver) if active_ver else None,
        "versions": [_version_to_dict(v) for v in versions],
    }


def _version_to_dict(v: FunctionVersion) -> dict[str, Any]:
    return {
        "version": v.version,
        "backend": v.backend,
        "code": v.code,
        "config": v.config,
        "input_schema": v.input_schema,
        "output_schema": v.output_schema,
        "created_at": v.created_at.isoformat() if v.created_at else None,
    }


# --- Additional list endpoints for stat card drill-down ---


@router.get("/users")
async def list_users(
    _admin: AdminUserId,
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """All users with tier, status, namespace count."""
    result = await db.execute(
        select(User)
        .options(
            selectinload(User.account).selectinload(Account.namespaces),
            selectinload(User.subscription),
        )
        .order_by(User.created_at.desc())
    )
    users = result.scalars().all()

    return [
        {
            "id": str(u.id),
            "email": u.email,
            "name": u.name,
            "tier": u.tier,
            "status": u.status,
            "namespace_count": len(u.account.namespaces)
            if u.account and u.account.namespaces
            else 0,
            "subscription_status": u.subscription.status if u.subscription else None,
            "created_at": u.created_at.isoformat() if u.created_at else None,
        }
        for u in users
    ]


@router.get("/services")
async def list_all_services(
    _admin: AdminUserId,
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """All services across all namespaces."""
    result = await db.execute(
        select(NamespaceService)
        .options(
            selectinload(NamespaceService.namespace)
            .selectinload(Namespace.account)
            .selectinload(Account.user),
            selectinload(NamespaceService.functions),
        )
        .order_by(NamespaceService.created_at.desc())
    )
    services = result.scalars().all()

    return [
        {
            "name": svc.name,
            "description": svc.description,
            "namespace": svc.namespace.name if svc.namespace else None,
            "owner_email": (
                svc.namespace.account.user.email
                if svc.namespace and svc.namespace.account and svc.namespace.account.user
                else None
            ),
            "function_count": len(svc.functions) if svc.functions else 0,
            "call_count": svc.call_count,
            "created_at": svc.created_at.isoformat() if svc.created_at else None,
        }
        for svc in services
    ]


@router.get("/functions")
async def list_all_functions(
    _admin: AdminUserId,
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """All functions across all namespaces/services."""
    result = await db.execute(
        select(Function)
        .options(
            selectinload(Function.service).selectinload(NamespaceService.namespace),
        )
        .order_by(Function.created_at.desc())
    )
    functions = result.scalars().all()

    return [
        {
            "name": fn.name,
            "description": fn.description,
            "tags": fn.tags,
            "active_version": fn.active_version,
            "call_count": fn.call_count,
            "service": fn.service.name if fn.service else None,
            "namespace": fn.service.namespace.name if fn.service and fn.service.namespace else None,
            "created_at": fn.created_at.isoformat() if fn.created_at else None,
        }
        for fn in functions
    ]


@router.get("/executions")
async def list_all_executions(
    _admin: AdminUserId,
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """Recent executions across all users (last 100)."""
    result = await db.execute(
        select(Execution)
        .options(
            selectinload(Execution.user),
            selectinload(Execution.function),
        )
        .order_by(Execution.created_at.desc())
        .limit(100)
    )
    executions = result.scalars().all()

    return [
        {
            "id": str(ex.id),
            "user_email": ex.user.email if ex.user else None,
            "function_name": ex.function.name if ex.function else None,
            "workflow_id": ex.workflow_id,
            "status": ex.status,
            "started_at": ex.started_at.isoformat() if ex.started_at else None,
            "completed_at": ex.completed_at.isoformat() if ex.completed_at else None,
            "duration_seconds": ex.duration_seconds,
            "error_message": ex.error_message,
            "created_at": ex.created_at.isoformat() if ex.created_at else None,
        }
        for ex in executions
    ]


# --- Pending approvals management ---


class RejectRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


@router.get("/pending-approvals")
async def list_pending_approvals(
    _admin: AdminUserId,
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """List accounts pending admin approval."""
    result = await db.execute(
        select(User).where(User.status == "pending_approval").order_by(User.created_at.desc())
    )
    users = result.scalars().all()

    return [
        {
            "id": str(u.id),
            "email": u.email,
            "name": u.name,
            "created_at": u.created_at.isoformat() if u.created_at else None,
        }
        for u in users
    ]


@router.post("/users/{user_id}/approve")
async def approve_user(
    user_id: str,
    admin_id: AdminUserId,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Approve a pending user account."""
    result = await db.execute(select(User).where(User.id == uuid_module.UUID(user_id)))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.status != "pending_approval":
        raise HTTPException(status_code=409, detail="User is not in pending_approval status")

    user.status = "active"

    audit_log = AuditLog(
        user_id=uuid_module.UUID(admin_id),
        action="user_approved",
        resource_type="user",
        resource_id=user.id,
        event_data={"approved_user_email": user.email},
    )
    db.add(audit_log)

    asyncio.create_task(
        _fire_approval_security_event(admin_id, str(user.id), user.email, "approved")
    )
    asyncio.create_task(_send_approval_email(user.email, user.name))

    await db.commit()

    return {
        "user_id": str(user.id),
        "status": "active",
        "message": f"User {user.email} has been approved",
    }


@router.post("/users/{user_id}/reject")
async def reject_user(
    user_id: str,
    admin_id: AdminUserId,
    body: RejectRequest | None = None,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Reject a pending user account."""
    result = await db.execute(select(User).where(User.id == uuid_module.UUID(user_id)))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.status != "pending_approval":
        raise HTTPException(status_code=409, detail="User is not in pending_approval status")

    user.status = "rejected"
    reason = body.reason if body else None
    user.rejection_reason = reason

    audit_log = AuditLog(
        user_id=uuid_module.UUID(admin_id),
        action="user_rejected",
        resource_type="user",
        resource_id=user.id,
        event_data={"rejected_user_email": user.email, "reason": reason},
    )
    db.add(audit_log)

    asyncio.create_task(
        _fire_approval_security_event(admin_id, str(user.id), user.email, "rejected")
    )
    asyncio.create_task(_send_rejection_email(user.email, user.name, reason))

    await db.commit()

    return {
        "user_id": str(user.id),
        "status": "rejected",
        "message": f"User {user.email} has been rejected",
    }


async def _fire_approval_security_event(
    admin_id: str, user_id: str, email: str, action: str
) -> None:
    from mcpworks_api.core.database import get_db_context
    from mcpworks_api.services.security_event import fire_security_event

    try:
        async with get_db_context() as db:
            await fire_security_event(
                db,
                event_type=f"admin.user_{action}",
                severity="info",
                actor_id=admin_id,
                details={"target_user_id": user_id, "target_email": email},
            )
    except Exception as e:
        logger.warning("approval_security_event_failed", error=str(e))


async def _send_approval_email(email: str, name: str | None) -> None:
    try:
        from mcpworks_api.services.email import send_account_approved_email

        await send_account_approved_email(email, name)
    except Exception as e:
        logger.warning("approval_email_failed", error=str(e))


async def _send_rejection_email(email: str, name: str | None, reason: str | None) -> None:
    try:
        from mcpworks_api.services.email import send_account_rejected_email

        await send_account_rejected_email(email, name, reason)
    except Exception as e:
        logger.warning("rejection_email_failed", error=str(e))
