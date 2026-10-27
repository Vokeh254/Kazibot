"""
AI router — generates cover letter emails for job listings.

Endpoint:
  POST /api/ai/generate/{job_id} — Generate a cover letter and persist it.

Requirements: 2.1, 2.7
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.database import get_async_session
from backend.models.generated_email import GeneratedEmail
from backend.models.job_listing import JobListing, JobStatus
from backend.models.user_profile import UserProfile
from backend.services.ai_tailor import AITailor, AITailorError

logger = logging.getLogger(__name__)
router = APIRouter(tags=["ai"])


class GenerateResponse(BaseModel):
    job_id: int
    email_body: str
    message: str


@router.post("/ai/generate/{job_id}", response_model=GenerateResponse)
async def generate_email(
    job_id: int,
    session: AsyncSession = Depends(get_async_session),
) -> GenerateResponse:
    """Generate a personalised cover letter for the given job listing.

    - Fetches job + user profile from the database
    - Calls AI_Tailor.generate() with the prompt template
    - Persists the result to GeneratedEmail
    - Returns the generated email body

    On LLM error: logs (without the API key), job stays at pending_ai,
    and a 502 is returned to the client (Requirement 2.7).
    """
    # ── Fetch job listing ─────────────────────────────────────────────────────
    job_result = await session.execute(
        select(JobListing)
        .options(selectinload(JobListing.generated_email))
        .where(JobListing.id == job_id)
    )
    job = job_result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail=f"Job listing {job_id} not found")

    # ── Fetch user profile ────────────────────────────────────────────────────
    profile_result = await session.execute(
        select(UserProfile).where(UserProfile.id == 1)
    )
    profile = profile_result.scalar_one_or_none()
    if not profile or not profile.llm_api_key_encrypted:
        raise HTTPException(
            status_code=400,
            detail="User profile or LLM API key not configured. Set up your profile first.",
        )

    # Decrypt the API key — value must not appear in logs
    from cryptography.fernet import Fernet
    from backend.config import settings

    try:
        fernet = Fernet(settings.FERNET_KEY.encode())
        plain_key = fernet.decrypt(profile.llm_api_key_encrypted.encode()).decode()
    except Exception:
        raise HTTPException(
            status_code=500, detail="Failed to decrypt LLM API key."
        )

    # ── Generate cover letter ─────────────────────────────────────────────────
    try:
        tailor = AITailor(
            llm_provider=profile.llm_provider or settings.LLM_PROVIDER,
            api_key=plain_key,
        )
        email_body = await tailor.generate(
            job_title=job.title,
            company=job.company,
            job_description=job.description or "",
            resume_markdown=profile.resume_markdown or "",
            tech_stack=profile.tech_stack or [],
            github_url=profile.github_url,
            portfolio_url=profile.portfolio_url,
        )
    except AITailorError as exc:
        # Job status stays at pending_ai (Requirement 2.7)
        logger.error("AI generation failed for job %d: %s", job_id, str(exc))
        raise HTTPException(
            status_code=502,
            detail=f"LLM generation failed: {str(exc)}",
        )

    # ── Persist generated email ───────────────────────────────────────────────
    existing = job.generated_email
    if existing:
        existing.email_body = email_body
        await session.commit()
        await session.refresh(existing)
    else:
        new_email = GeneratedEmail(
            job_listing_id=job.id,
            email_body=email_body,
        )
        session.add(new_email)
        await session.commit()

    return GenerateResponse(
        job_id=job_id,
        email_body=email_body,
        message="Cover letter generated successfully.",
    )
