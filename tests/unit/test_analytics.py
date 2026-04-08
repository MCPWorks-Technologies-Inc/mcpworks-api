"""Tests for the MCP proxy analytics service."""

import uuid
from collections import namedtuple
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcpworks_api.services.analytics import (
    PERIOD_MAP,
    get_function_stats,
    get_platform_token_savings,
    get_token_savings,
    record_execution_stats,
    record_proxy_call,
    suggest_optimizations,
)

NS_ID = uuid.uuid4()
NS_ID_2 = uuid.uuid4()


def _make_db_ctx():
    mock_db = MagicMock()
    mock_db.commit = AsyncMock()
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    return mock_db, mock_ctx


class TestRecordExecutionStats:
    @pytest.mark.asyncio
    async def test_records_with_input_bytes(self):
        mock_db, mock_ctx = _make_db_ctx()

        with patch("mcpworks_api.core.database.get_db_context", return_value=mock_ctx):
            await record_execution_stats(
                namespace_id=NS_ID,
                execution_id="exec-1",
                mcp_calls_count=0,
                mcp_bytes_total=0,
                result_bytes=200,
                input_bytes=5000,
            )
            mock_db.add.assert_called_once()
            stat = mock_db.add.call_args[0][0]
            assert stat.input_bytes == 5000
            assert stat.result_bytes == 200
            assert stat.tokens_saved_est == (5000 - 200) // 4

    @pytest.mark.asyncio
    async def test_tokens_saved_uses_max_of_mcp_and_input(self):
        mock_db, mock_ctx = _make_db_ctx()

        with patch("mcpworks_api.core.database.get_db_context", return_value=mock_ctx):
            await record_execution_stats(
                namespace_id=NS_ID,
                execution_id="exec-2",
                mcp_calls_count=3,
                mcp_bytes_total=10000,
                result_bytes=500,
                input_bytes=2000,
            )
            stat = mock_db.add.call_args[0][0]
            assert stat.tokens_saved_est == (10000 - 500) // 4

    @pytest.mark.asyncio
    async def test_tokens_saved_never_negative(self):
        mock_db, mock_ctx = _make_db_ctx()

        with patch("mcpworks_api.core.database.get_db_context", return_value=mock_ctx):
            await record_execution_stats(
                namespace_id=NS_ID,
                execution_id="exec-3",
                mcp_calls_count=0,
                mcp_bytes_total=0,
                result_bytes=1000,
                input_bytes=100,
            )
            stat = mock_db.add.call_args[0][0]
            assert stat.tokens_saved_est == 0

    @pytest.mark.asyncio
    async def test_db_error_does_not_raise(self):
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(side_effect=Exception("db down"))
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("mcpworks_api.core.database.get_db_context", return_value=mock_ctx):
            await record_execution_stats(
                namespace_id=NS_ID,
                execution_id="exec-4",
                mcp_calls_count=0,
                mcp_bytes_total=0,
                result_bytes=0,
                input_bytes=0,
            )


class TestRecordProxyCall:
    @pytest.mark.asyncio
    async def test_records_call(self):
        mock_db, mock_ctx = _make_db_ctx()

        with patch("mcpworks_api.core.database.get_db_context", return_value=mock_ctx):
            await record_proxy_call(
                namespace_id=NS_ID,
                server_name="google",
                tool_name="search",
                latency_ms=150,
                response_bytes=4000,
                status="success",
            )
            mock_db.add.assert_called_once()
            call = mock_db.add.call_args[0][0]
            assert call.response_tokens_est == 1000
            assert call.server_name == "google"

    @pytest.mark.asyncio
    async def test_db_error_does_not_raise(self):
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(side_effect=Exception("db down"))
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("mcpworks_api.core.database.get_db_context", return_value=mock_ctx):
            await record_proxy_call(
                namespace_id=NS_ID,
                server_name="google",
                tool_name="search",
                latency_ms=150,
                response_bytes=4000,
                status="success",
            )


def _mock_db_result(rows):
    mock_result = MagicMock()
    mock_result.all.return_value = rows
    mock_result.one.return_value = rows[0] if rows else None
    return mock_result


class TestGetTokenSavings:
    @pytest.mark.asyncio
    async def test_returns_savings_data(self):
        ExecRow = namedtuple(
            "ExecRow",
            [
                "total_input_bytes",
                "total_mcp_bytes",
                "total_result_bytes",
                "total_tokens_saved",
                "total_executions",
            ],
        )
        exec_row = ExecRow(
            total_input_bytes=50000,
            total_mcp_bytes=80000,
            total_result_bytes=2000,
            total_tokens_saved=19500,
            total_executions=100,
        )

        TopRow = namedtuple("TopRow", ["server_name", "tool_name", "total_bytes"])
        top_rows = [TopRow("google", "search", 30000)]

        db = AsyncMock()
        call_count = 0

        async def fake_execute(stmt):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_db_result([exec_row])
            return _mock_db_result(top_rows)

        db.execute = fake_execute

        result = await get_token_savings(db, NS_ID, "24h")

        assert result["total_executions"] == 100
        assert result["input_bytes"] == 50000
        assert result["mcp_data_processed_bytes"] == 80000
        assert result["result_returned_bytes"] == 2000
        assert result["tokens_saved_est"] == 19500
        assert result["savings_percent"] == 97.5
        assert len(result["top_consumers"]) == 1

    @pytest.mark.asyncio
    async def test_zero_data_returns_zero_savings(self):
        ExecRow = namedtuple(
            "ExecRow",
            [
                "total_input_bytes",
                "total_mcp_bytes",
                "total_result_bytes",
                "total_tokens_saved",
                "total_executions",
            ],
        )
        exec_row = ExecRow(
            total_input_bytes=None,
            total_mcp_bytes=None,
            total_result_bytes=None,
            total_tokens_saved=None,
            total_executions=0,
        )

        db = AsyncMock()
        call_count = 0

        async def fake_execute(stmt):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_db_result([exec_row])
            return _mock_db_result([])

        db.execute = fake_execute

        result = await get_token_savings(db, NS_ID, "24h")

        assert result["total_executions"] == 0
        assert result["savings_percent"] == 0
        assert result["tokens_saved_est"] == 0
        assert result["top_consumers"] == []


class TestGetFunctionStats:
    @pytest.mark.asyncio
    async def test_returns_stats(self):
        Row = namedtuple("Row", ["executions", "avg_calls", "avg_bytes", "avg_result", "avg_saved"])
        row = Row(
            executions=50, avg_calls=2.5, avg_bytes=8000.0, avg_result=400.0, avg_saved=1900.0
        )

        db = AsyncMock()

        async def fake_execute(stmt):
            return _mock_db_result([row])

        db.execute = fake_execute

        result = await get_function_stats(db, NS_ID, "7d")

        assert result["executions"] == 50
        assert result["avg_mcp_calls_per_execution"] == 2.5
        assert result["avg_tokens_saved"] == 1900

    @pytest.mark.asyncio
    async def test_zero_data(self):
        Row = namedtuple("Row", ["executions", "avg_calls", "avg_bytes", "avg_result", "avg_saved"])
        row = Row(executions=0, avg_calls=None, avg_bytes=None, avg_result=None, avg_saved=None)

        db = AsyncMock()

        async def fake_execute(stmt):
            return _mock_db_result([row])

        db.execute = fake_execute

        result = await get_function_stats(db, NS_ID, "24h")

        assert result["executions"] == 0
        assert result["avg_mcp_calls_per_execution"] == 0
        assert result["avg_tokens_saved"] == 0


class TestGetPlatformTokenSavings:
    @pytest.mark.asyncio
    async def test_returns_aggregate(self):
        Row = namedtuple(
            "Row",
            [
                "total_executions",
                "total_input_bytes",
                "total_mcp_bytes",
                "total_result_bytes",
                "total_tokens_saved",
                "active_namespaces",
            ],
        )
        row = Row(
            total_executions=500,
            total_input_bytes=200000,
            total_mcp_bytes=400000,
            total_result_bytes=10000,
            total_tokens_saved=97500,
            active_namespaces=5,
        )

        TopRow = namedtuple("TopRow", ["namespace_id", "tokens_saved", "executions"])
        top_rows = [
            TopRow(NS_ID, 50000, 250),
            TopRow(NS_ID_2, 30000, 150),
        ]

        db = AsyncMock()
        call_count = 0

        async def fake_execute(stmt):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_db_result([row])
            return _mock_db_result(top_rows)

        db.execute = fake_execute

        result = await get_platform_token_savings(db, "30d")

        assert result["total_executions"] == 500
        assert result["active_namespaces"] == 5
        assert result["savings_percent"] == 97.5
        assert len(result["top_namespaces"]) == 2

    @pytest.mark.asyncio
    async def test_empty_platform(self):
        Row = namedtuple(
            "Row",
            [
                "total_executions",
                "total_input_bytes",
                "total_mcp_bytes",
                "total_result_bytes",
                "total_tokens_saved",
                "active_namespaces",
            ],
        )
        row = Row(
            total_executions=0,
            total_input_bytes=None,
            total_mcp_bytes=None,
            total_result_bytes=None,
            total_tokens_saved=None,
            active_namespaces=0,
        )

        db = AsyncMock()
        call_count = 0

        async def fake_execute(stmt):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_db_result([row])
            return _mock_db_result([])

        db.execute = fake_execute

        result = await get_platform_token_savings(db, "30d")

        assert result["total_executions"] == 0
        assert result["savings_percent"] == 0
        assert result["top_namespaces"] == []


class TestSuggestOptimizations:
    @pytest.mark.asyncio
    async def test_large_response_suggestion(self):
        with patch(
            "mcpworks_api.services.analytics.get_server_stats",
            return_value={
                "server": "google",
                "period": "7d",
                "total_calls": 100,
                "total_errors": 0,
                "error_rate": 0,
                "tools": [
                    {
                        "name": "search",
                        "calls": 100,
                        "avg_latency_ms": 200,
                        "avg_response_bytes": 200000,
                        "avg_response_tokens_est": 50000,
                        "error_count": 0,
                        "timeout_count": 0,
                        "truncation_count": 0,
                        "injections_detected": 0,
                    }
                ],
            },
        ):
            db = AsyncMock()
            result = await suggest_optimizations(db, NS_ID, "google")

            assert len(result) == 1
            assert result[0]["type"] == "redact_fields"
            assert "195KB" in result[0]["reason"]

    @pytest.mark.asyncio
    async def test_high_error_rate_suggestion(self):
        with patch(
            "mcpworks_api.services.analytics.get_server_stats",
            return_value={
                "server": "slack",
                "period": "7d",
                "total_calls": 50,
                "total_errors": 15,
                "error_rate": 0.3,
                "tools": [
                    {
                        "name": "send_message",
                        "calls": 50,
                        "avg_latency_ms": 100,
                        "avg_response_bytes": 500,
                        "avg_response_tokens_est": 125,
                        "error_count": 15,
                        "timeout_count": 0,
                        "truncation_count": 0,
                        "injections_detected": 0,
                    }
                ],
            },
        ):
            db = AsyncMock()
            result = await suggest_optimizations(db, NS_ID, "slack")

            assert len(result) == 1
            assert result[0]["type"] == "check_health"

    @pytest.mark.asyncio
    async def test_high_timeout_rate_suggestion(self):
        with patch(
            "mcpworks_api.services.analytics.get_server_stats",
            return_value={
                "server": "slow-api",
                "period": "7d",
                "total_calls": 100,
                "total_errors": 0,
                "error_rate": 0,
                "tools": [
                    {
                        "name": "query",
                        "calls": 100,
                        "avg_latency_ms": 25000,
                        "avg_response_bytes": 1000,
                        "avg_response_tokens_est": 250,
                        "error_count": 0,
                        "timeout_count": 20,
                        "truncation_count": 0,
                        "injections_detected": 0,
                    }
                ],
            },
        ):
            db = AsyncMock()
            result = await suggest_optimizations(db, NS_ID, "slow-api")

            assert len(result) == 1
            assert result[0]["type"] == "increase_timeout"

    @pytest.mark.asyncio
    async def test_truncation_suggestion(self):
        with patch(
            "mcpworks_api.services.analytics.get_server_stats",
            return_value={
                "server": "big-api",
                "period": "7d",
                "total_calls": 100,
                "total_errors": 0,
                "error_rate": 0,
                "tools": [
                    {
                        "name": "dump",
                        "calls": 100,
                        "avg_latency_ms": 200,
                        "avg_response_bytes": 50000,
                        "avg_response_tokens_est": 12500,
                        "error_count": 0,
                        "timeout_count": 0,
                        "truncation_count": 10,
                        "injections_detected": 0,
                    }
                ],
            },
        ):
            db = AsyncMock()
            result = await suggest_optimizations(db, NS_ID, "big-api")

            assert len(result) == 1
            assert result[0]["type"] == "reduce_response_size"

    @pytest.mark.asyncio
    async def test_no_suggestions_for_healthy_tool(self):
        with patch(
            "mcpworks_api.services.analytics.get_server_stats",
            return_value={
                "server": "healthy",
                "period": "7d",
                "total_calls": 100,
                "total_errors": 1,
                "error_rate": 0.01,
                "tools": [
                    {
                        "name": "get",
                        "calls": 100,
                        "avg_latency_ms": 50,
                        "avg_response_bytes": 2000,
                        "avg_response_tokens_est": 500,
                        "error_count": 1,
                        "timeout_count": 0,
                        "truncation_count": 0,
                        "injections_detected": 0,
                    }
                ],
            },
        ):
            db = AsyncMock()
            result = await suggest_optimizations(db, NS_ID, "healthy")

            assert len(result) == 0


class TestPeriodMap:
    def test_all_periods_exist(self):
        assert "1h" in PERIOD_MAP
        assert "24h" in PERIOD_MAP
        assert "7d" in PERIOD_MAP
        assert "30d" in PERIOD_MAP

    def test_period_durations(self):
        assert PERIOD_MAP["1h"] == timedelta(hours=1)
        assert PERIOD_MAP["24h"] == timedelta(hours=24)
        assert PERIOD_MAP["7d"] == timedelta(days=7)
        assert PERIOD_MAP["30d"] == timedelta(days=30)
