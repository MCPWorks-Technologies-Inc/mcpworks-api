"""Unit tests for backend base classes and utilities."""

from datetime import datetime

import pytest

from mcpworks_api.backends.base import Backend, ExecutionResult, ValidationResult


class TestExecutionResult:
    """Tests for ExecutionResult dataclass."""

    def test_execution_result_success(self):
        """Test successful execution result."""
        result = ExecutionResult(
            success=True,
            output={"value": 42},
            stdout="Computed result\n",
            stderr=None,
            error=None,
            error_type=None,
            execution_time_ms=150,
        )
        assert result.success is True
        assert result.output == {"value": 42}
        assert result.stdout == "Computed result\n"
        assert result.error is None

    def test_execution_result_failure(self):
        """Test failed execution result."""
        result = ExecutionResult(
            success=False,
            output=None,
            error="Division by zero",
            error_type="ZeroDivisionError",
            execution_time_ms=50,
        )
        assert result.success is False
        assert result.output is None
        assert result.error == "Division by zero"
        assert result.error_type == "ZeroDivisionError"

    def test_execution_result_with_resource_usage(self):
        """Test execution result with resource metrics."""
        result = ExecutionResult(
            success=True,
            output="done",
            resource_usage={
                "memory_mb": 64,
                "cpu_ms": 100,
            },
        )
        assert result.resource_usage["memory_mb"] == 64

    def test_execution_result_defaults(self):
        """Test execution result default values."""
        result = ExecutionResult(success=True, output=None)
        assert result.stdout is None
        assert result.stderr is None
        assert result.error is None
        assert result.error_type is None
        assert result.execution_time_ms is None
        assert result.resource_usage is None


class TestValidationResult:
    """Tests for ValidationResult dataclass."""

    def test_validation_result_valid(self):
        """Test valid validation result."""
        result = ValidationResult(valid=True)
        assert result.valid is True
        assert result.errors == []
        assert result.warnings == []

    def test_validation_result_with_errors(self):
        """Test validation result with errors."""
        result = ValidationResult(
            valid=False,
            errors=["Syntax error on line 5", "Missing import"],
        )
        assert result.valid is False
        assert len(result.errors) == 2
        assert "Syntax error" in result.errors[0]

    def test_validation_result_with_warnings(self):
        """Test validation result with warnings."""
        result = ValidationResult(
            valid=True,
            warnings=["Potentially dangerous pattern: eval()"],
        )
        assert result.valid is True
        assert len(result.warnings) == 1

    def test_validation_result_errors_and_warnings(self):
        """Test validation result with both errors and warnings."""
        result = ValidationResult(
            valid=False,
            errors=["Code too large"],
            warnings=["Uses subprocess"],
        )
        assert result.valid is False
        assert len(result.errors) == 1
        assert len(result.warnings) == 1


class TestBackendAbstract:
    """Tests for Backend abstract base class."""

    def test_backend_default_description(self):
        """Test default description property."""

        class TestBackend(Backend):
            @property
            def name(self) -> str:
                return "test_backend"

            async def execute(self, *args, **kwargs):
                pass

            async def validate(self, *args, **kwargs):
                pass

        backend = TestBackend()
        assert backend.description == "test_backend backend"

    def test_backend_default_languages(self):
        """Test default supported languages."""

        class TestBackend(Backend):
            @property
            def name(self) -> str:
                return "test"

            async def execute(self, *args, **kwargs):
                pass

            async def validate(self, *args, **kwargs):
                pass

        backend = TestBackend()
        assert backend.supported_languages == []

    @pytest.mark.asyncio
    async def test_backend_default_estimate_cost(self):
        """Test default cost estimation."""

        class TestBackend(Backend):
            @property
            def name(self) -> str:
                return "test"

            async def execute(self, *args, **kwargs):
                pass

            async def validate(self, *args, **kwargs):
                pass

        backend = TestBackend()
        cost = await backend.estimate_cost(None, None)
        assert cost == 1.0

    @pytest.mark.asyncio
    async def test_backend_default_health_check(self):
        """Test default health check."""

        class TestBackend(Backend):
            @property
            def name(self) -> str:
                return "test"

            async def execute(self, *args, **kwargs):
                pass

            async def validate(self, *args, **kwargs):
                pass

        backend = TestBackend()
        health = await backend.health_check()
        assert health["backend"] == "test"
        assert health["healthy"] is True
        assert "checked_at" in health
