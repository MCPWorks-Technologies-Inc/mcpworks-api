"""Unit tests for the Code Execution Sandbox Backend."""

from unittest.mock import MagicMock, patch

import pytest

from mcpworks_api.backends.sandbox import (
    DANGEROUS_PATTERNS,
    DEFAULT_TIER,
    TIER_CONFIG,
    ExecutionTier,
    SandboxBackend,
)


class TestExecutionTier:
    """Tests for ExecutionTier enum."""

    def test_tier_values(self):
        """Test tier enum values."""
        assert ExecutionTier.FREE.value == "free"
        assert ExecutionTier.FOUNDER.value == "founder"
        assert ExecutionTier.FOUNDER_PRO.value == "founder_pro"
        assert ExecutionTier.ENTERPRISE.value == "enterprise"

    def test_tier_config_exists_for_all_tiers(self):
        """Test all tiers have configuration."""
        for tier in ExecutionTier:
            assert tier in TIER_CONFIG
            config = TIER_CONFIG[tier]
            assert "timeout_sec" in config
            assert "memory_mb" in config
            assert "max_pids" in config
            assert "network_hosts" in config


class TestTierConfig:
    """Tests for tier configuration."""

    def test_free_tier_limits(self):
        """Test free tier has restrictive limits."""
        config = TIER_CONFIG[ExecutionTier.FREE]
        assert config["timeout_sec"] == 10
        assert config["memory_mb"] == 128
        assert config["network_hosts"] == 0  # No network access

    def test_founder_tier_limits(self):
        """Test founder tier has moderate limits."""
        config = TIER_CONFIG[ExecutionTier.FOUNDER]
        assert config["timeout_sec"] == 30
        assert config["memory_mb"] == 256
        assert config["network_hosts"] == 5

    def test_enterprise_tier_limits(self):
        """Test enterprise tier has generous limits."""
        config = TIER_CONFIG[ExecutionTier.ENTERPRISE]
        assert config["timeout_sec"] == 300
        assert config["memory_mb"] == 2048
        assert config["network_hosts"] == -1  # Unlimited

    def test_tier_progression(self):
        """Test limits increase with tier."""
        free = TIER_CONFIG[ExecutionTier.FREE]
        founder = TIER_CONFIG[ExecutionTier.FOUNDER]
        pro = TIER_CONFIG[ExecutionTier.FOUNDER_PRO]
        enterprise = TIER_CONFIG[ExecutionTier.ENTERPRISE]

        # Timeout increases
        assert free["timeout_sec"] < founder["timeout_sec"]
        assert founder["timeout_sec"] < pro["timeout_sec"]
        assert pro["timeout_sec"] < enterprise["timeout_sec"]

        # Memory increases
        assert free["memory_mb"] < founder["memory_mb"]
        assert founder["memory_mb"] < pro["memory_mb"]
        assert pro["memory_mb"] < enterprise["memory_mb"]


class TestDangerousPatterns:
    """Tests for dangerous pattern detection."""

    def test_dangerous_patterns_defined(self):
        """Test dangerous patterns are defined."""
        assert len(DANGEROUS_PATTERNS) > 0
        assert "os.system" in DANGEROUS_PATTERNS
        assert "subprocess" in DANGEROUS_PATTERNS
        assert "eval(" in DANGEROUS_PATTERNS
        assert "exec(" in DANGEROUS_PATTERNS

    def test_dangerous_patterns_include_security_risks(self):
        """Test patterns include common security risks."""
        assert "__import__" in DANGEROUS_PATTERNS
        assert "ctypes" in DANGEROUS_PATTERNS
        assert "builtins" in DANGEROUS_PATTERNS


class TestSandboxBackend:
    """Tests for SandboxBackend class."""

    def test_backend_name(self):
        """Test backend name."""
        backend = SandboxBackend(dev_mode=True)
        assert backend.name == "code_sandbox"

    def test_backend_description_dev_mode(self):
        """Test description in dev mode."""
        backend = SandboxBackend(dev_mode=True)
        assert "development" in backend.description.lower()
        assert "NOT SECURE" in backend.description

    def test_backend_description_prod_mode(self):
        """Test description in production mode."""
        backend = SandboxBackend(dev_mode=False)
        assert "Secure" in backend.description

    def test_supported_languages(self):
        """Test supported languages."""
        backend = SandboxBackend(dev_mode=True)
        assert "python" in backend.supported_languages

    def test_dev_mode_from_env(self):
        """Test dev mode detection from environment."""
        with patch.dict("os.environ", {"SANDBOX_DEV_MODE": "false"}):
            backend = SandboxBackend()
            assert backend._dev_mode is False

        with patch.dict("os.environ", {"SANDBOX_DEV_MODE": "true"}):
            backend = SandboxBackend()
            assert backend._dev_mode is True

    def test_dev_mode_override(self):
        """Test dev mode can be explicitly set."""
        backend = SandboxBackend(dev_mode=True)
        assert backend._dev_mode is True

        backend = SandboxBackend(dev_mode=False)
        assert backend._dev_mode is False

    def test_get_tier_config_with_account(self):
        """Test tier config retrieval."""
        backend = SandboxBackend(dev_mode=True)

        # Mock account with tier
        account = MagicMock()
        account.tier = "founder"

        config = backend._get_tier_config(account)
        assert config == TIER_CONFIG[ExecutionTier.FOUNDER]

    def test_get_tier_config_default(self):
        """Test default tier config when account has no tier."""
        backend = SandboxBackend(dev_mode=True)

        account = MagicMock()
        account.tier = None

        config = backend._get_tier_config(account)
        assert config == TIER_CONFIG[DEFAULT_TIER]

    def test_get_tier_config_invalid_tier(self):
        """Test fallback for invalid tier."""
        backend = SandboxBackend(dev_mode=True)

        account = MagicMock()
        account.tier = "invalid_tier"

        config = backend._get_tier_config(account)
        assert config == TIER_CONFIG[DEFAULT_TIER]


class TestSandboxValidation:
    """Tests for SandboxBackend.validate()."""

    @pytest.mark.asyncio
    async def test_validate_valid_code(self):
        """Test validation of valid Python code."""
        backend = SandboxBackend(dev_mode=True)
        result = await backend.validate(
            code="result = input_data['x'] + input_data['y']",
            config=None,
        )
        assert result.valid is True
        assert len(result.errors) == 0

    @pytest.mark.asyncio
    async def test_validate_syntax_error(self):
        """Test validation catches syntax errors."""
        backend = SandboxBackend(dev_mode=True)
        result = await backend.validate(
            code="def broken(\n",
            config=None,
        )
        assert result.valid is False
        assert any("Syntax error" in e for e in result.errors)

    @pytest.mark.asyncio
    async def test_validate_empty_code(self):
        """Test validation requires code."""
        backend = SandboxBackend(dev_mode=True)
        result = await backend.validate(code=None, config=None)
        assert result.valid is False
        assert any("required" in e.lower() for e in result.errors)

    @pytest.mark.asyncio
    async def test_validate_code_too_large(self):
        """Test validation catches oversized code."""
        backend = SandboxBackend(dev_mode=True)
        large_code = "x = 1\n" * 200000  # > 1MB
        result = await backend.validate(code=large_code, config=None)
        assert result.valid is False
        assert any("size" in e.lower() for e in result.errors)

    @pytest.mark.asyncio
    async def test_validate_dangerous_pattern_warning(self):
        """Test validation warns on dangerous patterns."""
        backend = SandboxBackend(dev_mode=True)
        result = await backend.validate(
            code="import os\nos.system('ls')",
            config=None,
        )
        # Should still be valid (warnings don't block)
        # but should have warnings
        assert len(result.warnings) > 0
        assert any("os.system" in w for w in result.warnings)

    @pytest.mark.asyncio
    async def test_validate_multiple_dangerous_patterns(self):
        """Test validation catches multiple dangerous patterns."""
        backend = SandboxBackend(dev_mode=True)
        result = await backend.validate(
            code="import subprocess\neval('1+1')",
            config=None,
        )
        assert len(result.warnings) >= 2


class TestSandboxCostEstimation:
    """Tests for SandboxBackend.estimate_cost()."""

    @pytest.mark.asyncio
    async def test_estimate_cost_base(self):
        """Test base cost for simple code."""
        backend = SandboxBackend(dev_mode=True)
        cost = await backend.estimate_cost(code="x = 1", config=None)
        assert cost >= 1.0

    @pytest.mark.asyncio
    async def test_estimate_cost_no_code(self):
        """Test cost when no code provided."""
        backend = SandboxBackend(dev_mode=True)
        cost = await backend.estimate_cost(code=None, config=None)
        assert cost == 1.0

    @pytest.mark.asyncio
    async def test_estimate_cost_complex_code(self):
        """Test cost increases with code complexity."""
        backend = SandboxBackend(dev_mode=True)

        simple_code = "x = 1"
        complex_code = "x = 1\n" * 10000  # ~60KB

        simple_cost = await backend.estimate_cost(code=simple_code, config=None)
        complex_cost = await backend.estimate_cost(code=complex_code, config=None)

        assert complex_cost > simple_cost

    @pytest.mark.asyncio
    async def test_estimate_cost_capped(self):
        """Test cost is capped at maximum."""
        backend = SandboxBackend(dev_mode=True)

        huge_code = "x = 1\n" * 100000  # Very large

        cost = await backend.estimate_cost(code=huge_code, config=None)
        assert cost <= 6.0  # Base (1) + max complexity (5)


class TestSandboxHealthCheck:
    """Tests for SandboxBackend.health_check()."""

    @pytest.mark.asyncio
    async def test_health_check_dev_mode(self):
        """Test health check in dev mode."""
        backend = SandboxBackend(dev_mode=True)
        health = await backend.health_check()

        assert health["backend"] == "code_sandbox"
        assert health["healthy"] is True
        assert health["mode"] == "development"
        assert "checked_at" in health

    @pytest.mark.asyncio
    async def test_health_check_prod_mode(self):
        """Test health check in production mode."""
        backend = SandboxBackend(dev_mode=False)
        health = await backend.health_check()

        assert health["mode"] == "production"

    @pytest.mark.asyncio
    async def test_health_check_nsjail_availability(self):
        """Test health check reports nsjail availability."""
        backend = SandboxBackend(dev_mode=False)
        health = await backend.health_check()

        assert "nsjail_available" in health
        assert "exec_dir" in health


class TestSandboxCodeWrapping:
    """Tests for code wrapping functionality."""

    def test_wrap_code_contains_harness(self):
        """Test wrapped code contains execution harness."""
        backend = SandboxBackend(dev_mode=True)
        wrapped = backend._wrap_code("result = 42")

        assert "import json" in wrapped
        assert "import sys" in wrapped
        assert "input_data" in wrapped
        assert "output.json" in wrapped

    def test_wrap_code_includes_user_code(self):
        """Test wrapped code includes original code."""
        backend = SandboxBackend(dev_mode=True)
        user_code = "result = input_data['x'] * 2"
        wrapped = backend._wrap_code(user_code)

        assert user_code in wrapped

    def test_wrap_code_handles_errors(self):
        """Test wrapped code has error handling."""
        backend = SandboxBackend(dev_mode=True)
        wrapped = backend._wrap_code("result = 1")

        assert "try:" in wrapped
        assert "except" in wrapped
        assert "traceback" in wrapped
