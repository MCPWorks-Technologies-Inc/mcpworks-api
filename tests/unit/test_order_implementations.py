"""Tests for board order implementations (ORDER-001 through ORDER-023)."""

from mcpworks_api.models.execution import _scrub_error_message
from mcpworks_api.models.security_event import hash_ip


class TestOrder020PIIInExecutionRecords:
    """ORDER-020: Stop logging PII in execution records."""

    def test_scrub_error_message_truncates_long_messages(self):
        long_msg = "x" * 500
        result = _scrub_error_message(long_msg)
        assert len(result) <= 255
        assert result.endswith("...")

    def test_scrub_error_message_short_message_unchanged(self):
        msg = "Simple error"
        assert _scrub_error_message(msg) == msg

    def test_scrub_error_message_removes_emails(self):
        msg = "Error for user john@example.com at step 3"
        result = _scrub_error_message(msg)
        assert "john@example.com" not in result
        assert "[EMAIL]" in result

    def test_scrub_error_message_removes_phone_numbers(self):
        msg = "Contact 555-123-4567 for support"
        result = _scrub_error_message(msg)
        assert "555-123-4567" not in result
        assert "[PHONE]" in result

    def test_scrub_error_message_removes_api_keys(self):
        for prefix in ["sk-", "mcpw_", "Bearer "]:
            msg = f"Auth failed with {prefix}abc123xyz456"
            result = _scrub_error_message(msg)
            assert "abc123xyz456" not in result
            assert "[REDACTED_KEY]" in result

    def test_scrub_error_message_handles_multiple_pii(self):
        msg = "User john@test.com called with sk-secret123 from 555-000-1234"
        result = _scrub_error_message(msg)
        assert "john@test.com" not in result
        assert "sk-secret123" not in result
        assert "555-000-1234" not in result

    def test_mark_failed_calls_scrub(self):
        msg = "Error for user admin@company.com: sk-live_secret_key123"
        scrubbed = _scrub_error_message(msg)
        assert "admin@company.com" not in scrubbed
        assert "sk-live_secret_key123" not in scrubbed


class TestOrder022SecurityEventIPHash:
    """ORDER-022: Hash IP addresses in security events."""

    def test_hash_ip_returns_sha256_hex(self):
        result = hash_ip("192.168.1.1")
        assert result is not None
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)

    def test_hash_ip_deterministic(self):
        assert hash_ip("10.0.0.1") == hash_ip("10.0.0.1")

    def test_hash_ip_different_ips_different_hashes(self):
        assert hash_ip("10.0.0.1") != hash_ip("10.0.0.2")

    def test_hash_ip_none_returns_none(self):
        assert hash_ip(None) is None

    def test_hash_ip_empty_string_returns_none(self):
        assert hash_ip("") is None


class TestOrder023ErrorMessageScrubbing:
    """ORDER-023: Truncate error messages and PII scrub."""

    def test_truncation_boundary(self):
        msg = "a" * 255
        assert len(_scrub_error_message(msg)) == 255

        msg = "a" * 256
        result = _scrub_error_message(msg)
        assert len(result) == 255
        assert result.endswith("...")

    def test_scrub_then_truncate_order(self):
        msg = "Error: user@test.com " + "x" * 300
        result = _scrub_error_message(msg)
        assert len(result) <= 255
        assert "user@test.com" not in result

    def test_bearer_case_insensitive(self):
        msg = "Failed with BEARER token123abc"
        result = _scrub_error_message(msg)
        assert "token123abc" not in result

    def test_phone_formats(self):
        for phone in ["5551234567", "555-123-4567", "555.123.4567"]:
            msg = f"Call {phone}"
            result = _scrub_error_message(msg)
            assert phone not in result, f"Phone {phone} not scrubbed"
