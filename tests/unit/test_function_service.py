"""Unit tests for FunctionService."""

import uuid

import pytest

from mcpworks_api.core.exceptions import ConflictError, NotFoundError
from mcpworks_api.models import Account, Function, Namespace, NamespaceService, User
from mcpworks_api.services.function import FunctionService


@pytest.fixture
async def test_user(db):
    """Create a test user."""
    user = User(
        email=f"test-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="hashed_password",
        name="Test User",
        tier="free",
        status="active",
    )
    db.add(user)
    await db.flush()
    return user


@pytest.fixture
async def test_account(db, test_user):
    """Create a test account."""
    account = Account(
        user_id=test_user.id,
        name="Test Account",
    )
    db.add(account)
    await db.flush()
    return account


@pytest.fixture
async def test_namespace(db, test_account):
    """Create a test namespace."""
    namespace = Namespace(
        name=f"test-ns-{uuid.uuid4().hex[:8]}",
        account_id=test_account.id,
    )
    db.add(namespace)
    await db.flush()
    return namespace


@pytest.fixture
async def test_service(db, test_namespace):
    """Create a test service within the namespace."""
    service = NamespaceService(
        namespace_id=test_namespace.id,
        name="test-service",
        description="Test service for function tests",
    )
    db.add(service)
    await db.flush()
    return service


@pytest.fixture
async def test_function(db, test_service):
    """Create a test function with initial version."""
    function_service = FunctionService(db)
    return await function_service.create(
        service_id=test_service.id,
        name="test-function",
        backend="code_sandbox",
        description="Test function",
        tags=["test", "example"],
        code="result = 42",
        input_schema={"type": "object"},
        output_schema={"type": "integer"},
    )


class TestFunctionServiceCreate:
    """Tests for FunctionService.create()."""

    @pytest.mark.asyncio
    async def test_create_function_basic(self, db, test_service):
        """Test creating a basic function."""
        service = FunctionService(db)

        function = await service.create(
            service_id=test_service.id,
            name="my-function",
            backend="code_sandbox",
        )

        assert function.name == "my-function"
        assert function.service_id == test_service.id
        assert function.active_version == 1
        assert len(function.versions) == 1

    @pytest.mark.asyncio
    async def test_create_function_with_all_fields(self, db, test_service):
        """Test creating a function with all optional fields."""
        service = FunctionService(db)

        function = await service.create(
            service_id=test_service.id,
            name="full-function",
            backend="code_sandbox",
            description="A complete function",
            tags=["auth", "security"],
            code="result = input_data['x'] * 2",
            config={"timeout": 30},
            input_schema={"type": "object", "properties": {"x": {"type": "integer"}}},
            output_schema={"type": "integer"},
        )

        assert function.name == "full-function"
        assert function.description == "A complete function"
        assert function.tags == ["auth", "security"]

        version = function.versions[0]
        assert version.backend == "code_sandbox"
        assert version.code == "result = input_data['x'] * 2"
        assert version.config == {"timeout": 30}
        assert version.input_schema == {
            "type": "object",
            "properties": {"x": {"type": "integer"}},
        }

    @pytest.mark.asyncio
    async def test_create_function_name_normalized(self, db, test_service):
        """Test function name is normalized to lowercase."""
        service = FunctionService(db)

        function = await service.create(
            service_id=test_service.id,
            name="MyFunction",
            backend="code_sandbox",
        )

        assert function.name == "myfunction"

    @pytest.mark.asyncio
    async def test_create_function_duplicate_name_conflict(
        self, db, test_service, test_function
    ):
        """Test creating duplicate function name raises conflict."""
        service = FunctionService(db)

        with pytest.raises(ConflictError) as exc_info:
            await service.create(
                service_id=test_service.id,
                name="test-function",  # Same name as test_function
                backend="code_sandbox",
            )

        assert "already exists" in str(exc_info.value)


class TestFunctionServiceGetById:
    """Tests for FunctionService.get_by_id()."""

    @pytest.mark.asyncio
    async def test_get_by_id_found(self, db, test_function):
        """Test getting function by ID."""
        service = FunctionService(db)

        function = await service.get_by_id(test_function.id)

        assert function.id == test_function.id
        assert function.name == test_function.name

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self, db):
        """Test getting non-existent function raises error."""
        service = FunctionService(db)

        with pytest.raises(NotFoundError):
            await service.get_by_id(uuid.uuid4())


class TestFunctionServiceGetByName:
    """Tests for FunctionService.get_by_name()."""

    @pytest.mark.asyncio
    async def test_get_by_name_found(self, db, test_service, test_function):
        """Test getting function by name within service."""
        service = FunctionService(db)

        function = await service.get_by_name(
            service_id=test_service.id,
            name="test-function",
        )

        assert function.id == test_function.id

    @pytest.mark.asyncio
    async def test_get_by_name_not_found(self, db, test_service):
        """Test getting non-existent function by name raises error."""
        service = FunctionService(db)

        with pytest.raises(NotFoundError):
            await service.get_by_name(
                service_id=test_service.id,
                name="nonexistent",
            )


class TestFunctionServiceList:
    """Tests for FunctionService.list()."""

    @pytest.mark.asyncio
    async def test_list_empty(self, db, test_service):
        """Test listing functions in empty service."""
        service = FunctionService(db)

        functions, total = await service.list(service_id=test_service.id)

        assert functions == []
        assert total == 0

    @pytest.mark.asyncio
    async def test_list_with_functions(self, db, test_service):
        """Test listing functions."""
        service = FunctionService(db)

        # Create multiple functions
        await service.create(
            service_id=test_service.id,
            name="function-a",
            backend="code_sandbox",
        )
        await service.create(
            service_id=test_service.id,
            name="function-b",
            backend="code_sandbox",
        )
        await service.create(
            service_id=test_service.id,
            name="function-c",
            backend="code_sandbox",
        )

        functions, total = await service.list(service_id=test_service.id)

        assert len(functions) == 3
        assert total == 3
        # Should be sorted by name
        assert [f.name for f in functions] == ["function-a", "function-b", "function-c"]

    @pytest.mark.asyncio
    async def test_list_pagination(self, db, test_service):
        """Test listing functions with pagination."""
        service = FunctionService(db)

        # Create 5 functions
        for i in range(5):
            await service.create(
                service_id=test_service.id,
                name=f"func-{i:02d}",
                backend="code_sandbox",
            )

        # Get first page
        page1, total = await service.list(
            service_id=test_service.id, page=1, page_size=2
        )
        assert len(page1) == 2
        assert total == 5

        # Get second page
        page2, _ = await service.list(
            service_id=test_service.id, page=2, page_size=2
        )
        assert len(page2) == 2

        # Get third page (partial)
        page3, _ = await service.list(
            service_id=test_service.id, page=3, page_size=2
        )
        assert len(page3) == 1

    @pytest.mark.asyncio
    async def test_list_filter_by_tags(self, db, test_service):
        """Test listing functions filtered by tags."""
        service = FunctionService(db)

        await service.create(
            service_id=test_service.id,
            name="auth-func",
            backend="code_sandbox",
            tags=["auth", "security"],
        )
        await service.create(
            service_id=test_service.id,
            name="payment-func",
            backend="code_sandbox",
            tags=["payment", "stripe"],
        )
        await service.create(
            service_id=test_service.id,
            name="secure-payment",
            backend="code_sandbox",
            tags=["payment", "security"],
        )

        # Filter by security tag
        functions, total = await service.list(
            service_id=test_service.id, tags=["security"]
        )
        assert total == 2
        assert {f.name for f in functions} == {"auth-func", "secure-payment"}


class TestFunctionServiceUpdate:
    """Tests for FunctionService.update()."""

    @pytest.mark.asyncio
    async def test_update_description(self, db, test_function):
        """Test updating function description."""
        service = FunctionService(db)

        updated = await service.update(
            function_id=test_function.id,
            description="Updated description",
        )

        assert updated.description == "Updated description"

    @pytest.mark.asyncio
    async def test_update_tags(self, db, test_function):
        """Test updating function tags."""
        service = FunctionService(db)

        updated = await service.update(
            function_id=test_function.id,
            tags=["new", "tags"],
        )

        assert updated.tags == ["new", "tags"]

    @pytest.mark.asyncio
    async def test_update_not_found(self, db):
        """Test updating non-existent function raises error."""
        service = FunctionService(db)

        with pytest.raises(NotFoundError):
            await service.update(
                function_id=uuid.uuid4(),
                description="New description",
            )


class TestFunctionServiceVersioning:
    """Tests for function version management."""

    @pytest.mark.asyncio
    async def test_create_version(self, db, test_function):
        """Test creating a new version."""
        service = FunctionService(db)

        version = await service.create_version(
            function_id=test_function.id,
            backend="code_sandbox",
            code="result = 100",
        )

        assert version.version == 2
        assert version.code == "result = 100"

        # Refresh function to see new active version
        function = await service.get_by_id(test_function.id)
        assert function.active_version == 2

    @pytest.mark.asyncio
    async def test_create_version_without_activation(self, db, test_function):
        """Test creating version without activating it."""
        service = FunctionService(db)

        version = await service.create_version(
            function_id=test_function.id,
            backend="code_sandbox",
            code="result = 200",
            activate=False,
        )

        assert version.version == 2

        # Active version should still be 1
        function = await service.get_by_id(test_function.id)
        assert function.active_version == 1

    @pytest.mark.asyncio
    async def test_get_version(self, db, test_function):
        """Test getting a specific version."""
        service = FunctionService(db)

        version = await service.get_version(test_function.id, version=1)

        assert version.version == 1
        assert version.function_id == test_function.id

    @pytest.mark.asyncio
    async def test_get_version_not_found(self, db, test_function):
        """Test getting non-existent version raises error."""
        service = FunctionService(db)

        with pytest.raises(NotFoundError):
            await service.get_version(test_function.id, version=999)

    @pytest.mark.asyncio
    async def test_get_active_version(self, db, test_function):
        """Test getting the active version."""
        service = FunctionService(db)

        version = await service.get_active_version(test_function.id)

        assert version.version == 1

    @pytest.mark.asyncio
    async def test_set_active_version(self, db, test_function):
        """Test setting the active version."""
        service = FunctionService(db)

        # Create version 2 without activating
        await service.create_version(
            function_id=test_function.id,
            backend="code_sandbox",
            code="result = 999",
            activate=False,
        )

        # Set version 2 as active
        function = await service.set_active_version(test_function.id, version=2)

        assert function.active_version == 2

    @pytest.mark.asyncio
    async def test_set_active_version_not_found(self, db, test_function):
        """Test setting non-existent version as active raises error."""
        service = FunctionService(db)

        with pytest.raises(NotFoundError):
            await service.set_active_version(test_function.id, version=999)


class TestFunctionServiceDelete:
    """Tests for FunctionService.delete()."""

    @pytest.mark.asyncio
    async def test_delete_function(self, db, test_function):
        """Test deleting a function."""
        service = FunctionService(db)
        function_id = test_function.id

        await service.delete(function_id)

        # Should not be found after deletion
        with pytest.raises(NotFoundError):
            await service.get_by_id(function_id)

    @pytest.mark.asyncio
    async def test_delete_not_found(self, db):
        """Test deleting non-existent function raises error."""
        service = FunctionService(db)

        with pytest.raises(NotFoundError):
            await service.delete(uuid.uuid4())


class TestFunctionServiceNamespaceMethods:
    """Tests for namespace-level function methods."""

    @pytest.fixture
    async def second_service(self, db, test_namespace):
        """Create a second service in the namespace."""
        service = NamespaceService(
            namespace_id=test_namespace.id,
            name="other-service",
            description="Second test service",
        )
        db.add(service)
        await db.flush()
        return service

    @pytest.mark.asyncio
    async def test_list_all_for_namespace(
        self, db, test_namespace, test_service, second_service
    ):
        """Test listing all functions across namespace."""
        service = FunctionService(db)

        # Create functions in both services
        await service.create(
            service_id=test_service.id,
            name="func-a",
            backend="code_sandbox",
            code="result = 1",
        )
        await service.create(
            service_id=second_service.id,
            name="func-b",
            backend="code_sandbox",
            code="result = 2",
        )

        pairs = await service.list_all_for_namespace(test_namespace.id)

        assert len(pairs) == 2
        # Should return tuples of (Function, FunctionVersion)
        for fn, version in pairs:
            assert isinstance(fn, Function)
            assert version.version == fn.active_version

    @pytest.mark.asyncio
    async def test_get_for_execution(
        self, db, test_namespace, test_service
    ):
        """Test getting function for execution by names."""
        service = FunctionService(db)

        await service.create(
            service_id=test_service.id,
            name="exec-func",
            backend="code_sandbox",
            code="result = 42",
        )

        fn, version = await service.get_for_execution(
            namespace_id=test_namespace.id,
            service_name="test-service",
            function_name="exec-func",
        )

        assert fn.name == "exec-func"
        assert version.code == "result = 42"

    @pytest.mark.asyncio
    async def test_get_for_execution_not_found(
        self, db, test_namespace
    ):
        """Test getting non-existent function for execution raises error."""
        service = FunctionService(db)

        with pytest.raises(NotFoundError):
            await service.get_for_execution(
                namespace_id=test_namespace.id,
                service_name="no-service",
                function_name="no-func",
            )


class TestFunctionServiceDescribe:
    """Tests for FunctionService.describe()."""

    @pytest.mark.asyncio
    async def test_describe_function(self, db, test_function):
        """Test getting detailed function description."""
        service = FunctionService(db)

        details = await service.describe(test_function.id)

        assert details["id"] == str(test_function.id)
        assert details["name"] == "test-function"
        assert details["description"] == "Test function"
        assert details["tags"] == ["test", "example"]
        assert details["active_version"] == 1
        assert details["active_version_details"] is not None
        assert details["active_version_details"]["backend"] == "code_sandbox"
        assert len(details["versions"]) == 1

    @pytest.mark.asyncio
    async def test_describe_with_multiple_versions(self, db, test_function):
        """Test describe shows all versions."""
        service = FunctionService(db)
        function_id = test_function.id  # Store ID before any expiration

        # Create additional versions (commit and expire between to ensure visibility)
        await service.create_version(
            function_id=function_id,
            backend="code_sandbox",
            code="result = 100",
        )
        await db.commit()
        db.expire_all()  # Clear session cache so next query fetches fresh data

        await service.create_version(
            function_id=function_id,
            backend="code_sandbox",
            code="result = 200",
        )
        await db.commit()
        db.expire_all()

        details = await service.describe(function_id)

        assert details["active_version"] == 3
        assert len(details["versions"]) == 3
        # Versions should be sorted descending
        assert [v["version"] for v in details["versions"]] == [3, 2, 1]

    @pytest.mark.asyncio
    async def test_describe_not_found(self, db):
        """Test describing non-existent function raises error."""
        service = FunctionService(db)

        with pytest.raises(NotFoundError):
            await service.describe(uuid.uuid4())
