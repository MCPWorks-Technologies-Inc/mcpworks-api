"""Execution service - manages workflow execution lifecycle."""

import contextlib
import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mcpworks_api.core.exceptions import (
    InsufficientTierError,
    InvalidHoldError,
    ServiceTimeoutError,
    ServiceUnavailableError,
)
from mcpworks_api.models import (
    CreditTransaction,
    Execution,
    ExecutionStatus,
    Service,
)
from mcpworks_api.services.credit import CreditService
from mcpworks_api.services.router import ServiceRouter


class ExecutionService:
    """Manages workflow execution lifecycle with credit integration."""

    def __init__(self, db: AsyncSession) -> None:
        """Initialize execution service."""
        self.db = db
        self.router = ServiceRouter(db)
        self.credit_service = CreditService(db)

    async def start_execution(
        self,
        workflow_id: str,
        user_id: uuid.UUID,
        user_tier: str,
        input_data: dict[str, Any] | None = None,
    ) -> tuple[Execution, CreditTransaction | None]:
        """Start a workflow execution.

        1. Check agent service availability
        2. Check user tier access
        3. Hold credits for execution
        4. Create execution record
        5. Route request to mcpworks-agent

        Args:
            workflow_id: ID of the workflow to execute
            user_id: ID of the user executing
            user_tier: User's subscription tier
            input_data: Input parameters for the workflow

        Returns:
            Tuple of (Execution record, CreditTransaction hold)

        Raises:
            ServiceUnavailableError: If agent service is unavailable
            InsufficientTierError: If user tier doesn't allow access
            InsufficientCreditsError: If user has insufficient credits
        """
        # Get agent service
        service = await self.router.get_service("agent")
        if service is None:
            raise ServiceUnavailableError(
                service_name="agent",
                message="Agent service not configured",
            )

        if not service.is_available:
            raise ServiceUnavailableError(
                service_name="agent",
                retry_after=30,
            )

        # Check tier access
        if not self.router.can_access_service(user_tier, service):
            raise InsufficientTierError(
                message=f"Agent service requires tier '{service.tier_required}' or higher",
                details={
                    "required_tier": service.tier_required,
                    "user_tier": user_tier,
                },
            )

        # Hold credits
        hold_txn = None
        if service.credit_cost > 0:
            hold_txn = await self.credit_service.hold(
                user_id=user_id,
                amount=service.credit_cost,
                metadata={
                    "service": "agent",
                    "workflow_id": workflow_id,
                },
            )

        # Create execution record
        execution = Execution(
            user_id=user_id,
            workflow_id=workflow_id,
            status=ExecutionStatus.PENDING.value,
            hold_transaction_id=hold_txn.id if hold_txn else None,
            input_data=input_data,
        )
        self.db.add(execution)
        await self.db.commit()
        await self.db.refresh(execution)

        # Route to agent service (fire and forget - agent will callback)
        try:
            status_code, _, response_body = await self._send_to_agent(
                execution_id=str(execution.id),
                workflow_id=workflow_id,
                input_data=input_data,
                service=service,
            )

            # Check if agent accepted the request (2xx response)
            if 200 <= status_code < 300:
                # Mark as running
                execution.mark_running()
                await self.db.commit()
            else:
                # Agent rejected the request (4xx/5xx)
                # Release credits and mark as failed
                if hold_txn is not None:
                    await self.credit_service.release(
                        hold_id=hold_txn.id,
                        metadata={
                            "reason": "agent_rejected",
                            "response_status": status_code,
                        },
                    )

                # Extract error message from response
                error_msg = "Agent rejected request"
                if isinstance(response_body, dict):
                    error_msg = str(
                        response_body.get("error")
                        or response_body.get("message")
                        or error_msg
                    )

                execution.mark_failed(
                    error_message=f"Agent returned {status_code}: {error_msg}",
                    error_code="AGENT_REJECTED",
                )
                await self.db.commit()

                raise ServiceUnavailableError(
                    service_name="agent",
                    message=f"Agent rejected execution: {error_msg}",
                )

        except (ServiceTimeoutError, ServiceUnavailableError) as e:
            # Release credits on service failure (if not already released above)
            if hold_txn is not None and execution.status == ExecutionStatus.PENDING.value:
                await self.credit_service.release(
                    hold_id=hold_txn.id,
                    metadata={"reason": "agent_service_error"},
                )

                # Mark execution as failed
                execution.mark_failed(
                    error_message=str(e),
                    error_code="AGENT_SERVICE_ERROR",
                )
                await self.db.commit()
            raise

        return execution, hold_txn

    async def _send_to_agent(
        self,
        execution_id: str,
        workflow_id: str,
        input_data: dict[str, Any] | None,
        service: Service,
    ) -> tuple[int, dict[str, Any], Any]:
        """Send execution request to mcpworks-agent.

        Args:
            execution_id: Our execution ID
            workflow_id: Workflow to execute
            input_data: Workflow input
            service: Agent service record

        Returns:
            Tuple of (status_code, headers, body) from agent response
        """
        return await self.router._make_request(
            method="POST",
            url=f"{service.url.rstrip('/')}/execute/{workflow_id}",
            body={
                "execution_id": execution_id,
                "input_data": input_data or {},
                "callback_url": f"/v1/services/agent/executions/{execution_id}/callback",
            },
        )

    async def handle_callback(
        self,
        execution_id: uuid.UUID,
        status: str,
        result_data: dict[str, Any] | None = None,
        error_message: str | None = None,
        error_code: str | None = None,
    ) -> tuple[Execution, str, Decimal]:
        """Handle callback from mcpworks-agent.

        1. Update execution status
        2. Commit or release credits based on result
        3. Store result data

        Args:
            execution_id: Execution to update
            status: New status (completed or failed)
            result_data: Execution result (on success)
            error_message: Error message (on failure)
            error_code: Error code (on failure)

        Returns:
            Tuple of (Execution, credits_action, credits_amount)

        Raises:
            ValueError: If execution not found or already completed
        """
        # Get execution
        result = await self.db.execute(select(Execution).where(Execution.id == execution_id))
        execution = result.scalar_one_or_none()

        if execution is None:
            raise ValueError(f"Execution {execution_id} not found")

        if execution.is_terminal:
            raise ValueError(
                f"Execution {execution_id} already in terminal state: {execution.status}"
            )

        # Get the hold transaction for credit operations
        credits_action = "none"
        credits_amount = Decimal("0.00")

        if execution.hold_transaction_id:
            hold_result = await self.db.execute(
                select(CreditTransaction).where(
                    CreditTransaction.id == execution.hold_transaction_id
                )
            )
            hold_txn = hold_result.scalar_one_or_none()

            if hold_txn:
                credits_amount = hold_txn.amount

                if status == "completed":
                    # Commit credits on success
                    await self.credit_service.commit(
                        hold_id=hold_txn.id,
                        metadata={
                            "execution_id": str(execution_id),
                            "workflow_id": execution.workflow_id,
                        },
                    )
                    credits_action = "committed"
                else:
                    # Release credits on failure
                    await self.credit_service.release(
                        hold_id=hold_txn.id,
                        metadata={
                            "execution_id": str(execution_id),
                            "workflow_id": execution.workflow_id,
                            "reason": error_code or "execution_failed",
                        },
                    )
                    credits_action = "released"

        # Update execution
        if status == "completed":
            execution.mark_completed(result_data)
        else:
            execution.mark_failed(
                error_message=error_message or "Unknown error",
                error_code=error_code,
            )

        await self.db.commit()
        await self.db.refresh(execution)

        return execution, credits_action, credits_amount

    async def get_execution(self, execution_id: uuid.UUID) -> Execution | None:
        """Get execution by ID.

        Args:
            execution_id: Execution ID

        Returns:
            Execution or None if not found
        """
        result = await self.db.execute(select(Execution).where(Execution.id == execution_id))
        return result.scalar_one_or_none()

    async def get_user_executions(
        self,
        user_id: uuid.UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Execution], int]:
        """Get executions for a user.

        Args:
            user_id: User ID
            limit: Max results
            offset: Pagination offset

        Returns:
            Tuple of (executions list, total count)
        """
        # Get total count
        count_result = await self.db.execute(select(Execution).where(Execution.user_id == user_id))
        total = len(count_result.scalars().all())

        # Get page
        result = await self.db.execute(
            select(Execution)
            .where(Execution.user_id == user_id)
            .order_by(Execution.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        executions = list(result.scalars().all())

        return executions, total

    async def cancel_execution(self, execution_id: uuid.UUID) -> Execution:
        """Cancel a pending or running execution.

        Args:
            execution_id: Execution to cancel

        Returns:
            Updated Execution

        Raises:
            ValueError: If execution not found or cannot be cancelled
        """
        result = await self.db.execute(select(Execution).where(Execution.id == execution_id))
        execution = result.scalar_one_or_none()

        if execution is None:
            raise ValueError(f"Execution {execution_id} not found")

        if execution.is_terminal:
            raise ValueError(f"Cannot cancel execution in state: {execution.status}")

        # Release any held credits (if not already processed)
        if execution.hold_transaction_id:
            with contextlib.suppress(InvalidHoldError):
                await self.credit_service.release(
                    hold_id=execution.hold_transaction_id,
                    metadata={
                        "execution_id": str(execution_id),
                        "reason": "cancelled",
                    },
                )

        execution.mark_cancelled()
        await self.db.commit()
        await self.db.refresh(execution)

        return execution
