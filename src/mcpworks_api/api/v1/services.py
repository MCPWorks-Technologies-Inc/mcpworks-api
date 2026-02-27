"""Service endpoints - service catalog and routing to backend services.

Usage tracking is handled by BillingMiddleware via Redis.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mcpworks_api.core.database import get_db
from mcpworks_api.core.exceptions import (
    InsufficientTierError,
    ServiceTimeoutError,
    ServiceUnavailableError,
)
from mcpworks_api.dependencies import ActiveUserId as CurrentUserId
from mcpworks_api.dependencies import verify_agent_callback_secret
from mcpworks_api.models import User
from mcpworks_api.schemas.service import (
    AgentCallbackRequest,
    AgentCallbackResponse,
    AgentExecuteRequest,
    AgentExecuteResponse,
    ExecutionInfo,
    ExecutionList,
    MathHelpRequest,
    MathHelpResponse,
    MathVerifyRequest,
    MathVerifyResponse,
    ServiceCatalog,
    ServiceInfo,
)
from mcpworks_api.services.execution import ExecutionService
from mcpworks_api.services.router import ServiceRouter

router = APIRouter(prefix="/services", tags=["services"])


async def get_user_tier(user_id: str, db: AsyncSession) -> str:
    """Get user's subscription tier."""
    result = await db.execute(select(User.tier).where(User.id == uuid.UUID(user_id)))
    tier = result.scalar_one_or_none()
    return tier or "free"


@router.get(
    "",
    response_model=ServiceCatalog,
    responses={
        200: {"description": "List of available services"},
        401: {"description": "Not authenticated"},
    },
)
async def list_services(
    user_id: CurrentUserId,
    db: AsyncSession = Depends(get_db),
) -> ServiceCatalog:
    """Get catalog of available services.

    FR-ROUTE-004: Return service catalog with costs and tier requirements.
    """
    user_tier = await get_user_tier(user_id, db)
    router_service = ServiceRouter(db)
    services = await router_service.list_services(user_tier)

    return ServiceCatalog(
        services=[
            ServiceInfo(
                name=svc.name,
                display_name=svc.display_name,
                description=svc.description,
                credit_cost=svc.credit_cost,
                tier_required=svc.tier_required,
                status=svc.status,
                is_available=svc.is_available,
            )
            for svc in services
        ]
    )


@router.post(
    "/math/verify",
    response_model=MathVerifyResponse,
    responses={
        200: {"description": "Math verification result"},
        400: {"description": "Invalid request"},
        401: {"description": "Not authenticated"},
        402: {"description": "Execution limit exceeded"},
        403: {"description": "Tier not permitted"},
        503: {"description": "Math service unavailable"},
        504: {"description": "Request timed out"},
    },
)
async def verify_math(
    body: MathVerifyRequest,
    user_id: CurrentUserId,
    db: AsyncSession = Depends(get_db),
) -> MathVerifyResponse:
    """Verify a mathematical statement or calculation.

    FR-ROUTE-001: Route request to mcpworks-math service.
    """
    user_tier = await get_user_tier(user_id, db)
    router_service = ServiceRouter(db)

    try:
        status_code, headers, response_data = await router_service.route_request(
            service_name="math",
            method="POST",
            path="/verify",
            user_id=uuid.UUID(user_id),
            user_tier=user_tier,
            body={
                "problem": body.problem,
                "expected_answer": body.expected_answer,
                "show_work": body.show_work,
                "verification_mode": body.verification_mode,
                "context": body.context,
            },
        )

        # Handle non-200 responses from backend
        if status_code != 200:
            raise HTTPException(
                status_code=status_code,
                detail=(
                    response_data if isinstance(response_data, dict) else {"error": response_data}
                ),
            )

        # Map response to our schema
        return MathVerifyResponse(
            is_correct=response_data.get("is_correct", False),
            confidence=response_data.get("confidence", 0.0),
            solution=response_data.get("solution"),
            correct_answer=response_data.get("correct_answer"),
            model_used=response_data.get("model_used", "unknown"),
        )

    except InsufficientTierError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=e.to_dict(),
        )
    except ServiceUnavailableError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=e.to_dict(),
            headers={"Retry-After": str(e.retry_after)},
        )
    except ServiceTimeoutError as e:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=e.to_dict(),
        )


@router.post(
    "/math/help",
    response_model=MathHelpResponse,
    responses={
        200: {"description": "Math tutoring response"},
        400: {"description": "Invalid request"},
        401: {"description": "Not authenticated"},
        402: {"description": "Execution limit exceeded"},
        403: {"description": "Tier not permitted"},
        503: {"description": "Math service unavailable"},
        504: {"description": "Request timed out"},
    },
)
async def get_math_help(
    body: MathHelpRequest,
    user_id: CurrentUserId,
    db: AsyncSession = Depends(get_db),
) -> MathHelpResponse:
    """Get math tutoring and guidance.

    FR-ROUTE-001: Route request to mcpworks-math service.
    """
    user_tier = await get_user_tier(user_id, db)
    router_service = ServiceRouter(db)

    try:
        status_code, headers, response_data = await router_service.route_request(
            service_name="math",
            method="POST",
            path="/help",
            user_id=uuid.UUID(user_id),
            user_tier=user_tier,
            body={
                "question": body.question,
                "guidance_type": body.guidance_type,
                "detail_level": body.detail_level,
                "context": body.context,
            },
        )

        # Handle non-200 responses from backend
        if status_code != 200:
            raise HTTPException(
                status_code=status_code,
                detail=(
                    response_data if isinstance(response_data, dict) else {"error": response_data}
                ),
            )

        # Map response to our schema
        return MathHelpResponse(
            answer=response_data.get("answer", ""),
            guidance_type=response_data.get("guidance_type", body.guidance_type),
            related_topics=response_data.get("related_topics", []),
        )

    except InsufficientTierError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=e.to_dict(),
        )
    except ServiceUnavailableError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=e.to_dict(),
            headers={"Retry-After": str(e.retry_after)},
        )
    except ServiceTimeoutError as e:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=e.to_dict(),
        )


@router.get(
    "/{service_name}/health",
    responses={
        200: {"description": "Service is healthy"},
        503: {"description": "Service is unhealthy"},
    },
)
async def check_service_health(
    service_name: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Check health of a specific service.

    FR-ROUTE-003: Health check endpoint for services.
    """
    router_service = ServiceRouter(db)
    service = await router_service.get_service(service_name)

    if service is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "SERVICE_NOT_FOUND",
                "message": f"Service '{service_name}' not found",
            },
        )

    is_healthy = await router_service.check_service_health(service)

    if not is_healthy:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": "SERVICE_UNAVAILABLE",
                "message": f"Service '{service_name}' is not healthy",
                "status": service.status,
            },
            headers={"Retry-After": "30"},
        )

    return {
        "service": service_name,
        "status": "healthy",
        "last_check": service.last_health_check.isoformat() if service.last_health_check else None,
    }


# Agent execution endpoints


@router.post(
    "/agent/execute/{workflow_id}",
    response_model=AgentExecuteResponse,
    responses={
        200: {"description": "Execution started"},
        400: {"description": "Invalid request"},
        401: {"description": "Not authenticated"},
        402: {"description": "Execution limit exceeded"},
        403: {"description": "Tier not permitted"},
        503: {"description": "Agent service unavailable"},
    },
)
async def execute_workflow(
    workflow_id: str,
    body: AgentExecuteRequest,
    user_id: CurrentUserId,
    db: AsyncSession = Depends(get_db),
) -> AgentExecuteResponse:
    """Execute a workflow via mcpworks-agent.

    FR-ROUTE-002: Route requests to mcpworks-agent.
    Usage tracking is handled by BillingMiddleware via Redis.
    """
    user_tier = await get_user_tier(user_id, db)
    execution_service = ExecutionService(db)

    try:
        execution = await execution_service.start_execution(
            workflow_id=workflow_id,
            user_id=uuid.UUID(user_id),
            user_tier=user_tier,
            input_data=body.input_data,
        )

        return AgentExecuteResponse(
            execution_id=str(execution.id),
            workflow_id=workflow_id,
            status=execution.status,
            message="Execution started",
        )

    except InsufficientTierError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=e.to_dict(),
        )
    except ServiceUnavailableError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=e.to_dict(),
            headers={"Retry-After": str(e.retry_after)},
        )


@router.get(
    "/agent/executions/{execution_id}",
    response_model=ExecutionInfo,
    responses={
        200: {"description": "Execution details"},
        401: {"description": "Not authenticated"},
        404: {"description": "Execution not found"},
    },
)
async def get_execution(
    execution_id: str,
    user_id: CurrentUserId,
    db: AsyncSession = Depends(get_db),
) -> ExecutionInfo:
    """Get execution details by ID."""
    execution_service = ExecutionService(db)

    try:
        execution_uuid = uuid.UUID(execution_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "INVALID_ID", "message": "Invalid execution ID format"},
        )

    execution = await execution_service.get_execution(execution_uuid)

    if execution is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "NOT_FOUND", "message": f"Execution {execution_id} not found"},
        )

    # Check ownership
    if str(execution.user_id) != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "NOT_FOUND", "message": f"Execution {execution_id} not found"},
        )

    return ExecutionInfo(
        execution_id=str(execution.id),
        workflow_id=execution.workflow_id,
        status=execution.status,
        started_at=execution.started_at,
        completed_at=execution.completed_at,
        duration_seconds=execution.duration_seconds,
        result_data=execution.result_data,
        error_message=execution.error_message,
        error_code=execution.error_code,
    )


@router.get(
    "/agent/executions",
    response_model=ExecutionList,
    responses={
        200: {"description": "List of executions"},
        401: {"description": "Not authenticated"},
    },
)
async def list_executions(
    user_id: CurrentUserId,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
) -> ExecutionList:
    """List user's workflow executions."""
    execution_service = ExecutionService(db)

    executions, total = await execution_service.get_user_executions(
        user_id=uuid.UUID(user_id),
        limit=min(limit, 100),
        offset=offset,
    )

    return ExecutionList(
        executions=[
            ExecutionInfo(
                execution_id=str(e.id),
                workflow_id=e.workflow_id,
                status=e.status,
                started_at=e.started_at,
                completed_at=e.completed_at,
                duration_seconds=e.duration_seconds,
                result_data=e.result_data,
                error_message=e.error_message,
                error_code=e.error_code,
            )
            for e in executions
        ],
        total=total,
    )


@router.post(
    "/agent/executions/{execution_id}/callback",
    response_model=AgentCallbackResponse,
    responses={
        200: {"description": "Callback processed"},
        400: {"description": "Invalid request or execution state"},
        401: {"description": "Missing X-Agent-Secret header"},
        403: {"description": "Invalid agent secret"},
        404: {"description": "Execution not found"},
    },
)
async def execution_callback(
    execution_id: str,
    body: AgentCallbackRequest,
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(verify_agent_callback_secret),
) -> AgentCallbackResponse:
    """Handle callback from mcpworks-agent.

    This endpoint is called by mcpworks-agent when workflow execution
    completes (success or failure).

    Requires X-Agent-Secret header with valid shared secret.
    """
    execution_service = ExecutionService(db)

    try:
        execution_uuid = uuid.UUID(execution_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "INVALID_ID", "message": "Invalid execution ID format"},
        )

    try:
        execution = await execution_service.handle_callback(
            execution_id=execution_uuid,
            status=body.status,
            result_data=body.result_data,
            error_message=body.error_message,
            error_code=body.error_code,
        )

        return AgentCallbackResponse(
            execution_id=str(execution.id),
            status=execution.status,
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "INVALID_STATE", "message": str(e)},
        )


@router.post(
    "/agent/executions/{execution_id}/cancel",
    response_model=ExecutionInfo,
    responses={
        200: {"description": "Execution cancelled"},
        400: {"description": "Cannot cancel execution"},
        401: {"description": "Not authenticated"},
        404: {"description": "Execution not found"},
    },
)
async def cancel_execution(
    execution_id: str,
    user_id: CurrentUserId,
    db: AsyncSession = Depends(get_db),
) -> ExecutionInfo:
    """Cancel a pending or running execution."""
    execution_service = ExecutionService(db)

    try:
        execution_uuid = uuid.UUID(execution_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "INVALID_ID", "message": "Invalid execution ID format"},
        )

    # Get execution to check ownership
    execution = await execution_service.get_execution(execution_uuid)

    if execution is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "NOT_FOUND", "message": f"Execution {execution_id} not found"},
        )

    # Check ownership
    if str(execution.user_id) != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "NOT_FOUND", "message": f"Execution {execution_id} not found"},
        )

    try:
        execution = await execution_service.cancel_execution(execution_uuid)

        return ExecutionInfo(
            execution_id=str(execution.id),
            workflow_id=execution.workflow_id,
            status=execution.status,
            started_at=execution.started_at,
            completed_at=execution.completed_at,
            duration_seconds=execution.duration_seconds,
            result_data=execution.result_data,
            error_message=execution.error_message,
            error_code=execution.error_code,
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "CANNOT_CANCEL", "message": str(e)},
        )
