"""Unit tests for envelope encryption module (core/encryption.py).

Target: 95% coverage.
"""

import base64
import os
from unittest.mock import patch

import pytest
from cryptography.exceptions import InvalidTag

from mcpworks_api.core import encryption
from mcpworks_api.core.encryption import (
    decrypt_dek,
    decrypt_string,
    decrypt_value,
    encrypt_dek,
    encrypt_string,
    encrypt_value,
    generate_dek,
)

TEST_KEK = os.urandom(32)
TEST_KEK_B64 = base64.b64encode(TEST_KEK).decode()


@pytest.fixture(autouse=True)
def _reset_kek():
    encryption._kek = None
    yield
    encryption._kek = None


@pytest.fixture(autouse=True)
def _mock_settings():
    with patch("mcpworks_api.config.get_settings") as mock:
        mock.return_value.encryption_kek_b64 = TEST_KEK_B64
        yield mock


class TestGenerateDEK:
    def test_returns_32_bytes(self):
        dek = generate_dek()
        assert isinstance(dek, bytes)
        assert len(dek) == 32

    def test_unique_each_call(self):
        assert generate_dek() != generate_dek()


class TestEncryptDecryptDEK:
    def test_round_trip(self):
        dek = generate_dek()
        encrypted = encrypt_dek(dek, kek=TEST_KEK)
        decrypted = decrypt_dek(encrypted, kek=TEST_KEK)
        assert decrypted == dek

    def test_encrypted_dek_is_nonce_plus_ciphertext(self):
        dek = generate_dek()
        encrypted = encrypt_dek(dek, kek=TEST_KEK)
        assert len(encrypted) == 12 + 32 + 16  # nonce + dek + GCM tag

    def test_wrong_kek_fails(self):
        dek = generate_dek()
        encrypted = encrypt_dek(dek, kek=TEST_KEK)
        wrong_kek = os.urandom(32)
        with pytest.raises(InvalidTag):
            decrypt_dek(encrypted, kek=wrong_kek)

    def test_uses_global_kek_when_none_provided(self):
        dek = generate_dek()
        encrypted = encrypt_dek(dek)
        decrypted = decrypt_dek(encrypted)
        assert decrypted == dek

    def test_tampered_ciphertext_fails(self):
        dek = generate_dek()
        encrypted = bytearray(encrypt_dek(dek, kek=TEST_KEK))
        encrypted[-1] ^= 0xFF
        with pytest.raises(InvalidTag):
            decrypt_dek(bytes(encrypted), kek=TEST_KEK)


class TestEncryptDecryptValue:
    def test_round_trip_dict(self):
        original = {"api_key": "sk-test-123", "nested": {"a": 1}}  # pragma: allowlist secret
        ciphertext, encrypted_dek = encrypt_value(original)
        decrypted = decrypt_value(ciphertext, encrypted_dek)
        assert decrypted == original

    def test_round_trip_string(self):
        ciphertext, encrypted_dek = encrypt_value("hello world")
        assert decrypt_value(ciphertext, encrypted_dek) == "hello world"

    def test_round_trip_number(self):
        ciphertext, encrypted_dek = encrypt_value(42)
        assert decrypt_value(ciphertext, encrypted_dek) == 42

    def test_round_trip_list(self):
        original = [1, "two", {"three": 3}]
        ciphertext, encrypted_dek = encrypt_value(original)
        assert decrypt_value(ciphertext, encrypted_dek) == original

    def test_round_trip_null(self):
        ciphertext, encrypted_dek = encrypt_value(None)
        assert decrypt_value(ciphertext, encrypted_dek) is None

    def test_ciphertext_not_plaintext(self):
        original = {"secret": "this should be encrypted"}  # pragma: allowlist secret
        ciphertext, _ = encrypt_value(original)
        assert b"secret" not in ciphertext
        assert b"encrypted" not in ciphertext

    def test_unique_ciphertext_per_call(self):
        ct1, _ = encrypt_value("same data")
        ct2, _ = encrypt_value("same data")
        assert ct1 != ct2

    def test_unique_dek_per_call(self):
        _, dek1 = encrypt_value("same data")
        _, dek2 = encrypt_value("same data")
        assert dek1 != dek2


class TestEncryptDecryptString:
    def test_round_trip(self):
        original = "sk-ant-api03-secret-key"
        ciphertext, encrypted_dek = encrypt_string(original)
        assert decrypt_string(ciphertext, encrypted_dek) == original

    def test_unicode(self):
        original = "héllo wörld 🔑"
        ciphertext, encrypted_dek = encrypt_string(original)
        assert decrypt_string(ciphertext, encrypted_dek) == original

    def test_empty_string(self):
        ciphertext, encrypted_dek = encrypt_string("")
        assert decrypt_string(ciphertext, encrypted_dek) == ""

    def test_long_string(self):
        original = "x" * 10000
        ciphertext, encrypted_dek = encrypt_string(original)
        assert decrypt_string(ciphertext, encrypted_dek) == original


class TestGetKEK:
    def test_missing_kek_raises(self, _mock_settings):
        _mock_settings.return_value.encryption_kek_b64 = ""
        with pytest.raises(RuntimeError, match="not configured"):
            encrypt_value("test")

    def test_wrong_length_kek_raises(self, _mock_settings):
        short_key = base64.b64encode(os.urandom(16)).decode()
        _mock_settings.return_value.encryption_kek_b64 = short_key
        with pytest.raises(RuntimeError, match="32 bytes"):
            encrypt_value("test")

    def test_kek_cached_after_first_call(self, _mock_settings):
        encrypt_value("test1")
        encrypt_value("test2")
        assert _mock_settings.call_count == 1
