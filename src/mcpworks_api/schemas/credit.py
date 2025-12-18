"""Pydantic schemas for credit endpoints."""

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class CreditBalance(BaseModel):
    """Response schema for credit balance."""

    available_credits: Decimal = Field(
        ...,
        description="Credits available for use",
        examples=["100.00"],
    )
    held_credits: Decimal = Field(
        ...,
        description="Credits currently held for pending operations",
        examples=["10.00"],
    )
    lifetime_earned: Decimal = Field(
        ...,
        description="Total credits earned over account lifetime",
        examples=["500.00"],
    )
    lifetime_spent: Decimal = Field(
        ...,
        description="Total credits spent over account lifetime",
        examples=["400.00"],
    )

    model_config = ConfigDict(from_attributes=True)


class HoldRequest(BaseModel):
    """Request body for POST /credits/hold."""

    amount: Decimal = Field(
        ...,
        gt=0,
        description="Amount of credits to hold (must be positive)",
        examples=["10.00"],
    )
    execution_id: uuid.UUID | None = Field(
        default=None,
        description="Optional reference to the execution/operation",
    )
    metadata: dict | None = Field(
        default=None,
        description="Optional metadata for the transaction",
    )


class HoldResponse(BaseModel):
    """Response body for POST /credits/hold."""

    hold_id: uuid.UUID = Field(
        ...,
        description="UUID of the hold transaction",
    )
    amount: Decimal = Field(
        ...,
        description="Amount of credits held",
    )
    expires_at: datetime = Field(
        ...,
        description="When the hold will expire",
    )
    available_balance: Decimal = Field(
        ...,
        description="Remaining available balance after hold",
    )


class CommitRequest(BaseModel):
    """Request body for POST /credits/hold/{hold_id}/commit."""

    amount: Decimal | None = Field(
        default=None,
        ge=0,
        description="Amount to commit (None = full held amount). Must not exceed held amount.",
        examples=["8.50"],
    )
    metadata: dict | None = Field(
        default=None,
        description="Optional metadata for the transaction",
    )


class CommitResponse(BaseModel):
    """Response body for POST /credits/hold/{hold_id}/commit."""

    transaction_id: uuid.UUID = Field(
        ...,
        description="UUID of the commit transaction",
    )
    committed_amount: Decimal = Field(
        ...,
        description="Amount of credits committed (charged)",
    )
    released_amount: Decimal = Field(
        ...,
        description="Amount returned to available (if partial commit)",
    )
    available_balance: Decimal = Field(
        ...,
        description="New available balance after commit",
    )


class ReleaseRequest(BaseModel):
    """Request body for POST /credits/hold/{hold_id}/release."""

    metadata: dict | None = Field(
        default=None,
        description="Optional metadata for the transaction",
    )


class ReleaseResponse(BaseModel):
    """Response body for POST /credits/hold/{hold_id}/release."""

    transaction_id: uuid.UUID = Field(
        ...,
        description="UUID of the release transaction",
    )
    released_amount: Decimal = Field(
        ...,
        description="Amount of credits returned to available",
    )
    available_balance: Decimal = Field(
        ...,
        description="New available balance after release",
    )


class AddCreditsRequest(BaseModel):
    """Request body for POST /credits/add (admin/internal)."""

    amount: Decimal = Field(
        ...,
        gt=0,
        description="Amount of credits to add (must be positive)",
        examples=["100.00"],
    )
    transaction_type: str = Field(
        default="grant",
        description="Type of credit addition: purchase, grant, or refund",
        pattern="^(purchase|grant|refund)$",
    )
    metadata: dict | None = Field(
        default=None,
        description="Optional metadata for the transaction",
    )


class AddCreditsResponse(BaseModel):
    """Response body for POST /credits/add."""

    transaction_id: uuid.UUID = Field(
        ...,
        description="UUID of the transaction",
    )
    amount: Decimal = Field(
        ...,
        description="Amount of credits added",
    )
    available_balance: Decimal = Field(
        ...,
        description="New available balance after addition",
    )


class TransactionSummary(BaseModel):
    """Summary of a credit transaction."""

    id: uuid.UUID = Field(
        ...,
        description="Transaction UUID",
    )
    type: str = Field(
        ...,
        description="Transaction type: hold, commit, release, purchase, grant, refund",
    )
    amount: Decimal = Field(
        ...,
        description="Transaction amount",
    )
    balance_before: Decimal = Field(
        ...,
        description="Available balance before transaction",
    )
    balance_after: Decimal = Field(
        ...,
        description="Available balance after transaction",
    )
    created_at: datetime = Field(
        ...,
        description="When the transaction was created",
    )
    execution_id: uuid.UUID | None = Field(
        default=None,
        description="Reference to associated execution (if any)",
    )
    hold_id: uuid.UUID | None = Field(
        default=None,
        description="Reference to original hold (for commit/release)",
    )

    model_config = ConfigDict(from_attributes=True)


class TransactionList(BaseModel):
    """Paginated list of credit transactions."""

    transactions: list[TransactionSummary] = Field(
        ...,
        description="List of transactions",
    )
    total: int = Field(
        ...,
        description="Total number of transactions (for pagination)",
    )
    limit: int = Field(
        ...,
        description="Number of transactions per page",
    )
    offset: int = Field(
        ...,
        description="Number of transactions skipped",
    )
