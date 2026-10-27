"""
Profile router — GET and PUT /api/profile.

The LLM API key is encrypted with Fernet before being stored and is
never returned in plain text (Requirements 5.7, 8.2, 8.3).
"""

from __future__ import annotations

import logging

from cryptography.fernet import Fernet
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.database import get_async_session
from backend.models.user_profile import UserProfile
from backend.schemas.user_profile import (
    UserProfileRequest,
    UserProfileResponse,
    _mask_api_key,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["profile"])

_fernet = Fernet(settings.FERNET_KEY.encode())


def _encrypt_key(plain: str) -> str:
    """Encrypt an API key string and return base64 ciphertext."""
    return _fernet.encrypt(plain.encode()).decode()


def _decrypt_key(cipher: str) -> str:
    """Decrypt a Fernet-encrypted API key and return the plain text."""
    return _fernet.decrypt(cipher.encode()).decode()


def _build_response(profile: UserProfile) -> UserProfileResponse:
    """Map an ORM UserProfile to the response schema with the key masked."""
    masked: str | None = None
    if profile.llm_api_key_encrypted:
        try:
            plain = _decrypt_key(profile.llm_api_key_encrypted)
            masked = _mask_api_key(plain)
        except Exception:
            # Decryption failure — surface no key info rather than crashing
            masked = "****"

    return UserProfileResponse(
        id=profile.id,
        resume_markdown=profile.resume_markdown,
        tech_stack=profile.tech_stack,
        github_url=profile.github_url,
        portfolio_url=profile.portfolio_url,
        llm_provider=profile.llm_provider,
        llm_api_key_masked=masked,
    )


@router.get("/profile", response_model=UserProfileResponse)
async def get_profile(
    session: AsyncSession = Depends(get_async_session),
) -> UserProfileResponse:
    """Return the current user profile (API key is masked)."""
    result = await session.execute(select(UserProfile).where(UserProfile.id == 1))
    profile = result.scalar_one_or_none()

    if profile is None:
        # Return an empty profile rather than a 404 on first use
        return UserProfileResponse(
            id=0,
            resume_markdown=None,
            tech_stack=None,
            github_url=None,
            portfolio_url=None,
            llm_provider="openai",
            llm_api_key_masked=None,
        )

    return _build_response(profile)


@router.put("/profile", response_model=UserProfileResponse)
async def update_profile(
    payload: UserProfileRequest,
    session: AsyncSession = Depends(get_async_session),
) -> UserProfileResponse:
    """Create or update the singleton user profile row (upsert on id=1).

    The llm_api_key, if provided, is encrypted before being stored.
    The key value itself is never written to any log.
    """
    result = await session.execute(select(UserProfile).where(UserProfile.id == 1))
    profile = result.scalar_one_or_none()

    if profile is None:
        profile = UserProfile(id=1)
        session.add(profile)

    # Apply scalar fields
    if payload.resume_markdown is not None:
        profile.resume_markdown = payload.resume_markdown
    if payload.tech_stack is not None:
        profile.tech_stack = payload.tech_stack
    if payload.github_url is not None:
        profile.github_url = payload.github_url
    if payload.portfolio_url is not None:
        profile.portfolio_url = payload.portfolio_url
    if payload.llm_provider is not None:
        profile.llm_provider = payload.llm_provider

    # Encrypt the API key — NEVER log the plain value (Requirement 8.3)
    if payload.llm_api_key is not None:
        profile.llm_api_key_encrypted = _encrypt_key(payload.llm_api_key)
        logger.info("LLM API key updated (value not logged)")

    await session.commit()
    await session.refresh(profile)

    return _build_response(profile)
