"""Namespace service - CRUD operations for namespaces."""

import builtins
import uuid
from datetime import UTC, datetime

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
        network_whitelist: list[str] | None = None,
    ) -> Namespace:
        """Create a new namespace.

        Args:
            account_id: The account that will own this namespace.
            name: Unique namespace name (DNS-compliant).
            description: Optional description.
            network_whitelist: Optional list of allowed IPs/CIDRs.

        Returns:
            The created namespace.

        Raises:
            ConflictError: If namespace name already exists.
            ValidationError: If name format is invalid.
        """
        # Check if namespace already exists
        existing = await self.db.execute(
            select(Namespace).where(Namespace.name == name.lower())
        )
        if existing.scalar_one_or_none():
            raise ConflictError(f"Namespace '{name}' already exists")

        # Create namespace
        namespace = Namespace(
            account_id=account_id,
            name=name.lower(),
            description=description,
            network_whitelist=network_whitelist,
        )
        self.db.add(namespace)
        await self.db.flush()
        await self.db.refresh(namespace)

        return namespace

    async def get_by_id(
        self,
        namespace_id: uuid.UUID,
        account_id: uuid.UUID | None = None,
    ) -> Namespace:
        """Get namespace by ID.

        Args:
            namespace_id: The namespace UUID.
            account_id: Optional account ID for access control.

        Returns:
            The namespace.

        Raises:
            NotFoundError: If namespace not found.
            ForbiddenError: If account doesn't own the namespace.
        """
        result = await self.db.execute(
            select(Namespace)
            .where(Namespace.id == namespace_id)
            .options(selectinload(Namespace.services))
        )
        namespace = result.scalar_one_or_none()

        if not namespace:
            raise NotFoundError(f"Namespace '{namespace_id}' not found")

        if account_id and namespace.account_id != account_id:
            raise ForbiddenError("Access denied to this namespace")

        return namespace

    async def get_by_name(
        self,
        name: str,
        account_id: uuid.UUID | None = None,
    ) -> Namespace:
        """Get namespace by name.

        Args:
            name: The namespace name.
            account_id: Optional account ID for access control.

        Returns:
            The namespace.

        Raises:
            NotFoundError: If namespace not found.
            ForbiddenError: If account doesn't own the namespace.
        """
        result = await self.db.execute(
            select(Namespace)
            .where(Namespace.name == name.lower())
            .options(selectinload(Namespace.services))
        )
        namespace = result.scalar_one_or_none()

        if not namespace:
            raise NotFoundError(f"Namespace '{name}' not found")

        if account_id and namespace.account_id != account_id:
            raise ForbiddenError("Access denied to this namespace")

        return namespace

    async def list(
        self,
        account_id: uuid.UUID,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[Namespace], int]:
        """List namespaces for an account.

        Args:
            account_id: The account ID.
            page: Page number (1-indexed).
            page_size: Number of items per page.

        Returns:
            Tuple of (namespaces list, total count).
        """
        # Get total count
        count_result = await self.db.execute(
            select(func.count())
            .select_from(Namespace)
            .where(Namespace.account_id == account_id)
        )
        total = count_result.scalar() or 0

        # Get paginated results
        offset = (page - 1) * page_size
        result = await self.db.execute(
            select(Namespace)
            .where(Namespace.account_id == account_id)
            .order_by(Namespace.name)
            .offset(offset)
            .limit(page_size)
        )
        namespaces = list(result.scalars().all())

        return namespaces, total

    async def update(
        self,
        namespace_id: uuid.UUID,
        account_id: uuid.UUID,
        description: str | None = None,
        network_whitelist: builtins.list[str] | None = None,
    ) -> Namespace:
        """Update a namespace.

        Args:
            namespace_id: The namespace UUID.
            account_id: The account ID for access control.
            description: New description (if provided).
            network_whitelist: New whitelist (if provided).

        Returns:
            The updated namespace.

        Raises:
            NotFoundError: If namespace not found.
            ForbiddenError: If account doesn't own the namespace.
            ValidationError: If whitelist update rate limit exceeded.
        """
        namespace = await self.get_by_id(namespace_id, account_id)

        if description is not None:
            namespace.description = description

        if network_whitelist is not None:
            # Check rate limit
            if not namespace.can_update_whitelist():
                raise ValidationError(
                    "Whitelist update rate limit exceeded (max 5 per 24 hours)"
                )
            namespace.network_whitelist = network_whitelist
            namespace.whitelist_updated_at = datetime.now(UTC)
            namespace.whitelist_changes_today += 1

        await self.db.flush()
        await self.db.refresh(namespace)

        return namespace

    async def delete(
        self,
        namespace_id: uuid.UUID,
        account_id: uuid.UUID,
    ) -> None:
        """Delete a namespace.

        This will cascade delete all services and functions within.

        Args:
            namespace_id: The namespace UUID.
            account_id: The account ID for access control.

        Raises:
            NotFoundError: If namespace not found.
            ForbiddenError: If account doesn't own the namespace.
        """
        namespace = await self.get_by_id(namespace_id, account_id)
        await self.db.delete(namespace)
        await self.db.flush()


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
            raise ConflictError(
                f"Service '{name}' already exists in this namespace"
            )

        service = NamespaceService(
            namespace_id=namespace_id,
            name=name.lower(),
            description=description,
        )
        self.db.add(service)
        await self.db.flush()
        await self.db.refresh(service)

        return service

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
