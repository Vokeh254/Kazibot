"""
Property-based tests for TokenStore encrypt-decrypt round-trip.

# Feature: kazibot, Property 12: Token store encrypt-decrypt round-trip

For any arbitrary token dict, saving it via TokenStore and loading it back
shall yield the original dict. The raw bytes on disk must not be valid
UTF-8 JSON (i.e. they are encrypted ciphertext, not plaintext).

Validates: Requirements 8.1
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from cryptography.fernet import Fernet
from hypothesis import given, settings
from hypothesis import strategies as st

from backend.services.token_store import TokenStore

# ── Hypothesis strategies ─────────────────────────────────────────────────────

# Primitive values that can appear inside a JSON-serialisable token dict.
_primitive = st.one_of(
    st.text(min_size=0, max_size=80),
    st.integers(min_value=-(2**31), max_value=2**31 - 1),
    st.floats(allow_nan=False, allow_infinity=False),
    st.booleans(),
    st.none(),
)

# Token dicts: string keys, primitive values (mirrors real OAuth2 token shape).
token_dict_st = st.dictionaries(
    keys=st.text(alphabet=st.characters(whitelist_categories=("L", "N", "P")), min_size=1, max_size=40),
    values=_primitive,
    min_size=0,
    max_size=20,
)


# ── Property 12: Token store encrypt-decrypt round-trip ───────────────────────

@given(token_dict=token_dict_st)
@settings(max_examples=100)
def test_token_store_encrypt_decrypt_round_trip(token_dict):
    """
    # Feature: kazibot, Property 12: Token store encrypt-decrypt round-trip
    **Validates: Requirements 8.1**

    For any arbitrary token dict:
    1. save() then load() yields the original dict (lossless round-trip).
    2. The raw bytes written to disk are NOT valid UTF-8 JSON (i.e. they are
       encrypted ciphertext, not plain-text).
    """
    # Generate a fresh Fernet key for this test — never read from environment.
    fresh_key = Fernet.generate_key().decode()

    with tempfile.NamedTemporaryFile(suffix=".enc", delete=True) as tmp:
        token_path = Path(tmp.name)

    # Patch settings.FERNET_KEY so TokenStore picks up our fresh key.
    with patch("backend.services.token_store.settings") as mock_settings:
        mock_settings.FERNET_KEY = fresh_key

        store = TokenStore(token_path=token_path)
        try:
            # ── Assertion 1: lossless round-trip ─────────────────────────────
            store.save(token_dict)
            loaded = store.load()
            assert loaded == token_dict, (
                f"Round-trip failed: original={token_dict!r}, loaded={loaded!r}"
            )

            # ── Assertion 2: on-disk bytes are NOT plain-text UTF-8 JSON ─────
            raw_bytes = token_path.read_bytes()

            is_plaintext_json = False
            try:
                decoded = raw_bytes.decode("utf-8")
                json.loads(decoded)
                is_plaintext_json = True
            except (UnicodeDecodeError, json.JSONDecodeError):
                pass

            assert not is_plaintext_json, (
                "Token file contains plain-text JSON — data is not encrypted!"
            )
        finally:
            # Clean up the temp file if it still exists.
            if token_path.exists():
                token_path.unlink()
