"""Unit tests for function result cache key generation and policy parsing."""

from mcpworks_api.services.result_cache import get_cache_policy, make_cache_key


class TestMakeCacheKey:
    def test_deterministic_key(self):
        key1 = make_cache_key("abc-123", 1, {"x": 1, "y": 2})
        key2 = make_cache_key("abc-123", 1, {"x": 1, "y": 2})
        assert key1 == key2

    def test_different_inputs_different_keys(self):
        key1 = make_cache_key("abc-123", 1, {"x": 1})
        key2 = make_cache_key("abc-123", 1, {"x": 2})
        assert key1 != key2

    def test_key_order_independent(self):
        key1 = make_cache_key("abc-123", 1, {"b": 2, "a": 1})
        key2 = make_cache_key("abc-123", 1, {"a": 1, "b": 2})
        assert key1 == key2

    def test_different_versions_different_keys(self):
        key1 = make_cache_key("abc-123", 1, {"x": 1})
        key2 = make_cache_key("abc-123", 2, {"x": 1})
        assert key1 != key2

    def test_different_functions_different_keys(self):
        key1 = make_cache_key("abc-123", 1, {"x": 1})
        key2 = make_cache_key("def-456", 1, {"x": 1})
        assert key1 != key2

    def test_none_input(self):
        key = make_cache_key("abc-123", 1, None)
        assert key.startswith("fncache:abc-123:v1:")

    def test_empty_input(self):
        key1 = make_cache_key("abc-123", 1, {})
        key2 = make_cache_key("abc-123", 1, None)
        assert key1 == key2

    def test_key_format(self):
        key = make_cache_key("func-id", 3, {"q": "hello"})
        assert key.startswith("fncache:func-id:v3:")
        assert len(key.split(":")) == 4


class FakeFunction:
    def __init__(self, cache_policy=None):
        self.cache_policy = cache_policy


class TestGetCachePolicy:
    def test_no_policy(self):
        fn = FakeFunction()
        enabled, ttl = get_cache_policy(fn)
        assert enabled is False
        assert ttl == 0

    def test_none_policy(self):
        fn = FakeFunction(cache_policy=None)
        enabled, ttl = get_cache_policy(fn)
        assert enabled is False

    def test_enabled_policy(self):
        fn = FakeFunction(cache_policy={"enabled": True, "ttl_seconds": 600})
        enabled, ttl = get_cache_policy(fn)
        assert enabled is True
        assert ttl == 600

    def test_disabled_policy(self):
        fn = FakeFunction(cache_policy={"enabled": False, "ttl_seconds": 300})
        enabled, ttl = get_cache_policy(fn)
        assert enabled is False
        assert ttl == 0

    def test_default_ttl(self):
        fn = FakeFunction(cache_policy={"enabled": True})
        enabled, ttl = get_cache_policy(fn)
        assert enabled is True
        assert ttl == 300

    def test_zero_ttl_disables(self):
        fn = FakeFunction(cache_policy={"enabled": True, "ttl_seconds": 0})
        enabled, ttl = get_cache_policy(fn)
        assert enabled is False

    def test_invalid_policy_type(self):
        fn = FakeFunction(cache_policy="invalid")
        enabled, ttl = get_cache_policy(fn)
        assert enabled is False
