"""
Property-based test for AI prompt completeness.

# Feature: kazibot, Property 4: AI prompt completeness

For any UserProfile with non-empty resume text and tech stack, the prompt
string constructed by AITailor._build_prompt() shall contain: the full job
description text, the resume text, the tech stack, the GitHub URL (when
non-null), and the portfolio URL (when non-null).

**Validates: Requirements 2.1, 2.2, 2.4, 2.5**
"""

from __future__ import annotations

from unittest.mock import patch

from hypothesis import given, settings
from hypothesis import strategies as st

from backend.services.ai_tailor import AITailor

# ── Hypothesis strategies ─────────────────────────────────────────────────────

_printable = st.characters(whitelist_categories=("L", "N", "P", "Z"))
_non_empty = st.text(alphabet=_printable, min_size=1, max_size=200)

# Tech stack: list of 1–8 non-empty skill strings
_tech_stack_st = st.lists(_non_empty, min_size=1, max_size=8)

# Optional URLs — use simple ASCII strings to avoid encoding surprises
_url_st = st.builds(
    lambda domain, path: f"https://{domain}.com/{path}",
    domain=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=3, max_size=15),
    path=st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789-_", min_size=0, max_size=30),
)
_optional_url_st = st.one_of(st.none(), _url_st)


# ── Property 4: AI prompt completeness ───────────────────────────────────────

@given(
    job_title=_non_empty,
    company=_non_empty,
    job_description=_non_empty,
    resume_markdown=_non_empty,
    tech_stack=_tech_stack_st,
    github_url=_optional_url_st,
    portfolio_url=_optional_url_st,
)
@settings(max_examples=100)
def test_ai_prompt_completeness(
    job_title: str,
    company: str,
    job_description: str,
    resume_markdown: str,
    tech_stack: list[str],
    github_url: str | None,
    portfolio_url: str | None,
) -> None:
    """
    # Feature: kazibot, Property 4: AI prompt completeness
    **Validates: Requirements 2.1, 2.2, 2.4, 2.5**

    For any combination of job and profile data, the prompt built by
    AITailor._build_prompt() must contain:
    1. The full job description text
    2. The resume markdown text
    3. All tech stack skills
    4. The GitHub URL (when non-null)
    5. The portfolio URL (when non-null)
    """
    # Build an AITailor with a dummy key — we only call _build_prompt(),
    # which never touches the LLM client.
    with patch("backend.services.ai_tailor.settings") as mock_settings:
        mock_settings.LLM_PROVIDER = "openai"
        tailor = AITailor(llm_provider="openai", api_key="dummy-test-key")

    prompt = tailor._build_prompt(
        job_title=job_title,
        company=company,
        job_description=job_description,
        resume_markdown=resume_markdown,
        tech_stack=tech_stack,
        github_url=github_url,
        portfolio_url=portfolio_url,
    )

    # 1. Job description must appear in full
    assert job_description in prompt, (
        f"Job description not found in prompt.\n"
        f"  job_description={job_description!r}\n"
        f"  prompt (first 300 chars)={prompt[:300]!r}"
    )

    # 2. Resume text must appear in full
    assert resume_markdown in prompt, (
        f"Resume markdown not found in prompt.\n"
        f"  resume_markdown={resume_markdown!r}\n"
        f"  prompt (first 300 chars)={prompt[:300]!r}"
    )

    # 3. Every tech stack skill must appear in the prompt
    for skill in tech_stack:
        assert skill in prompt, (
            f"Tech stack skill {skill!r} not found in prompt.\n"
            f"  tech_stack={tech_stack!r}"
        )

    # 4. GitHub URL must be present when non-null
    if github_url is not None:
        assert github_url in prompt, (
            f"GitHub URL {github_url!r} not found in prompt."
        )

    # 5. Portfolio URL must be present when non-null
    if portfolio_url is not None:
        assert portfolio_url in prompt, (
            f"Portfolio URL {portfolio_url!r} not found in prompt."
        )
