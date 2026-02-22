"""Tests for credential scanning in function code submissions."""

from mcpworks_api.sandbox.credential_scan import scan_code_for_credentials


class TestAWSKeys:
    def test_aws_access_key(self):
        code = 'aws_key = "AKIAIOSFODNN7EXAMPLE"'
        warnings = scan_code_for_credentials(code)
        assert len(warnings) == 1
        assert "AWS access key" in warnings[0]
        assert "line 1" in warnings[0]

    def test_aws_secret_key(self):
        code = 'aws_secret = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"'
        warnings = scan_code_for_credentials(code)
        assert any("AWS secret key" in w for w in warnings)

    def test_aws_secret_key_colon_syntax(self):
        code = 'secret_access_key: "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"'
        warnings = scan_code_for_credentials(code)
        assert any("AWS secret key" in w for w in warnings)


class TestAPIKeys:
    def test_openai_sk_prefix(self):
        code = 'key = "sk-proj-abcdefghijklmnopqrstuvwx"'
        warnings = scan_code_for_credentials(code)
        assert any("API key" in w for w in warnings)

    def test_stripe_live_key(self):
        code = 'STRIPE_KEY = "sk_live_abcdefghijklmnopqrstuvwx"'
        warnings = scan_code_for_credentials(code)
        assert any("API key" in w for w in warnings)

    def test_stripe_test_key(self):
        code = 'key = "sk_test_abcdefghijklmnopqrstuvwx"'
        warnings = scan_code_for_credentials(code)
        assert any("API key" in w for w in warnings)

    def test_rk_live_key(self):
        code = 'key = "rk_live_abcdefghijklmnopqrstuvwx"'
        warnings = scan_code_for_credentials(code)
        assert any("API key" in w for w in warnings)


class TestGitHubTokens:
    def test_ghp_token(self):
        code = 'token = "ghp_abcdefghijklmnopqrstuvwxyz12"'
        warnings = scan_code_for_credentials(code)
        assert any("GitHub token" in w for w in warnings)

    def test_ghs_token(self):
        code = 'token = "ghs_abcdefghijklmnopqrstuvwxyz12"'
        warnings = scan_code_for_credentials(code)
        assert any("GitHub token" in w for w in warnings)

    def test_github_pat(self):
        code = 'token = "github_pat_abcdefghijklmnopqrstuvwxyz12"'
        warnings = scan_code_for_credentials(code)
        assert any("GitHub token" in w for w in warnings)


class TestPrivateKeys:
    def test_rsa_private_key(self):
        code = '-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIB...'
        warnings = scan_code_for_credentials(code)
        assert any("private key" in w for w in warnings)

    def test_ec_private_key(self):
        code = '-----BEGIN EC PRIVATE KEY-----'
        warnings = scan_code_for_credentials(code)
        assert any("private key" in w for w in warnings)

    def test_generic_private_key(self):
        code = '-----BEGIN PRIVATE KEY-----'
        warnings = scan_code_for_credentials(code)
        assert any("private key" in w for w in warnings)


class TestJWT:
    def test_jwt_token(self):
        code = 'token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"'
        warnings = scan_code_for_credentials(code)
        assert any("JWT token" in w for w in warnings)


class TestConnectionStrings:
    def test_postgresql(self):
        code = 'db = "postgresql://admin:secretpass@db.example.com/mydb"'
        warnings = scan_code_for_credentials(code)
        assert any("connection string" in w for w in warnings)

    def test_mysql(self):
        code = 'db = "mysql://root:password@localhost/db"'
        warnings = scan_code_for_credentials(code)
        assert any("connection string" in w for w in warnings)

    def test_mongodb(self):
        code = 'db = "mongodb://user:pass@mongo.example.com/db"'
        warnings = scan_code_for_credentials(code)
        assert any("connection string" in w for w in warnings)

    def test_redis(self):
        code = 'r = "redis://default:mypassword@redis.example.com:6379"'
        warnings = scan_code_for_credentials(code)
        assert any("connection string" in w for w in warnings)


class TestHardcodedSecrets:
    def test_password_assignment(self):
        code = 'password = "my_super_secret_password"'
        warnings = scan_code_for_credentials(code)
        assert any("hardcoded secret" in w for w in warnings)

    def test_api_key_assignment(self):
        code = 'api_key = "abcdef123456789012"'
        warnings = scan_code_for_credentials(code)
        assert any("hardcoded secret" in w for w in warnings)

    def test_token_assignment(self):
        code = "token = 'long_token_value_here_abcdef'"
        warnings = scan_code_for_credentials(code)
        assert any("hardcoded secret" in w for w in warnings)

    def test_short_values_ignored(self):
        code = 'password = "short"'
        warnings = scan_code_for_credentials(code)
        assert not any("hardcoded secret" in w for w in warnings)


class TestOsEnvironAssignment:
    def test_os_environ_direct_set(self):
        code = 'os.environ["API_KEY"] = "my_secret_value"'
        warnings = scan_code_for_credentials(code)
        assert any("os.environ assignment" in w for w in warnings)


class TestLineNumbers:
    def test_reports_correct_line(self):
        code = "import os\n\n# line 3\npassword = \"supersecretpassword123\""
        warnings = scan_code_for_credentials(code)
        assert any("line 4" in w for w in warnings)

    def test_multiple_findings_different_lines(self):
        code = (
            'aws_key = "AKIAIOSFODNN7EXAMPLE"\n'
            "clean_line = 42\n"
            'token = "ghp_abcdefghijklmnopqrstuvwxyz12"'
        )
        warnings = scan_code_for_credentials(code)
        assert any("line 1" in w for w in warnings)
        assert any("line 3" in w for w in warnings)


class TestSafeCode:
    def test_normal_code(self):
        code = """
import json
import os

def handler(input):
    name = input.get("name", "World")
    return {"greeting": f"Hello, {name}!"}
"""
        assert scan_code_for_credentials(code) == []

    def test_env_var_read(self):
        code = 'api_key = os.environ.get("API_KEY")'
        assert scan_code_for_credentials(code) == []

    def test_required_env_usage(self):
        code = 'key = os.environ["OPENAI_API_KEY"]'
        assert scan_code_for_credentials(code) == []

    def test_empty_code(self):
        assert scan_code_for_credentials("") == []

    def test_base64_in_comments(self):
        code = "# Example: base64 encoded value\nresult = decode(data)"
        assert scan_code_for_credentials(code) == []

    def test_short_sk_prefix_not_matched(self):
        code = 'prefix = "sk-short"'
        assert scan_code_for_credentials(code) == []


class TestRequiredEnvSuggestion:
    def test_warning_suggests_required_env(self):
        code = 'key = "sk_live_abcdefghijklmnopqrstuvwx"'
        warnings = scan_code_for_credentials(code)
        assert all("required_env" in w for w in warnings)
