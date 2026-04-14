"""Tests for execution service query helpers."""

from mcpworks_api.services.execution import _to_detail, _to_summary


class FakeExecution:
    def __init__(self, **kwargs):
        defaults = {
            "id": "00000000-0000-0000-0000-000000000001",
            "namespace_id": "00000000-0000-0000-0000-000000000002",
            "service_name": "social",
            "function_name": "post-to-bluesky",
            "function_version_num": 2,
            "status": "completed",
            "error_message": None,
            "execution_time_ms": 1250,
            "started_at": None,
            "completed_at": None,
            "backend": "code_sandbox",
            "input_data": {"text": "hello"},
            "result_data": {"success": True},
            "error_code": None,
            "backend_metadata": None,
            "created_at": None,
            "agent_run_id": None,
        }
        defaults.update(kwargs)
        for k, v in defaults.items():
            setattr(self, k, v)


class TestToSummary:
    def test_basic_fields(self):
        e = FakeExecution()
        s = _to_summary(e)
        assert s["id"] == "00000000-0000-0000-0000-000000000001"
        assert s["service"] == "social"
        assert s["function"] == "post-to-bluesky"
        assert s["version"] == 2
        assert s["status"] == "completed"
        assert s["execution_time_ms"] == 1250

    def test_failed_execution(self):
        e = FakeExecution(status="failed", error_message="Text too long")
        s = _to_summary(e)
        assert s["status"] == "failed"
        assert s["error_message"] == "Text too long"

    def test_none_namespace(self):
        e = FakeExecution(namespace_id=None)
        s = _to_summary(e)
        assert s["namespace_id"] is None


class TestToDetail:
    def test_includes_summary_fields(self):
        e = FakeExecution()
        d = _to_detail(e)
        assert d["service"] == "social"
        assert d["function"] == "post-to-bluesky"
        assert d["status"] == "completed"

    def test_includes_input_output(self):
        e = FakeExecution()
        d = _to_detail(e)
        assert d["input_data"] == {"text": "hello"}
        assert d["result_data"] == {"success": True}
        assert d["backend"] == "code_sandbox"

    def test_includes_stdout_stderr_from_metadata(self):
        e = FakeExecution(backend_metadata={"stdout": "print output", "stderr": "warning msg"})
        d = _to_detail(e)
        assert d["stdout"] == "print output"
        assert d["stderr"] == "warning msg"

    def test_no_metadata(self):
        e = FakeExecution(backend_metadata=None)
        d = _to_detail(e)
        assert d["stdout"] is None
        assert d["stderr"] is None

    def test_failed_with_error(self):
        e = FakeExecution(
            status="failed",
            error_message="Timeout",
            error_code="EXECUTION_TIMEOUT",
            result_data=None,
        )
        d = _to_detail(e)
        assert d["error_message"] == "Timeout"
        assert d["error_code"] == "EXECUTION_TIMEOUT"
        assert d["result_data"] is None
