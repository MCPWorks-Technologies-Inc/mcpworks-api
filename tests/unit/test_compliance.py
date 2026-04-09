"""Unit tests for OWASP compliance evaluation service."""

from mcpworks_api.services.compliance import evaluate_compliance


class TestComplianceEvaluation:
    def test_empty_config_has_gaps(self):
        report = evaluate_compliance(
            namespace="test-ns",
            scanner_pipeline=None,
            access_rules_exist=False,
            sandbox_tier="free",
            auth_enabled=True,
            rate_limit_enabled=False,
            trust_scoring_enabled=False,
        )
        assert report["framework"] == "owasp-agentic-top-10"
        assert len(report["risks"]) == 10
        gap_count = sum(1 for r in report["risks"] if r["status"] == "gap")
        assert gap_count > 0
        assert report["grade"] in ("C", "D", "F")

    def test_full_config_scores_high(self):
        full_pipeline = {
            "scanners": [
                {
                    "type": "builtin",
                    "name": "pattern_scanner",
                    "direction": "both",
                    "enabled": True,
                },
                {
                    "type": "builtin",
                    "name": "secret_scanner",
                    "direction": "output",
                    "enabled": True,
                },
                {
                    "type": "builtin",
                    "name": "trust_boundary",
                    "direction": "output",
                    "enabled": True,
                },
                {
                    "type": "builtin",
                    "name": "pattern_scanner",
                    "direction": "input",
                    "enabled": True,
                },
            ]
        }
        report = evaluate_compliance(
            namespace="test-ns",
            scanner_pipeline=full_pipeline,
            access_rules_exist=True,
            sandbox_tier="builder",
            auth_enabled=True,
            rate_limit_enabled=True,
            trust_scoring_enabled=True,
        )
        assert report["grade"] in ("A", "B")
        assert report["coverage_pct"] >= 80

    def test_ten_risks_always_returned(self):
        report = evaluate_compliance(
            namespace="test-ns",
            scanner_pipeline=None,
            access_rules_exist=False,
            sandbox_tier="free",
            auth_enabled=False,
            rate_limit_enabled=False,
            trust_scoring_enabled=False,
        )
        assert len(report["risks"]) == 10
        ids = [r["id"] for r in report["risks"]]
        for i in range(1, 11):
            assert f"OWASP-AT-{i:02d}" in ids

    def test_grade_calculation(self):
        report = evaluate_compliance(
            namespace="test-ns",
            scanner_pipeline={
                "scanners": [
                    {
                        "type": "builtin",
                        "name": "pattern_scanner",
                        "direction": "input",
                        "enabled": True,
                    },
                    {
                        "type": "builtin",
                        "name": "secret_scanner",
                        "direction": "output",
                        "enabled": True,
                    },
                ]
            },
            access_rules_exist=True,
            sandbox_tier="builder",
            auth_enabled=True,
            rate_limit_enabled=True,
            trust_scoring_enabled=False,
        )
        assert report["grade"] in ("A", "B", "C", "D", "F")
        pct = report["coverage_pct"]
        grade = report["grade"]
        if pct >= 90:
            assert grade == "A"
        elif pct >= 80:
            assert grade == "B"
        elif pct >= 70:
            assert grade == "C"
        elif pct >= 60:
            assert grade == "D"
        else:
            assert grade == "F"

    def test_detail_full_includes_remediation(self):
        report = evaluate_compliance(
            namespace="test-ns",
            scanner_pipeline=None,
            access_rules_exist=False,
            sandbox_tier="free",
            auth_enabled=True,
            rate_limit_enabled=False,
            trust_scoring_enabled=False,
            detail="full",
        )
        gap_risks = [r for r in report["risks"] if r["status"] == "gap"]
        for risk in gap_risks:
            assert risk["remediation"] is not None

    def test_detail_summary_omits_remediation(self):
        report = evaluate_compliance(
            namespace="test-ns",
            scanner_pipeline=None,
            access_rules_exist=False,
            sandbox_tier="free",
            auth_enabled=True,
            rate_limit_enabled=False,
            trust_scoring_enabled=False,
            detail="summary",
        )
        for risk in report["risks"]:
            assert risk.get("remediation") is None
