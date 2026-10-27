"""
AI_Tailor service — generates personalised cover letter emails via LLM.

Supports OpenAI and Anthropic as interchangeable providers (Requirement 2.6).
The prompt template is read from prompts/cover_letter.txt at runtime so
prompt edits require no code changes (Requirement 2.8).

Requirements: 2.1–2.8
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Protocol, runtime_checkable

import anthropic
import openai

from backend.config import settings

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "cover_letter.txt"


# ── LLM Provider protocol ─────────────────────────────────────────────────────


@runtime_checkable
class LLMProvider(Protocol):
    """Minimal interface every LLM provider must implement."""

    async def complete(self, prompt: str) -> str:
        """Send *prompt* to the LLM and return the generated text."""
        ...


# ── Concrete providers ────────────────────────────────────────────────────────


class OpenAIProvider:
    """Thin async wrapper around the OpenAI chat completions API."""

    def __init__(self, api_key: str) -> None:
        self._client = openai.AsyncOpenAI(api_key=api_key)

    async def complete(self, prompt: str) -> str:
        response = await self._client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=600,
            temperature=0.7,
        )
        return response.choices[0].message.content or ""


class AnthropicProvider:
    """Thin async wrapper around the Anthropic messages API."""

    def __init__(self, api_key: str) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=api_key)

    async def complete(self, prompt: str) -> str:
        message = await self._client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text if message.content else ""


# ── AI_Tailor service ─────────────────────────────────────────────────────────


class AITailorError(Exception):
    """Raised when the LLM API returns an error."""


class AITailor:
    """Generates a personalised cover letter email for a given job listing.

    Usage::

        from backend.services.ai_tailor import AITailor
        tailor = AITailor(llm_provider="openai", api_key="sk-...")
        email_body = await tailor.generate(job, profile)
    """

    def __init__(self, llm_provider: str | None = None, api_key: str | None = None) -> None:
        provider_name = (llm_provider or settings.LLM_PROVIDER).lower()
        if not api_key:
            raise AITailorError("No LLM API key provided")

        if provider_name == "openai":
            self._provider: LLMProvider = OpenAIProvider(api_key)
        elif provider_name == "anthropic":
            self._provider = AnthropicProvider(api_key)
        else:
            raise AITailorError(f"Unknown LLM provider: {provider_name!r}")

        self._prompt_template: str = _PROMPT_PATH.read_text(encoding="utf-8")

    async def generate(
        self,
        job_title: str,
        company: str,
        job_description: str,
        resume_markdown: str,
        tech_stack: list[str],
        github_url: str | None = None,
        portfolio_url: str | None = None,
    ) -> str:
        """Construct the prompt, call the LLM, and return the email body.

        Raises:
            AITailorError: If the LLM API returns an error or empty response.
        """
        prompt = self._build_prompt(
            job_title=job_title,
            company=company,
            job_description=job_description,
            resume_markdown=resume_markdown,
            tech_stack=tech_stack,
            github_url=github_url,
            portfolio_url=portfolio_url,
        )

        try:
            result = await self._provider.complete(prompt)
        except Exception as exc:
            # Log without the API key value (Requirement 8.3)
            logger.error(
                "LLM API error for job '%s' at '%s': %s",
                job_title,
                company,
                type(exc).__name__,
            )
            raise AITailorError(f"LLM API call failed: {type(exc).__name__}") from exc

        if not result or not result.strip():
            raise AITailorError("LLM returned an empty response")

        return result.strip()

    def _build_prompt(
        self,
        job_title: str,
        company: str,
        job_description: str,
        resume_markdown: str,
        tech_stack: list[str],
        github_url: str | None,
        portfolio_url: str | None,
    ) -> str:
        """Interpolate all profile and job fields into the prompt template."""
        github_section = (
            f"GitHub Profile: {github_url}" if github_url else ""
        )
        portfolio_section = (
            f"Portfolio / Behance: {portfolio_url}" if portfolio_url else ""
        )

        return self._prompt_template.format(
            job_title=job_title,
            company=company,
            job_description=job_description,
            resume_markdown=resume_markdown,
            tech_stack=", ".join(tech_stack) if tech_stack else "Not specified",
            github_section=github_section,
            portfolio_section=portfolio_section,
        )
