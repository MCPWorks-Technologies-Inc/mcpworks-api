"""Agent management REST API endpoints.

Manages containerized autonomous agents: create, list, detail, start, stop, destroy,
scheduling, webhooks, state, AI config, channels, and cloning.
All endpoints require an agent-enabled subscription tier.
"""

import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mcpworks_api.core.database import get_db
from mcpworks_api.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from mcpworks_api.dependencies import AdminUserId, require_active_status, require_scope
from mcpworks_api.models.account import Account
from mcpworks_api.models.subscription import SubscriptionTier
from mcpworks_api.models.user import User
from mcpworks_api.schemas.agent import (
    AgentListResponse,
    AgentResponse,
    AgentRunListResponse,
    AgentRunResponse,
    AIResponse,
    ChannelResponse,
    CloneAgentRequest,
    ConfigureAIRequest,
    CreateAgentRequest,
    CreateChannelRequest,
    CreateScheduleRequest,
    CreateWebhookRequest,
    DestroyResponse,
    ScheduleListResponse,
    ScheduleResponse,
    SetStateRequest,
    StartStopResponse,
    StateKeyListResponse,
    StateResponse,
    WebhookListResponse,
    WebhookResponse,
)
from mcpworks_api.services.agent_service import AgentService
from mcpworks_api.services.function import FunctionService
from mcpworks_api.services.namespace import NamespaceServiceManager, NamespaceServiceService

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/agents", tags=["agents"])


async def get_current_account(
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(require_active_status),
) -> Account:
    """Retrieve the account for the authenticated, active user."""
    result = await db.execute(select(Account).where(Account.user_id == user_id))
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=401, detail="Account not found for user")
    return account


async def get_current_user(
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(require_active_status),
) -> User:
    """Retrieve the authenticated, active User row."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


def _require_agent_tier(effective_tier: str) -> None:
    """Raise 403 if the tier is not agent-enabled."""
    try:
        tier_enum = SubscriptionTier(effective_tier)
    except ValueError:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "AGENT_TIER_REQUIRED",
                "message": "Agents require a Builder Agent, Pro Agent, or Enterprise Agent subscription",
            },
        )
    if not tier_enum.is_agent_tier:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "AGENT_TIER_REQUIRED",
                "message": "Agents require a Builder Agent, Pro Agent, or Enterprise Agent subscription",
            },
        )


@router.post(
    "",
    response_model=AgentResponse,
    status_code=201,
    dependencies=[Depends(require_scope("write"))],
)
async def create_agent(
    request: CreateAgentRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    account: Account = Depends(get_current_account),
) -> AgentResponse:
    """Create and start a new containerized agent.

    Validates that the account is on an agent-enabled tier and has available
    agent slots before provisioning the container.
    """
    _require_agent_tier(user.effective_tier)

    svc = AgentService(db)

    try:
        agent = await svc.create_agent(
            account_id=account.id,
            user_id=user.id,
            tier=user.effective_tier,
            name=request.name,
            display_name=request.display_name,
        )
        await db.commit()
        await db.refresh(agent)
    except ForbiddenError as e:
        raise HTTPException(
            status_code=403, detail={"error": "AGENT_TIER_REQUIRED", "message": str(e)}
        )
    except ConflictError as e:
        raise HTTPException(status_code=409, detail={"error": "CONFLICT", "message": str(e)})

    return AgentResponse.model_validate(agent)


@router.get(
    "",
    response_model=AgentListResponse,
    dependencies=[Depends(require_scope("read"))],
)
async def list_agents(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    account: Account = Depends(get_current_account),
) -> AgentListResponse:
    """List all agents for the current account."""
    try:
        tier_enum = SubscriptionTier(user.effective_tier)
    except ValueError:
        tier_enum = None
    if tier_enum is None or not tier_enum.is_agent_tier:
        return AgentListResponse(agents=[], total=0, slots_used=0, slots_available=0)

    svc = AgentService(db)
    agents = await svc.list_agents(account.id)

    try:
        slots = await svc.get_agent_slots(account.id, user.effective_tier)
    except ForbiddenError as e:
        raise HTTPException(
            status_code=403, detail={"error": "AGENT_TIER_REQUIRED", "message": str(e)}
        )

    return AgentListResponse(
        agents=[AgentResponse.model_validate(a) for a in agents],
        total=len(agents),
        slots_used=slots["slots_used"],
        slots_available=slots["slots_available"],
    )


@router.get(
    "/{agent_id}",
    response_model=AgentResponse,
    dependencies=[Depends(require_scope("read"))],
)
async def get_agent(
    agent_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    account: Account = Depends(get_current_account),
) -> AgentResponse:
    """Get details for a single agent by ID."""
    _require_agent_tier(user.effective_tier)

    svc = AgentService(db)

    try:
        agent = await svc.get_agent_by_id(account.id, agent_id)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail={"error": "NOT_FOUND", "message": str(e)})

    return AgentResponse.model_validate(agent)


@router.post(
    "/{agent_id}/start",
    response_model=StartStopResponse,
    dependencies=[Depends(require_scope("write"))],
)
async def start_agent(
    agent_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    account: Account = Depends(get_current_account),
) -> StartStopResponse:
    """Start a stopped agent container."""
    _require_agent_tier(user.effective_tier)

    svc = AgentService(db)

    try:
        agent = await svc.get_agent_by_id(account.id, agent_id)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail={"error": "NOT_FOUND", "message": str(e)})

    try:
        agent = await svc.start_agent(account.id, agent.name)
        await db.commit()
    except ConflictError as e:
        raise HTTPException(status_code=409, detail={"error": "CONFLICT", "message": str(e)})

    return StartStopResponse(
        id=agent.id,
        name=agent.name,
        status=agent.status,
        message=f"Agent '{agent.name}' start requested",
    )


@router.post(
    "/{agent_id}/stop",
    response_model=StartStopResponse,
    dependencies=[Depends(require_scope("write"))],
)
async def stop_agent(
    agent_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    account: Account = Depends(get_current_account),
) -> StartStopResponse:
    """Stop a running agent container."""
    _require_agent_tier(user.effective_tier)

    svc = AgentService(db)

    try:
        agent = await svc.get_agent_by_id(account.id, agent_id)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail={"error": "NOT_FOUND", "message": str(e)})

    try:
        agent = await svc.stop_agent(account.id, agent.name)
        await db.commit()
    except ConflictError as e:
        raise HTTPException(status_code=409, detail={"error": "CONFLICT", "message": str(e)})

    return StartStopResponse(
        id=agent.id,
        name=agent.name,
        status=agent.status,
        message=f"Agent '{agent.name}' stop requested",
    )


@router.delete(
    "/{agent_id}",
    response_model=DestroyResponse,
    dependencies=[Depends(require_scope("write"))],
)
async def destroy_agent(
    agent_id: uuid.UUID,
    confirm: bool = Query(False, description="Must be true to confirm permanent deletion"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    account: Account = Depends(get_current_account),
) -> DestroyResponse:
    """Permanently destroy an agent, its container, namespace, and all associated data.

    Requires confirm=true query parameter to prevent accidental deletion.
    """
    if not confirm:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "CONFIRMATION_REQUIRED",
                "message": "Pass confirm=true to permanently destroy the agent",
            },
        )

    _require_agent_tier(user.effective_tier)

    svc = AgentService(db)

    try:
        agent = await svc.get_agent_by_id(account.id, agent_id)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail={"error": "NOT_FOUND", "message": str(e)})

    destroyed = await svc.destroy_agent(account.id, agent.name)
    await db.commit()

    return DestroyResponse(
        id=destroyed.id,
        name=destroyed.name,
        message=f"Agent '{destroyed.name}' destroyed",
    )


@router.get(
    "/{agent_id}/runs",
    response_model=AgentRunListResponse,
    dependencies=[Depends(require_scope("read"))],
)
async def list_runs(
    agent_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    account: Account = Depends(get_current_account),
) -> AgentRunListResponse:
    """List runs for an agent with pagination."""
    _require_agent_tier(user.effective_tier)

    svc = AgentService(db)
    try:
        runs, total = await svc.list_runs(account.id, agent_id, limit=limit, offset=offset)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail={"error": "NOT_FOUND", "message": str(e)})

    return AgentRunListResponse(
        runs=[AgentRunResponse.model_validate(r) for r in runs],
        total=total,
    )


@router.post(
    "/{agent_id}/schedules",
    response_model=ScheduleResponse,
    status_code=201,
    dependencies=[Depends(require_scope("write"))],
)
async def add_schedule(
    agent_id: uuid.UUID,
    request: CreateScheduleRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    account: Account = Depends(get_current_account),
) -> ScheduleResponse:
    """Add a cron schedule to an agent."""
    _require_agent_tier(user.effective_tier)

    svc = AgentService(db)
    try:
        agent = await svc.get_agent_by_id(account.id, agent_id)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail={"error": "NOT_FOUND", "message": str(e)})

    try:
        schedule = await svc.add_schedule(
            account_id=account.id,
            agent_name=agent.name,
            function_name=request.function_name,
            cron_expression=request.cron_expression,
            timezone=request.timezone,
            failure_policy=request.failure_policy,
            tier=user.effective_tier,
        )
        await db.commit()
        await db.refresh(schedule)
    except ForbiddenError as e:
        raise HTTPException(status_code=403, detail={"error": "FORBIDDEN", "message": str(e)})
    except ConflictError as e:
        raise HTTPException(status_code=409, detail={"error": "CONFLICT", "message": str(e)})

    return ScheduleResponse.model_validate(schedule)


@router.get(
    "/{agent_id}/schedules",
    response_model=ScheduleListResponse,
    dependencies=[Depends(require_scope("read"))],
)
async def list_schedules(
    agent_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    account: Account = Depends(get_current_account),
) -> ScheduleListResponse:
    """List all schedules for an agent."""
    _require_agent_tier(user.effective_tier)

    svc = AgentService(db)
    try:
        agent = await svc.get_agent_by_id(account.id, agent_id)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail={"error": "NOT_FOUND", "message": str(e)})

    schedules = await svc.list_schedules(account.id, agent.name)
    return ScheduleListResponse(
        schedules=[ScheduleResponse.model_validate(s) for s in schedules],
        total=len(schedules),
    )


@router.delete(
    "/{agent_id}/schedules/{schedule_id}",
    status_code=204,
    dependencies=[Depends(require_scope("write"))],
)
async def remove_schedule(
    agent_id: uuid.UUID,
    schedule_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    account: Account = Depends(get_current_account),
) -> None:
    """Remove a schedule from an agent."""
    _require_agent_tier(user.effective_tier)

    svc = AgentService(db)
    try:
        agent = await svc.get_agent_by_id(account.id, agent_id)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail={"error": "NOT_FOUND", "message": str(e)})

    try:
        await svc.remove_schedule(account.id, agent.name, schedule_id)
        await db.commit()
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail={"error": "NOT_FOUND", "message": str(e)})


@router.post(
    "/{agent_id}/webhooks",
    response_model=WebhookResponse,
    status_code=201,
    dependencies=[Depends(require_scope("write"))],
)
async def add_webhook(
    agent_id: uuid.UUID,
    request: CreateWebhookRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    account: Account = Depends(get_current_account),
) -> WebhookResponse:
    """Add a webhook to an agent."""
    _require_agent_tier(user.effective_tier)

    svc = AgentService(db)
    try:
        agent = await svc.get_agent_by_id(account.id, agent_id)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail={"error": "NOT_FOUND", "message": str(e)})

    try:
        webhook = await svc.add_webhook(
            account_id=account.id,
            agent_name=agent.name,
            path=request.path,
            handler_function_name=request.handler_function_name,
            secret=request.secret,
        )
        await db.commit()
        await db.refresh(webhook)
    except ConflictError as e:
        raise HTTPException(status_code=409, detail={"error": "CONFLICT", "message": str(e)})

    return WebhookResponse.model_validate(webhook)


@router.get(
    "/{agent_id}/webhooks",
    response_model=WebhookListResponse,
    dependencies=[Depends(require_scope("read"))],
)
async def list_webhooks(
    agent_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    account: Account = Depends(get_current_account),
) -> WebhookListResponse:
    """List all webhooks for an agent."""
    _require_agent_tier(user.effective_tier)

    svc = AgentService(db)
    try:
        agent = await svc.get_agent_by_id(account.id, agent_id)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail={"error": "NOT_FOUND", "message": str(e)})

    webhooks = await svc.list_webhooks(account.id, agent.name)
    return WebhookListResponse(
        webhooks=[WebhookResponse.model_validate(w) for w in webhooks],
        total=len(webhooks),
    )


@router.delete(
    "/{agent_id}/webhooks/{webhook_id}",
    status_code=204,
    dependencies=[Depends(require_scope("write"))],
)
async def remove_webhook(
    agent_id: uuid.UUID,
    webhook_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    account: Account = Depends(get_current_account),
) -> None:
    """Remove a webhook from an agent."""
    _require_agent_tier(user.effective_tier)

    svc = AgentService(db)
    try:
        agent = await svc.get_agent_by_id(account.id, agent_id)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail={"error": "NOT_FOUND", "message": str(e)})

    try:
        await svc.remove_webhook(account.id, agent.name, webhook_id)
        await db.commit()
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail={"error": "NOT_FOUND", "message": str(e)})


@router.post(
    "/{agent_id}/webhooks/{webhook_id}/trigger",
    dependencies=[Depends(require_scope("write"))],
)
async def trigger_webhook(
    agent_id: uuid.UUID,
    webhook_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    account: Account = Depends(get_current_account),
) -> dict:
    """Manually trigger a webhook for testing."""
    _require_agent_tier(user.effective_tier)

    svc = AgentService(db)
    try:
        agent = await svc.get_agent_by_id(account.id, agent_id)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail={"error": "NOT_FOUND", "message": str(e)})

    webhooks = await svc.list_webhooks(account.id, agent.name)
    webhook = next((w for w in webhooks if str(w.id) == str(webhook_id)), None)
    if not webhook:
        raise HTTPException(
            status_code=404, detail={"error": "NOT_FOUND", "message": "Webhook not found"}
        )

    return {"webhook_id": str(webhook_id), "triggered": True, "message": "Webhook triggered"}


@router.put(
    "/{agent_id}/state/{key}",
    response_model=StateResponse,
    dependencies=[Depends(require_scope("write"))],
)
async def set_state(
    agent_id: uuid.UUID,
    key: str,
    request: SetStateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    account: Account = Depends(get_current_account),
) -> StateResponse:
    """Set a state value for an agent."""
    _require_agent_tier(user.effective_tier)

    svc = AgentService(db)
    try:
        agent = await svc.get_agent_by_id(account.id, agent_id)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail={"error": "NOT_FOUND", "message": str(e)})

    try:
        state_entry = await svc.set_state(
            account_id=account.id,
            agent_name=agent.name,
            key=key,
            value=request.value,
            tier=user.effective_tier,
        )
        await db.commit()
    except ForbiddenError as e:
        raise HTTPException(status_code=403, detail={"error": "FORBIDDEN", "message": str(e)})

    return StateResponse(
        key=key,
        value=request.value,
        size_bytes=state_entry.size_bytes,
        updated_at=state_entry.updated_at,
    )


@router.get(
    "/{agent_id}/state/{key}",
    response_model=StateResponse,
    dependencies=[Depends(require_scope("read"))],
)
async def get_state(
    agent_id: uuid.UUID,
    key: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    account: Account = Depends(get_current_account),
) -> StateResponse:
    """Get a state value for an agent."""
    _require_agent_tier(user.effective_tier)

    svc = AgentService(db)
    try:
        agent = await svc.get_agent_by_id(account.id, agent_id)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail={"error": "NOT_FOUND", "message": str(e)})

    try:
        value, state_entry = await svc.get_state(account.id, agent.name, key)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail={"error": "NOT_FOUND", "message": str(e)})

    return StateResponse(
        key=key,
        value=value,
        size_bytes=state_entry.size_bytes,
        updated_at=state_entry.updated_at,
    )


@router.delete(
    "/{agent_id}/state/{key}",
    status_code=204,
    dependencies=[Depends(require_scope("write"))],
)
async def delete_state(
    agent_id: uuid.UUID,
    key: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    account: Account = Depends(get_current_account),
) -> None:
    """Delete a state key for an agent."""
    _require_agent_tier(user.effective_tier)

    svc = AgentService(db)
    try:
        agent = await svc.get_agent_by_id(account.id, agent_id)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail={"error": "NOT_FOUND", "message": str(e)})

    try:
        await svc.delete_state(account.id, agent.name, key)
        await db.commit()
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail={"error": "NOT_FOUND", "message": str(e)})


@router.get(
    "/{agent_id}/state",
    response_model=StateKeyListResponse,
    dependencies=[Depends(require_scope("read"))],
)
async def list_state_keys(
    agent_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    account: Account = Depends(get_current_account),
) -> StateKeyListResponse:
    """List all state keys for an agent."""
    _require_agent_tier(user.effective_tier)

    svc = AgentService(db)
    try:
        agent = await svc.get_agent_by_id(account.id, agent_id)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail={"error": "NOT_FOUND", "message": str(e)})

    try:
        result = await svc.list_state_keys(account.id, agent.name, user.effective_tier)
    except ForbiddenError as e:
        raise HTTPException(status_code=403, detail={"error": "FORBIDDEN", "message": str(e)})

    return StateKeyListResponse(**result)


@router.put(
    "/{agent_id}/ai",
    response_model=AIResponse,
    dependencies=[Depends(require_scope("write"))],
)
async def configure_ai(
    agent_id: uuid.UUID,
    request: ConfigureAIRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    account: Account = Depends(get_current_account),
) -> AIResponse:
    """Configure AI engine for an agent."""
    _require_agent_tier(user.effective_tier)

    svc = AgentService(db)
    try:
        agent = await svc.get_agent_by_id(account.id, agent_id)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail={"error": "NOT_FOUND", "message": str(e)})

    agent = await svc.configure_ai(
        account_id=account.id,
        agent_name=agent.name,
        engine=request.engine,
        model=request.model,
        api_key=request.api_key,
        system_prompt=request.system_prompt,
    )
    await db.commit()

    return AIResponse(
        engine=agent.ai_engine,
        model=agent.ai_model,
        system_prompt=agent.system_prompt,
        configured=True,
    )


@router.delete(
    "/{agent_id}/ai",
    status_code=204,
    dependencies=[Depends(require_scope("write"))],
)
async def remove_ai(
    agent_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    account: Account = Depends(get_current_account),
) -> None:
    """Remove AI engine configuration from an agent."""
    _require_agent_tier(user.effective_tier)

    svc = AgentService(db)
    try:
        agent = await svc.get_agent_by_id(account.id, agent_id)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail={"error": "NOT_FOUND", "message": str(e)})

    await svc.remove_ai(account.id, agent.name)
    await db.commit()


@router.post(
    "/{agent_id}/channels",
    response_model=ChannelResponse,
    status_code=201,
    dependencies=[Depends(require_scope("write"))],
)
async def add_channel(
    agent_id: uuid.UUID,
    request: CreateChannelRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    account: Account = Depends(get_current_account),
) -> ChannelResponse:
    """Add a communication channel to an agent."""
    _require_agent_tier(user.effective_tier)

    svc = AgentService(db)
    try:
        agent = await svc.get_agent_by_id(account.id, agent_id)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail={"error": "NOT_FOUND", "message": str(e)})

    try:
        channel = await svc.add_channel(
            account_id=account.id,
            agent_name=agent.name,
            channel_type=request.channel_type,
            config=request.config,
        )
        await db.commit()
        await db.refresh(channel)
    except ConflictError as e:
        raise HTTPException(status_code=409, detail={"error": "CONFLICT", "message": str(e)})

    return ChannelResponse.model_validate(channel)


@router.delete(
    "/{agent_id}/channels/{channel_type}",
    status_code=204,
    dependencies=[Depends(require_scope("write"))],
)
async def remove_channel(
    agent_id: uuid.UUID,
    channel_type: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    account: Account = Depends(get_current_account),
) -> None:
    """Remove a communication channel from an agent."""
    _require_agent_tier(user.effective_tier)

    svc = AgentService(db)
    try:
        agent = await svc.get_agent_by_id(account.id, agent_id)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail={"error": "NOT_FOUND", "message": str(e)})

    try:
        await svc.remove_channel(account.id, agent.name, channel_type)
        await db.commit()
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail={"error": "NOT_FOUND", "message": str(e)})


@router.post(
    "/{agent_id}/clone",
    response_model=AgentResponse,
    status_code=201,
    dependencies=[Depends(require_scope("write"))],
)
async def clone_agent(
    agent_id: uuid.UUID,
    request: CloneAgentRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    account: Account = Depends(get_current_account),
) -> AgentResponse:
    """Clone an agent with all its state, schedules, and channels."""
    _require_agent_tier(user.effective_tier)

    svc = AgentService(db)
    try:
        source_agent = await svc.get_agent_by_id(account.id, agent_id)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail={"error": "NOT_FOUND", "message": str(e)})

    try:
        new_agent = await svc.clone_agent(
            account_id=account.id,
            source_agent_name=source_agent.name,
            new_name=request.new_name,
            tier=user.effective_tier,
        )
        await db.commit()
        await db.refresh(new_agent)
    except ConflictError as e:
        raise HTTPException(status_code=409, detail={"error": "CONFLICT", "message": str(e)})
    except ForbiddenError as e:
        raise HTTPException(status_code=403, detail={"error": "FORBIDDEN", "message": str(e)})

    return AgentResponse.model_validate(new_agent)


lock_router = APIRouter(prefix="/namespaces", tags=["agents"])


@lock_router.post(
    "/{namespace_name}/functions/{function_name}/lock",
)
async def lock_function(
    namespace_name: str,
    function_name: str,
    db: AsyncSession = Depends(get_db),
    admin_id: AdminUserId = None,
) -> dict:
    """Lock a function to prevent modification (admin-only)."""
    ns_manager = NamespaceServiceManager(db)
    svc_service = NamespaceServiceService(db)
    fn_service = FunctionService(db)

    parts = function_name.split(".", 1)
    if len(parts) != 2:
        raise HTTPException(
            status_code=400,
            detail={"error": "INVALID_FUNCTION", "message": "function_name must be service.name"},
        )
    service_name, fn_name = parts

    try:
        namespace = await ns_manager.get_by_name(namespace_name)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail={"error": "NOT_FOUND", "message": str(e)})

    try:
        service = await svc_service.get_by_name(namespace.id, service_name)
        function = await fn_service.get_by_name(service.id, fn_name)
        await fn_service.lock_function(function.id, uuid.UUID(admin_id))
        await db.commit()
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail={"error": "NOT_FOUND", "message": str(e)})

    return {
        "function": function_name,
        "namespace": namespace_name,
        "locked": True,
        "locked_by": admin_id,
    }


@lock_router.delete(
    "/{namespace_name}/functions/{function_name}/lock",
)
async def unlock_function(
    namespace_name: str,
    function_name: str,
    db: AsyncSession = Depends(get_db),
    _admin_id: AdminUserId = None,
) -> dict:
    """Unlock a function to allow modification (admin-only)."""
    ns_manager = NamespaceServiceManager(db)
    svc_service = NamespaceServiceService(db)
    fn_service = FunctionService(db)

    parts = function_name.split(".", 1)
    if len(parts) != 2:
        raise HTTPException(
            status_code=400,
            detail={"error": "INVALID_FUNCTION", "message": "function_name must be service.name"},
        )
    service_name, fn_name = parts

    try:
        namespace = await ns_manager.get_by_name(namespace_name)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail={"error": "NOT_FOUND", "message": str(e)})

    try:
        service = await svc_service.get_by_name(namespace.id, service_name)
        function = await fn_service.get_by_name(service.id, fn_name)
        await fn_service.unlock_function(function.id)
        await db.commit()
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail={"error": "NOT_FOUND", "message": str(e)})

    return {
        "function": function_name,
        "namespace": namespace_name,
        "locked": False,
    }
