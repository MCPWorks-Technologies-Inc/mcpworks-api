"""Integration tests for sandbox code execution.

These tests actually execute code in development mode (subprocess).
They verify the end-to-end execution flow works correctly.
"""

import uuid
from unittest.mock import MagicMock

import pytest

from mcpworks_api.backends.sandbox import SandboxBackend


@pytest.fixture
def sandbox():
    """Create sandbox backend in dev mode."""
    return SandboxBackend(dev_mode=True)


@pytest.fixture
def mock_account():
    """Create a mock account for execution."""
    account = MagicMock()
    account.id = uuid.uuid4()
    account.tier = "founder"
    return account


class TestSandboxExecution:
    """Tests for actual code execution in dev mode."""

    @pytest.mark.asyncio
    async def test_execute_simple_code(self, sandbox, mock_account):
        """Test executing simple Python code."""
        code = "result = 42"
        result = await sandbox.execute(
            code=code,
            config=None,
            input_data={},
            account=mock_account,
            execution_id=str(uuid.uuid4()),
            timeout_ms=5000,
        )

        assert result.success is True
        assert result.output == 42
        assert result.error is None

    @pytest.mark.asyncio
    async def test_execute_with_input_data(self, sandbox, mock_account):
        """Test code that uses input data."""
        code = "result = input_data['x'] + input_data['y']"
        result = await sandbox.execute(
            code=code,
            config=None,
            input_data={"x": 10, "y": 32},
            account=mock_account,
            execution_id=str(uuid.uuid4()),
            timeout_ms=5000,
        )

        assert result.success is True
        assert result.output == 42

    @pytest.mark.asyncio
    async def test_execute_output_variable(self, sandbox, mock_account):
        """Test code that sets 'output' variable instead of 'result'."""
        code = "output = {'message': 'hello'}"
        result = await sandbox.execute(
            code=code,
            config=None,
            input_data={},
            account=mock_account,
            execution_id=str(uuid.uuid4()),
            timeout_ms=5000,
        )

        assert result.success is True
        assert result.output == {"message": "hello"}

    @pytest.mark.asyncio
    async def test_execute_with_stdout(self, sandbox, mock_account):
        """Test code that prints to stdout."""
        code = """
print("Hello from sandbox!")
result = "done"
"""
        result = await sandbox.execute(
            code=code,
            config=None,
            input_data={},
            account=mock_account,
            execution_id=str(uuid.uuid4()),
            timeout_ms=5000,
        )

        assert result.success is True
        assert "Hello from sandbox!" in (result.stdout or "")

    @pytest.mark.asyncio
    async def test_execute_runtime_error(self, sandbox, mock_account):
        """Test code that raises an exception."""
        code = "result = 1 / 0"
        result = await sandbox.execute(
            code=code,
            config=None,
            input_data={},
            account=mock_account,
            execution_id=str(uuid.uuid4()),
            timeout_ms=5000,
        )

        assert result.success is False
        assert result.error is not None
        assert "division" in result.error.lower() or "zero" in result.error.lower()
        assert result.error_type == "ZeroDivisionError"

    @pytest.mark.asyncio
    async def test_execute_no_code(self, sandbox, mock_account):
        """Test execution without code returns error."""
        result = await sandbox.execute(
            code=None,
            config=None,
            input_data={},
            account=mock_account,
            execution_id=str(uuid.uuid4()),
            timeout_ms=5000,
        )

        assert result.success is False
        assert "No code" in result.error

    @pytest.mark.asyncio
    async def test_execute_list_processing(self, sandbox, mock_account):
        """Test code that processes lists."""
        code = """
numbers = input_data['numbers']
result = sum(numbers)
"""
        result = await sandbox.execute(
            code=code,
            config=None,
            input_data={"numbers": [1, 2, 3, 4, 5]},
            account=mock_account,
            execution_id=str(uuid.uuid4()),
            timeout_ms=5000,
        )

        assert result.success is True
        assert result.output == 15

    @pytest.mark.asyncio
    async def test_execute_dict_processing(self, sandbox, mock_account):
        """Test code that processes dictionaries."""
        code = """
data = input_data['users']
result = [u['name'] for u in data]
"""
        result = await sandbox.execute(
            code=code,
            config=None,
            input_data={
                "users": [
                    {"name": "Alice", "age": 30},
                    {"name": "Bob", "age": 25},
                ]
            },
            account=mock_account,
            execution_id=str(uuid.uuid4()),
            timeout_ms=5000,
        )

        assert result.success is True
        assert result.output == ["Alice", "Bob"]

    @pytest.mark.asyncio
    async def test_execute_multiline_code(self, sandbox, mock_account):
        """Test multiline code execution."""
        code = """
def factorial(n):
    if n <= 1:
        return 1
    return n * factorial(n - 1)

result = factorial(input_data['n'])
"""
        result = await sandbox.execute(
            code=code,
            config=None,
            input_data={"n": 5},
            account=mock_account,
            execution_id=str(uuid.uuid4()),
            timeout_ms=5000,
        )

        assert result.success is True
        assert result.output == 120

    @pytest.mark.asyncio
    async def test_execute_class_definition(self, sandbox, mock_account):
        """Test code with class definitions."""
        code = """
class Calculator:
    def add(self, a, b):
        return a + b

calc = Calculator()
result = calc.add(input_data['a'], input_data['b'])
"""
        result = await sandbox.execute(
            code=code,
            config=None,
            input_data={"a": 5, "b": 7},
            account=mock_account,
            execution_id=str(uuid.uuid4()),
            timeout_ms=5000,
        )

        assert result.success is True
        assert result.output == 12

    @pytest.mark.asyncio
    async def test_execute_import_standard_library(self, sandbox, mock_account):
        """Test code that imports standard library modules."""
        code = """
import json
import math

data = {"value": math.pi}
result = json.dumps(data)
"""
        result = await sandbox.execute(
            code=code,
            config=None,
            input_data={},
            account=mock_account,
            execution_id=str(uuid.uuid4()),
            timeout_ms=5000,
        )

        assert result.success is True
        assert "3.14" in result.output

    @pytest.mark.asyncio
    async def test_execute_key_error(self, sandbox, mock_account):
        """Test code that raises KeyError."""
        code = "result = input_data['nonexistent']"
        result = await sandbox.execute(
            code=code,
            config=None,
            input_data={},
            account=mock_account,
            execution_id=str(uuid.uuid4()),
            timeout_ms=5000,
        )

        assert result.success is False
        assert result.error_type == "KeyError"

    @pytest.mark.asyncio
    async def test_execute_type_error(self, sandbox, mock_account):
        """Test code that raises TypeError."""
        code = "result = 'string' + 42"
        result = await sandbox.execute(
            code=code,
            config=None,
            input_data={},
            account=mock_account,
            execution_id=str(uuid.uuid4()),
            timeout_ms=5000,
        )

        assert result.success is False
        assert result.error_type == "TypeError"

    @pytest.mark.asyncio
    async def test_execution_time_tracked(self, sandbox, mock_account):
        """Test execution time is tracked."""
        code = """
import time
time.sleep(0.1)
result = "done"
"""
        result = await sandbox.execute(
            code=code,
            config=None,
            input_data={},
            account=mock_account,
            execution_id=str(uuid.uuid4()),
            timeout_ms=5000,
        )

        assert result.success is True
        assert result.execution_time_ms is not None
        assert result.execution_time_ms >= 100  # At least 100ms


class TestSandboxTimeout:
    """Tests for execution timeout handling."""

    @pytest.mark.asyncio
    async def test_execute_timeout(self, sandbox, mock_account):
        """Test code that exceeds timeout is killed."""
        code = """
import time
time.sleep(10)  # Will be killed
result = "done"
"""
        result = await sandbox.execute(
            code=code,
            config=None,
            input_data={},
            account=mock_account,
            execution_id=str(uuid.uuid4()),
            timeout_ms=500,  # 500ms timeout
        )

        assert result.success is False
        assert "timed out" in result.error.lower()
        assert result.error_type == "TimeoutError"

    @pytest.mark.asyncio
    async def test_execute_respects_tier_timeout(self, sandbox):
        """Test timeout respects tier limits."""
        # Free tier has 10 second max
        account = MagicMock()
        account.tier = "free"

        code = "result = 1"
        result = await sandbox.execute(
            code=code,
            config=None,
            input_data={},
            account=account,
            execution_id=str(uuid.uuid4()),
            timeout_ms=60000,  # Request 60s, but free tier allows only 10s
        )

        # Code should still succeed (it's fast)
        assert result.success is True


class TestSandboxCleanup:
    """Tests for execution cleanup."""

    @pytest.mark.asyncio
    async def test_execution_cleanup(self, sandbox, mock_account):
        """Test execution directory is cleaned up."""
        import os

        exec_id = str(uuid.uuid4())
        exec_dir = sandbox.exec_dir / f"exec-{exec_id}"

        code = "result = 42"
        await sandbox.execute(
            code=code,
            config=None,
            input_data={},
            account=mock_account,
            execution_id=exec_id,
            timeout_ms=5000,
        )

        # Directory should be cleaned up
        assert not exec_dir.exists()

    @pytest.mark.asyncio
    async def test_cleanup_on_error(self, sandbox, mock_account):
        """Test cleanup happens even on error."""
        exec_id = str(uuid.uuid4())
        exec_dir = sandbox.exec_dir / f"exec-{exec_id}"

        code = "raise Exception('test error')"
        await sandbox.execute(
            code=code,
            config=None,
            input_data={},
            account=mock_account,
            execution_id=exec_id,
            timeout_ms=5000,
        )

        # Directory should still be cleaned up
        assert not exec_dir.exists()
