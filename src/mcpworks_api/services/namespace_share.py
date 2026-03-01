"""Namespace share service - invite/accept/decline/revoke sharing."""

import asyncio
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from mcpworks_api.core.exceptions import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from mcpworks_api.models.namespace import Namespace
from mcpworks_api.models.namespace_share import NamespaceShare, ShareStatus
from mcpworks_api.models.user import User

VALID_PERMISSIONS = frozenset({"read", "execute"})


class NamespaceShareService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def check_access(
        self,
        namespace_id: uuid.UUID,
        user_id: uuid.UUID,
        required_permission: str,
    ) -> NamespaceShare | None:
        result = await self.db.execute(
            select(NamespaceShare).where(
                NamespaceShare.namespace_id == namespace_id,
                NamespaceShare.user_id == user_id,
                NamespaceShare.status == ShareStatus.ACCEPTED.value,
            )
        )
        share = result.scalar_one_or_none()
        if share and required_permission in share.permissions:
            return share
        return None

    async def create_invite(
        self,
        namespace_id: uuid.UUID,
        invitee_email: str,
        permissions: list[str],
        granted_by_user_id: uuid.UUID,
    ) -> NamespaceShare:
        invalid = set(permissions) - VALID_PERMISSIONS
        if invalid:
            raise ValidationError(f"Invalid permissions: {', '.join(invalid)}")
        if not permissions:
            raise ValidationError("At least one permission required")

        ns_result = await self.db.execute(select(Namespace).where(Namespace.id == namespace_id))
        namespace = ns_result.scalar_one_or_none()
        if not namespace:
            raise NotFoundError("Namespace not found")

        owner_result = await self.db.execute(select(User).where(User.id == granted_by_user_id))
        owner = owner_result.scalar_one_or_none()
        if not owner:
            raise NotFoundError("Owner user not found")

        from mcpworks_api.models.account import Account

        account_result = await self.db.execute(
            select(Account).where(Account.id == namespace.account_id)
        )
        account = account_result.scalar_one_or_none()
        if not account or account.user_id != granted_by_user_id:
            raise ForbiddenError("Only the namespace owner can share it")

        invitee_result = await self.db.execute(
            select(User).where(User.email == invitee_email.lower())
        )
        invitee = invitee_result.scalar_one_or_none()
        if not invitee:
            raise NotFoundError(f"No user found with email '{invitee_email}'")

        if invitee.id == granted_by_user_id:
            raise ValidationError("Cannot share a namespace with yourself")

        existing_result = await self.db.execute(
            select(NamespaceShare).where(
                NamespaceShare.namespace_id == namespace_id,
                NamespaceShare.user_id == invitee.id,
            )
        )
        existing = existing_result.scalar_one_or_none()

        if existing:
            if existing.status in (ShareStatus.PENDING.value, ShareStatus.ACCEPTED.value):
                raise ConflictError("This user already has a pending or active share")
            existing.status = ShareStatus.PENDING.value
            existing.permissions = permissions
            existing.granted_by_user_id = granted_by_user_id
            existing.accepted_at = None
            existing.revoked_at = None
            await self.db.flush()
            await self.db.refresh(existing)
            self._send_invite_email(invitee.email, invitee.name, namespace.name, owner.name)
            return existing

        share = NamespaceShare(
            namespace_id=namespace_id,
            user_id=invitee.id,
            granted_by_user_id=granted_by_user_id,
            permissions=permissions,
            status=ShareStatus.PENDING.value,
        )
        self.db.add(share)
        await self.db.flush()
        await self.db.refresh(share)

        self._send_invite_email(invitee.email, invitee.name, namespace.name, owner.name)
        return share

    async def accept(self, share_id: uuid.UUID, user_id: uuid.UUID) -> NamespaceShare:
        share = await self._get_share(share_id)
        if share.user_id != user_id:
            raise ForbiddenError("You can only accept invitations sent to you")
        if share.status != ShareStatus.PENDING.value:
            raise ValidationError(f"Cannot accept a share with status '{share.status}'")

        share.status = ShareStatus.ACCEPTED.value
        share.accepted_at = datetime.now(UTC)
        await self.db.flush()
        await self.db.refresh(share)
        return share

    async def decline(self, share_id: uuid.UUID, user_id: uuid.UUID) -> NamespaceShare:
        share = await self._get_share(share_id)
        if share.user_id != user_id:
            raise ForbiddenError("You can only decline invitations sent to you")
        if share.status != ShareStatus.PENDING.value:
            raise ValidationError(f"Cannot decline a share with status '{share.status}'")

        share.status = ShareStatus.DECLINED.value
        await self.db.flush()
        await self.db.refresh(share)
        return share

    async def revoke(self, share_id: uuid.UUID, owner_user_id: uuid.UUID) -> NamespaceShare:
        share = await self._get_share(share_id)

        ns_result = await self.db.execute(
            select(Namespace).where(Namespace.id == share.namespace_id)
        )
        namespace = ns_result.scalar_one_or_none()
        if not namespace:
            raise NotFoundError("Namespace not found")

        from mcpworks_api.models.account import Account

        account_result = await self.db.execute(
            select(Account).where(Account.id == namespace.account_id)
        )
        account = account_result.scalar_one_or_none()
        if not account or account.user_id != owner_user_id:
            raise ForbiddenError("Only the namespace owner can revoke shares")

        share.status = ShareStatus.REVOKED.value
        share.revoked_at = datetime.now(UTC)
        await self.db.flush()
        await self.db.refresh(share)
        return share

    async def list_for_namespace(
        self,
        namespace_id: uuid.UUID,
    ) -> list[NamespaceShare]:
        result = await self.db.execute(
            select(NamespaceShare)
            .where(NamespaceShare.namespace_id == namespace_id)
            .options(selectinload(NamespaceShare.user))
            .order_by(NamespaceShare.created_at.desc())
        )
        return list(result.scalars().all())

    async def list_invitations(self, user_id: uuid.UUID) -> list[NamespaceShare]:
        result = await self.db.execute(
            select(NamespaceShare)
            .where(
                NamespaceShare.user_id == user_id,
                NamespaceShare.status == ShareStatus.PENDING.value,
            )
            .options(
                selectinload(NamespaceShare.namespace),
                selectinload(NamespaceShare.granted_by),
            )
            .order_by(NamespaceShare.created_at.desc())
        )
        return list(result.scalars().all())

    async def list_shared_with_me(self, user_id: uuid.UUID) -> list[NamespaceShare]:
        result = await self.db.execute(
            select(NamespaceShare)
            .where(
                NamespaceShare.user_id == user_id,
                NamespaceShare.status == ShareStatus.ACCEPTED.value,
            )
            .options(
                selectinload(NamespaceShare.namespace),
                selectinload(NamespaceShare.granted_by),
            )
            .order_by(NamespaceShare.created_at.desc())
        )
        return list(result.scalars().all())

    async def _get_share(self, share_id: uuid.UUID) -> NamespaceShare:
        result = await self.db.execute(select(NamespaceShare).where(NamespaceShare.id == share_id))
        share = result.scalar_one_or_none()
        if not share:
            raise NotFoundError("Share not found")
        return share

    @staticmethod
    def _send_invite_email(
        email: str,
        name: str | None,
        namespace_name: str,
        owner_name: str | None,
    ) -> None:
        from mcpworks_api.services.email import send_email

        subject = f"You've been invited to namespace '{namespace_name}' on mcpworks"
        asyncio.create_task(
            send_email(
                to=email,
                email_type="namespace_invite",
                subject=subject,
                template_name="namespace_invite",
                template_vars={
                    "name": name or email,
                    "namespace_name": namespace_name,
                    "owner_name": owner_name or "a mcpworks user",
                },
            )
        )
