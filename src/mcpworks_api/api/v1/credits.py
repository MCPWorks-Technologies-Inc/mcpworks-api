"""Credit endpoints - balance and transaction management."""

import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from mcpworks_api.core.database import get_db
from mcpworks_api.core.exceptions import InsufficientCreditsError, InvalidHoldError
from mcpworks_api.dependencies import CurrentUserId
from mcpworks_api.models.credit_transaction import TransactionType
from mcpworks_api.schemas.credit import (
    AddCreditsRequest,
    AddCreditsResponse,
    CommitRequest,
    CommitResponse,
    CreditBalance,
    HoldRequest,
    HoldResponse,
    ReleaseRequest,
    ReleaseResponse,
    TransactionList,
    TransactionSummary,
)
from mcpworks_api.services.credit import CreditService

router = APIRouter(prefix="/credits", tags=["credits"])


@router.get(
    "",
    response_model=CreditBalance,
    responses={
        200: {"description": "Current credit balance"},
        401: {"description": "Not authenticated or token expired"},
    },
)
async def get_credit_balance(
    user_id: CurrentUserId,
    db: AsyncSession = Depends(get_db),
) -> CreditBalance:
    """Get the authenticated user's credit balance.

    FR-CREDIT-001: Return available and held credit balances.
    """
    credit_service = CreditService(db)
    credit = await credit_service.get_balance(uuid.UUID(user_id))

    return CreditBalance(
        available_credits=credit.available_balance,
        held_credits=credit.held_balance,
        lifetime_earned=credit.lifetime_earned,
        lifetime_spent=credit.lifetime_spent,
    )


@router.get(
    "/transactions",
    response_model=TransactionList,
    responses={
        200: {"description": "List of credit transactions"},
        401: {"description": "Not authenticated or token expired"},
    },
)
async def get_transactions(
    user_id: CurrentUserId,
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=100, description="Number of transactions to return"),
    offset: int = Query(default=0, ge=0, description="Number of transactions to skip"),
) -> TransactionList:
    """Get the authenticated user's transaction history.

    FR-CREDIT-005: Return audit trail of all credit transactions.
    """
    credit_service = CreditService(db)
    transactions = await credit_service.get_transactions(
        user_id=uuid.UUID(user_id),
        limit=limit,
        offset=offset,
    )

    return TransactionList(
        transactions=[
            TransactionSummary(
                id=txn.id,
                type=txn.type,
                amount=txn.amount,
                balance_before=txn.balance_before,
                balance_after=txn.balance_after,
                created_at=txn.created_at,
                execution_id=txn.execution_id,
                hold_id=txn.hold_id,
            )
            for txn in transactions
        ],
        total=len(transactions),  # TODO: Add actual count query for pagination
        limit=limit,
        offset=offset,
    )


@router.post(
    "/hold",
    response_model=HoldResponse,
    responses={
        200: {"description": "Credits successfully held"},
        400: {"description": "Insufficient credits or invalid amount"},
        401: {"description": "Not authenticated or token expired"},
    },
)
async def create_hold(
    body: HoldRequest,
    user_id: CurrentUserId,
    db: AsyncSession = Depends(get_db),
) -> HoldResponse:
    """Create a credit hold for a pending operation.

    FR-CREDIT-002: Hold credits before operation starts.
    Moves credits from available_balance to held_balance.
    Holds expire after 1 hour if not committed or released.
    """
    credit_service = CreditService(db)

    try:
        transaction = await credit_service.hold(
            user_id=uuid.UUID(user_id),
            amount=body.amount,
            execution_id=body.execution_id,
            metadata=body.metadata,
        )
    except InsufficientCreditsError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=e.to_dict(),
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "INVALID_AMOUNT",
                "message": str(e),
                "details": {},
            },
        )

    # Calculate expiry time
    expires_at = transaction.created_at + timedelta(hours=CreditService.HOLD_EXPIRY_HOURS)

    return HoldResponse(
        hold_id=transaction.id,
        amount=transaction.amount,
        expires_at=expires_at,
        available_balance=transaction.balance_after,
    )


@router.post(
    "/hold/{hold_id}/commit",
    response_model=CommitResponse,
    responses={
        200: {"description": "Hold successfully committed"},
        400: {"description": "Invalid hold or amount"},
        401: {"description": "Not authenticated or token expired"},
    },
)
async def commit_hold(
    hold_id: uuid.UUID,
    body: CommitRequest,
    user_id: CurrentUserId,
    db: AsyncSession = Depends(get_db),
) -> CommitResponse:
    """Commit a credit hold, finalizing the charge.

    FR-CREDIT-003: Commit (deduct) credits after operation succeeds.
    If amount is less than held, excess is returned to available_balance.
    """
    credit_service = CreditService(db)

    try:
        # Get the original hold to calculate released amount
        from sqlalchemy import select

        from mcpworks_api.models import CreditTransaction

        result = await db.execute(
            select(CreditTransaction)
            .where(CreditTransaction.id == hold_id)
            .where(CreditTransaction.type == TransactionType.HOLD.value)
        )
        hold_txn = result.scalar_one_or_none()

        if hold_txn is None:
            raise InvalidHoldError(hold_id=str(hold_id), reason="Hold not found")

        # Verify the hold belongs to this user
        if str(hold_txn.user_id) != user_id:
            raise InvalidHoldError(hold_id=str(hold_id), reason="Hold not found")

        held_amount = hold_txn.amount
        commit_amount = body.amount if body.amount is not None else held_amount

        transaction = await credit_service.commit(
            hold_id=hold_id,
            amount=body.amount,
            metadata=body.metadata,
        )
    except InvalidHoldError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=e.to_dict(),
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "INVALID_AMOUNT",
                "message": str(e),
                "details": {},
            },
        )

    return CommitResponse(
        transaction_id=transaction.id,
        committed_amount=transaction.amount,
        released_amount=held_amount - commit_amount,
        available_balance=transaction.balance_after,
    )


@router.post(
    "/hold/{hold_id}/release",
    response_model=ReleaseResponse,
    responses={
        200: {"description": "Hold successfully released"},
        400: {"description": "Invalid or already processed hold"},
        401: {"description": "Not authenticated or token expired"},
    },
)
async def release_hold(
    hold_id: uuid.UUID,
    body: ReleaseRequest,
    user_id: CurrentUserId,
    db: AsyncSession = Depends(get_db),
) -> ReleaseResponse:
    """Release a credit hold, returning credits to available balance.

    FR-CREDIT-004: Release held credits if operation fails or is cancelled.
    """
    credit_service = CreditService(db)

    try:
        # Verify the hold belongs to this user
        from sqlalchemy import select

        from mcpworks_api.models import CreditTransaction

        result = await db.execute(
            select(CreditTransaction)
            .where(CreditTransaction.id == hold_id)
            .where(CreditTransaction.type == TransactionType.HOLD.value)
        )
        hold_txn = result.scalar_one_or_none()

        if hold_txn is None:
            raise InvalidHoldError(hold_id=str(hold_id), reason="Hold not found")

        if str(hold_txn.user_id) != user_id:
            raise InvalidHoldError(hold_id=str(hold_id), reason="Hold not found")

        transaction = await credit_service.release(
            hold_id=hold_id,
            metadata=body.metadata,
        )
    except InvalidHoldError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=e.to_dict(),
        )

    return ReleaseResponse(
        transaction_id=transaction.id,
        released_amount=transaction.amount,
        available_balance=transaction.balance_after,
    )


@router.post(
    "/add",
    response_model=AddCreditsResponse,
    responses={
        200: {"description": "Credits successfully added"},
        400: {"description": "Invalid amount or transaction type"},
        401: {"description": "Not authenticated or token expired"},
    },
)
async def add_credits(
    body: AddCreditsRequest,
    user_id: CurrentUserId,
    db: AsyncSession = Depends(get_db),
) -> AddCreditsResponse:
    """Add credits to the user's available balance.

    Used for purchases, grants (subscription), and refunds.
    Note: In production, this would require additional authorization
    (admin role or verified payment).
    """
    credit_service = CreditService(db)

    # Map string to enum
    type_map = {
        "purchase": TransactionType.PURCHASE,
        "grant": TransactionType.GRANT,
        "refund": TransactionType.REFUND,
    }
    transaction_type = type_map.get(body.transaction_type, TransactionType.GRANT)

    try:
        transaction = await credit_service.add_credits(
            user_id=uuid.UUID(user_id),
            amount=body.amount,
            transaction_type=transaction_type,
            metadata=body.metadata,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "INVALID_AMOUNT",
                "message": str(e),
                "details": {},
            },
        )

    return AddCreditsResponse(
        transaction_id=transaction.id,
        amount=transaction.amount,
        available_balance=transaction.balance_after,
    )
