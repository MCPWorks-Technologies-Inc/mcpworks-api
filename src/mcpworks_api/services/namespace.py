"""Namespace service - CRUD operations for namespaces."""

import builtins
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from mcpworks_api.core.exceptions import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from mcpworks_api.models import Namespace, NamespaceService
from mcpworks_api.models.namespace_share import NamespaceShare, ShareStatus


class NamespaceServiceManager:
    """Service for namespace management operations.

    Provides CRUD operations for namespaces with account isolation.
    All namespaces are scoped to an account for multi-tenancy.
    """

    def __init__(self, db: AsyncSession) -> None:
        """Initialize namespace service with database session."""
        self.db = db

    async def create(
        self,
        account_id: uuid.UUID,
        name: str,
        description: str | None = None,
        network_allowlist: list[str] | None = None,
    ) -> Namespace:
        """Create a new namespace.

        Args:
            account_id: The account that will own this namespace.
            name: Unique namespace name (DNS-compliant).
            description: Optional description.
            network_allowlist: Optional list of allowed IPs/CIDRs.

        Returns:
            The created namespace.

        Raises:
            ConflictError: If namespace name already exists.
            ValidationError: If name format is invalid.
        """
        existing = await self.db.execute(select(Namespace).where(Namespace.name == name.lower()))
        found = existing.scalar_one_or_none()
        if found:
            if found.deleted_at is not None:
                recovery_until = found.deleted_at + timedelta(days=30)
                raise ConflictError(
                    f"Namespace '{name}' was deleted and is in a 30-day recovery period "
                    f"until {recovery_until.strftime('%Y-%m-%d')}. "
                    f"Contact support to restore or wait for the recovery period to expire."
                )
            raise ConflictError(f"Namespace '{name}' already exists")

        # Create namespace
        namespace = Namespace(
            account_id=account_id,
            name=name.lower(),
            description=description,
            network_allowlist=network_allowlist,
        )
        self.db.add(namespace)
        await self.db.flush()
        await self.db.refresh(namespace)

        return namespace

    async def get_by_id(
        self,
        namespace_id: uuid.UUID,
        account_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
        required_permission: str | None = None,
    ) -> Namespace:
        """Get namespace by ID.

        Args:
            namespace_id: The namespace UUID.
            account_id: Optional account ID for access control.
            user_id: Optional user ID for share-based access check.
            required_permission: Permission needed (e.g. "read", "execute").

        Returns:
            The namespace.

        Raises:
            NotFoundError: If namespace not found.
            ForbiddenError: If account doesn't own the namespace and no share access.
        """
        result = await self.db.execute(
            select(Namespace)
            .where(Namespace.id == namespace_id, Namespace.deleted_at.is_(None))
            .options(selectinload(Namespace.services))
        )
        namespace = result.scalar_one_or_none()

        if not namespace:
            raise NotFoundError(f"Namespace '{namespace_id}' not found")

        if account_id and namespace.account_id != account_id:
            if (
                user_id
                and required_permission
                and await self._check_share_access(namespace.id, user_id, required_permission)
            ):
                return namespace
            raise ForbiddenError("Access denied to this namespace")

        return namespace

    async def get_by_name(
        self,
        name: str,
        account_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
        required_permission: str | None = None,
    ) -> Namespace:
        """Get namespace by name.

        Args:
            name: The namespace name.
            account_id: Optional account ID for access control.
            user_id: Optional user ID for share-based access check.
            required_permission: Permission needed (e.g. "read", "execute").

        Returns:
            The namespace.

        Raises:
            NotFoundError: If namespace not found.
            ForbiddenError: If account doesn't own the namespace and no share access.
        """
        result = await self.db.execute(
            select(Namespace)
            .where(Namespace.name == name.lower(), Namespace.deleted_at.is_(None))
            .options(selectinload(Namespace.services))
        )
        namespace = result.scalar_one_or_none()

        if not namespace:
            raise NotFoundError(f"Namespace '{name}' not found")

        if account_id and namespace.account_id != account_id:
            if (
                user_id
                and required_permission
                and await self._check_share_access(namespace.id, user_id, required_permission)
            ):
                return namespace
            raise ForbiddenError("Access denied to this namespace")

        return namespace

    async def list(
        self,
        account_id: uuid.UUID,
        user_id: uuid.UUID | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[Namespace], int]:
        """List namespaces for an account, plus shared namespaces.

        Args:
            account_id: The account ID.
            user_id: Optional user ID to also include shared namespaces.
            page: Page number (1-indexed).
            page_size: Number of items per page.

        Returns:
            Tuple of (namespaces list, total count).
        """
        count_result = await self.db.execute(
            select(func.count())
            .select_from(Namespace)
            .where(Namespace.account_id == account_id, Namespace.deleted_at.is_(None))
        )
        owned_total = count_result.scalar() or 0

        offset = (page - 1) * page_size
        result = await self.db.execute(
            select(Namespace)
            .where(Namespace.account_id == account_id, Namespace.deleted_at.is_(None))
            .order_by(Namespace.name)
            .offset(offset)
            .limit(page_size)
        )
        namespaces = list(result.scalars().all())

        # Also fetch shared namespaces if user_id provided
        shared_total = 0
        if user_id:
            shared_count_result = await self.db.execute(
                select(func.count())
                .select_from(NamespaceShare)
                .join(Namespace, NamespaceShare.namespace_id == Namespace.id)
                .where(
                    NamespaceShare.user_id == user_id,
                    NamespaceShare.status == ShareStatus.ACCEPTED.value,
                    Namespace.deleted_at.is_(None),
                )
            )
            shared_total = shared_count_result.scalar() or 0

            if shared_total > 0:
                shared_result = await self.db.execute(
                    select(Namespace)
                    .join(NamespaceShare, NamespaceShare.namespace_id == Namespace.id)
                    .where(
                        NamespaceShare.user_id == user_id,
                        NamespaceShare.status == ShareStatus.ACCEPTED.value,
                        Namespace.deleted_at.is_(None),
                    )
                    .order_by(Namespace.name)
                )
                shared_namespaces = list(shared_result.scalars().all())
                for ns in shared_namespaces:
                    ns._is_shared = True  # type: ignore[attr-defined]
                namespaces.extend(shared_namespaces)

        return namespaces, owned_total + shared_total

    async def _check_share_access(
        self,
        namespace_id: uuid.UUID,
        user_id: uuid.UUID,
        permission: str,
    ) -> bool:
        result = await self.db.execute(
            select(NamespaceShare).where(
                NamespaceShare.namespace_id == namespace_id,
                NamespaceShare.user_id == user_id,
                NamespaceShare.status == ShareStatus.ACCEPTED.value,
            )
        )
        share = result.scalar_one_or_none()
        return share is not None and permission in share.permissions

    async def update(
        self,
        namespace_id: uuid.UUID,
        account_id: uuid.UUID,
        description: str | None = None,
        network_allowlist: builtins.list[str] | None = None,
    ) -> Namespace:
        """Update a namespace.

        Args:
            namespace_id: The namespace UUID.
            account_id: The account ID for access control.
            description: New description (if provided).
            network_allowlist: New allowlist (if provided).

        Returns:
            The updated namespace.

        Raises:
            NotFoundError: If namespace not found.
            ForbiddenError: If account doesn't own the namespace.
            ValidationError: If allowlist update rate limit exceeded.
        """
        namespace = await self.get_by_id(namespace_id, account_id)

        if description is not None:
            namespace.description = description

        if network_allowlist is not None:
            if not namespace.can_update_allowlist():
                raise ValidationError("Allowlist update rate limit exceeded (max 5 per 24 hours)")
            namespace.network_allowlist = network_allowlist
            namespace.allowlist_updated_at = datetime.now(UTC)
            namespace.allowlist_changes_today += 1

        await self.db.flush()
        await self.db.refresh(namespace)

        return namespace

    async def delete(
        self,
        namespace_id: uuid.UUID,
        account_id: uuid.UUID,
    ) -> "Namespace":
        """Soft-delete a namespace.

        Sets deleted_at timestamp. Children (services, functions, API keys)
        remain in the database but become inaccessible because all queries
        filter on Namespace.deleted_at IS NULL.

        Recoverable for 30 days after deletion.

        Args:
            namespace_id: The namespace UUID.
            account_id: The account ID for access control.

        Returns:
            The soft-deleted namespace.

        Raises:
            NotFoundError: If namespace not found.
            ForbiddenError: If account doesn't own the namespace.
        """
        namespace = await self.get_by_id(namespace_id, account_id)
        namespace.deleted_at = datetime.now(UTC)
        await self.db.flush()
        return namespace


class NamespaceServiceService:
    """Service for namespace service (function grouping) management.

    Provides CRUD operations for services within namespaces.
    """

    def __init__(self, db: AsyncSession) -> None:
        """Initialize service with database session."""
        self.db = db

    async def create(
        self,
        namespace_id: uuid.UUID,
        name: str,
        description: str | None = None,
    ) -> NamespaceService:
        """Create a new service within a namespace.

        Args:
            namespace_id: The namespace that will contain this service.
            name: Service name (unique within namespace).
            description: Optional description.

        Returns:
            The created service.

        Raises:
            ConflictError: If service name already exists in namespace.
        """
        # Check if service already exists in this namespace
        existing = await self.db.execute(
            select(NamespaceService).where(
                NamespaceService.namespace_id == namespace_id,
                NamespaceService.name == name.lower(),
            )
        )
        if existing.scalar_one_or_none():
            raise ConflictError(f"Service '{name}' already exists in this namespace")

        service = NamespaceService(
            namespace_id=namespace_id,
            name=name.lower(),
            description=description,
        )
        self.db.add(service)
        await self.db.flush()

        # Re-fetch with functions relationship loaded to avoid lazy loading issues
        result = await self.db.execute(
            select(NamespaceService)
            .where(NamespaceService.id == service.id)
            .options(selectinload(NamespaceService.functions))
        )
        return result.scalar_one()

    async def get_by_id(
        self,
        service_id: uuid.UUID,
    ) -> NamespaceService:
        """Get service by ID.

        Args:
            service_id: The service UUID.

        Returns:
            The service.

        Raises:
            NotFoundError: If service not found.
        """
        result = await self.db.execute(
            select(NamespaceService)
            .where(NamespaceService.id == service_id)
            .options(selectinload(NamespaceService.functions))
        )
        service = result.scalar_one_or_none()

        if not service:
            raise NotFoundError(f"Service '{service_id}' not found")

        return service

    async def get_by_name(
        self,
        namespace_id: uuid.UUID,
        name: str,
    ) -> NamespaceService:
        """Get service by name within a namespace.

        Args:
            namespace_id: The namespace UUID.
            name: The service name.

        Returns:
            The service.

        Raises:
            NotFoundError: If service not found.
        """
        result = await self.db.execute(
            select(NamespaceService)
            .where(
                NamespaceService.namespace_id == namespace_id,
                NamespaceService.name == name.lower(),
            )
            .options(selectinload(NamespaceService.functions))
        )
        service = result.scalar_one_or_none()

        if not service:
            raise NotFoundError(f"Service '{name}' not found in namespace")

        return service

    async def list(
        self,
        namespace_id: uuid.UUID,
    ) -> list[NamespaceService]:
        """List all services in a namespace.

        Args:
            namespace_id: The namespace UUID.

        Returns:
            List of services.
        """
        result = await self.db.execute(
            select(NamespaceService)
            .where(NamespaceService.namespace_id == namespace_id)
            .options(selectinload(NamespaceService.functions))
            .order_by(NamespaceService.name)
        )
        return list(result.scalars().all())

    async def update(
        self,
        service_id: uuid.UUID,
        description: str | None = None,
    ) -> NamespaceService:
        """Update a service.

        Args:
            service_id: The service UUID.
            description: New description (if provided).

        Returns:
            The updated service.

        Raises:
            NotFoundError: If service not found.
        """
        service = await self.get_by_id(service_id)

        if description is not None:
            service.description = description

        await self.db.flush()
        await self.db.refresh(service)

        return service

    async def delete(
        self,
        service_id: uuid.UUID,
    ) -> None:
        """Delete a service.

        This will cascade delete all functions within.

        Args:
            service_id: The service UUID.

        Raises:
            NotFoundError: If service not found.
        """
        service = await self.get_by_id(service_id)
        await self.db.delete(service)
        await self.db.flush()
