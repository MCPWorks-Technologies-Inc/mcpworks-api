"""OWASP Agentic Top 10 compliance reporting endpoint."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mcpworks_api.core.database import get_db
from mcpworks_api.dependencies import require_active_status
from mcpworks_api.models.agent import Agent
from mcpworks_api.models.user import User
from mcpworks_api.services.compliance import evaluate_compliance
from mcpworks_api.services.namespace import NamespaceServiceManager

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/namespaces", tags=["compliance"])


async def _get_current_user(
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(require_active_status),
) -> User:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


@router.get("/{namespace}/compliance")
async def get_namespace_compliance(
    namespace: str,
    detail: str = Query("summary", enum=["summary", "full"]),
    user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    ns_service = NamespaceServiceManager(db)
    ns = await ns_service.get_by_name(namespace, user.account_id, user_id=user.id)

    access_rules_exist = False
    trust_scoring_enabled = False
    result = await db.execute(
        select(Agent.access_rules, Agent.trust_score).where(Agent.namespace_id == ns.id).limit(1)
    )
    agent_row = result.first()
    if agent_row:
        access_rules_exist = bool(agent_row.access_rules)
        trust_scoring_enabled = agent_row.trust_score != 500

    report = evaluate_compliance(
        namespace=namespace,
        scanner_pipeline=ns.scanner_pipeline,
        access_rules_exist=access_rules_exist,
        sandbox_tier=getattr(ns, "sandbox_tier", "free"),
        auth_enabled=True,
        rate_limit_enabled=True,
        trust_scoring_enabled=trust_scoring_enabled,
        detail=detail,
    )

    logger.info(
        "compliance_evaluated",
        namespace=namespace,
        grade=report["grade"],
        coverage_pct=report["coverage_pct"],
    )

    return report
