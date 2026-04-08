"""Unit tests for Agent OS scanner."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcpworks_api.core.scanners.base import ScanContext


@pytest.fixture
def scan_context():
    return ScanContext(
        direction="input",
        namespace="test-ns",
        service="test-svc",
        function="test-fn",
        execution_id="exec-123",
        output_trust="prompt",
    )


class TestAgentOSScannerWithMockSDK:
    @pytest.fixture(autouse=True)
    def _setup_mock_sdk(self):
        mock_kernel = MagicMock()
        mock_result = MagicMock()
        mock_result.allowed = True
        mock_result.action = "pass"
        mock_kernel.execute = AsyncMock(return_value=mock_result)

        mock_module = MagicMock()
        mock_module.StatelessKernel.return_value = mock_kernel
        mock_module.ExecutionContext = MagicMock

        self.mock_kernel = mock_kernel
        self.mock_result = mock_result
        self.mock_module = mock_module

    async def test_yaml_policy_pass(self, scan_context):
        with patch.dict("sys.modules", {"agent_os": self.mock_module}):
            from mcpworks_api.core.scanners.agent_os_scanner import AgentOSScanner

            scanner = AgentOSScanner(
                config={"policy_format": "yaml", "policy": "version: '1.0'\nname: test\nrules: []"}
            )
            verdict = await scanner.scan("safe content", scan_context)
            assert verdict.action == "pass"
            assert verdict.scanner_name == "agent_os"

    async def test_cedar_policy_block(self, scan_context):
        self.mock_result.allowed = False
        self.mock_result.action = "deny"
        with patch.dict("sys.modules", {"agent_os": self.mock_module}):
            from mcpworks_api.core.scanners.agent_os_scanner import AgentOSScanner

            scanner = AgentOSScanner(
                config={"policy_format": "cedar", "policy": "forbid(principal, action, resource);"}
            )
            verdict = await scanner.scan("blocked content", scan_context)
            assert verdict.action == "block"

    async def test_rego_policy_pass(self, scan_context):
        with patch.dict("sys.modules", {"agent_os": self.mock_module}):
            from mcpworks_api.core.scanners.agent_os_scanner import AgentOSScanner

            scanner = AgentOSScanner(
                config={"policy_format": "rego", "policy": "package test\ndefault allow = true"}
            )
            verdict = await scanner.scan("some content", scan_context)
            assert verdict.action == "pass"


class TestAgentOSScannerGracefulDegradation:
    async def test_missing_package_returns_pass(self, scan_context):
        with patch.dict("sys.modules", {"agent_os": None}):
            import importlib

            import mcpworks_api.core.scanners.agent_os_scanner as mod

            importlib.reload(mod)

            scanner = mod.AgentOSScanner(config={"policy_format": "yaml", "policy": ""})
            verdict = await scanner.scan("content", scan_context)
            assert verdict.action == "pass"
            assert "not installed" in verdict.reason

    async def test_sdk_exception_returns_pass(self, scan_context):
        mock_kernel = MagicMock()
        mock_kernel.execute = AsyncMock(side_effect=RuntimeError("SDK error"))
        mock_module = MagicMock()
        mock_module.StatelessKernel.return_value = mock_kernel
        mock_module.ExecutionContext = MagicMock

        with patch.dict("sys.modules", {"agent_os": mock_module}):
            from mcpworks_api.core.scanners.agent_os_scanner import AgentOSScanner

            scanner = AgentOSScanner(config={"policy_format": "yaml", "policy": "version: '1.0'"})
            verdict = await scanner.scan("content", scan_context)
            assert verdict.action == "pass"
            assert "error" in verdict.reason.lower()
