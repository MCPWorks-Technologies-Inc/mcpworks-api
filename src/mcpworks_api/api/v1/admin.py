"""Admin API endpoints - superadmin cross-user visibility."""

import asyncio
import os
import uuid as uuid_module
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from mcpworks_api.config import get_settings
from mcpworks_api.core.database import get_db, get_engine
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
    SecurityEvent,
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


@router.get("/stats/sandbox")
async def get_sandbox_stats(
    _admin: AdminUserId,
) -> dict[str, Any]:
    """Real-time sandbox execution metrics (in-memory since last restart)."""
    from mcpworks_api.middleware.execution_metrics import get_stats_snapshot

    return get_stats_snapshot()


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


@router.post("/users/{user_id}/delete")
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

    if user.email in get_settings().admin_emails:
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
        description="Tier to grant",
        pattern="^(trial|pro|enterprise|dedicated|trial-agent|pro-agent|enterprise-agent|dedicated-agent)$",
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


@router.post("/users/{user_id}/clear-tier-override")
async def clear_tier_override_post(
    user_id: str,
    admin_id: AdminUserId,
    body: TierOverrideClearRequest | None = None,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """POST variant of clear_tier_override for browser compatibility."""
    return await clear_tier_override(user_id, admin_id, body, db)


@router.post("/users/{user_id}/impersonate")
async def impersonate_user(
    user_id: str,
    request: Request,
    admin_id: AdminUserId,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Generate a short-lived access token to log in as another user."""
    from datetime import timedelta

    from mcpworks_api.core.security import create_access_token

    target_uid = uuid_module.UUID(user_id)

    if str(target_uid) == admin_id:
        raise HTTPException(status_code=422, detail="Cannot impersonate yourself")

    result = await db.execute(select(User).where(User.id == target_uid))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.email in get_settings().admin_emails:
        raise HTTPException(status_code=403, detail="Cannot impersonate admin accounts")

    admin_result = await db.execute(select(User.email).where(User.id == admin_id))
    admin_email = admin_result.scalar_one()

    ip_address = (
        request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        or request.headers.get("X-Real-IP")
        or (request.client.host if request.client else "unknown")
    )
    user_agent = request.headers.get("User-Agent", "unknown")

    token = create_access_token(
        user_id=str(user.id),
        expires_delta=timedelta(hours=1),
        additional_claims={"impersonated_by": admin_id},
    )

    audit_log = AuditLog(
        user_id=uuid_module.UUID(admin_id),
        action="user_impersonated",
        resource_type="user",
        resource_id=user.id,
        event_data={
            "target_email": user.email,
            "ip_address": ip_address,
            "user_agent": user_agent,
        },
    )
    db.add(audit_log)
    await db.commit()

    asyncio.create_task(
        _fire_approval_security_event(admin_id, str(user.id), user.email, "impersonated")
    )
    asyncio.create_task(
        _send_impersonation_email(
            admin_email,
            user.email,
            ip_address,
            user_agent,
        )
    )
    asyncio.create_task(
        _send_impersonation_discord_alert(
            admin_email,
            user.email,
            ip_address,
            user_agent,
        )
    )

    logger.info(
        "admin_impersonate",
        admin_id=admin_id,
        admin_email=admin_email,
        target_user=str(user.id),
        target_email=user.email,
        ip_address=ip_address,
    )

    return {
        "access_token": token,
        "user_id": str(user.id),
        "email": user.email,
        "expires_in": 3600,
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


async def _send_impersonation_email(
    admin_email: str, target_email: str, ip_address: str, user_agent: str
) -> None:
    try:
        from mcpworks_api.services.email import send_admin_impersonation_email

        await send_admin_impersonation_email(
            admin_email=admin_email,
            target_email=target_email,
            ip_address=ip_address,
            user_agent=user_agent,
            timestamp=datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC"),
        )
    except Exception as e:
        logger.warning("impersonation_email_failed", error=str(e))


async def _send_impersonation_discord_alert(
    admin_email: str, target_email: str, ip_address: str, user_agent: str
) -> None:
    try:
        from mcpworks_api.services.discord_alerts import send_impersonation_alert

        await send_impersonation_alert(
            admin_email=admin_email,
            target_email=target_email,
            ip_address=ip_address,
            user_agent=user_agent,
            timestamp=datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC"),
        )
    except Exception as e:
        logger.warning("impersonation_discord_alert_failed", error=str(e))


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


@router.get("/audit-logs")
async def list_audit_logs(
    _admin: AdminUserId,
    db: AsyncSession = Depends(get_db),
    limit: int = 50,
    offset: int = 0,
    action: str | None = None,
    user_id: str | None = None,
) -> dict[str, Any]:
    """Paginated audit log viewer."""
    q = select(AuditLog).order_by(AuditLog.created_at.desc())
    count_q = select(func.count(AuditLog.id))

    if action:
        q = q.where(AuditLog.action == action)
        count_q = count_q.where(AuditLog.action == action)
    if user_id:
        try:
            uid = uuid_module.UUID(user_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid user_id format")
        q = q.where(AuditLog.user_id == uid)
        count_q = count_q.where(AuditLog.user_id == uid)

    total = (await db.execute(count_q)).scalar() or 0
    rows = (await db.execute(q.limit(min(limit, 100)).offset(offset))).scalars().all()

    user_ids = {r.user_id for r in rows if r.user_id}
    user_map: dict[str, str] = {}
    if user_ids:
        user_rows = (
            await db.execute(select(User.id, User.email).where(User.id.in_(user_ids)))
        ).all()
        user_map = {str(u.id): u.email for u in user_rows}

    return {
        "total": total,
        "items": [
            {
                "id": str(r.id),
                "action": r.action,
                "user_email": user_map.get(str(r.user_id)) if r.user_id else None,
                "resource_type": r.resource_type,
                "resource_id": str(r.resource_id) if r.resource_id else None,
                "ip_address": str(r.ip_address) if r.ip_address else None,
                "event_data": r.event_data,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
    }


@router.get("/security-events")
async def list_security_events(
    _admin: AdminUserId,
    db: AsyncSession = Depends(get_db),
    limit: int = 50,
    offset: int = 0,
    severity: str | None = None,
    event_type: str | None = None,
) -> dict[str, Any]:
    """Paginated security events viewer."""
    q = select(SecurityEvent).order_by(SecurityEvent.timestamp.desc())
    count_q = select(func.count(SecurityEvent.id))

    if severity:
        q = q.where(SecurityEvent.severity == severity)
        count_q = count_q.where(SecurityEvent.severity == severity)
    if event_type:
        q = q.where(SecurityEvent.event_type == event_type)
        count_q = count_q.where(SecurityEvent.event_type == event_type)

    total = (await db.execute(count_q)).scalar() or 0
    rows = (await db.execute(q.limit(min(limit, 100)).offset(offset))).scalars().all()

    return {
        "total": total,
        "items": [
            {
                "id": str(r.id),
                "event_type": r.event_type,
                "severity": r.severity,
                "actor_id": r.actor_id,
                "details": r.details,
                "timestamp": r.timestamp.isoformat() if r.timestamp else None,
            }
            for r in rows
        ],
    }


@router.get("/system/health")
async def get_system_health(
    _admin: AdminUserId,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """System health overview for admin dashboard."""
    from mcpworks_api.core.redis import get_redis_context
    from mcpworks_api.middleware.execution_metrics import get_stats_snapshot

    components: dict[str, str] = {}

    try:
        await db.execute(select(func.count(User.id)))
        components["database"] = "healthy"
    except Exception as e:
        components["database"] = f"unhealthy: {e}"

    redis_uptime = 0
    try:
        async with get_redis_context() as redis:
            info = await redis.info("server")
            components["redis"] = "healthy"
            redis_uptime = info.get("uptime_in_seconds", 0)
    except Exception as e:
        components["redis"] = f"unhealthy: {e}"

    sandbox_stats = get_stats_snapshot()

    severity_counts_q = select(
        SecurityEvent.severity,
        func.count(SecurityEvent.id),
    ).group_by(SecurityEvent.severity)
    severity_rows = (await db.execute(severity_counts_q)).all()
    severity_counts = {r[0]: r[1] for r in severity_rows}

    return {
        "components": components,
        "sandbox": sandbox_stats,
        "redis_uptime_seconds": redis_uptime,
        "security_summary": severity_counts,
    }


# --- Execution detail & search ---


@router.get("/executions/{execution_id}")
async def get_execution_detail(
    execution_id: str,
    _admin: AdminUserId,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Full execution detail: input, output, error, timing, metadata."""
    result = await db.execute(
        select(Execution)
        .where(Execution.id == uuid_module.UUID(execution_id))
        .options(
            selectinload(Execution.user),
            selectinload(Execution.function)
            .selectinload(Function.service)
            .selectinload(NamespaceService.namespace),
        )
    )
    ex = result.scalar_one_or_none()

    if not ex:
        raise HTTPException(status_code=404, detail="Execution not found")

    return {
        "id": str(ex.id),
        "user_id": str(ex.user_id),
        "user_email": ex.user.email if ex.user else None,
        "function_id": str(ex.function_id) if ex.function_id else None,
        "function_name": ex.function.name if ex.function else None,
        "service_name": ex.function.service.name if ex.function and ex.function.service else None,
        "namespace": (
            ex.function.service.namespace.name
            if ex.function and ex.function.service and ex.function.service.namespace
            else None
        ),
        "function_version": ex.function_version_num,
        "backend": ex.backend,
        "workflow_id": ex.workflow_id,
        "status": ex.status,
        "input_data": None,
        "result_data": None,
        "error_message": ex.error_message,
        "error_code": ex.error_code,
        "backend_metadata": ex.backend_metadata,
        "started_at": ex.started_at.isoformat() if ex.started_at else None,
        "completed_at": ex.completed_at.isoformat() if ex.completed_at else None,
        "duration_seconds": ex.duration_seconds,
        "created_at": ex.created_at.isoformat() if ex.created_at else None,
    }


@router.get("/executions-search")
async def search_executions(
    _admin: AdminUserId,
    db: AsyncSession = Depends(get_db),
    status: str | None = None,
    user_id: str | None = None,
    function_id: str | None = None,
    namespace: str | None = None,
    since: str | None = Query(
        default=None, description="ISO datetime or relative like '1h', '24h', '7d'"
    ),
    limit: int = Query(default=50, le=200),
    offset: int = 0,
) -> dict[str, Any]:
    """Search executions with filters."""
    q = (
        select(Execution)
        .options(
            selectinload(Execution.user),
            selectinload(Execution.function)
            .selectinload(Function.service)
            .selectinload(NamespaceService.namespace),
        )
        .order_by(Execution.created_at.desc())
    )
    count_q = select(func.count(Execution.id))

    if status:
        q = q.where(Execution.status == status)
        count_q = count_q.where(Execution.status == status)
    if user_id:
        uid = uuid_module.UUID(user_id)
        q = q.where(Execution.user_id == uid)
        count_q = count_q.where(Execution.user_id == uid)
    if function_id:
        fid = uuid_module.UUID(function_id)
        q = q.where(Execution.function_id == fid)
        count_q = count_q.where(Execution.function_id == fid)
    if namespace:
        q = (
            q.join(Function, Execution.function_id == Function.id)
            .join(NamespaceService, Function.service_id == NamespaceService.id)
            .join(Namespace, NamespaceService.namespace_id == Namespace.id)
            .where(Namespace.name == namespace)
        )
        count_q = (
            count_q.join(Function, Execution.function_id == Function.id)
            .join(NamespaceService, Function.service_id == NamespaceService.id)
            .join(Namespace, NamespaceService.namespace_id == Namespace.id)
            .where(Namespace.name == namespace)
        )
    if since:
        since_dt = _parse_relative_time(since)
        q = q.where(Execution.created_at >= since_dt)
        count_q = count_q.where(Execution.created_at >= since_dt)

    total = (await db.execute(count_q)).scalar() or 0
    rows = (await db.execute(q.limit(limit).offset(offset))).scalars().all()

    return {
        "total": total,
        "items": [
            {
                "id": str(ex.id),
                "user_email": ex.user.email if ex.user else None,
                "function_name": ex.function.name if ex.function else None,
                "namespace": (
                    ex.function.service.namespace.name
                    if ex.function and ex.function.service and ex.function.service.namespace
                    else None
                ),
                "status": ex.status,
                "error_message": ex.error_message,
                "error_code": ex.error_code,
                "duration_seconds": ex.duration_seconds,
                "created_at": ex.created_at.isoformat() if ex.created_at else None,
            }
            for ex in rows
        ],
    }


# --- User activity timeline ---


@router.get("/users/{user_id}/activity")
async def get_user_activity(
    user_id: str,
    _admin: AdminUserId,
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=50, le=200),
) -> dict[str, Any]:
    """User activity timeline: recent executions, audit logs, security events."""
    uid = uuid_module.UUID(user_id)

    result = await db.execute(select(User).where(User.id == uid))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    exec_q = (
        select(Execution)
        .where(Execution.user_id == uid)
        .options(selectinload(Execution.function))
        .order_by(Execution.created_at.desc())
        .limit(limit)
    )
    exec_rows = (await db.execute(exec_q)).scalars().all()

    audit_q = (
        select(AuditLog)
        .where(AuditLog.user_id == uid)
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
    )
    audit_rows = (await db.execute(audit_q)).scalars().all()

    sec_q = (
        select(SecurityEvent)
        .where(SecurityEvent.actor_id == str(uid))
        .order_by(SecurityEvent.timestamp.desc())
        .limit(limit)
    )
    sec_rows = (await db.execute(sec_q)).scalars().all()

    return {
        "user": {
            "id": str(user.id),
            "email": user.email,
            "name": user.name,
            "tier": user.tier,
            "effective_tier": user.effective_tier,
            "status": user.status,
        },
        "recent_executions": [
            {
                "id": str(ex.id),
                "function_name": ex.function.name if ex.function else None,
                "status": ex.status,
                "error_message": ex.error_message,
                "duration_seconds": ex.duration_seconds,
                "created_at": ex.created_at.isoformat() if ex.created_at else None,
            }
            for ex in exec_rows
        ],
        "recent_audit_logs": [
            {
                "id": str(r.id),
                "action": r.action,
                "resource_type": r.resource_type,
                "event_data": r.event_data,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in audit_rows
        ],
        "recent_security_events": [
            {
                "id": str(r.id),
                "event_type": r.event_type,
                "severity": r.severity,
                "details": r.details,
                "timestamp": r.timestamp.isoformat() if r.timestamp else None,
            }
            for r in sec_rows
        ],
    }


# --- Error aggregation ---


@router.get("/errors")
async def get_error_summary(
    _admin: AdminUserId,
    db: AsyncSession = Depends(get_db),
    since: str | None = Query(default="24h", description="Relative time like '1h', '24h', '7d'"),
) -> dict[str, Any]:
    """Error aggregation: recent failures grouped by error code and function."""
    since_dt = _parse_relative_time(since or "24h")

    by_code_q = (
        select(
            Execution.error_code,
            func.count(Execution.id).label("count"),
        )
        .where(Execution.status == "failed", Execution.created_at >= since_dt)
        .group_by(Execution.error_code)
        .order_by(func.count(Execution.id).desc())
        .limit(20)
    )
    by_code_rows = (await db.execute(by_code_q)).all()

    by_fn_q = (
        select(
            Function.name.label("function_name"),
            Namespace.name.label("namespace"),
            func.count(Execution.id).label("count"),
        )
        .join(Function, Execution.function_id == Function.id)
        .join(NamespaceService, Function.service_id == NamespaceService.id)
        .join(Namespace, NamespaceService.namespace_id == Namespace.id)
        .where(Execution.status == "failed", Execution.created_at >= since_dt)
        .group_by(Function.name, Namespace.name)
        .order_by(func.count(Execution.id).desc())
        .limit(20)
    )
    by_fn_rows = (await db.execute(by_fn_q)).all()

    recent_q = (
        select(Execution)
        .options(
            selectinload(Execution.user),
            selectinload(Execution.function),
        )
        .where(Execution.status == "failed", Execution.created_at >= since_dt)
        .order_by(Execution.created_at.desc())
        .limit(20)
    )
    recent_rows = (await db.execute(recent_q)).scalars().all()

    total_failed = (
        await db.execute(
            select(func.count(Execution.id)).where(
                Execution.status == "failed", Execution.created_at >= since_dt
            )
        )
    ).scalar() or 0

    total_all = (
        await db.execute(select(func.count(Execution.id)).where(Execution.created_at >= since_dt))
    ).scalar() or 0

    return {
        "since": since_dt.isoformat(),
        "total_executions": total_all,
        "total_failures": total_failed,
        "failure_rate": round(total_failed / total_all * 100, 2) if total_all > 0 else 0,
        "by_error_code": [
            {"error_code": r.error_code or "unknown", "count": r.count} for r in by_code_rows
        ],
        "by_function": [
            {"namespace": r.namespace, "function": r.function_name, "count": r.count}
            for r in by_fn_rows
        ],
        "recent_failures": [
            {
                "id": str(ex.id),
                "user_email": ex.user.email if ex.user else None,
                "function_name": ex.function.name if ex.function else None,
                "error_code": ex.error_code,
                "error_message": ex.error_message,
                "created_at": ex.created_at.isoformat() if ex.created_at else None,
            }
            for ex in recent_rows
        ],
    }


# --- Usage overview ---


@router.get("/usage")
async def get_usage_overview(
    _admin: AdminUserId,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """All accounts' current month usage vs tier limits."""
    from mcpworks_api.core.redis import get_redis_context
    from mcpworks_api.middleware.billing import BillingMiddleware

    now = datetime.now(UTC)

    result = await db.execute(
        select(User)
        .options(selectinload(User.account))
        .where(User.status == "active")
        .order_by(User.created_at.desc())
    )
    users = result.scalars().all()

    usage_data = []
    async with get_redis_context() as redis:
        for user in users:
            if not user.account:
                continue
            month_key = f"usage:{user.account.id}:{now.year}:{now.month}"
            current = await redis.get(month_key)
            usage_count = int(current) if current else 0
            tier = user.effective_tier or user.tier or "trial"
            limit = BillingMiddleware.TIER_LIMITS.get(tier, 125_000)
            pct = round(usage_count / limit * 100, 1) if limit > 0 else 0.0

            usage_data.append(
                {
                    "user_id": str(user.id),
                    "email": user.email,
                    "tier": tier,
                    "usage": usage_count,
                    "limit": limit,
                    "usage_pct": pct,
                    "at_risk": pct >= 80,
                }
            )

    usage_data.sort(key=lambda x: x["usage"], reverse=True)

    return {
        "month": f"{now.year}-{now.month:02d}",
        "accounts": usage_data,
        "accounts_at_risk": [u for u in usage_data if u["at_risk"]],
    }


# --- System resources ---


@router.get("/system/resources")
async def get_system_resources(
    _admin: AdminUserId,
) -> dict[str, Any]:
    """Server resource usage: CPU, memory, disk."""
    resources: dict[str, Any] = {}

    try:
        with open("/proc/loadavg") as f:
            parts = f.read().strip().split()
            resources["cpu"] = {
                "load_1m": float(parts[0]),
                "load_5m": float(parts[1]),
                "load_15m": float(parts[2]),
            }
    except Exception:
        resources["cpu"] = {"error": "unavailable"}

    try:
        with open("/proc/meminfo") as f:
            meminfo = {}
            for line in f:
                key, val = line.split(":", 1)
                meminfo[key.strip()] = int(val.strip().split()[0])
            total_kb = meminfo.get("MemTotal", 0)
            available_kb = meminfo.get("MemAvailable", 0)
            used_kb = total_kb - available_kb
            resources["memory"] = {
                "total_mb": round(total_kb / 1024, 1),
                "used_mb": round(used_kb / 1024, 1),
                "available_mb": round(available_kb / 1024, 1),
                "usage_pct": round(used_kb / total_kb * 100, 1) if total_kb else 0,
            }
    except Exception:
        resources["memory"] = {"error": "unavailable"}

    try:
        statvfs = os.statvfs("/")
        total = statvfs.f_frsize * statvfs.f_blocks
        available = statvfs.f_frsize * statvfs.f_bavail
        used = total - available
        resources["disk"] = {
            "total_gb": round(total / (1024**3), 2),
            "used_gb": round(used / (1024**3), 2),
            "available_gb": round(available / (1024**3), 2),
            "usage_pct": round(used / total * 100, 1) if total else 0,
        }
    except Exception:
        resources["disk"] = {"error": "unavailable"}

    try:
        with open("/proc/uptime") as f:
            uptime_seconds = float(f.read().split()[0])
            days = int(uptime_seconds // 86400)
            hours = int((uptime_seconds % 86400) // 3600)
            resources["uptime"] = {
                "seconds": int(uptime_seconds),
                "human": f"{days}d {hours}h",
            }
    except Exception:
        resources["uptime"] = {"error": "unavailable"}

    return resources


# --- Database diagnostics ---


@router.get("/system/database")
async def get_database_diagnostics(
    _admin: AdminUserId,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Database diagnostics: pool stats, table sizes, active connections."""
    diagnostics: dict[str, Any] = {}

    engine = get_engine()
    pool = engine.pool
    diagnostics["pool"] = {
        "size": pool.size(),
        "checked_in": pool.checkedin(),
        "checked_out": pool.checkedout(),
        "overflow": pool.overflow(),
        "status": pool.status(),
    }

    try:
        conn_result = await db.execute(
            text("SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()")
        )
        diagnostics["active_connections"] = conn_result.scalar()
    except Exception as e:
        diagnostics["active_connections_error"] = str(e)

    try:
        size_result = await db.execute(
            text("SELECT pg_size_pretty(pg_database_size(current_database())) AS db_size")
        )
        diagnostics["database_size"] = size_result.scalar()
    except Exception as e:
        diagnostics["database_size_error"] = str(e)

    try:
        table_result = await db.execute(
            text("""
            SELECT s.relname AS table_name,
                   pg_size_pretty(pg_total_relation_size(c.oid)) AS total_size,
                   s.n_live_tup AS row_count
            FROM pg_class c
            JOIN pg_stat_user_tables s ON c.relname = s.relname
            WHERE c.relkind = 'r'
            ORDER BY pg_total_relation_size(c.oid) DESC
            LIMIT 20
        """)
        )
        diagnostics["tables"] = [
            {"table": r.table_name, "size": r.total_size, "rows": r.row_count} for r in table_result
        ]
    except Exception as e:
        diagnostics["tables_error"] = str(e)

    try:
        slow_result = await db.execute(
            text("""
            SELECT query, calls, mean_exec_time, total_exec_time
            FROM pg_stat_statements
            ORDER BY mean_exec_time DESC
            LIMIT 10
        """)
        )
        diagnostics["slow_queries"] = [
            {
                "query": r.query[:200],
                "calls": r.calls,
                "avg_ms": round(r.mean_exec_time, 2),
                "total_ms": round(r.total_exec_time, 2),
            }
            for r in slow_result
        ]
    except Exception:
        diagnostics["slow_queries"] = "pg_stat_statements extension not available"

    return diagnostics


# --- Redis diagnostics ---


@router.get("/system/redis")
async def get_redis_diagnostics(
    _admin: AdminUserId,
) -> dict[str, Any]:
    """Redis diagnostics: memory, keys, clients, key patterns."""
    from mcpworks_api.core.redis import get_redis_context

    diagnostics: dict[str, Any] = {}

    async with get_redis_context() as redis:
        try:
            info = await redis.info()
            diagnostics["server"] = {
                "version": info.get("redis_version"),
                "uptime_seconds": info.get("uptime_in_seconds"),
                "uptime_human": info.get("uptime_in_days", 0),
                "connected_clients": info.get("connected_clients"),
            }
            diagnostics["memory"] = {
                "used_human": info.get("used_memory_human"),
                "used_bytes": info.get("used_memory"),
                "peak_human": info.get("used_memory_peak_human"),
                "fragmentation_ratio": info.get("mem_fragmentation_ratio"),
            }
            diagnostics["stats"] = {
                "total_commands_processed": info.get("total_commands_processed"),
                "keyspace_hits": info.get("keyspace_hits"),
                "keyspace_misses": info.get("keyspace_misses"),
                "evicted_keys": info.get("evicted_keys"),
            }
        except Exception as e:
            diagnostics["error"] = str(e)

        try:
            db_size = await redis.dbsize()
            diagnostics["total_keys"] = db_size
        except Exception:
            pass

        try:
            usage_keys = []
            async for key in redis.scan_iter("usage:*", count=100):
                val = await redis.get(key)
                ttl = await redis.ttl(key)
                usage_keys.append({"key": key, "value": int(val) if val else 0, "ttl_seconds": ttl})
            diagnostics["usage_keys"] = sorted(usage_keys, key=lambda x: x["value"], reverse=True)
        except Exception:
            pass

        try:
            rl_keys = []
            async for key in redis.scan_iter("ratelimit:*", count=100):
                val = await redis.get(key)
                ttl = await redis.ttl(key)
                rl_keys.append({"key": key, "value": int(val) if val else 0, "ttl_seconds": ttl})
            diagnostics["rate_limit_keys"] = rl_keys
        except Exception:
            pass

    return diagnostics


# --- Rate limit inspection ---


@router.get("/rate-limits")
async def get_rate_limit_state(
    _admin: AdminUserId,
) -> dict[str, Any]:
    """Current rate limit state: who's being throttled and approaching limits."""
    from mcpworks_api.core.redis import get_redis_context
    from mcpworks_api.middleware.rate_limit import RateLimitMiddleware

    limits_config = RateLimitMiddleware.LIMITS
    result: dict[str, Any] = {"config": limits_config, "active": []}

    async with get_redis_context() as redis:
        async for key in redis.scan_iter("ratelimit:*", count=200):
            val = await redis.get(key)
            ttl = await redis.ttl(key)
            count = int(val) if val else 0

            parts = key.split(":") if isinstance(key, str) else key.decode().split(":")
            key_type = parts[1] if len(parts) > 1 else "unknown"
            identifier = ":".join(parts[2:]) if len(parts) > 2 else "unknown"

            config = limits_config.get(
                {
                    "auth": "auth_attempt",
                    "auth_fail": "auth_failure",
                    "register": "registration",
                }.get(key_type, "ip_request"),
                {"limit": 0, "window": 0},
            )

            result["active"].append(
                {
                    "key": key if isinstance(key, str) else key.decode(),
                    "type": key_type,
                    "identifier": identifier,
                    "count": count,
                    "limit": config["limit"],
                    "is_limited": count >= config["limit"],
                    "ttl_seconds": ttl,
                }
            )

    result["active"].sort(key=lambda x: x["count"], reverse=True)
    result["currently_limited"] = [x for x in result["active"] if x["is_limited"]]

    return result


# --- Usage reset (admin action) ---


@router.post("/users/{user_id}/reset-usage")
async def reset_user_usage(
    user_id: str,
    admin_id: AdminUserId,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Reset a user's monthly usage counter."""
    from mcpworks_api.middleware.billing import reset_account_usage

    result = await db.execute(
        select(User).where(User.id == uuid_module.UUID(user_id)).options(selectinload(User.account))
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not user.account:
        raise HTTPException(status_code=404, detail="User has no account")

    success = await reset_account_usage(user.account.id)

    audit_log = AuditLog(
        user_id=uuid_module.UUID(admin_id),
        action="usage_reset",
        resource_type="user",
        resource_id=user.id,
        event_data={"target_email": user.email},
    )
    db.add(audit_log)

    return {
        "user_id": str(user.id),
        "email": user.email,
        "usage_reset": success,
    }


# --- Execution status timeline ---


@router.get("/system/execution-timeline")
async def get_execution_timeline(
    _admin: AdminUserId,
    db: AsyncSession = Depends(get_db),
    hours: int = Query(default=24, le=168),
) -> dict[str, Any]:
    """Execution counts grouped by hour for the past N hours."""
    since = datetime.now(UTC) - timedelta(hours=hours)

    result = await db.execute(
        text("""
        SELECT
            date_trunc('hour', created_at) AS hour,
            status,
            count(*) AS count
        FROM executions
        WHERE created_at >= :since
        GROUP BY hour, status
        ORDER BY hour DESC
    """).bindparams(since=since)
    )

    timeline: dict[str, dict[str, int]] = {}
    for row in result:
        hour_str = row.hour.isoformat() if row.hour else "unknown"
        if hour_str not in timeline:
            timeline[hour_str] = {}
        timeline[hour_str][row.status] = row.count

    return {
        "hours": hours,
        "since": since.isoformat(),
        "timeline": timeline,
    }


# --- Helpers ---


def _parse_relative_time(value: str) -> datetime:
    """Parse relative time string like '1h', '24h', '7d' or ISO datetime."""
    value = value.strip()
    try:
        if value.endswith("m"):
            return datetime.now(UTC) - timedelta(minutes=int(value[:-1]))
        if value.endswith("h"):
            return datetime.now(UTC) - timedelta(hours=int(value[:-1]))
        if value.endswith("d"):
            return datetime.now(UTC) - timedelta(days=int(value[:-1]))
        return datetime.fromisoformat(value)
    except (ValueError, OverflowError):
        return datetime.now(UTC) - timedelta(hours=24)


@router.delete("/namespaces/{ns_name}")
async def admin_delete_namespace(
    ns_name: str,
    admin_id: AdminUserId,
    hard: bool = Query(
        False, description="Hard delete (permanent) vs soft delete (30-day recovery)"
    ),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    result = await db.execute(select(Namespace).where(Namespace.name == ns_name.lower()))
    namespace = result.scalar_one_or_none()
    if not namespace:
        raise HTTPException(status_code=404, detail=f"Namespace '{ns_name}' not found")

    fn_count = (
        await db.execute(
            select(func.count())
            .select_from(Function)
            .join(NamespaceService, Function.service_id == NamespaceService.id)
            .where(NamespaceService.namespace_id == namespace.id)
        )
    ).scalar() or 0

    svc_count = (
        await db.execute(
            select(func.count())
            .select_from(NamespaceService)
            .where(NamespaceService.namespace_id == namespace.id)
        )
    ).scalar() or 0

    if hard:
        shares = (
            (
                await db.execute(
                    select(NamespaceShare).where(NamespaceShare.namespace_id == namespace.id)
                )
            )
            .scalars()
            .all()
        )
        for share in shares:
            await db.delete(share)

        services = (
            (
                await db.execute(
                    select(NamespaceService).where(NamespaceService.namespace_id == namespace.id)
                )
            )
            .scalars()
            .all()
        )
        for svc in services:
            fns = (
                (await db.execute(select(Function).where(Function.service_id == svc.id)))
                .scalars()
                .all()
            )
            for fn in fns:
                versions = (
                    (
                        await db.execute(
                            select(FunctionVersion).where(FunctionVersion.function_id == fn.id)
                        )
                    )
                    .scalars()
                    .all()
                )
                for v in versions:
                    await db.delete(v)
                await db.delete(fn)
            await db.delete(svc)

        await db.delete(namespace)
    else:
        namespace.deleted_at = datetime.now(UTC)

    audit_log = AuditLog(
        user_id=uuid_module.UUID(admin_id),
        action="admin.namespace_deleted",
        resource_type="namespace",
        resource_id=namespace.id,
        event_data={
            "namespace": ns_name,
            "hard_delete": hard,
            "services_deleted": svc_count,
            "functions_deleted": fn_count,
        },
    )
    db.add(audit_log)

    await db.commit()

    return {
        "namespace": ns_name,
        "deleted": True,
        "hard_delete": hard,
        "services_deleted": svc_count,
        "functions_deleted": fn_count,
    }


class AgentTierUpgradeRequest(BaseModel):
    tier: str = Field(
        ...,
        description="Target agent tier (trial-agent, pro-agent, enterprise-agent, dedicated-agent)",
    )


@router.post("/accounts/{account_id}/agent-tier")
async def upgrade_agent_tier(
    account_id: uuid_module.UUID,
    body: AgentTierUpgradeRequest,
    admin_id: AdminUserId,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Upgrade (or set) an account's agent tier. Admin only.

    Blocks downgrade if the account has existing agents that would exceed
    the new tier's slot limit (FR-021).
    """
    from mcpworks_api.models.agent import Agent
    from mcpworks_api.models.subscription import AGENT_TIER_CONFIG

    valid_agent_tiers = {"trial-agent", "pro-agent", "enterprise-agent", "dedicated-agent"}
    if body.tier not in valid_agent_tiers:
        raise HTTPException(status_code=422, detail=f"Invalid agent tier: {body.tier}")

    account_q = await db.execute(
        select(Account).options(selectinload(Account.user)).where(Account.id == account_id)
    )
    account = account_q.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    user = account.user
    new_config = AGENT_TIER_CONFIG[body.tier]

    agent_count_q = await db.execute(
        select(func.count(Agent.id)).where(Agent.account_id == account_id)
    )
    agent_count = agent_count_q.scalar_one()

    if agent_count > new_config["max_agents"]:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot set tier to {body.tier}: account has {agent_count} agents "
            f"but tier allows {new_config['max_agents']}. "
            f"Destroy excess agents before downgrading.",
        )

    old_tier = user.tier
    user.tier = body.tier
    await db.flush()

    audit_log = AuditLog(
        user_id=uuid_module.UUID(admin_id),
        action="admin.agent_tier_upgrade",
        resource_type="user",
        resource_id=user.id,
        event_data={
            "old_tier": old_tier,
            "new_tier": body.tier,
            "account_id": str(account_id),
        },
    )
    db.add(audit_log)
    await db.commit()

    logger.info(
        "agent_tier_upgraded",
        account_id=str(account_id),
        old_tier=old_tier,
        new_tier=body.tier,
        admin_id=admin_id,
    )

    return {
        "account_id": str(account_id),
        "old_tier": old_tier,
        "new_tier": body.tier,
        "max_agents": new_config["max_agents"],
        "current_agents": agent_count,
    }


@router.get("/agent-runs")
async def list_agent_runs(
    _admin: AdminUserId,
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    status_filter: str | None = Query(None, alias="status"),
    agent_id: uuid_module.UUID | None = Query(None),
) -> dict[str, Any]:
    """Unified run history across all agents."""
    from mcpworks_api.models.agent import Agent, AgentRun

    offset = (page - 1) * page_size

    query = select(AgentRun, Agent.name).join(Agent, AgentRun.agent_id == Agent.id)
    count_query = select(func.count(AgentRun.id))

    if status_filter:
        query = query.where(AgentRun.status == status_filter)
        count_query = count_query.where(AgentRun.status == status_filter)
    if agent_id:
        query = query.where(AgentRun.agent_id == agent_id)
        count_query = count_query.where(AgentRun.agent_id == agent_id)

    total = (await db.execute(count_query)).scalar_one()
    rows = (
        await db.execute(query.order_by(AgentRun.created_at.desc()).offset(offset).limit(page_size))
    ).all()

    return {
        "runs": [
            {
                "id": str(r.id),
                "agent_id": str(r.agent_id),
                "agent_name": agent_name,
                "trigger_type": r.trigger_type,
                "trigger_detail": r.trigger_detail,
                "function_name": r.function_name,
                "status": r.status,
                "duration_ms": r.duration_ms,
                "result_summary": (r.result_summary or "")[:200],
                "error": (r.error or "")[:200] if r.error else None,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "completed_at": r.completed_at.isoformat() if r.completed_at else None,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r, agent_name in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/agents/schedule-health")
async def agents_schedule_health(
    _admin: AdminUserId,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Schedule health overview — find troubled schedules."""
    from datetime import UTC, datetime

    from mcpworks_api.models.agent import Agent, AgentSchedule

    result = await db.execute(
        select(AgentSchedule, Agent.name)
        .join(Agent, AgentSchedule.agent_id == Agent.id)
        .order_by(AgentSchedule.consecutive_failures.desc())
    )
    rows = result.all()

    now = datetime.now(UTC)
    total = len(rows)
    enabled = sum(1 for s, _ in rows if s.enabled)
    healthy = sum(1 for s, _ in rows if s.enabled and s.consecutive_failures == 0)
    warning = sum(1 for s, _ in rows if s.enabled and 0 < s.consecutive_failures < 3)
    critical = sum(
        1
        for s, _ in rows
        if s.consecutive_failures >= 3 or (not s.enabled and s.consecutive_failures > 0)
    )
    overdue = sum(1 for s, _ in rows if s.enabled and s.next_run_at and s.next_run_at < now)

    return {
        "summary": {
            "total": total,
            "enabled": enabled,
            "healthy": healthy,
            "warning": warning,
            "critical": critical,
            "overdue": overdue,
        },
        "schedules": [
            {
                "id": str(s.id),
                "agent_name": agent_name,
                "function_name": s.function_name,
                "cron": s.cron_expression,
                "timezone": s.timezone,
                "mode": s.orchestration_mode,
                "enabled": s.enabled,
                "consecutive_failures": s.consecutive_failures,
                "next_run_at": s.next_run_at.isoformat() if s.next_run_at else None,
                "last_run_at": s.last_run_at.isoformat() if s.last_run_at else None,
            }
            for s, agent_name in rows
        ],
    }


@router.get("/agents")
async def list_all_agents(
    _admin: AdminUserId,
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
) -> dict[str, Any]:
    """List all agents with schedule counts, last run, and error rates."""
    from datetime import timedelta

    from mcpworks_api.models.agent import Agent, AgentRun, AgentSchedule

    offset = (page - 1) * page_size
    total_q = await db.execute(select(func.count(Agent.id)))
    total = total_q.scalar_one()

    agents_q = await db.execute(
        select(Agent, User.email)
        .join(Account, Agent.account_id == Account.id)
        .join(User, Account.user_id == User.id)
        .order_by(Agent.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    rows = agents_q.all()

    agent_ids = [a.id for a, _ in rows]

    schedule_counts = {}
    if agent_ids:
        sc_q = await db.execute(
            select(AgentSchedule.agent_id, func.count(AgentSchedule.id))
            .where(AgentSchedule.agent_id.in_(agent_ids))
            .group_by(AgentSchedule.agent_id)
        )
        schedule_counts = dict(sc_q.all())

    last_runs = {}
    if agent_ids:
        lr_q = await db.execute(
            select(AgentRun.agent_id, func.max(AgentRun.created_at))
            .where(AgentRun.agent_id.in_(agent_ids))
            .group_by(AgentRun.agent_id)
        )
        last_runs = dict(lr_q.all())

    error_rates = {}
    if agent_ids:
        from datetime import UTC, datetime

        cutoff = datetime.now(UTC) - timedelta(days=1)
        from sqlalchemy import case

        er_q = await db.execute(
            select(
                AgentRun.agent_id,
                func.count(AgentRun.id).label("total"),
                func.sum(case((AgentRun.status == "failed", 1), else_=0)).label("failed"),
            )
            .where(AgentRun.agent_id.in_(agent_ids), AgentRun.created_at >= cutoff)
            .group_by(AgentRun.agent_id)
        )
        for agent_id, run_total, failed in er_q.all():
            error_rates[agent_id] = (
                round((failed or 0) / run_total * 100, 1) if run_total > 0 else 0
            )

    return {
        "agents": [
            {
                "id": str(a.id),
                "name": a.name,
                "display_name": a.display_name,
                "account_id": str(a.account_id),
                "owner_email": email,
                "status": a.status,
                "ai_engine": a.ai_engine,
                "ai_model": a.ai_model,
                "memory_limit_mb": a.memory_limit_mb,
                "cpu_limit": a.cpu_limit,
                "enabled": a.enabled,
                "schedule_count": schedule_counts.get(a.id, 0),
                "last_run_at": last_runs[a.id].isoformat()
                if a.id in last_runs and last_runs[a.id]
                else None,
                "error_rate_24h": error_rates.get(a.id, 0),
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a, email in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/agents/health")
async def agent_fleet_health(
    _admin: AdminUserId,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Fleet health overview: counts by status, memory/CPU usage, capacity."""
    from mcpworks_api.models.agent import Agent

    agents_q = await db.execute(select(Agent))
    agents = list(agents_q.scalars().all())

    status_counts: dict[str, int] = {}
    total_memory_mb = 0
    total_cpu = 0.0
    for a in agents:
        status_counts[a.status] = status_counts.get(a.status, 0) + 1
        if a.status == "running":
            total_memory_mb += a.memory_limit_mb
            total_cpu += a.cpu_limit

    return {
        "total_agents": len(agents),
        "status_counts": status_counts,
        "running_memory_mb": total_memory_mb,
        "running_cpu_vcpus": round(total_cpu, 2),
        "capacity": {
            "max_memory_mb": 6800,
            "max_cpu_vcpus": 3.2,
            "memory_available_mb": 6800 - total_memory_mb,
            "cpu_available_vcpus": round(3.2 - total_cpu, 2),
        },
    }


@router.get("/agents/{agent_id}")
async def admin_agent_detail(
    agent_id: uuid_module.UUID,
    _admin: AdminUserId,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get detailed agent info including schedules, webhooks, runs, state, and container stats."""
    from sqlalchemy.orm import selectinload

    from mcpworks_api.models.agent import Agent, AgentRun, AgentState
    from mcpworks_api.services.agent_service import AgentService

    result = await db.execute(
        select(Agent)
        .where(Agent.id == agent_id)
        .options(
            selectinload(Agent.schedules),
            selectinload(Agent.webhooks),
            selectinload(Agent.channels),
        )
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    owner_result = await db.execute(
        select(User.email)
        .join(Account, Account.user_id == User.id)
        .where(Account.id == agent.account_id)
    )
    owner_email = owner_result.scalar_one_or_none() or "unknown"

    tier_result = await db.execute(
        select(User.tier, User.tier_override)
        .join(Account, Account.user_id == User.id)
        .where(Account.id == agent.account_id)
    )
    tier_row = tier_result.one_or_none()
    tier = (tier_row[1] or tier_row[0]) if tier_row else "unknown"

    runs_result = await db.execute(
        select(AgentRun)
        .where(AgentRun.agent_id == agent_id)
        .order_by(AgentRun.created_at.desc())
        .limit(15)
    )
    recent_runs = runs_result.scalars().all()

    state_result = await db.execute(select(AgentState).where(AgentState.agent_id == agent_id))
    state_entries = state_result.scalars().all()

    svc = AgentService(db)
    stats = await svc.get_container_stats(agent)

    return {
        "id": str(agent.id),
        "name": agent.name,
        "display_name": agent.display_name,
        "account_id": str(agent.account_id),
        "owner_email": owner_email,
        "tier": tier,
        "status": agent.status,
        "container_id": agent.container_id,
        "memory_limit_mb": agent.memory_limit_mb,
        "cpu_limit": agent.cpu_limit,
        "ai_engine": agent.ai_engine,
        "ai_model": agent.ai_model,
        "system_prompt": (agent.system_prompt or "")[:500],
        "enabled": agent.enabled,
        "created_at": agent.created_at.isoformat() if agent.created_at else None,
        "container_stats": stats,
        "schedules": [
            {
                "id": str(s.id),
                "function_name": s.function_name,
                "cron": s.cron_expression,
                "timezone": s.timezone,
                "mode": s.orchestration_mode,
                "enabled": s.enabled,
                "consecutive_failures": s.consecutive_failures,
                "next_run_at": s.next_run_at.isoformat() if s.next_run_at else None,
                "last_run_at": s.last_run_at.isoformat() if s.last_run_at else None,
            }
            for s in agent.schedules
        ],
        "webhooks": [
            {
                "id": str(w.id),
                "path": w.path,
                "handler": w.handler_function_name,
                "enabled": w.enabled,
            }
            for w in agent.webhooks
        ],
        "channels": [
            {"id": str(c.id), "type": c.channel_type, "enabled": c.enabled} for c in agent.channels
        ],
        "recent_runs": [
            {
                "id": str(r.id),
                "trigger_type": r.trigger_type,
                "function_name": r.function_name,
                "status": r.status,
                "duration_ms": r.duration_ms,
                "error": (r.error or "")[:200] if r.error else None,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in recent_runs
        ],
        "state_key_count": len(state_entries),
        "state_total_bytes": sum(len(s.value_encrypted or b"") for s in state_entries),
    }


@router.post("/agents/{agent_id}/restart")
async def admin_force_restart(
    agent_id: uuid_module.UUID,
    admin_id: AdminUserId,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Force restart an agent container."""
    from mcpworks_api.models.agent import Agent
    from mcpworks_api.services.agent_service import AgentService

    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    svc = AgentService(db)
    agent = await svc.force_restart_agent(agent)

    audit_log = AuditLog(
        user_id=uuid_module.UUID(admin_id),
        action="admin.agent_force_restart",
        resource_type="agent",
        resource_id=agent.id,
        event_data={"agent_name": agent.name, "status": agent.status},
    )
    db.add(audit_log)
    await db.commit()

    return {"id": str(agent.id), "name": agent.name, "status": agent.status}


@router.delete("/agents/{agent_id}")
async def admin_force_destroy(
    agent_id: uuid_module.UUID,
    admin_id: AdminUserId,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Force destroy an agent (admin override)."""
    from mcpworks_api.models.agent import Agent
    from mcpworks_api.services.agent_service import AgentService

    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    svc = AgentService(db)
    destroyed = await svc.destroy_agent(agent.account_id, agent.name)

    audit_log = AuditLog(
        user_id=uuid_module.UUID(admin_id),
        action="admin.agent_force_destroy",
        resource_type="agent",
        resource_id=destroyed.id,
        event_data={"agent_name": destroyed.name},
    )
    db.add(audit_log)
    await db.commit()

    return {"id": str(destroyed.id), "name": destroyed.name, "destroyed": True}


@router.get("/analytics/token-savings")
async def admin_token_savings(
    period: str = Query("30d", description="Time period", enum=["1h", "24h", "7d", "30d"]),
    _admin: AdminUserId = None,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    from mcpworks_api.services.analytics import get_platform_token_savings

    return await get_platform_token_savings(db, period)
