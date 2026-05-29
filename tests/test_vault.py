"""Test vault encryption — encrypt/decrypt roundtrip, no plaintext fallback."""
import sys
sys.path.insert(0, ".")

from potato.vault import _encrypt, _decrypt


class TestVault:
    def test_encrypt_decrypt_roundtrip(self):
        original = "my_secret_api_key_12345"
        encrypted = _encrypt(original)
        decrypted = _decrypt(encrypted)
        assert decrypted == original

    def test_decrypt_garbage_raises(self):
        try:
            _decrypt("not-valid-encrypted-data-at-all")
            assert False, "Should have raised RuntimeError"
        except RuntimeError as e:
            assert "decryption failed" in str(e).lower() or "neither" in str(e).lower()

    def test_decrypt_base64_legacy(self):
        import base64
        legacy = base64.b64encode(b"legacy_value").decode("ascii")
        result = _decrypt(legacy)
        assert result == "legacy_value"

    def test_encrypt_different_values(self):
        vals = ["key1", "key2", "sk-abc123def456"]
        for v in vals:
            assert _decrypt(_encrypt(v)) == v