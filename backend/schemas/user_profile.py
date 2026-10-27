"""
Pydantic schemas for user profile requests and responses.

The LLM API key is accepted in plain text on input but is always returned
in masked form (only the last 4 characters are visible).
"""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, HttpUrl


def _mask_api_key(key: str) -> str:
    """Return the key with all but the last 4 characters replaced by '*'.

    For keys shorter than or equal to 4 characters the whole key is shown
    (no masking applied — there is nothing meaningful to hide).

    >>> _mask_api_key("sk-abcdefgh")
    '******efgh'
    >>> _mask_api_key("abcd")
    'abcd'
    """
    if len(key) <= 4:
        return key
    return "*" * (len(key) - 4) + key[-4:]


class UserProfileRequest(BaseModel):
    """Payload accepted by PUT /api/profile.

    ``llm_api_key`` is accepted as plain text; the router is responsible for
    encrypting it with Fernet before persisting to the database.  It is never
    returned to the client in plain form — use ``UserProfileResponse`` which
    carries only ``llm_api_key_masked``.
    """

    resume_markdown: str
    tech_stack: List[str]
    github_url: Optional[HttpUrl] = None
    portfolio_url: Optional[HttpUrl] = None
    llm_provider: Literal["openai", "anthropic"]
    # Stored encrypted; never echoed back in plain text.
    llm_api_key: str


class UserProfileResponse(BaseModel):
    """Payload returned by GET /api/profile.

    The LLM API key is never returned in plain text — only the masked form
    is included (e.g. ``"******efgh"``).  ``github_url`` and
    ``portfolio_url`` are returned as plain strings rather than ``HttpUrl``
    objects so that serialisation is straightforward for the frontend.
    """

    model_config = ConfigDict(from_attributes=True)

    resume_markdown: Optional[str]
    tech_stack: Optional[List[str]]
    github_url: Optional[str]
    portfolio_url: Optional[str]
    llm_provider: Optional[str]
    # Last 4 chars of the key, all preceding chars replaced with '*'.
    # None when no key has been stored yet.
    llm_api_key_masked: Optional[str]
