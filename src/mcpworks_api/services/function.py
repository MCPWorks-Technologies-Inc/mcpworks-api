"""Function service - CRUD operations for functions and versions."""

import builtins
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from mcpworks_api.core.exceptions import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
)
from mcpworks_api.models import Function, FunctionVersion


class FunctionService:
    """Service for function management operations.

    Provides CRUD operations for functions with immutable versioning.
    Functions are organized within services within namespaces.
    """

    def __init__(self, db: AsyncSession) -> None:
        """Initialize function service with database session."""
        self.db = db

    async def create(
        self,
        service_id: uuid.UUID,
        name: str,
        backend: str,
        description: str | None = None,
        tags: list[str] | None = None,
        code: str | None = None,
        config: dict[str, Any] | None = None,
        input_schema: dict[str, Any] | None = None,
        output_schema: dict[str, Any] | None = None,
        requirements: list[str] | None = None,
        required_env: list[str] | None = None,
        optional_env: list[str] | None = None,
        created_by: str | None = None,
        language: str = "python",
        public_safe: bool = False,
        output_trust: str = "prompt",
    ) -> Function:
        """Create a new function with initial version.

        Args:
            service_id: The service that will contain this function.
            name: Function name (unique within service).
            backend: Backend type (code_sandbox, nanobot, github_repo).
            description: Optional description.
            tags: Optional tags for categorization.
            code: Optional code (for code_sandbox backend).
            config: Optional backend-specific configuration.
            input_schema: Optional JSON Schema for input validation.
            output_schema: Optional JSON Schema for output validation.
            requirements: Optional list of allowed Python packages.

        Returns:
            The created function with initial version.

        Raises:
            ConflictError: If function name already exists in service.
            ValidationError: If backend is not supported.
        """
        existing_result = await self.db.execute(
            select(Function)
            .where(
                Function.service_id == service_id,
                Function.name == name.lower(),
            )
            .options(selectinload(Function.versions))
        )
        existing = existing_result.scalar_one_or_none()

        if existing and existing.deleted_at is None:
            raise ConflictError(f"Function '{name}' already exists in this service")

        if existing and existing.deleted_at is not None:
            function = existing
            function.description = description
            function.tags = tags
            function.output_trust = output_trust
            function.deleted_at = None
            function.locked = False
            function.locked_by = None
            function.locked_at = None

            next_version = max((v.version for v in function.versions), default=0) + 1
            version = FunctionVersion(
                function_id=function.id,
                version=next_version,
                backend=backend,
                language=language,
                code=code,
                config=config,
                input_schema=input_schema,
                output_schema=output_schema,
                requirements=requirements,
                required_env=required_env,
                optional_env=optional_env,
                created_by=created_by,
            )
            self.db.add(version)
            function.active_version = next_version
            await self.db.flush()
            await self.db.refresh(function, ["versions"])
            return function

        function = Function(
            service_id=service_id,
            name=name.lower(),
            description=description,
            tags=tags,
            output_trust=output_trust,
            active_version=1,
            public_safe=public_safe,
        )
        self.db.add(function)
        await self.db.flush()

        version = FunctionVersion(
            function_id=function.id,
            version=1,
            backend=backend,
            language=language,
            code=code,
            config=config,
            input_schema=input_schema,
            output_schema=output_schema,
            requirements=requirements,
            required_env=required_env,
            optional_env=optional_env,
            created_by=created_by,
        )
        self.db.add(version)
        await self.db.flush()

        await self.db.refresh(function, ["versions"])

        return function

    async def get_by_id(
        self,
        function_id: uuid.UUID,
    ) -> Function:
        """Get function by ID.

        Args:
            function_id: The function UUID.

        Returns:
            The function with versions loaded.

        Raises:
            NotFoundError: If function not found.
        """
        result = await self.db.execute(
            select(Function)
            .where(Function.id == function_id, Function.deleted_at.is_(None))
            .options(selectinload(Function.versions))
        )
        function = result.scalar_one_or_none()

        if not function:
            raise NotFoundError(f"Function '{function_id}' not found")

        return function

    async def get_by_name(
        self,
        service_id: uuid.UUID,
        name: str,
    ) -> Function:
        """Get function by name within a service.

        Args:
            service_id: The service UUID.
            name: The function name.

        Returns:
            The function with versions loaded.

        Raises:
            NotFoundError: If function not found.
        """
        result = await self.db.execute(
            select(Function)
            .where(
                Function.service_id == service_id,
                Function.name == name.lower(),
                Function.deleted_at.is_(None),
            )
            .options(selectinload(Function.versions))
        )
        function = result.scalar_one_or_none()

        if not function:
            raise NotFoundError(f"Function '{name}' not found in service")

        return function

    async def list(
        self,
        service_id: uuid.UUID,
        page: int = 1,
        page_size: int = 50,
        tags: list[str] | None = None,
    ) -> tuple[list[Function], int]:
        """List functions in a service.

        Args:
            service_id: The service UUID.
            page: Page number (1-indexed).
            page_size: Number of items per page.
            tags: Optional filter by tags (any match).

        Returns:
            Tuple of (functions list, total count).
        """
        query = select(Function).where(
            Function.service_id == service_id,
            Function.deleted_at.is_(None),
        )

        if tags:
            # Filter by tags using array overlap
            query = query.where(Function.tags.overlap(tags))

        # Get total count
        count_result = await self.db.execute(select(func.count()).select_from(query.subquery()))
        total = count_result.scalar() or 0

        # Get paginated results
        offset = (page - 1) * page_size
        result = await self.db.execute(
            query.order_by(Function.name).offset(offset).limit(page_size)
        )
        functions = list(result.scalars().all())

        return functions, total

    async def update(
        self,
        function_id: uuid.UUID,
        description: str | None = None,
        tags: builtins.list[str] | None = None,
        public_safe: bool | None = None,
        output_trust: str | None = None,
    ) -> Function:
        """Update function metadata (not code/version).

        For code changes, use create_version().
        """
        function = await self.get_by_id(function_id)

        if description is not None:
            function.description = description

        if tags is not None:
            function.tags = tags

        if public_safe is not None:
            function.public_safe = public_safe

        if output_trust is not None:
            function.output_trust = output_trust

        await self.db.flush()
        await self.db.refresh(function)

        return function

    async def create_version(
        self,
        function_id: uuid.UUID,
        backend: str,
        code: str | None = None,
        config: dict[str, Any] | None = None,
        input_schema: dict[str, Any] | None = None,
        output_schema: dict[str, Any] | None = None,
        requirements: builtins.list[str] | None = None,
        required_env: builtins.list[str] | None = None,
        optional_env: builtins.list[str] | None = None,
        created_by: str | None = None,
        activate: bool = True,
        is_admin: bool = False,
        language: str | None = None,
    ) -> FunctionVersion:
        """Create a new version of a function.

        Function versions are immutable once created.

        Args:
            function_id: The function UUID.
            backend: Backend type.
            code: Optional code (for code_sandbox backend).
            config: Optional backend-specific configuration.
            input_schema: Optional JSON Schema for input validation.
            output_schema: Optional JSON Schema for output validation.
            requirements: Optional list of allowed packages.
            activate: Whether to set this as the active version.
            language: Programming language. If None, inherits from the
                latest existing version. Cannot differ from existing
                versions (language is immutable per function).

        Returns:
            The created version.

        Raises:
            NotFoundError: If function not found.
            ValueError: If language differs from existing versions.
        """
        function = await self.get_by_id(function_id)

        if function.locked and not is_admin:
            raise ForbiddenError(f"Function '{function.name}' is locked and cannot be modified")

        # Language immutability: inherit from existing versions or validate match
        if function.versions:
            existing_language = function.versions[0].language
            if language is None:
                language = existing_language
            elif language != existing_language:
                raise ValueError(
                    f"Cannot change function language from '{existing_language}' to '{language}'. "
                    "Create a new function for a different language."
                )
        elif language is None:
            language = "python"

        # Determine next version number
        next_version = 1
        if function.versions:
            next_version = max(v.version for v in function.versions) + 1

        # Create new version
        version = FunctionVersion(
            function_id=function_id,
            version=next_version,
            backend=backend,
            language=language,
            code=code,
            config=config,
            input_schema=input_schema,
            output_schema=output_schema,
            requirements=requirements,
            required_env=required_env,
            optional_env=optional_env,
            created_by=created_by,
        )
        self.db.add(version)

        if activate:
            function.active_version = next_version

        await self.db.flush()
        await self.db.refresh(version)

        return version

    async def get_version(
        self,
        function_id: uuid.UUID,
        version: int,
    ) -> FunctionVersion:
        """Get a specific version of a function.

        Args:
            function_id: The function UUID.
            version: The version number.

        Returns:
            The function version.

        Raises:
            NotFoundError: If version not found.
        """
        result = await self.db.execute(
            select(FunctionVersion).where(
                FunctionVersion.function_id == function_id,
                FunctionVersion.version == version,
            )
        )
        func_version = result.scalar_one_or_none()

        if not func_version:
            raise NotFoundError(f"Version {version} not found for function '{function_id}'")

        return func_version

    async def get_active_version(
        self,
        function_id: uuid.UUID,
    ) -> FunctionVersion:
        """Get the active version of a function.

        Args:
            function_id: The function UUID.

        Returns:
            The active function version.

        Raises:
            NotFoundError: If function or active version not found.
        """
        function = await self.get_by_id(function_id)
        return await self.get_version(function_id, function.active_version)

    async def set_active_version(
        self,
        function_id: uuid.UUID,
        version: int,
    ) -> Function:
        """Set the active version of a function.

        Args:
            function_id: The function UUID.
            version: The version number to activate.

        Returns:
            The updated function.

        Raises:
            NotFoundError: If function or version not found.
        """
        function = await self.get_by_id(function_id)

        # Verify version exists
        await self.get_version(function_id, version)

        function.active_version = version
        await self.db.flush()
        await self.db.refresh(function)

        return function

    async def delete(
        self,
        function_id: uuid.UUID,
        is_admin: bool = False,
    ) -> None:
        """Soft-delete a function. Versions are preserved so re-creation
        with the same name continues the version history.

        Args:
            function_id: The function UUID.
            is_admin: Whether caller has admin privileges (bypasses lock check).

        Raises:
            NotFoundError: If function not found.
            ForbiddenError: If function is locked.
        """
        function = await self.get_by_id(function_id)
        if function.locked and not is_admin:
            raise ForbiddenError(f"Function '{function.name}' is locked and cannot be deleted")
        function.deleted_at = datetime.now(tz=UTC)
        await self.db.flush()

    async def lock_function(
        self,
        function_id: uuid.UUID,
        locked_by: uuid.UUID,
    ) -> Function:
        """Lock a function to prevent modification.

        Args:
            function_id: The function UUID.
            locked_by: The user UUID locking the function.

        Returns:
            The updated function.

        Raises:
            NotFoundError: If function not found.
        """
        function = await self.get_by_id(function_id)
        function.locked = True
        function.locked_by = locked_by
        function.locked_at = datetime.now(tz=UTC)
        await self.db.flush()
        await self.db.refresh(function)
        return function

    async def unlock_function(
        self,
        function_id: uuid.UUID,
    ) -> Function:
        """Unlock a function to allow modification.

        Args:
            function_id: The function UUID.

        Returns:
            The updated function.

        Raises:
            NotFoundError: If function not found.
        """
        function = await self.get_by_id(function_id)
        function.locked = False
        function.locked_by = None
        function.locked_at = None
        await self.db.flush()
        await self.db.refresh(function)
        return function

    async def list_all_for_namespace(
        self,
        namespace_id: uuid.UUID,
    ) -> builtins.list[tuple["Function", "FunctionVersion"]]:
        """List all functions in a namespace with their active versions.

        Used by run handler to generate dynamic tools list.

        Args:
            namespace_id: The namespace UUID.

        Returns:
            List of tuples (Function, FunctionVersion) for all functions.
        """
        from mcpworks_api.models import NamespaceService

        # Get all functions across all services in the namespace
        result = await self.db.execute(
            select(Function)
            .join(NamespaceService, Function.service_id == NamespaceService.id)
            .where(
                NamespaceService.namespace_id == namespace_id,
                Function.deleted_at.is_(None),
            )
            .options(
                selectinload(Function.versions),
                selectinload(Function.service),
            )
        )
        functions = result.scalars().all()

        # Pair each function with its active version
        pairs = []
        for fn in functions:
            active_version = fn.get_active_version_obj()
            if active_version:
                pairs.append((fn, active_version))

        return pairs

    async def get_for_execution(
        self,
        namespace_id: uuid.UUID,
        service_name: str,
        function_name: str,
    ) -> tuple["Function", "FunctionVersion"]:
        """Get function and its active version for execution.

        Args:
            namespace_id: The namespace UUID.
            service_name: The service name.
            function_name: The function name.

        Returns:
            Tuple of (Function, active FunctionVersion).

        Raises:
            NotFoundError: If function not found or has no active version.
        """
        from mcpworks_api.models import NamespaceService

        # Get function with service join
        result = await self.db.execute(
            select(Function)
            .join(NamespaceService, Function.service_id == NamespaceService.id)
            .where(
                NamespaceService.namespace_id == namespace_id,
                NamespaceService.name == service_name.lower(),
                Function.name == function_name.lower(),
                Function.deleted_at.is_(None),
            )
            .options(
                selectinload(Function.versions),
                selectinload(Function.service),
            )
        )
        function = result.scalar_one_or_none()

        if not function:
            raise NotFoundError(f"Function '{service_name}.{function_name}' not found")

        active_version = function.get_active_version_obj()
        if not active_version:
            raise NotFoundError(f"Function '{service_name}.{function_name}' has no active version")

        return function, active_version

    async def describe(
        self,
        function_id: uuid.UUID,
    ) -> dict[str, Any]:
        """Get detailed description of a function.

        Includes function metadata, all versions, and active version details.

        Args:
            function_id: The function UUID.

        Returns:
            Dictionary with function details.

        Raises:
            NotFoundError: If function not found.
        """
        function = await self.get_by_id(function_id)
        active_version = function.get_active_version_obj()

        return {
            "id": str(function.id),
            "name": function.name,
            "description": function.description,
            "tags": function.tags or [],
            "public_safe": function.public_safe,
            "call_count": function.call_count,
            "active_version": function.active_version,
            "active_version_details": {
                "id": str(active_version.id) if active_version else None,
                "version": active_version.version if active_version else None,
                "backend": active_version.backend if active_version else None,
                "language": active_version.language if active_version else None,
                "code": active_version.code if active_version else None,
                "config": active_version.config if active_version else None,
                "input_schema": active_version.input_schema if active_version else None,
                "output_schema": active_version.output_schema if active_version else None,
                "requirements": active_version.requirements if active_version else None,
                "required_env": active_version.required_env if active_version else None,
                "optional_env": active_version.optional_env if active_version else None,
                "created_by": active_version.created_by if active_version else None,
                "created_at": active_version.created_at.isoformat() if active_version else None,
            }
            if active_version
            else None,
            "versions": [
                {
                    "version": v.version,
                    "backend": v.backend,
                    "language": v.language,
                    "created_by": v.created_by,
                    "created_at": v.created_at.isoformat(),
                }
                for v in sorted(function.versions, key=lambda x: x.version, reverse=True)
            ],
            "created_at": function.created_at.isoformat(),
            "updated_at": function.updated_at.isoformat() if function.updated_at else None,
        }

    async def get_version_detail(
        self,
        function_id: uuid.UUID,
        version_number: int,
    ) -> dict[str, Any]:
        """Get full detail for a specific version of a function.

        Args:
            function_id: The function UUID.
            version_number: The version number.

        Returns:
            Dictionary with version details including code, config, schemas,
            requirements, env vars, and is_active flag.

        Raises:
            NotFoundError: If function or version not found.
        """
        function = await self.get_by_id(function_id)
        version = await self.get_version(function_id, version_number)

        return {
            "id": str(version.id),
            "version": version.version,
            "backend": version.backend,
            "language": version.language,
            "code": version.code,
            "config": version.config,
            "input_schema": version.input_schema,
            "output_schema": version.output_schema,
            "requirements": version.requirements,
            "required_env": version.required_env,
            "optional_env": version.optional_env,
            "created_by": version.created_by,
            "is_active": version.version == function.active_version,
            "created_at": version.created_at.isoformat(),
        }
