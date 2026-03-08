"""Abstract base class for function backends.

Backends provide the execution layer for functions. Each backend type
(code_sandbox, activepieces, nanobot, github_repo) implements this interface.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from mcpworks_api.models import Account


@dataclass
class ExecutionResult:
    """Result from backend execution.

    Attributes:
        success: Whether execution completed successfully.
        output: The function's return value (JSON-serializable).
        stdout: Captured standard output.
        stderr: Captured standard error.
        error: Error message if execution failed.
        error_type: Classification of error (timeout, runtime, validation, etc.)
        execution_time_ms: Time taken to execute in milliseconds.
        resource_usage: Optional resource metrics (memory, cpu).
    """

    success: bool
    output: Any
    stdout: str | None = None
    stderr: str | None = None
    error: str | None = None
    error_type: str | None = None
    execution_time_ms: int | None = None
    resource_usage: dict[str, Any] | None = None
    call_log: list[str] = field(default_factory=list)


@dataclass
class ValidationResult:
    """Result from code/config validation.

    Attributes:
        valid: Whether the code/config is valid.
        errors: List of validation errors.
        warnings: List of non-fatal warnings.
    """

    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class Backend(ABC):
    """Abstract backend interface.

    All function backends must implement this interface to support
    execution and validation of functions.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Backend identifier (code_sandbox, activepieces, nanobot, github_repo)."""
        pass

    @property
    def description(self) -> str:
        """Human-readable description of the backend."""
        return f"{self.name} backend"

    @property
    def supported_languages(self) -> list[str]:
        """List of supported programming languages (for code backends)."""
        return []

    @abstractmethod
    async def execute(
        self,
        code: str | None,
        config: dict[str, Any] | None,
        input_data: dict[str, Any],
        account: Account,
        execution_id: str,
        timeout_ms: int = 30000,
        extra_files: dict[str, str] | None = None,
        sandbox_env: dict[str, str] | None = None,
    ) -> ExecutionResult:
        """Execute function code/config with input data.

        Args:
            code: Function source code (for code_sandbox backend).
            config: Backend-specific configuration.
            input_data: Input arguments for the function.
            account: The account executing the function (for quotas/billing).
            execution_id: Unique execution identifier for tracing.
            timeout_ms: Maximum execution time in milliseconds.
            extra_files: Optional mapping of relative paths to file contents
                to write into the execution directory before running code.
            sandbox_env: User-provided environment variables to inject into
                the sandbox. Already validated and filtered to declared vars.
                Values are NEVER logged or persisted.

        Returns:
            ExecutionResult with output or error details.
        """
        pass

    @abstractmethod
    async def validate(
        self,
        code: str | None,
        config: dict[str, Any] | None,
    ) -> ValidationResult:
        """Validate code/config before saving.

        This should check:
        - Syntax validity
        - Dangerous patterns (for sandboxed execution)
        - Configuration completeness
        - Resource requirements

        Args:
            code: Function source code to validate.
            config: Backend-specific configuration to validate.

        Returns:
            ValidationResult indicating validity and any errors/warnings.
        """
        pass

    async def estimate_cost(
        self,
        code: str | None,
        config: dict[str, Any] | None,
    ) -> float:
        """Estimate execution cost in credits.

        Default implementation returns base cost.
        Backends can override for more accurate estimates.

        Args:
            code: Function source code.
            config: Backend-specific configuration.

        Returns:
            Estimated cost in credits.
        """
        return 1.0  # Base cost of 1 credit per execution

    async def health_check(self) -> dict[str, Any]:
        """Check backend health and availability.

        Returns:
            Dict with health status and metrics.
        """
        return {
            "backend": self.name,
            "healthy": True,
            "checked_at": datetime.utcnow().isoformat(),
        }
