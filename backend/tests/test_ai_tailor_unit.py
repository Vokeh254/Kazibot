"""
Unit tests for AITailor with mocked LLM clients.

Tests verify prompt construction, response handling, and error behaviour
for both OpenAI and Anthropic providers without making real API calls.

Requirements: 2.7
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.services.ai_tailor import AITailor, AITailorError, OpenAIProvider, AnthropicProvider


def run_async(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ── Fixtures ──────────────────────────────────────────────────────────────────

SAMPLE_JOB = dict(
    job_title="Software Engineer",
    company="Acme Corp",
    job_description="We need a Python developer with FastAPI experience.",
    resume_markdown="3 years Python experience. Built REST APIs.",
    tech_stack=["Python", "FastAPI", "SQLAlchemy"],
    github_url="https://github.com/testuser",
    portfolio_url=None,
)

SAMPLE_RESPONSE = "Dear Acme Corp Hiring Team, I am excited to apply..."


def _make_tailor(provider: str = "openai") -> AITailor:
    """Build an AITailor with a dummy key, patching settings."""
    with patch("backend.services.ai_tailor.settings") as mock_settings:
        mock_settings.LLM_PROVIDER = provider
        return AITailor(llm_provider=provider, api_key="test-key-123")


# ── OpenAIProvider tests ──────────────────────────────────────────────────────

class TestOpenAIProvider:

    def test_generate_returns_llm_response(self):
        """AITailor.generate() returns the text from the OpenAI API."""
        tailor = _make_tailor("openai")

        # Mock the underlying OpenAI provider's complete() method
        tailor._provider.complete = AsyncMock(return_value=SAMPLE_RESPONSE)

        result = run_async(tailor.generate(**SAMPLE_JOB))

        assert result == SAMPLE_RESPONSE
        tailor._provider.complete.assert_awaited_once()

    def test_generate_prompt_contains_job_description(self):
        """AITailor sends a prompt containing the job description to the LLM."""
        tailor = _make_tailor("openai")
        captured_prompt: list[str] = []

        async def _capture(prompt: str) -> str:
            captured_prompt.append(prompt)
            return SAMPLE_RESPONSE

        tailor._provider.complete = _capture

        run_async(tailor.generate(**SAMPLE_JOB))

        assert len(captured_prompt) == 1
        assert SAMPLE_JOB["job_description"] in captured_prompt[0]

    def test_generate_prompt_contains_tech_stack(self):
        """AITailor prompt includes every skill from the tech stack."""
        tailor = _make_tailor("openai")
        captured_prompt: list[str] = []

        async def _capture(prompt: str) -> str:
            captured_prompt.append(prompt)
            return SAMPLE_RESPONSE

        tailor._provider.complete = _capture
        run_async(tailor.generate(**SAMPLE_JOB))

        for skill in SAMPLE_JOB["tech_stack"]:
            assert skill in captured_prompt[0], f"Skill {skill!r} missing from prompt"

    def test_generate_prompt_contains_github_url(self):
        """AITailor prompt includes the GitHub URL when provided."""
        tailor = _make_tailor("openai")
        captured_prompt: list[str] = []

        async def _capture(prompt: str) -> str:
            captured_prompt.append(prompt)
            return SAMPLE_RESPONSE

        tailor._provider.complete = _capture
        run_async(tailor.generate(**SAMPLE_JOB))

        assert SAMPLE_JOB["github_url"] in captured_prompt[0]

    def test_llm_api_error_raises_ai_tailor_error(self):
        """AITailor raises AITailorError when the LLM client throws an exception."""
        tailor = _make_tailor("openai")
        tailor._provider.complete = AsyncMock(side_effect=Exception("API timeout"))

        with pytest.raises(AITailorError, match="LLM API call failed"):
            run_async(tailor.generate(**SAMPLE_JOB))

    def test_empty_llm_response_raises_ai_tailor_error(self):
        """AITailor raises AITailorError when the LLM returns an empty string."""
        tailor = _make_tailor("openai")
        tailor._provider.complete = AsyncMock(return_value="")

        with pytest.raises(AITailorError, match="empty response"):
            run_async(tailor.generate(**SAMPLE_JOB))

    def test_whitespace_only_response_raises_ai_tailor_error(self):
        """AITailor raises AITailorError when the LLM returns only whitespace."""
        tailor = _make_tailor("openai")
        tailor._provider.complete = AsyncMock(return_value="   \n  ")

        with pytest.raises(AITailorError, match="empty response"):
            run_async(tailor.generate(**SAMPLE_JOB))


# ── AnthropicProvider tests ───────────────────────────────────────────────────

class TestAnthropicProvider:

    def test_generate_returns_llm_response(self):
        """AITailor.generate() returns the text from the Anthropic API."""
        tailor = _make_tailor("anthropic")
        tailor._provider.complete = AsyncMock(return_value=SAMPLE_RESPONSE)

        result = run_async(tailor.generate(**SAMPLE_JOB))

        assert result == SAMPLE_RESPONSE
        tailor._provider.complete.assert_awaited_once()

    def test_anthropic_error_raises_ai_tailor_error(self):
        """AITailor raises AITailorError when the Anthropic client throws."""
        tailor = _make_tailor("anthropic")
        tailor._provider.complete = AsyncMock(side_effect=Exception("Rate limit"))

        with pytest.raises(AITailorError):
            run_async(tailor.generate(**SAMPLE_JOB))


# ── Provider selection tests ──────────────────────────────────────────────────

class TestProviderSelection:

    def test_openai_provider_selected(self):
        """AITailor uses OpenAIProvider when llm_provider='openai'."""
        tailor = _make_tailor("openai")
        assert isinstance(tailor._provider, OpenAIProvider)

    def test_anthropic_provider_selected(self):
        """AITailor uses AnthropicProvider when llm_provider='anthropic'."""
        tailor = _make_tailor("anthropic")
        assert isinstance(tailor._provider, AnthropicProvider)

    def test_unknown_provider_raises_error(self):
        """AITailor raises AITailorError for an unknown provider name."""
        with patch("backend.services.ai_tailor.settings") as mock_settings:
            mock_settings.LLM_PROVIDER = "unknown"
            with pytest.raises(AITailorError, match="Unknown LLM provider"):
                AITailor(llm_provider="unknown", api_key="key")

    def test_missing_api_key_raises_error(self):
        """AITailor raises AITailorError when no API key is provided."""
        with patch("backend.services.ai_tailor.settings") as mock_settings:
            mock_settings.LLM_PROVIDER = "openai"
            with pytest.raises(AITailorError, match="No LLM API key"):
                AITailor(llm_provider="openai", api_key=None)


# ── Portfolio URL tests ───────────────────────────────────────────────────────

class TestPortfolioAndOptionalUrls:

    def test_portfolio_url_in_prompt_when_provided(self):
        """Prompt includes the portfolio URL when it is non-null."""
        tailor = _make_tailor("openai")
        captured: list[str] = []

        async def _capture(prompt: str) -> str:
            captured.append(prompt)
            return SAMPLE_RESPONSE

        tailor._provider.complete = _capture
        job_with_portfolio = {**SAMPLE_JOB, "portfolio_url": "https://behance.net/testuser"}
        run_async(tailor.generate(**job_with_portfolio))

        assert "https://behance.net/testuser" in captured[0]

    def test_no_github_url_excluded_from_prompt(self):
        """GitHub section is empty (not a spurious 'None' string) when URL is None."""
        tailor = _make_tailor("openai")
        captured: list[str] = []

        async def _capture(prompt: str) -> str:
            captured.append(prompt)
            return SAMPLE_RESPONSE

        tailor._provider.complete = _capture
        job_no_github = {**SAMPLE_JOB, "github_url": None}
        run_async(tailor.generate(**job_no_github))

        # The word 'None' should not appear as a literal URL substitute
        assert "GitHub Profile: None" not in captured[0]
