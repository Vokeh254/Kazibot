"""
Property-based tests for API key masking.

# Feature: kazibot, Property 10: API key masking preserves last 4 characters

For any key string of length ≥ 4:
- The masked form ends with exactly the same last 4 characters as the original.
- All characters preceding those last 4 are replaced with the mask character '*'.
- The masked form has the same length as the original.

**Validates: Requirements 5.7**
"""

from hypothesis import given, settings
from hypothesis import strategies as st

from backend.schemas.user_profile import _mask_api_key


# ── Property 10: API key masking preserves last 4 characters ─────────────────

@given(key=st.text(min_size=4))
@settings(max_examples=100)
def test_api_key_masking_preserves_last_4_characters(key: str):
    """
    # Feature: kazibot, Property 10: API key masking preserves last 4 characters
    **Validates: Requirements 5.7**

    For any key string of length ≥ 4:
    1. The masked form ends with exactly the same last 4 characters as the original.
    2. All characters preceding those last 4 are replaced with '*'.
    3. The length of the masked form equals the length of the original.
    """
    masked = _mask_api_key(key)

    # Assertion 1: last 4 characters are preserved
    assert masked[-4:] == key[-4:], (
        f"Last 4 chars differ: original={key!r}, masked={masked!r}"
    )

    # Assertion 2: all preceding characters are replaced with '*'
    prefix_length = len(key) - 4
    assert all(c == "*" for c in masked[:prefix_length]), (
        f"Prefix not fully masked: original={key!r}, masked={masked!r}"
    )

    # Assertion 3: length is preserved
    assert len(masked) == len(key), (
        f"Length mismatch: original len={len(key)}, masked len={len(masked)}, "
        f"original={key!r}, masked={masked!r}"
    )
