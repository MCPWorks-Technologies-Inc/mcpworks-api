"""Stub backend for development and testing.

Provides a mock implementation that returns predictable results
without actually executing code. Used until Phase 6 implements
the real code_sandbox backend.
"""

from datetime import datetime
from typing import Any

from mcpworks_api.backends.base import Backend, ExecutionResult, ValidationResult
from mcpworks_api.models import Account


class StubBackend(Backend):
    """Stub backend for development.

    Returns mock results instead of actually executing code.
    Useful for:
    - Development before Phase 6
    - Testing without sandbox infrastructure
    - Demo/validation scenarios
    """

    @property
    def name(self) -> str:
        """Backend identifier."""
        return "code_sandbox"

    @property
    def description(self) -> str:
        """Human-readable description."""
        return "Stub code sandbox (development mode)"

    @property
    def supported_languages(self) -> list[str]:
        """Supported programming languages."""
        return ["python", "typescript", "javascript"]

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
        """Mock execution returning predictable results.

        Returns a result that includes:
        - The input data echoed back
        - Metadata about the execution
        - Simulated execution time
        """
        # Simulate processing
        output = {
            "status": "stub_execution",
            "message": "Stub backend - replace with real sandbox in Phase 6",
            "input": input_data,
            "code_provided": code is not None,
            "code_length": len(code) if code else 0,
            "config": config,
            "execution_id": execution_id,
            "timestamp": datetime.utcnow().isoformat(),
        }

        return ExecutionResult(
            success=True,
            output=output,
            stdout="[stub] Function executed successfully\n",
            stderr=None,
            error=None,
            error_type=None,
            execution_time_ms=5,  # Simulated fast execution
            resource_usage={
                "memory_mb": 0,
                "cpu_percent": 0,
            },
        )

    async def validate(
        self,
        code: str | None,
        config: dict[str, Any] | None,
    ) -> ValidationResult:
        """Basic validation of code/config.

        Performs simple checks:
        - Code is not empty (if provided)
        - No obvious dangerous patterns
        """
        errors = []
        warnings = []

        if code is not None:
            if not code.strip():
                errors.append("Code cannot be empty")

            # Check for dangerous patterns (basic)
            dangerous = ["os.system", "subprocess", "eval(", "exec("]
            for pattern in dangerous:
                if pattern in code:
                    warnings.append(f"Potentially dangerous pattern detected: {pattern}")

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )

    async def estimate_cost(
        self,
        code: str | None,
        config: dict[str, Any] | None,
    ) -> float:
        """Estimate execution cost.

        Stub always returns 1.0 credit.
        """
        return 1.0

    async def health_check(self) -> dict[str, Any]:
        """Check backend health."""
        return {
            "backend": self.name,
            "healthy": True,
            "mode": "stub",
            "checked_at": datetime.utcnow().isoformat(),
        }


# Create singleton instance
_stub_backend = StubBackend()


def get_stub_backend() -> StubBackend:
    """Get the stub backend instance."""
    return _stub_backend
