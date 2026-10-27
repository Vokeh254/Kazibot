"""
Pydantic schemas for user profile requests and responses.

The LLM API key is accepted in plain text on input but is always returned
in masked form (only the last 4 characters are visible).
"""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, HttpUrl, field_validator, model_validator


def _mask_api_key(key: str) -> str:
    """Return the key with all but the last 4 characters replaced by '*'.

    >>> _mask_api_key("sk-abcdefgh")
    '******efgh'
    >>> _mask_api_key("abcd")
    'abcd'
    """
    if len(key) <= 4:
        return key
    return "*" * (len(key) - 4) + key[-4:]


class UserProfileRequest(BaseModel):
    """Payload accepted by PUT /api/profile."""

    resume_markdown: Optional[str] = None
    tech_stack: Optional[List[str]] = None
    github_url: Optional[str] = None
    portfolio_url: Optional[str] = None
    llm_provider: Literal["openai", "anthropic"] = "openai"
    # Accepted as plain text; the router encrypts before storing
    llm_api_key: Optional[str] = None


class UserProfileResponse(BaseModel):
    """Payload returned by GET /api/profile.

    The LLM API key is never returned in plain text — only the masked form.
    """

    id: int
    resume_markdown: Optional[str]
    tech_stack: Optional[List[str]]
    github_url: Optional[str]
    portfolio_url: Optional[str]
    llm_provider: Optional[str]
    # Shown as e.g. "******efgh" or None if not set
    llm_api_key_masked: Optional[str]

    model_config = {"from_attributes": True}
