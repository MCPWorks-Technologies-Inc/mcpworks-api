"""Unit tests for NamespaceServiceManager and NamespaceServiceService."""

import uuid

import pytest

from mcpworks_api.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from mcpworks_api.models import Account, User
from mcpworks_api.services.namespace import NamespaceServiceManager, NamespaceServiceService


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
async def other_account(db):
    """Create another account for access control tests."""
    user = User(
        email=f"other-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="hashed_password",
        name="Other User",
        tier="free",
        status="active",
    )
    db.add(user)
    await db.flush()

    account = Account(
        user_id=user.id,
        name="Other Account",
    )
    db.add(account)
    await db.flush()
    return account


@pytest.fixture
async def test_namespace(db, test_account):
    """Create a test namespace."""
    manager = NamespaceServiceManager(db)
    return await manager.create(
        account_id=test_account.id,
        name=f"test-ns-{uuid.uuid4().hex[:8]}",
        description="Test namespace",
    )


@pytest.fixture
async def test_service(db, test_namespace):
    """Create a test service within the namespace."""
    service_manager = NamespaceServiceService(db)
    return await service_manager.create(
        namespace_id=test_namespace.id,
        name="test-service",
        description="Test service",
    )


class TestNamespaceServiceManagerCreate:
    """Tests for NamespaceServiceManager.create()."""

    @pytest.mark.asyncio
    async def test_create_namespace_basic(self, db, test_account):
        """Test creating a basic namespace."""
        manager = NamespaceServiceManager(db)

        namespace = await manager.create(
            account_id=test_account.id,
            name="my-namespace",
        )

        assert namespace.name == "my-namespace"
        assert namespace.account_id == test_account.id
        assert namespace.description is None

    @pytest.mark.asyncio
    async def test_create_namespace_with_description(self, db, test_account):
        """Test creating a namespace with description."""
        manager = NamespaceServiceManager(db)

        namespace = await manager.create(
            account_id=test_account.id,
            name="described-ns",
            description="A namespace with a description",
        )

        assert namespace.description == "A namespace with a description"

    @pytest.mark.asyncio
    async def test_create_namespace_with_network_whitelist(self, db, test_account):
        """Test creating a namespace with network whitelist."""
        manager = NamespaceServiceManager(db)

        namespace = await manager.create(
            account_id=test_account.id,
            name="whitelisted-ns",
            network_whitelist=["192.168.1.0/24", "10.0.0.1"],
        )

        assert namespace.network_whitelist == ["192.168.1.0/24", "10.0.0.1"]

    @pytest.mark.asyncio
    async def test_create_namespace_name_normalized(self, db, test_account):
        """Test namespace name is normalized to lowercase."""
        manager = NamespaceServiceManager(db)

        namespace = await manager.create(
            account_id=test_account.id,
            name="MyNamespace",
        )

        assert namespace.name == "mynamespace"

    @pytest.mark.asyncio
    async def test_create_namespace_duplicate_conflict(self, db, test_account, test_namespace):
        """Test creating duplicate namespace raises conflict."""
        manager = NamespaceServiceManager(db)

        with pytest.raises(ConflictError) as exc_info:
            await manager.create(
                account_id=test_account.id,
                name=test_namespace.name,  # Same name
            )

        assert "already exists" in str(exc_info.value)


class TestNamespaceServiceManagerGetById:
    """Tests for NamespaceServiceManager.get_by_id()."""

    @pytest.mark.asyncio
    async def test_get_by_id_found(self, db, test_namespace):
        """Test getting namespace by ID."""
        manager = NamespaceServiceManager(db)

        namespace = await manager.get_by_id(test_namespace.id)

        assert namespace.id == test_namespace.id
        assert namespace.name == test_namespace.name

    @pytest.mark.asyncio
    async def test_get_by_id_with_account_access(self, db, test_account, test_namespace):
        """Test getting namespace with account access control."""
        manager = NamespaceServiceManager(db)

        namespace = await manager.get_by_id(
            namespace_id=test_namespace.id,
            account_id=test_account.id,
        )

        assert namespace.id == test_namespace.id

    @pytest.mark.asyncio
    async def test_get_by_id_forbidden(self, db, test_namespace, other_account):
        """Test getting namespace owned by different account is forbidden."""
        manager = NamespaceServiceManager(db)

        with pytest.raises(ForbiddenError):
            await manager.get_by_id(
                namespace_id=test_namespace.id,
                account_id=other_account.id,
            )

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self, db):
        """Test getting non-existent namespace raises error."""
        manager = NamespaceServiceManager(db)

        with pytest.raises(NotFoundError):
            await manager.get_by_id(uuid.uuid4())


class TestNamespaceServiceManagerGetByName:
    """Tests for NamespaceServiceManager.get_by_name()."""

    @pytest.mark.asyncio
    async def test_get_by_name_found(self, db, test_namespace):
        """Test getting namespace by name."""
        manager = NamespaceServiceManager(db)

        namespace = await manager.get_by_name(test_namespace.name)

        assert namespace.id == test_namespace.id

    @pytest.mark.asyncio
    async def test_get_by_name_with_account_access(self, db, test_account, test_namespace):
        """Test getting namespace by name with account access control."""
        manager = NamespaceServiceManager(db)

        namespace = await manager.get_by_name(
            name=test_namespace.name,
            account_id=test_account.id,
        )

        assert namespace.id == test_namespace.id

    @pytest.mark.asyncio
    async def test_get_by_name_forbidden(self, db, test_namespace, other_account):
        """Test getting namespace by name owned by different account is forbidden."""
        manager = NamespaceServiceManager(db)

        with pytest.raises(ForbiddenError):
            await manager.get_by_name(
                name=test_namespace.name,
                account_id=other_account.id,
            )

    @pytest.mark.asyncio
    async def test_get_by_name_not_found(self, db):
        """Test getting non-existent namespace by name raises error."""
        manager = NamespaceServiceManager(db)

        with pytest.raises(NotFoundError):
            await manager.get_by_name("nonexistent-namespace")


class TestNamespaceServiceManagerList:
    """Tests for NamespaceServiceManager.list()."""

    @pytest.mark.asyncio
    async def test_list_empty(self, db, test_account):
        """Test listing namespaces for account with none."""
        manager = NamespaceServiceManager(db)

        namespaces, total = await manager.list(account_id=test_account.id)

        assert namespaces == []
        assert total == 0

    @pytest.mark.asyncio
    async def test_list_with_namespaces(self, db, test_account):
        """Test listing namespaces."""
        manager = NamespaceServiceManager(db)

        await manager.create(account_id=test_account.id, name="ns-alpha")
        await manager.create(account_id=test_account.id, name="ns-beta")
        await manager.create(account_id=test_account.id, name="ns-gamma")

        namespaces, total = await manager.list(account_id=test_account.id)

        assert len(namespaces) == 3
        assert total == 3
        # Should be sorted by name
        assert [ns.name for ns in namespaces] == ["ns-alpha", "ns-beta", "ns-gamma"]

    @pytest.mark.asyncio
    async def test_list_pagination(self, db, test_account):
        """Test listing namespaces with pagination."""
        manager = NamespaceServiceManager(db)

        for i in range(5):
            await manager.create(
                account_id=test_account.id,
                name=f"ns-{i:02d}",
            )

        # Get first page
        page1, total = await manager.list(
            account_id=test_account.id, page=1, page_size=2
        )
        assert len(page1) == 2
        assert total == 5

        # Get second page
        page2, _ = await manager.list(
            account_id=test_account.id, page=2, page_size=2
        )
        assert len(page2) == 2

        # Get third page (partial)
        page3, _ = await manager.list(
            account_id=test_account.id, page=3, page_size=2
        )
        assert len(page3) == 1

    @pytest.mark.asyncio
    async def test_list_only_own_namespaces(self, db, test_account, other_account):
        """Test list only returns namespaces owned by account."""
        manager = NamespaceServiceManager(db)

        await manager.create(account_id=test_account.id, name="my-namespace")
        await manager.create(account_id=other_account.id, name="other-namespace")

        my_namespaces, total = await manager.list(account_id=test_account.id)

        assert len(my_namespaces) == 1
        assert total == 1
        assert my_namespaces[0].name == "my-namespace"


class TestNamespaceServiceManagerUpdate:
    """Tests for NamespaceServiceManager.update()."""

    @pytest.mark.asyncio
    async def test_update_description(self, db, test_account, test_namespace):
        """Test updating namespace description."""
        manager = NamespaceServiceManager(db)
        namespace_id = test_namespace.id

        updated = await manager.update(
            namespace_id=namespace_id,
            account_id=test_account.id,
            description="Updated description",
        )

        assert updated.description == "Updated description"

    @pytest.mark.asyncio
    async def test_update_forbidden(self, db, test_namespace, other_account):
        """Test updating namespace owned by different account is forbidden."""
        manager = NamespaceServiceManager(db)

        with pytest.raises(ForbiddenError):
            await manager.update(
                namespace_id=test_namespace.id,
                account_id=other_account.id,
                description="Hacked!",
            )


class TestNamespaceServiceManagerDelete:
    """Tests for NamespaceServiceManager.delete()."""

    @pytest.mark.asyncio
    async def test_delete_namespace(self, db, test_account, test_namespace):
        """Test deleting a namespace."""
        manager = NamespaceServiceManager(db)
        namespace_id = test_namespace.id

        await manager.delete(
            namespace_id=namespace_id,
            account_id=test_account.id,
        )

        # Should not be found after deletion
        with pytest.raises(NotFoundError):
            await manager.get_by_id(namespace_id)

    @pytest.mark.asyncio
    async def test_delete_forbidden(self, db, test_namespace, other_account):
        """Test deleting namespace owned by different account is forbidden."""
        manager = NamespaceServiceManager(db)

        with pytest.raises(ForbiddenError):
            await manager.delete(
                namespace_id=test_namespace.id,
                account_id=other_account.id,
            )

    @pytest.mark.asyncio
    async def test_delete_not_found(self, db, test_account):
        """Test deleting non-existent namespace raises error."""
        manager = NamespaceServiceManager(db)

        with pytest.raises(NotFoundError):
            await manager.delete(
                namespace_id=uuid.uuid4(),
                account_id=test_account.id,
            )


# ============================================================
# Tests for NamespaceServiceService (service within namespace)
# ============================================================


class TestNamespaceServiceServiceCreate:
    """Tests for NamespaceServiceService.create()."""

    @pytest.mark.asyncio
    async def test_create_service_basic(self, db, test_namespace):
        """Test creating a basic service."""
        service_manager = NamespaceServiceService(db)

        service = await service_manager.create(
            namespace_id=test_namespace.id,
            name="my-service",
        )

        assert service.name == "my-service"
        assert service.namespace_id == test_namespace.id
        assert service.description is None

    @pytest.mark.asyncio
    async def test_create_service_with_description(self, db, test_namespace):
        """Test creating a service with description."""
        service_manager = NamespaceServiceService(db)

        service = await service_manager.create(
            namespace_id=test_namespace.id,
            name="described-svc",
            description="A service with a description",
        )

        assert service.description == "A service with a description"

    @pytest.mark.asyncio
    async def test_create_service_name_normalized(self, db, test_namespace):
        """Test service name is normalized to lowercase."""
        service_manager = NamespaceServiceService(db)

        service = await service_manager.create(
            namespace_id=test_namespace.id,
            name="MyService",
        )

        assert service.name == "myservice"

    @pytest.mark.asyncio
    async def test_create_service_duplicate_conflict(self, db, test_namespace, test_service):
        """Test creating duplicate service raises conflict."""
        service_manager = NamespaceServiceService(db)

        with pytest.raises(ConflictError) as exc_info:
            await service_manager.create(
                namespace_id=test_namespace.id,
                name=test_service.name,  # Same name
            )

        assert "already exists" in str(exc_info.value)


class TestNamespaceServiceServiceGetById:
    """Tests for NamespaceServiceService.get_by_id()."""

    @pytest.mark.asyncio
    async def test_get_by_id_found(self, db, test_service):
        """Test getting service by ID."""
        service_manager = NamespaceServiceService(db)

        service = await service_manager.get_by_id(test_service.id)

        assert service.id == test_service.id
        assert service.name == test_service.name

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self, db):
        """Test getting non-existent service raises error."""
        service_manager = NamespaceServiceService(db)

        with pytest.raises(NotFoundError):
            await service_manager.get_by_id(uuid.uuid4())


class TestNamespaceServiceServiceGetByName:
    """Tests for NamespaceServiceService.get_by_name()."""

    @pytest.mark.asyncio
    async def test_get_by_name_found(self, db, test_namespace, test_service):
        """Test getting service by name."""
        service_manager = NamespaceServiceService(db)

        service = await service_manager.get_by_name(
            namespace_id=test_namespace.id,
            name=test_service.name,
        )

        assert service.id == test_service.id

    @pytest.mark.asyncio
    async def test_get_by_name_not_found(self, db, test_namespace):
        """Test getting non-existent service by name raises error."""
        service_manager = NamespaceServiceService(db)

        with pytest.raises(NotFoundError):
            await service_manager.get_by_name(
                namespace_id=test_namespace.id,
                name="nonexistent-service",
            )


class TestNamespaceServiceServiceList:
    """Tests for NamespaceServiceService.list()."""

    @pytest.mark.asyncio
    async def test_list_empty(self, db, test_namespace):
        """Test listing services in empty namespace."""
        service_manager = NamespaceServiceService(db)

        services = await service_manager.list(namespace_id=test_namespace.id)

        assert services == []

    @pytest.mark.asyncio
    async def test_list_with_services(self, db, test_namespace):
        """Test listing services."""
        service_manager = NamespaceServiceService(db)

        await service_manager.create(namespace_id=test_namespace.id, name="svc-alpha")
        await service_manager.create(namespace_id=test_namespace.id, name="svc-beta")
        await service_manager.create(namespace_id=test_namespace.id, name="svc-gamma")

        services = await service_manager.list(namespace_id=test_namespace.id)

        assert len(services) == 3
        # Should be sorted by name
        assert [s.name for s in services] == ["svc-alpha", "svc-beta", "svc-gamma"]


class TestNamespaceServiceServiceUpdate:
    """Tests for NamespaceServiceService.update()."""

    @pytest.mark.asyncio
    async def test_update_description(self, db, test_service):
        """Test updating service description."""
        service_manager = NamespaceServiceService(db)

        updated = await service_manager.update(
            service_id=test_service.id,
            description="Updated description",
        )

        assert updated.description == "Updated description"

    @pytest.mark.asyncio
    async def test_update_not_found(self, db):
        """Test updating non-existent service raises error."""
        service_manager = NamespaceServiceService(db)

        with pytest.raises(NotFoundError):
            await service_manager.update(
                service_id=uuid.uuid4(),
                description="New description",
            )


class TestNamespaceServiceServiceDelete:
    """Tests for NamespaceServiceService.delete()."""

    @pytest.mark.asyncio
    async def test_delete_service(self, db, test_service):
        """Test deleting a service."""
        service_manager = NamespaceServiceService(db)
        service_id = test_service.id

        await service_manager.delete(service_id)

        # Should not be found after deletion
        with pytest.raises(NotFoundError):
            await service_manager.get_by_id(service_id)

    @pytest.mark.asyncio
    async def test_delete_not_found(self, db):
        """Test deleting non-existent service raises error."""
        service_manager = NamespaceServiceService(db)

        with pytest.raises(NotFoundError):
            await service_manager.delete(uuid.uuid4())
