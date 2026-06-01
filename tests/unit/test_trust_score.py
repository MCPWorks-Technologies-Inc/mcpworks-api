"""Unit tests for trust score service."""

from mcpworks_api.services.trust_score import (
    DEFAULT_DELTA,
    EVENT_DELTAS,
    TRUST_DEFAULT,
    TRUST_MAX,
    TRUST_MIN,
    TRUST_RECOVERY_CAP,
    TRUST_RECOVERY_DELTA,
    get_delta_for_event,
)


class TestTrustScoreConstants:
    def test_default_score(self):
        assert TRUST_DEFAULT == 500

    def test_score_bounds(self):
        assert TRUST_MIN == 0
        assert TRUST_MAX == 1000

    def test_recovery_cap_at_default(self):
        assert TRUST_RECOVERY_CAP == TRUST_DEFAULT

    def test_recovery_delta_is_one(self):
        assert TRUST_RECOVERY_DELTA == 1


class TestGetDeltaForEvent:
    def test_prompt_injection_delta(self):
        assert get_delta_for_event("scanner.prompt_injection") == -50

    def test_secret_leak_delta(self):
        assert get_delta_for_event("scanner.secret_leak") == -100

    def test_output_blocked_delta(self):
        assert get_delta_for_event("scanner.output_blocked") == -25

    def test_unauthorized_access_delta(self):
        assert get_delta_for_event("agent.unauthorized_access") == -50

    def test_unknown_event_uses_default(self):
        assert get_delta_for_event("some.unknown.event") == DEFAULT_DELTA

    def test_default_delta_is_negative(self):
        assert DEFAULT_DELTA < 0

    def test_all_event_deltas_are_negative(self):
        for event_type, delta in EVENT_DELTAS.items():
            assert delta < 0, f"{event_type} delta should be negative, got {delta}"
