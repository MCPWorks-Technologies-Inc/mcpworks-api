"""Namespace sharing REST API endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from mcpworks_api.api.v1.namespaces import get_current_account
from mcpworks_api.core.database import get_db
from mcpworks_api.core.exceptions import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from mcpworks_api.dependencies import require_scope
from mcpworks_api.models import Account
from mcpworks_api.services.namespace import NamespaceServiceManager
from mcpworks_api.services.namespace_share import NamespaceShareService

router = APIRouter(tags=["shares"])


class CreateShareRequest(BaseModel):
    email: str = Field(..., description="Email of the user to invite")
    permissions: list[str] = Field(
        default=["read", "execute"],
        description="Permissions to grant: read, execute",
    )
    acknowledge_billing: bool = Field(
        ...,
        description="Must be true. Acknowledges that executions by the invited user will count against your namespace's quota and billing.",
    )


class ShareResponse(BaseModel):
    id: str
    namespace_id: str
    namespace_name: str | None = None
    user_id: str
    user_email: str | None = None
    granted_by_user_id: str | None = None
    granted_by_name: str | None = None
    permissions: list[str]
    status: str
    accepted_at: str | None = None
    revoked_at: str | None = None
    created_at: str


class ShareListResponse(BaseModel):
    shares: list[ShareResponse]


# --- Namespace-scoped endpoints (owner-only) ---


@router.post(
    "/namespaces/{namespace_name}/shares",
    response_model=ShareResponse,
    status_code=201,
    dependencies=[Depends(require_scope("write"))],
)
async def create_share(
    namespace_name: str,
    request: CreateShareRequest,
    db: AsyncSession = Depends(get_db),
    account: Account = Depends(get_current_account),
) -> ShareResponse:
    if not request.acknowledge_billing:
        raise HTTPException(
            status_code=422,
            detail="You must acknowledge that executions by shared users will be billed to your account. Set acknowledge_billing to true.",
        )

    ns_service = NamespaceServiceManager(db)
    share_service = NamespaceShareService(db)

    try:
        namespace = await ns_service.get_by_name(namespace_name, account.id)
        share = await share_service.create_invite(
            namespace_id=namespace.id,
            invitee_email=request.email,
            permissions=request.permissions,
            granted_by_user_id=account.user_id,
        )
        await db.commit()

        return ShareResponse(
            id=str(share.id),
            namespace_id=str(share.namespace_id),
            namespace_name=namespace_name,
            user_id=str(share.user_id),
            permissions=share.permissions,
            status=share.status,
            granted_by_user_id=str(share.granted_by_user_id) if share.granted_by_user_id else None,
            accepted_at=share.accepted_at.isoformat() if share.accepted_at else None,
            revoked_at=share.revoked_at.isoformat() if share.revoked_at else None,
            created_at=share.created_at.isoformat(),
        )
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ForbiddenError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get(
    "/namespaces/{namespace_name}/shares",
    response_model=ShareListResponse,
    dependencies=[Depends(require_scope("read"))],
)
async def list_namespace_shares(
    namespace_name: str,
    db: AsyncSession = Depends(get_db),
    account: Account = Depends(get_current_account),
) -> ShareListResponse:
    ns_service = NamespaceServiceManager(db)
    share_service = NamespaceShareService(db)

    try:
        namespace = await ns_service.get_by_name(namespace_name, account.id)
    except NotFoundError:
        raise HTTPException(status_code=404, detail=f"Namespace '{namespace_name}' not found")
    except ForbiddenError:
        raise HTTPException(status_code=403, detail="Access denied")

    shares = await share_service.list_for_namespace(namespace.id)
    return ShareListResponse(
        shares=[
            ShareResponse(
                id=str(s.id),
                namespace_id=str(s.namespace_id),
                namespace_name=namespace_name,
                user_id=str(s.user_id),
                user_email=s.user.email if s.user else None,
                permissions=s.permissions,
                status=s.status,
                granted_by_user_id=str(s.granted_by_user_id) if s.granted_by_user_id else None,
                accepted_at=s.accepted_at.isoformat() if s.accepted_at else None,
                revoked_at=s.revoked_at.isoformat() if s.revoked_at else None,
                created_at=s.created_at.isoformat(),
            )
            for s in shares
        ]
    )


@router.delete(
    "/namespaces/{namespace_name}/shares/{share_id}",
    status_code=204,
    dependencies=[Depends(require_scope("write"))],
)
async def revoke_share(
    namespace_name: str,  # noqa: ARG001
    share_id: str,
    db: AsyncSession = Depends(get_db),
    account: Account = Depends(get_current_account),
) -> None:
    share_service = NamespaceShareService(db)

    try:
        await share_service.revoke(
            share_id=share_id,
            owner_user_id=account.user_id,
        )
        await db.commit()
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ForbiddenError as e:
        raise HTTPException(status_code=403, detail=str(e))


# --- User-scoped endpoints (invitations & shared-with-me) ---


@router.get(
    "/shares/invitations",
    response_model=ShareListResponse,
    dependencies=[Depends(require_scope("read"))],
)
async def list_invitations(
    db: AsyncSession = Depends(get_db),
    account: Account = Depends(get_current_account),
) -> ShareListResponse:
    share_service = NamespaceShareService(db)
    shares = await share_service.list_invitations(account.user_id)

    return ShareListResponse(
        shares=[
            ShareResponse(
                id=str(s.id),
                namespace_id=str(s.namespace_id),
                namespace_name=s.namespace.name if s.namespace else None,
                user_id=str(s.user_id),
                permissions=s.permissions,
                status=s.status,
                granted_by_user_id=str(s.granted_by_user_id) if s.granted_by_user_id else None,
                granted_by_name=s.granted_by.name if s.granted_by else None,
                accepted_at=s.accepted_at.isoformat() if s.accepted_at else None,
                revoked_at=s.revoked_at.isoformat() if s.revoked_at else None,
                created_at=s.created_at.isoformat(),
            )
            for s in shares
        ]
    )


@router.post(
    "/shares/invitations/{share_id}/accept",
    response_model=ShareResponse,
    dependencies=[Depends(require_scope("write"))],
)
async def accept_invitation(
    share_id: str,
    db: AsyncSession = Depends(get_db),
    account: Account = Depends(get_current_account),
) -> ShareResponse:
    share_service = NamespaceShareService(db)

    try:
        share = await share_service.accept(share_id=share_id, user_id=account.user_id)
        await db.commit()
        return ShareResponse(
            id=str(share.id),
            namespace_id=str(share.namespace_id),
            user_id=str(share.user_id),
            permissions=share.permissions,
            status=share.status,
            granted_by_user_id=str(share.granted_by_user_id) if share.granted_by_user_id else None,
            accepted_at=share.accepted_at.isoformat() if share.accepted_at else None,
            revoked_at=share.revoked_at.isoformat() if share.revoked_at else None,
            created_at=share.created_at.isoformat(),
        )
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ForbiddenError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post(
    "/shares/invitations/{share_id}/decline",
    response_model=ShareResponse,
    dependencies=[Depends(require_scope("write"))],
)
async def decline_invitation(
    share_id: str,
    db: AsyncSession = Depends(get_db),
    account: Account = Depends(get_current_account),
) -> ShareResponse:
    share_service = NamespaceShareService(db)

    try:
        share = await share_service.decline(share_id=share_id, user_id=account.user_id)
        await db.commit()
        return ShareResponse(
            id=str(share.id),
            namespace_id=str(share.namespace_id),
            user_id=str(share.user_id),
            permissions=share.permissions,
            status=share.status,
            granted_by_user_id=str(share.granted_by_user_id) if share.granted_by_user_id else None,
            accepted_at=share.accepted_at.isoformat() if share.accepted_at else None,
            revoked_at=share.revoked_at.isoformat() if share.revoked_at else None,
            created_at=share.created_at.isoformat(),
        )
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ForbiddenError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get(
    "/shares",
    response_model=ShareListResponse,
    dependencies=[Depends(require_scope("read"))],
)
async def list_shared_with_me(
    db: AsyncSession = Depends(get_db),
    account: Account = Depends(get_current_account),
) -> ShareListResponse:
    share_service = NamespaceShareService(db)
    shares = await share_service.list_shared_with_me(account.user_id)

    return ShareListResponse(
        shares=[
            ShareResponse(
                id=str(s.id),
                namespace_id=str(s.namespace_id),
                namespace_name=s.namespace.name if s.namespace else None,
                user_id=str(s.user_id),
                permissions=s.permissions,
                status=s.status,
                granted_by_user_id=str(s.granted_by_user_id) if s.granted_by_user_id else None,
                granted_by_name=s.granted_by.name if s.granted_by else None,
                accepted_at=s.accepted_at.isoformat() if s.accepted_at else None,
                revoked_at=s.revoked_at.isoformat() if s.revoked_at else None,
                created_at=s.created_at.isoformat(),
            )
            for s in shares
        ]
    )
