"""API v1 package - Version 1 endpoints."""

from fastapi import APIRouter

from mcpworks_api.api.v1.account import router as account_router
from mcpworks_api.api.v1.admin import router as admin_router
from mcpworks_api.api.v1.agents import lock_router as agent_lock_router
from mcpworks_api.api.v1.agents import router as agents_router
from mcpworks_api.api.v1.analytics import router as analytics_router
from mcpworks_api.api.v1.audit import router as audit_router
from mcpworks_api.api.v1.auth import router as auth_router
from mcpworks_api.api.v1.compliance import router as compliance_router
from mcpworks_api.api.v1.demo import router as demo_router
from mcpworks_api.api.v1.executions import router as executions_router
from mcpworks_api.api.v1.health import router as health_router
from mcpworks_api.api.v1.legal import router as legal_router
from mcpworks_api.api.v1.llm import router as llm_router
from mcpworks_api.api.v1.namespaces import router as namespaces_router
from mcpworks_api.api.v1.oauth import router as oauth_router
from mcpworks_api.api.v1.observability import router as observability_router
from mcpworks_api.api.v1.procedures import router as procedures_router
from mcpworks_api.api.v1.quickstart import router as quickstart_router
from mcpworks_api.api.v1.shares import router as shares_router
from mcpworks_api.api.v1.subscriptions import router as subscriptions_router
from mcpworks_api.api.v1.subscriptions import webhook_router
from mcpworks_api.api.v1.users import router as users_router
from mcpworks_api.mcp.router import router as mcp_router

# Main v1 router
router = APIRouter(prefix="/v1")

# Include all v1 routers
router.include_router(health_router)
router.include_router(legal_router)  # ORDER-007: Legal documents
router.include_router(quickstart_router)  # ORDER-012: Getting-started docs
router.include_router(llm_router)  # LLM-oriented instructions
router.include_router(auth_router)
router.include_router(oauth_router)  # OAuth social login
router.include_router(account_router)  # Usage tracking
router.include_router(users_router)
router.include_router(subscriptions_router)
router.include_router(webhook_router)
router.include_router(namespaces_router)  # A0: Namespace management
router.include_router(agents_router)  # A0: Containerized agents
router.include_router(procedures_router)  # A0: Procedures framework
router.include_router(agent_lock_router)  # A0: Function locking (admin)
router.include_router(shares_router)  # Namespace sharing
router.include_router(audit_router)  # ORDER-022: Security audit logs
router.include_router(admin_router)  # Admin dashboard
router.include_router(demo_router)  # Demo booking form
router.include_router(analytics_router)  # Token savings & MCP analytics
router.include_router(executions_router)  # Execution debugging
router.include_router(observability_router)  # Orchestration observability
router.include_router(compliance_router)  # OWASP compliance reporting
router.include_router(mcp_router)  # A0: MCP JSON-RPC endpoints

__all__ = ["router"]
