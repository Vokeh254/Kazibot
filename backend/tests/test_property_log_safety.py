"""
Property-based tests for API key log safety.

# Feature: kazibot, Property 13: API key never appears in log output

For any arbitrary API key string, running the profile-save code paths
(encryption) and prompt-construction code paths (AI_Tailor._build_prompt)
shall produce zero log records whose message contains the key value.

**Validates: Requirements 8.3**
"""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import patch

from cryptography.fernet import Fernet
from hypothesis import given, settings
from hypothesis import strategies as st

from backend.routers.profile import _encrypt_key
from backend.schemas.user_profile import _mask_api_key
from backend.services.ai_tailor import AITailor


# ── Custom log capture handler ────────────────────────────────────────────────


class _CapturingHandler(logging.Handler):
    """Captures all log records emitted to it for later inspection."""

    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)

    def get_all_messages(self) -> list[str]:
        """Return all formatted log messages captured so far."""
        return [self.format(record) for record in self.records]


def _attach_handler_to_loggers(handler: _CapturingHandler) -> list[logging.Logger]:
    """Attach *handler* to all loggers relevant to the code under test.

    Returns the list of loggers so the caller can detach later.
    """
    logger_names = [
        "backend.routers.profile",
        "backend.services.ai_tailor",
        # Root logger — catches anything that propagates up
        "",
    ]
    loggers: list[logging.Logger] = []
    for name in logger_names:
        lgr = logging.getLogger(name)
        lgr.addHandler(handler)
        loggers.append(lgr)
    return loggers


def _detach_handler_from_loggers(
    handler: _CapturingHandler, loggers: list[logging.Logger]
) -> None:
    for lgr in loggers:
        lgr.removeHandler(handler)


# ── Hypothesis strategies ─────────────────────────────────────────────────────

# API key strings: non-empty, length 4–100 chars (mirrors task specification).
api_key_st = st.text(min_size=4, max_size=100)


# ── Property 13: API key never appears in log output ─────────────────────────


@given(api_key=api_key_st)
@settings(max_examples=50, deadline=None)
def test_api_key_never_appears_in_logs(api_key: str) -> None:
    """
    # Feature: kazibot, Property 13: API key never appears in log output
    **Validates: Requirements 8.3**

    For any arbitrary API key string:
    1. Passing the key through the encryption helper (_encrypt_key) does not
       produce any log record that contains the key value.
    2. Passing the key through the masking helper (_mask_api_key) does not
       produce any log record that contains the key value.
    3. Building an LLM prompt via AITailor._build_prompt (which receives
       profile data but NOT the raw API key) does not produce any log record
       that contains the key value.

    All three code paths are exercised with a single captured log handler
    attached to the relevant loggers before execution and removed after.
    ``deadline=None`` is set because provider initialisation on cold runs can
    exceed the default 200 ms Hypothesis deadline.
    """
    import backend.routers.profile as profile_module

    handler = _CapturingHandler()
    loggers = _attach_handler_to_loggers(handler)

    fresh_key = Fernet.generate_key().decode()

    try:
        # ── Code path 1: encryption (from profile router) ─────────────────────
        # Swap the module-level Fernet instance for a fresh one so we don't
        # depend on the .env key being valid; restore it afterwards.
        original_fernet = profile_module._fernet
        profile_module._fernet = Fernet(fresh_key.encode())
        try:
            _ciphertext = profile_module._encrypt_key(api_key)
        finally:
            profile_module._fernet = original_fernet

        # ── Code path 2: masking (from schemas) ───────────────────────────────
        _masked = _mask_api_key(api_key)

        # ── Code path 3: prompt construction (from AI_Tailor) ─────────────────
        # Build an AITailor instance with a dummy key (not the key under test).
        with patch("backend.services.ai_tailor.settings") as mock_ai_settings:
            mock_ai_settings.LLM_PROVIDER = "openai"
            tailor = AITailor(llm_provider="openai", api_key="dummy-key-for-provider")

        # _build_prompt receives profile/job data only — the raw api_key should
        # never be interpolated into the prompt or logged.
        _prompt = tailor._build_prompt(
            job_title="Software Engineer",
            company="Acme Corp",
            job_description="We need a Python developer.",
            resume_markdown="Experienced Python dev.",
            tech_stack=["Python", "FastAPI"],
            github_url="https://github.com/example",
            portfolio_url=None,
        )

    finally:
        _detach_handler_from_loggers(handler, loggers)

    # ── Assertion: no captured log message contains the raw key ───────────────
    all_messages = handler.get_all_messages()
    for message in all_messages:
        assert api_key not in message, (
            f"API key found in log output!\n"
            f"  key={api_key!r}\n"
            f"  log message={message!r}"
        )
