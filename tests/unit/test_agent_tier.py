"""Unit tests for agent tier mappings and configuration.

Tests SubscriptionTier agent properties, AGENT_TIER_CONFIG completeness,
and billing middleware TIER_LIMITS coverage.
"""

from mcpworks_api.middleware.billing import BillingMiddleware
from mcpworks_api.models.subscription import AGENT_TIER_CONFIG, SubscriptionTier


class TestSubscriptionTierIsAgent:
    def test_builder_agent_is_agent_tier(self):
        assert SubscriptionTier.BUILDER_AGENT.is_agent_tier is True

    def test_pro_agent_is_agent_tier(self):
        assert SubscriptionTier.PRO_AGENT.is_agent_tier is True

    def test_enterprise_agent_is_agent_tier(self):
        assert SubscriptionTier.ENTERPRISE_AGENT.is_agent_tier is True

    def test_free_is_not_agent_tier(self):
        assert SubscriptionTier.FREE.is_agent_tier is False

    def test_builder_is_not_agent_tier(self):
        assert SubscriptionTier.BUILDER.is_agent_tier is False

    def test_pro_is_not_agent_tier(self):
        assert SubscriptionTier.PRO.is_agent_tier is False

    def test_enterprise_is_not_agent_tier(self):
        assert SubscriptionTier.ENTERPRISE.is_agent_tier is False


class TestFunctionsTierMapping:
    def test_builder_agent_maps_to_builder(self):
        assert SubscriptionTier.BUILDER_AGENT.functions_tier == SubscriptionTier.BUILDER

    def test_pro_agent_maps_to_pro(self):
        assert SubscriptionTier.PRO_AGENT.functions_tier == SubscriptionTier.PRO

    def test_enterprise_agent_maps_to_enterprise(self):
        assert SubscriptionTier.ENTERPRISE_AGENT.functions_tier == SubscriptionTier.ENTERPRISE

    def test_non_agent_tier_maps_to_self(self):
        assert SubscriptionTier.FREE.functions_tier == SubscriptionTier.FREE
        assert SubscriptionTier.BUILDER.functions_tier == SubscriptionTier.BUILDER
        assert SubscriptionTier.PRO.functions_tier == SubscriptionTier.PRO
        assert SubscriptionTier.ENTERPRISE.functions_tier == SubscriptionTier.ENTERPRISE


class TestMonthlyExecutions:
    def test_agent_tiers_match_base_tiers(self):
        assert SubscriptionTier.BUILDER_AGENT.monthly_executions == 25_000
        assert SubscriptionTier.PRO_AGENT.monthly_executions == 250_000
        assert SubscriptionTier.ENTERPRISE_AGENT.monthly_executions == 1_000_000

    def test_base_tiers(self):
        assert SubscriptionTier.FREE.monthly_executions == 1_000
        assert SubscriptionTier.BUILDER.monthly_executions == 25_000
        assert SubscriptionTier.PRO.monthly_executions == 250_000
        assert SubscriptionTier.ENTERPRISE.monthly_executions == 1_000_000


class TestAgentTierConfig:
    AGENT_TIERS = ["builder-agent", "pro-agent", "enterprise-agent"]

    def test_all_agent_tiers_present(self):
        for tier in self.AGENT_TIERS:
            assert tier in AGENT_TIER_CONFIG, f"{tier} missing from AGENT_TIER_CONFIG"

    def test_required_keys_present(self):
        required = {
            "max_agents",
            "memory_limit_mb",
            "cpu_limit",
            "min_schedule_seconds",
            "max_state_bytes",
            "run_retention_days",
            "max_webhook_payload_bytes",
        }
        for tier, config in AGENT_TIER_CONFIG.items():
            missing = required - set(config.keys())
            assert not missing, f"{tier} missing keys: {missing}"

    def test_max_agents_ascending(self):
        assert AGENT_TIER_CONFIG["builder-agent"]["max_agents"] == 1
        assert AGENT_TIER_CONFIG["pro-agent"]["max_agents"] == 5
        assert AGENT_TIER_CONFIG["enterprise-agent"]["max_agents"] == 20

    def test_memory_limit_ascending(self):
        assert AGENT_TIER_CONFIG["builder-agent"]["memory_limit_mb"] == 256
        assert AGENT_TIER_CONFIG["pro-agent"]["memory_limit_mb"] == 512
        assert AGENT_TIER_CONFIG["enterprise-agent"]["memory_limit_mb"] == 1024

    def test_cpu_limit_ascending(self):
        assert AGENT_TIER_CONFIG["builder-agent"]["cpu_limit"] == 0.25
        assert AGENT_TIER_CONFIG["pro-agent"]["cpu_limit"] == 0.5
        assert AGENT_TIER_CONFIG["enterprise-agent"]["cpu_limit"] == 1.0

    def test_min_schedule_descending(self):
        assert AGENT_TIER_CONFIG["builder-agent"]["min_schedule_seconds"] == 300
        assert AGENT_TIER_CONFIG["pro-agent"]["min_schedule_seconds"] == 30
        assert AGENT_TIER_CONFIG["enterprise-agent"]["min_schedule_seconds"] == 15

    def test_state_size_ascending(self):
        b = AGENT_TIER_CONFIG["builder-agent"]["max_state_bytes"]
        p = AGENT_TIER_CONFIG["pro-agent"]["max_state_bytes"]
        e = AGENT_TIER_CONFIG["enterprise-agent"]["max_state_bytes"]
        assert b < p < e

    def test_retention_ascending(self):
        assert AGENT_TIER_CONFIG["builder-agent"]["run_retention_days"] == 7
        assert AGENT_TIER_CONFIG["pro-agent"]["run_retention_days"] == 30
        assert AGENT_TIER_CONFIG["enterprise-agent"]["run_retention_days"] == 90

    def test_no_extra_tiers(self):
        assert len(AGENT_TIER_CONFIG) == 3


class TestBillingTierLimits:
    def test_agent_tiers_in_billing(self):
        limits = BillingMiddleware.TIER_LIMITS
        assert "builder-agent" in limits
        assert "pro-agent" in limits
        assert "enterprise-agent" in limits

    def test_agent_tier_limits_match_base(self):
        limits = BillingMiddleware.TIER_LIMITS
        assert limits["builder-agent"] == limits["builder"]
        assert limits["pro-agent"] == limits["pro"]
        assert limits["enterprise-agent"] == limits["enterprise"]

    def test_all_subscription_tiers_covered(self):
        limits = BillingMiddleware.TIER_LIMITS
        for tier in SubscriptionTier:
            assert tier.value in limits, f"{tier.value} missing from TIER_LIMITS"
