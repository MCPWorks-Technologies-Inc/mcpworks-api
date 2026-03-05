"""Admin API endpoints - superadmin cross-user visibility."""

import asyncio
import uuid as uuid_module
from datetime import datetime
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
    NamespaceShare,
    User,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/search")
async def search(
    q: str,
    _admin: AdminUserId,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Search across users, namespaces, services, and functions."""
    term = f"%{q.strip().lower()}%"
    if len(q.strip()) < 2:
        return {"users": [], "namespaces": [], "services": [], "functions": []}

    users_q = (
        select(User)
        .where(func.lower(User.email).like(term) | func.lower(User.name).like(term))
        .order_by(User.created_at.desc())
        .limit(10)
    )
    users_rows = (await db.execute(users_q)).scalars().all()
    users = [
        {
            "id": str(u.id),
            "email": u.email,
            "name": u.name,
            "tier": u.tier,
            "status": u.status,
        }
        for u in users_rows
    ]

    ns_q = (
        select(Namespace)
        .options(selectinload(Namespace.account).selectinload(Account.user))
        .where(func.lower(Namespace.name).like(term))
        .order_by(Namespace.created_at.desc())
        .limit(10)
    )
    ns_rows = (await db.execute(ns_q)).scalars().all()
    namespaces = [
        {
            "name": ns.name,
            "owner_email": ns.account.user.email if ns.account and ns.account.user else None,
            "call_count": ns.call_count,
        }
        for ns in ns_rows
    ]

    svc_q = (
        select(NamespaceService)
        .options(selectinload(NamespaceService.namespace))
        .where(func.lower(NamespaceService.name).like(term))
        .order_by(NamespaceService.created_at.desc())
        .limit(10)
    )
    svc_rows = (await db.execute(svc_q)).scalars().all()
    services = [
        {
            "name": svc.name,
            "namespace": svc.namespace.name if svc.namespace else None,
            "call_count": svc.call_count,
        }
        for svc in svc_rows
    ]

    fn_q = (
        select(Function)
        .options(
            selectinload(Function.service).selectinload(NamespaceService.namespace),
        )
        .where(func.lower(Function.name).like(term))
        .order_by(Function.created_at.desc())
        .limit(10)
    )
    fn_rows = (await db.execute(fn_q)).scalars().all()
    functions = [
        {
            "name": fn.name,
            "service": fn.service.name if fn.service else None,
            "namespace": fn.service.namespace.name if fn.service and fn.service.namespace else None,
            "call_count": fn.call_count,
        }
        for fn in fn_rows
    ]

    return {
        "users": users,
        "namespaces": namespaces,
        "services": services,
        "functions": functions,
    }


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


@router.get("/stats/leaderboard")
async def get_stats_leaderboard(
    _admin: AdminUserId,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Leaderboard stats: top users, namespaces, services, functions by activity."""
    top_users_q = (
        select(
            User.id,
            User.email,
            User.name,
            User.tier,
            func.coalesce(func.sum(Namespace.call_count), 0).label("total_calls"),
            func.count(func.distinct(Namespace.id)).label("namespace_count"),
            func.count(func.distinct(Function.id)).label("function_count"),
        )
        .outerjoin(Account, User.id == Account.user_id)
        .outerjoin(Namespace, Account.id == Namespace.account_id)
        .outerjoin(NamespaceService, Namespace.id == NamespaceService.namespace_id)
        .outerjoin(Function, NamespaceService.id == Function.service_id)
        .where(User.status == "active")
        .group_by(User.id)
        .order_by(func.coalesce(func.sum(Namespace.call_count), 0).desc())
        .limit(10)
    )
    top_users_rows = (await db.execute(top_users_q)).all()
    top_users = [
        {
            "id": str(r.id),
            "email": r.email,
            "name": r.name,
            "tier": r.tier,
            "total_calls": int(r.total_calls),
            "namespace_count": int(r.namespace_count),
            "function_count": int(r.function_count),
        }
        for r in top_users_rows
    ]

    top_ns_q = (
        select(Namespace)
        .options(
            selectinload(Namespace.account).selectinload(Account.user),
            selectinload(Namespace.services).selectinload(NamespaceService.functions),
        )
        .order_by(Namespace.call_count.desc())
        .limit(10)
    )
    top_ns_rows = (await db.execute(top_ns_q)).scalars().all()
    top_namespaces = [
        {
            "name": ns.name,
            "call_count": ns.call_count,
            "owner_email": ns.account.user.email if ns.account and ns.account.user else None,
            "service_count": len(ns.services) if ns.services else 0,
            "function_count": sum(
                len(svc.functions) for svc in (ns.services or []) if svc.functions
            ),
        }
        for ns in top_ns_rows
    ]

    top_svc_q = (
        select(NamespaceService)
        .options(
            selectinload(NamespaceService.namespace)
            .selectinload(Namespace.account)
            .selectinload(Account.user),
        )
        .order_by(NamespaceService.call_count.desc())
        .limit(10)
    )
    top_svc_rows = (await db.execute(top_svc_q)).scalars().all()
    top_services = [
        {
            "name": svc.name,
            "call_count": svc.call_count,
            "namespace": svc.namespace.name if svc.namespace else None,
            "owner_email": (
                svc.namespace.account.user.email
                if svc.namespace and svc.namespace.account and svc.namespace.account.user
                else None
            ),
        }
        for svc in top_svc_rows
    ]

    top_fn_q = (
        select(Function)
        .options(
            selectinload(Function.service).selectinload(NamespaceService.namespace),
            selectinload(Function.versions),
        )
        .order_by(Function.call_count.desc())
        .limit(10)
    )
    top_fn_rows = (await db.execute(top_fn_q)).scalars().all()
    top_functions = [
        {
            "name": fn.name,
            "call_count": fn.call_count,
            "service": fn.service.name if fn.service else None,
            "namespace": fn.service.namespace.name if fn.service and fn.service.namespace else None,
            "backend": (
                fn.get_active_version_obj().backend if fn.get_active_version_obj() else None
            ),
        }
        for fn in top_fn_rows
    ]

    tier_q = (
        select(User.tier, func.count(User.id).label("count"))
        .where(User.status == "active")
        .group_by(User.tier)
    )
    tier_rows = (await db.execute(tier_q)).all()
    tier_breakdown = [{"tier": r.tier, "count": int(r.count)} for r in tier_rows]

    recent_exec_q = (
        select(Execution)
        .options(
            selectinload(Execution.user),
            selectinload(Execution.function),
        )
        .order_by(Execution.created_at.desc())
        .limit(10)
    )
    recent_exec_rows = (await db.execute(recent_exec_q)).scalars().all()
    recent_executions = [
        {
            "id": str(ex.id),
            "user_email": ex.user.email if ex.user else None,
            "function_name": ex.function.name if ex.function else None,
            "status": ex.status,
            "duration_seconds": ex.duration_seconds,
            "created_at": ex.created_at.isoformat() if ex.created_at else None,
        }
        for ex in recent_exec_rows
    ]

    return {
        "top_users": top_users,
        "top_namespaces": top_namespaces,
        "top_services": top_services,
        "top_functions": top_functions,
        "tier_breakdown": tier_breakdown,
        "recent_executions": recent_executions,
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
            selectinload(Namespace.shares).selectinload(NamespaceShare.user),
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
        "network_allowlist": ns.network_allowlist,
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
        "shares": [
            {
                "id": str(share.id),
                "user_email": share.user.email if share.user else None,
                "user_name": share.user.name if share.user else None,
                "permissions": share.permissions,
                "status": share.status,
                "created_at": share.created_at.isoformat() if share.created_at else None,
            }
            for share in (ns.shares or [])
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


class SuspendRequest(BaseModel):
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


@router.get("/users/{user_id}")
async def get_user(
    user_id: str,
    _admin: AdminUserId,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Full user detail: profile, namespaces, API keys, subscription."""
    result = await db.execute(
        select(User)
        .where(User.id == uuid_module.UUID(user_id))
        .options(
            selectinload(User.account)
            .selectinload(Account.namespaces)
            .selectinload(Namespace.services)
            .selectinload(NamespaceService.functions),
            selectinload(User.api_keys),
            selectinload(User.subscription),
        )
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    namespaces = []
    total_functions = 0
    total_calls = 0
    if user.account and user.account.namespaces:
        for ns in user.account.namespaces:
            fn_count = sum(len(svc.functions) for svc in (ns.services or []) if svc.functions)
            total_functions += fn_count
            total_calls += ns.call_count or 0
            namespaces.append(
                {
                    "name": ns.name,
                    "service_count": len(ns.services) if ns.services else 0,
                    "function_count": fn_count,
                    "call_count": ns.call_count or 0,
                    "created_at": ns.created_at.isoformat() if ns.created_at else None,
                }
            )

    api_keys = []
    for key in user.api_keys or []:
        if key.revoked_at:
            continue
        api_keys.append(
            {
                "prefix": key.key_prefix,
                "name": key.name,
                "scopes": key.scopes,
                "last_used_at": key.last_used_at.isoformat() if key.last_used_at else None,
                "created_at": key.created_at.isoformat() if key.created_at else None,
            }
        )

    return {
        "id": str(user.id),
        "email": user.email,
        "name": user.name,
        "tier": user.tier,
        "effective_tier": user.effective_tier,
        "tier_override": user.tier_override,
        "tier_override_reason": user.tier_override_reason,
        "tier_override_expires_at": (
            user.tier_override_expires_at.isoformat() if user.tier_override_expires_at else None
        ),
        "status": user.status,
        "email_verified": user.email_verified,
        "rejection_reason": user.rejection_reason,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "namespace_count": len(namespaces),
        "total_functions": total_functions,
        "total_calls": total_calls,
        "api_key_count": len(api_keys),
        "subscription_status": user.subscription.status if user.subscription else None,
        "namespaces": namespaces,
        "api_keys": api_keys,
    }


@router.post("/users/{user_id}/suspend")
async def suspend_user(
    user_id: str,
    admin_id: AdminUserId,
    body: SuspendRequest | None = None,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Suspend an active user account."""
    result = await db.execute(select(User).where(User.id == uuid_module.UUID(user_id)))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.status != "active":
        raise HTTPException(status_code=409, detail="User is not in active status")

    user.status = "suspended"
    reason = body.reason if body else None
    user.rejection_reason = reason

    audit_log = AuditLog(
        user_id=uuid_module.UUID(admin_id),
        action="user_suspended",
        resource_type="user",
        resource_id=user.id,
        event_data={"suspended_user_email": user.email, "reason": reason},
    )
    db.add(audit_log)

    asyncio.create_task(
        _fire_approval_security_event(admin_id, str(user.id), user.email, "suspended")
    )
    asyncio.create_task(_send_suspension_email(user.email, user.name, reason))

    await db.commit()

    return {
        "user_id": str(user.id),
        "status": "suspended",
        "message": f"User {user.email} has been suspended",
    }


@router.post("/users/{user_id}/unsuspend")
async def unsuspend_user(
    user_id: str,
    admin_id: AdminUserId,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Unsuspend a suspended user account."""
    result = await db.execute(select(User).where(User.id == uuid_module.UUID(user_id)))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.status != "suspended":
        raise HTTPException(status_code=409, detail="User is not in suspended status")

    user.status = "active"
    user.rejection_reason = None

    audit_log = AuditLog(
        user_id=uuid_module.UUID(admin_id),
        action="user_unsuspended",
        resource_type="user",
        resource_id=user.id,
        event_data={"unsuspended_user_email": user.email},
    )
    db.add(audit_log)

    asyncio.create_task(
        _fire_approval_security_event(admin_id, str(user.id), user.email, "unsuspended")
    )
    asyncio.create_task(_send_unsuspension_email(user.email, user.name))

    await db.commit()

    return {
        "user_id": str(user.id),
        "status": "active",
        "message": f"User {user.email} has been unsuspended",
    }


class DeleteAccountRequest(BaseModel):
    confirm_email: str = Field(..., description="Must match user email to confirm deletion")


@router.delete("/users/{user_id}")
async def delete_user_account(
    user_id: str,
    body: DeleteAccountRequest,
    admin_id: AdminUserId,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Permanently delete a user and all associated resources (GDPR Art. 17)."""
    result = await db.execute(
        select(User)
        .where(User.id == uuid_module.UUID(user_id))
        .options(
            selectinload(User.account)
            .selectinload(Account.namespaces)
            .selectinload(Namespace.services)
            .selectinload(NamespaceService.functions),
        )
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if body.confirm_email != user.email:
        raise HTTPException(status_code=422, detail="Email confirmation does not match")

    if user.is_admin:
        raise HTTPException(status_code=403, detail="Cannot delete admin accounts")

    email = user.email
    uid = str(user.id)

    ns_count = 0
    svc_count = 0
    fn_count = 0
    if user.account:
        for ns in user.account.namespaces or []:
            ns_count += 1
            for svc in ns.services or []:
                svc_count += 1
                fn_count += len(svc.functions) if svc.functions else 0

    audit_log = AuditLog(
        user_id=uuid_module.UUID(admin_id),
        action="user_account_deleted",
        resource_type="user",
        resource_id=uuid_module.UUID(uid),
        event_data={
            "deleted_email": email,
            "namespaces_deleted": ns_count,
            "services_deleted": svc_count,
            "functions_deleted": fn_count,
            "reason": "GDPR right to erasure / admin action",
        },
    )
    db.add(audit_log)

    await db.delete(user)
    await db.commit()

    asyncio.create_task(_fire_approval_security_event(admin_id, uid, email, "account_deleted"))

    logger.info(
        "user_account_deleted",
        user_id=uid,
        email=email,
        namespaces=ns_count,
        services=svc_count,
        functions=fn_count,
        admin_id=admin_id,
    )

    return {
        "deleted": True,
        "user_id": uid,
        "email": email,
        "resources_deleted": {
            "namespaces": ns_count,
            "services": svc_count,
            "functions": fn_count,
        },
    }


class TierOverrideRequest(BaseModel):
    tier: str = Field(
        ...,
        description="Tier to grant: builder, pro, or enterprise",
        pattern="^(builder|pro|enterprise)$",
    )
    reason: str = Field(
        ...,
        description="Reason for the override (required)",
        min_length=3,
        max_length=255,
    )
    expires_at: datetime | None = Field(
        default=None,
        description="When the override expires (null = indefinite)",
    )


class TierOverrideClearRequest(BaseModel):
    reason: str = Field(
        ...,
        description="Reason for clearing the override",
        min_length=3,
        max_length=255,
    )


@router.post("/users/{user_id}/tier-override")
async def set_tier_override(
    user_id: str,
    body: TierOverrideRequest,
    admin_id: AdminUserId,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Set a tier override on a user (e.g., grant free pro access)."""
    result = await db.execute(select(User).where(User.id == uuid_module.UUID(user_id)))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.tier_override = body.tier
    user.tier_override_reason = body.reason
    user.tier_override_expires_at = body.expires_at

    audit_log = AuditLog(
        user_id=uuid_module.UUID(admin_id),
        action="tier_override_set",
        resource_type="user",
        resource_id=user.id,
        event_data={
            "target_email": user.email,
            "tier_override": body.tier,
            "reason": body.reason,
            "expires_at": body.expires_at.isoformat() if body.expires_at else None,
        },
    )
    db.add(audit_log)

    await db.commit()

    return {
        "user_id": str(user.id),
        "tier": user.tier,
        "tier_override": user.tier_override,
        "effective_tier": user.effective_tier,
        "tier_override_reason": user.tier_override_reason,
        "tier_override_expires_at": (
            user.tier_override_expires_at.isoformat() if user.tier_override_expires_at else None
        ),
    }


@router.delete("/users/{user_id}/tier-override")
async def clear_tier_override(
    user_id: str,
    admin_id: AdminUserId,
    body: TierOverrideClearRequest | None = None,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Clear a tier override, reverting to subscription-based tier."""
    result = await db.execute(select(User).where(User.id == uuid_module.UUID(user_id)))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if not user.tier_override:
        raise HTTPException(status_code=409, detail="No tier override to clear")

    old_override = user.tier_override
    reason = body.reason if body else "No reason provided"

    user.tier_override = None
    user.tier_override_reason = None
    user.tier_override_expires_at = None

    audit_log = AuditLog(
        user_id=uuid_module.UUID(admin_id),
        action="tier_override_cleared",
        resource_type="user",
        resource_id=user.id,
        event_data={
            "target_email": user.email,
            "previous_override": old_override,
            "reason": reason,
        },
    )
    db.add(audit_log)

    await db.commit()

    return {
        "user_id": str(user.id),
        "tier": user.tier,
        "tier_override": None,
        "effective_tier": user.effective_tier,
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


async def _send_suspension_email(email: str, name: str | None, reason: str | None) -> None:
    try:
        from mcpworks_api.services.email import send_account_suspended_email

        await send_account_suspended_email(email, name, reason)
    except Exception as e:
        logger.warning("suspension_email_failed", error=str(e))


async def _send_unsuspension_email(email: str, name: str | None) -> None:
    try:
        from mcpworks_api.services.email import send_account_unsuspended_email

        await send_account_unsuspended_email(email, name)
    except Exception as e:
        logger.warning("unsuspension_email_failed", error=str(e))


# --- Namespace Shares (admin) ---


class AdminCreateShareRequest(BaseModel):
    email: str = Field(..., description="Email of the user to invite")
    permissions: list[str] = Field(default=["read", "execute"])


@router.post("/namespaces/{ns_name}/shares")
async def create_namespace_share(
    ns_name: str,
    request: AdminCreateShareRequest,
    _admin: AdminUserId,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Admin: create a share invite on a namespace."""
    from mcpworks_api.core.exceptions import (
        ConflictError,
        ForbiddenError,
        NotFoundError,
        ValidationError,
    )
    from mcpworks_api.services.namespace_share import NamespaceShareService

    ns_result = await db.execute(
        select(Namespace).where(Namespace.name == ns_name).options(selectinload(Namespace.account))
    )
    ns = ns_result.scalar_one_or_none()
    if not ns:
        raise HTTPException(status_code=404, detail=f"Namespace '{ns_name}' not found")

    share_service = NamespaceShareService(db)
    try:
        share = await share_service.create_invite(
            namespace_id=ns.id,
            invitee_email=request.email,
            permissions=request.permissions,
            granted_by_user_id=ns.account.user_id,
        )
        await db.commit()
        return {
            "id": str(share.id),
            "user_id": str(share.user_id),
            "permissions": share.permissions,
            "status": share.status,
        }
    except (NotFoundError, ForbiddenError) as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.delete("/namespaces/{ns_name}/shares/{share_id}")
async def revoke_namespace_share(
    ns_name: str,
    share_id: str,
    _admin: AdminUserId,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Admin: revoke a namespace share."""
    from mcpworks_api.core.exceptions import ForbiddenError, NotFoundError
    from mcpworks_api.services.namespace_share import NamespaceShareService

    ns_result = await db.execute(
        select(Namespace).where(Namespace.name == ns_name).options(selectinload(Namespace.account))
    )
    ns = ns_result.scalar_one_or_none()
    if not ns:
        raise HTTPException(status_code=404, detail=f"Namespace '{ns_name}' not found")

    share_service = NamespaceShareService(db)
    try:
        await share_service.revoke(
            share_id=share_id,
            owner_user_id=ns.account.user_id,
        )
        await db.commit()
        return {"status": "revoked"}
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ForbiddenError as e:
        raise HTTPException(status_code=403, detail=str(e))
