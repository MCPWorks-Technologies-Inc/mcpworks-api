"""API v1 package - Version 1 endpoints."""

from fastapi import APIRouter

from mcpworks_api.api.v1.auth import router as auth_router
from mcpworks_api.api.v1.credits import router as credits_router
from mcpworks_api.api.v1.health import router as health_router
from mcpworks_api.api.v1.services import router as services_router
from mcpworks_api.api.v1.subscriptions import router as subscriptions_router
from mcpworks_api.api.v1.subscriptions import webhook_router
from mcpworks_api.api.v1.users import router as users_router

# Main v1 router
router = APIRouter(prefix="/v1")

# Include all v1 routers
router.include_router(health_router)
router.include_router(auth_router)
router.include_router(users_router)
router.include_router(credits_router)
router.include_router(services_router)
router.include_router(subscriptions_router)
router.include_router(webhook_router)

__all__ = ["router"]
