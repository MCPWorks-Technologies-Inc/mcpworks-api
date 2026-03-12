"""Code Execution Sandbox Backend.

Executes LLM-authored Python code in a secure, isolated environment.

In production:
- Uses nsjail with Linux namespaces, cgroups v2, seccomp-bpf
- Egress proxy for network allowlist enforcement
- Per-tier resource limits

In development (SANDBOX_DEV_MODE=true):
- Falls back to subprocess execution with basic isolation
- Not secure - for local testing only
"""

import ast
import asyncio
import contextlib
import json
import secrets
import shutil
import tempfile
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

import structlog

from mcpworks_api.backends.base import Backend, ExecutionResult, ValidationResult
from mcpworks_api.config import get_settings
from mcpworks_api.middleware.execution_metrics import (
    record_execution,
    record_violation,
    track_execution,
)
from mcpworks_api.models import Account

logger = structlog.get_logger(__name__)


class ExecutionTier(str, Enum):
    """Execution tier for resource limits."""

    FREE = "free"
    BUILDER = "builder"
    PRO = "pro"
    ENTERPRISE = "enterprise"


TIER_CONFIG = {
    ExecutionTier.FREE: {
        "timeout_sec": 10,
        "memory_mb": 128,
        "max_pids": 16,
        "network": False,
    },
    ExecutionTier.BUILDER: {
        "timeout_sec": 30,
        "memory_mb": 256,
        "max_pids": 32,
        "network": True,
    },
    ExecutionTier.PRO: {
        "timeout_sec": 90,
        "memory_mb": 512,
        "max_pids": 64,
        "network": True,
    },
    ExecutionTier.ENTERPRISE: {
        "timeout_sec": 300,
        "memory_mb": 2048,
        "max_pids": 128,
        "network": True,
    },
}

DEFAULT_TIER = ExecutionTier.FREE

AGENT_TIER_MAP = {
    "builder-agent": ExecutionTier.BUILDER,
    "pro-agent": ExecutionTier.PRO,
    "enterprise-agent": ExecutionTier.ENTERPRISE,
}


def resolve_execution_tier(tier_str: str) -> ExecutionTier:
    """Map a tier string (including agent tiers) to an ExecutionTier."""
    if tier_str in AGENT_TIER_MAP:
        return AGENT_TIER_MAP[tier_str]
    try:
        return ExecutionTier(tier_str)
    except ValueError:
        return DEFAULT_TIER


# Dangerous patterns to check (defense-in-depth; seccomp is the real protection)
DANGEROUS_PATTERNS = [
    "os.system",
    "subprocess",
    "ctypes",
    "__import__",
    "eval(",
    "exec(",
    "compile(",
    "builtins",
]


class SandboxBackend(Backend):
    """Code Execution Sandbox Backend.

    Executes Python code in a secure sandbox using nsjail.
    Falls back to subprocess execution in development mode.
    """

    def __init__(
        self,
        sandbox_config: Path | None = None,
        spawn_script: Path | None = None,
        dev_mode: bool | None = None,
    ):
        """Initialize sandbox backend.

        Args:
            sandbox_config: Path to nsjail config file.
            spawn_script: Path to spawn-sandbox.sh script.
            dev_mode: Override for development mode. Defaults to Settings.sandbox_dev_mode.
        """
        settings = get_settings()
        self.sandbox_config = sandbox_config or settings.sandbox_config_path
        self.spawn_script = spawn_script or settings.sandbox_spawn_script
        self.exec_dir = Path(tempfile.gettempdir()) / "mcpworks-sandbox"
        self.exec_dir.mkdir(exist_ok=True)

        # Development mode: use subprocess instead of nsjail
        if dev_mode is not None:
            self._dev_mode = dev_mode
        else:
            self._dev_mode = settings.sandbox_dev_mode

    @property
    def name(self) -> str:
        """Backend identifier."""
        return "code_sandbox"

    @property
    def description(self) -> str:
        """Human-readable description."""
        if self._dev_mode:
            return "Code sandbox (development mode - NOT SECURE)"
        return "Secure Python code execution sandbox"

    @property
    def supported_languages(self) -> list[str]:
        """Supported programming languages."""
        return ["python"]

    def _get_tier_config(self, account: Account) -> dict[str, Any]:
        """Get tier configuration for account.

        Args:
            account: The executing account.

        Returns:
            Tier configuration dict.
        """
        tier_value = DEFAULT_TIER.value
        if hasattr(account, "user") and account.user is not None:
            tier_value = account.user.effective_tier
        tier = resolve_execution_tier(tier_value)
        return TIER_CONFIG.get(tier, TIER_CONFIG[DEFAULT_TIER])

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
        """Execute Python code in sandbox.

        Args:
            code: Python source code to execute.
            config: Backend configuration (not used for code_sandbox).
            input_data: Input arguments passed to the code.
            account: The account executing the function.
            execution_id: Unique execution identifier.
            timeout_ms: Maximum execution time in milliseconds.
            extra_files: Optional mapping of relative paths to file contents
                to write into the execution directory before running code.
                Used by code-mode to inject the ``functions/`` package.

        Returns:
            ExecutionResult with output or error details.
        """
        if not code:
            return ExecutionResult(
                success=False,
                output=None,
                error="No code provided",
                error_type="ValidationError",
            )

        tier_config = self._get_tier_config(account)
        timeout_sec = min(timeout_ms / 1000, tier_config["timeout_sec"])

        tier = DEFAULT_TIER.value
        if hasattr(account, "user") and account.user is not None:
            tier = account.user.effective_tier
        namespace = getattr(account, "namespace", None) or "unknown"

        if self._dev_mode:
            return await self._execute_dev_mode(
                code=code,
                input_data=input_data,
                execution_id=execution_id,
                timeout_sec=timeout_sec,
                tier=tier,
                namespace=namespace,
                extra_files=extra_files,
                sandbox_env=sandbox_env,
            )
        else:
            return await self._execute_nsjail(
                code=code,
                input_data=input_data,
                account=account,
                execution_id=execution_id,
                timeout_sec=timeout_sec,
                tier_config=tier_config,
                tier=tier,
                namespace=namespace,
                extra_files=extra_files,
                sandbox_env=sandbox_env,
            )

    async def _execute_dev_mode(
        self,
        code: str,
        input_data: dict[str, Any],
        execution_id: str,
        timeout_sec: float,
        tier: str = DEFAULT_TIER.value,
        namespace: str = "unknown",
        extra_files: dict[str, str] | None = None,
        sandbox_env: dict[str, str] | None = None,
    ) -> ExecutionResult:
        """Execute code in development mode (subprocess, no isolation).

        WARNING: Not secure! For local development only.
        """
        start_time = datetime.now(UTC)
        exec_dir = self.exec_dir / f"exec-{execution_id}"

        try:
            exec_dir.mkdir(mode=0o755, exist_ok=True)

            # Write extra files (code-mode functions/ package, etc.)
            if extra_files:
                for rel_path, content in extra_files.items():
                    file_path = exec_dir / rel_path
                    file_path.parent.mkdir(parents=True, exist_ok=True)
                    file_path.write_text(content)

            # Write env vars file if provided (never logged, never persisted)
            if sandbox_env:
                (exec_dir / ".sandbox_env.json").write_text(json.dumps(sandbox_env))
                sandbox_env.clear()

            # Write input and code files
            input_file = exec_dir / "input.json"
            code_file = exec_dir / "user_code.py"
            output_file = exec_dir / "output.json"

            input_file.write_text(json.dumps(input_data, default=str))

            # Wrap code with execution harness
            wrapped_code = self._wrap_code(code)
            code_file.write_text(wrapped_code)

            result: ExecutionResult

            async with track_execution(tier=tier, namespace=namespace):
                # Execute with subprocess
                process = await asyncio.create_subprocess_exec(
                    "python3",
                    str(code_file),
                    str(input_file),
                    str(output_file),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=str(exec_dir),
                )

                try:
                    stdout, stderr = await asyncio.wait_for(
                        process.communicate(),
                        timeout=timeout_sec,
                    )
                except TimeoutError:
                    process.kill()
                    await process.wait()
                    result = ExecutionResult(
                        success=False,
                        output=None,
                        stdout=None,
                        stderr=None,
                        error="Execution timed out",
                        error_type="TimeoutError",
                        execution_time_ms=int(timeout_sec * 1000),
                    )
                    record_execution(
                        tier=tier,
                        status="timeout",
                        duration_seconds=timeout_sec,
                        error_type="TimeoutError",
                        namespace=namespace,
                    )
                    return result

                execution_time_ms = int((datetime.now(UTC) - start_time).total_seconds() * 1000)

                # Read output
                if output_file.exists():
                    try:
                        output_data = json.loads(output_file.read_text())
                        result = ExecutionResult(
                            success=output_data.get("success", False),
                            output=output_data.get("result"),
                            stdout=output_data.get("stdout", stdout.decode() if stdout else None),
                            stderr=output_data.get("stderr", stderr.decode() if stderr else None),
                            error=output_data.get("error"),
                            error_type=output_data.get("error_type"),
                            execution_time_ms=execution_time_ms,
                            call_log=output_data.get("call_log", []),
                        )
                        status = "success" if result.success else "failure"
                        record_execution(
                            tier=tier,
                            status=status,
                            duration_seconds=execution_time_ms / 1000,
                            error_type=result.error_type if not result.success else None,
                            namespace=namespace,
                        )
                        return result
                    except json.JSONDecodeError:
                        pass

                # No output file or parse error
                result = ExecutionResult(
                    success=process.returncode == 0,
                    output=None,
                    stdout=stdout.decode() if stdout else None,
                    stderr=stderr.decode() if stderr else None,
                    error="No structured output produced" if process.returncode != 0 else None,
                    error_type="ExecutionError" if process.returncode != 0 else None,
                    execution_time_ms=execution_time_ms,
                )
                status = "success" if result.success else "failure"
                record_execution(
                    tier=tier,
                    status=status,
                    duration_seconds=execution_time_ms / 1000,
                    error_type=result.error_type if not result.success else None,
                    namespace=namespace,
                )
                return result

        finally:
            # Cleanup
            if exec_dir.exists():
                shutil.rmtree(exec_dir, ignore_errors=True)

    async def _execute_nsjail(
        self,
        code: str,
        input_data: dict[str, Any],
        account: Account,
        execution_id: str,
        timeout_sec: float,
        tier_config: dict[str, Any],
        tier: str = DEFAULT_TIER.value,
        namespace: str = "unknown",
        extra_files: dict[str, str] | None = None,
        sandbox_env: dict[str, str] | None = None,
    ) -> ExecutionResult:
        """Execute code in nsjail sandbox.

        Requires nsjail and spawn-sandbox.sh to be installed.
        """
        start_time = datetime.now(UTC)
        exec_dir = self.exec_dir / f"exec-{execution_id}"

        try:
            exec_dir.mkdir(mode=0o755, exist_ok=True)

            # Write extra files (code-mode functions/ package, etc.)
            if extra_files:
                for rel_path, content in extra_files.items():
                    file_path = exec_dir / rel_path
                    file_path.parent.mkdir(parents=True, exist_ok=True)
                    file_path.write_text(content)

            # Write env vars file if provided (never logged, never persisted)
            if sandbox_env:
                (exec_dir / ".sandbox_env.json").write_text(json.dumps(sandbox_env))
                sandbox_env.clear()

            # Write input and code files
            (exec_dir / "input.json").write_text(json.dumps(input_data, default=str))
            (exec_dir / "user_code.py").write_text(code)

            # ORDER-003: Generate execution token via file (never env var or /proc)
            exec_token = secrets.token_urlsafe(32)
            token_file = exec_dir / ".exec_token"
            token_file.write_text(exec_token)

            result: ExecutionResult

            async with track_execution(tier=tier, namespace=namespace):
                # Spawn sandbox process
                process = await asyncio.create_subprocess_exec(
                    str(self.spawn_script),
                    execution_id,
                    tier,
                    str(exec_dir / "user_code.py"),
                    str(exec_dir / "input.json"),
                    namespace,
                    str(token_file),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )

                try:
                    stdout, stderr = await asyncio.wait_for(
                        process.communicate(),
                        timeout=timeout_sec + 5,  # Grace period
                    )
                except TimeoutError:
                    process.kill()
                    await process.wait()
                    result = ExecutionResult(
                        success=False,
                        output=None,
                        error="Execution timed out",
                        error_type="TimeoutError",
                        execution_time_ms=int(timeout_sec * 1000),
                    )
                    record_execution(
                        tier=tier,
                        status="timeout",
                        duration_seconds=timeout_sec,
                        error_type="TimeoutError",
                        namespace=namespace,
                    )
                    return result

                execution_time_ms = int((datetime.now(UTC) - start_time).total_seconds() * 1000)

                # Read output
                output_file = exec_dir / "output.json"
                if output_file.exists():
                    try:
                        output_data = json.loads(output_file.read_text())
                        result = ExecutionResult(
                            success=output_data.get("success", False),
                            output=output_data.get("result"),
                            stdout=output_data.get("stdout", ""),
                            stderr=output_data.get("stderr", ""),
                            error=output_data.get("error"),
                            error_type=output_data.get("error_type"),
                            execution_time_ms=execution_time_ms,
                            call_log=output_data.get("call_log", []),
                        )
                        status = "success" if result.success else "failure"
                        record_execution(
                            tier=tier,
                            status=status,
                            duration_seconds=execution_time_ms / 1000,
                            error_type=result.error_type if not result.success else None,
                            namespace=namespace,
                        )
                        return result
                    except json.JSONDecodeError:
                        pass

                # ORDER-022: Log sandbox violations (nsjail seccomp/resource kills)
                if process.returncode and process.returncode not in (0, 1):
                    record_violation(tier=tier)
                    asyncio.create_task(
                        self._log_sandbox_violation(
                            execution_id=execution_id,
                            account_id=str(getattr(account, "id", "")),
                            exit_code=process.returncode,
                            stderr_tail=(stderr.decode()[-500:] if stderr else ""),
                        )
                    )
                    asyncio.create_task(
                        self._send_violation_alert(
                            execution_id=execution_id,
                            tier=tier,
                            namespace=namespace,
                            exit_code=process.returncode,
                        )
                    )

                # Fallback if no output file
                result = ExecutionResult(
                    success=False,
                    output=None,
                    stdout=stdout.decode() if stdout else None,
                    stderr=stderr.decode() if stderr else None,
                    error="No output produced by sandbox",
                    error_type="ExecutionError",
                    execution_time_ms=execution_time_ms,
                )
                record_execution(
                    tier=tier,
                    status="error",
                    duration_seconds=execution_time_ms / 1000,
                    error_type="ExecutionError",
                    namespace=namespace,
                )
                return result

        finally:
            # Cleanup
            if exec_dir.exists():
                shutil.rmtree(exec_dir, ignore_errors=True)

    @staticmethod
    async def _log_sandbox_violation(
        execution_id: str,
        account_id: str,
        exit_code: int,
        stderr_tail: str,
    ) -> None:
        """ORDER-022: Fire-and-forget security event for sandbox violations."""
        from mcpworks_api.core.database import get_db_context
        from mcpworks_api.services.security_event import fire_security_event

        async with get_db_context() as db:
            await fire_security_event(
                db,
                event_type="sandbox.violation",
                severity="error",
                actor_id=account_id,
                details={
                    "execution_id": execution_id,
                    "exit_code": exit_code,
                    "stderr_tail": stderr_tail[:255],
                },
            )

    @staticmethod
    async def _send_violation_alert(
        execution_id: str,
        tier: str,
        namespace: str,
        exit_code: int,
    ) -> None:
        from mcpworks_api.services.discord_alerts import send_execution_alert

        with contextlib.suppress(Exception):
            await send_execution_alert(
                event="violation",
                execution_id=execution_id,
                tier=tier,
                namespace=namespace,
                exit_code=exit_code,
            )

    def _wrap_code(self, code: str) -> str:
        """Wrap user code with execution harness.

        Creates a wrapper that:
        - Reads input from input.json
        - Makes input available to user code
        - Captures result and writes to output.json
        - Handles errors gracefully
        """
        return f'''#!/usr/bin/env python3
"""MCPWorks Execution Wrapper - Development Mode"""

import json
import sys
import traceback
from io import StringIO

def main():
    # Get file paths from args
    if len(sys.argv) < 3:
        print("Usage: python user_code.py <input.json> <output.json>", file=sys.stderr)
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = sys.argv[2]

    # Read input
    try:
        with open(input_path, 'r') as f:
            input_data = json.load(f)
    except Exception as e:
        input_data = {{}}

    # Capture stdout/stderr
    old_stdout = sys.stdout
    old_stderr = sys.stderr
    captured_stdout = StringIO()
    captured_stderr = StringIO()
    sys.stdout = captured_stdout
    sys.stderr = captured_stderr

    result = None
    error = None
    error_type = None
    success = True

    try:
        # Execute user code
        exec_globals = {{"input_data": input_data, "__name__": "__main__"}}
        exec("""
{code}
""", exec_globals)

        # Get result: check explicit variable, then callable main()
        if 'result' in exec_globals:
            result = exec_globals['result']
        elif 'output' in exec_globals:
            result = exec_globals['output']
        elif callable(exec_globals.get('main')):
            result = exec_globals['main'](input_data)
        elif callable(exec_globals.get('handler')):
            result = exec_globals['handler'](input_data, {{}})

    except Exception as e:
        success = False
        error = str(e)
        error_type = type(e).__name__
        traceback.print_exc(file=captured_stderr)

    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr

    # Write output
    output = {{
        "success": success,
        "result": result,
        "stdout": captured_stdout.getvalue(),
        "stderr": captured_stderr.getvalue(),
        "error": error,
        "error_type": error_type,
    }}

    with open(output_path, 'w') as f:
        json.dump(output, f)

if __name__ == "__main__":
    main()
'''

    async def validate(
        self,
        code: str | None,
        config: dict[str, Any] | None,
    ) -> ValidationResult:
        """Validate Python code before saving.

        Checks:
        - Syntax validity
        - Code size limits
        - Dangerous patterns (defense-in-depth)
        """
        errors = []
        warnings = []

        if not code:
            errors.append("Code is required for code_sandbox backend")
            return ValidationResult(valid=False, errors=errors, warnings=warnings)

        # Check code size (1MB limit)
        if len(code) > 1024 * 1024:
            errors.append("Code exceeds maximum size (1MB)")

        # Check syntax
        try:
            ast.parse(code)
        except SyntaxError as e:
            errors.append(f"Syntax error: {e.msg} at line {e.lineno}")

        # Check for dangerous patterns (defense-in-depth)
        for pattern in DANGEROUS_PATTERNS:
            if pattern in code:
                warnings.append(
                    f"Potentially dangerous pattern detected: {pattern}. "
                    "This will be blocked by sandbox seccomp policy."
                )

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
        """Estimate execution cost in credits.

        Base cost: 1 credit per execution
        Additional cost based on code complexity.
        """
        base_cost = 1.0

        if code:
            # Add complexity cost (0.1 credits per 1KB)
            complexity_cost = len(code) / 10240  # 0.1 per KB
            return base_cost + min(complexity_cost, 5.0)  # Cap at 5 extra credits

        return base_cost

    async def health_check(self) -> dict[str, Any]:
        """Check sandbox health and availability."""
        nsjail_binary = Path("/usr/local/bin/nsjail")
        sandbox_packages = Path("/opt/mcpworks/sandbox-root/site-packages")

        nsjail_available = (
            nsjail_binary.exists() and self.spawn_script.exists() and self.sandbox_config.exists()
        )
        packages_available = sandbox_packages.is_dir()

        return {
            "backend": self.name,
            "healthy": True,
            "mode": "development" if self._dev_mode else "production",
            "nsjail_available": nsjail_available,
            "nsjail_binary": nsjail_binary.exists(),
            "sandbox_packages": packages_available,
            "exec_dir": str(self.exec_dir),
            "checked_at": datetime.now(UTC).isoformat(),
        }
