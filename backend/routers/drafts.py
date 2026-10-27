"""
Drafts router — Gmail OAuth2 flow and draft creation.

Endpoints:
  GET  /api/auth/gmail          — Initiate OAuth2 redirect
  GET  /api/auth/gmail/callback — Exchange code for tokens
  POST /api/drafts/{job_id}     — Push generated email to Gmail Drafts

Requirements: 3.1, 3.5, 3.6, 8.1
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from google_auth_oauthlib.flow import Flow
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.config import settings
from backend.database import get_async_session
from backend.models.job_listing import JobListing
from backend.services.draft_service import (
    AuthenticationError,
    DraftService,
    GmailAPIError,
)
from backend.services.token_store import TokenStore

logger = logging.getLogger(__name__)
router = APIRouter(tags=["drafts"])

_GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.compose"]
_REDIRECT_URI = "http://localhost:8000/api/auth/gmail/callback"


def _get_oauth_flow() -> Flow:
    """Build a Google OAuth2 flow from environment credentials."""
    client_config = {
        "web": {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [_REDIRECT_URI],
        }
    }
    flow = Flow.from_client_config(client_config, scopes=_GMAIL_SCOPES)
    flow.redirect_uri = _REDIRECT_URI
    return flow


class DraftResponse(BaseModel):
    job_id: int
    message: str
    status: str


@router.get("/auth/gmail")
async def initiate_gmail_auth() -> RedirectResponse:
    """Redirect the user to the Google OAuth2 consent screen."""
    flow = _get_oauth_flow()
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",  # Force refresh token on every auth
    )
    return RedirectResponse(url=auth_url)


@router.get("/auth/gmail/callback")
async def gmail_auth_callback(code: str, state: str | None = None) -> dict:
    """Exchange the OAuth2 authorization code for tokens and store them."""
    flow = _get_oauth_flow()
    try:
        flow.fetch_token(code=code)
    except Exception as exc:
        logger.error("OAuth2 token exchange failed: %s", type(exc).__name__)
        raise HTTPException(
            status_code=400,
            detail="OAuth2 token exchange failed. Please try authenticating again.",
        )

    credentials = flow.credentials
    token_store = TokenStore()
    token_store.save(
        {
            "token": credentials.token,
            "refresh_token": credentials.refresh_token,
            "token_uri": credentials.token_uri,
            "client_id": credentials.client_id,
            "client_secret": credentials.client_secret,
            "scopes": list(credentials.scopes or _GMAIL_SCOPES),
        }
    )
    logger.info("Gmail OAuth2 tokens stored successfully")
    return {"message": "Gmail authentication successful. You can now create drafts."}


@router.post("/drafts/{job_id}", response_model=DraftResponse)
async def push_to_gmail_drafts(
    job_id: int,
    session: AsyncSession = Depends(get_async_session),
) -> DraftResponse:
    """Push the generated email for *job_id* to Gmail Drafts.

    - Fetches the generated email from the database
    - Calls DraftService.push_to_draft()
    - Returns success or structured error

    On auth error: returns 401.
    On other Gmail API errors: returns 502 without changing job status.
    """
    # Fetch job + generated email
    result = await session.execute(
        select(JobListing)
        .options(selectinload(JobListing.generated_email))
        .where(JobListing.id == job_id)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail=f"Job listing {job_id} not found")

    if not job.generated_email:
        raise HTTPException(
            status_code=400,
            detail="No generated email found for this job. Run AI generation first.",
        )

    svc = DraftService()
    try:
        await svc.push_to_draft(
            job_id=job.id,
            email_body=job.generated_email.email_body,
            to_address=job.application_email,
            session=session,
        )
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=401,
            detail=str(exc),
        )
    except GmailAPIError as exc:
        # Do NOT change job status (Requirement 3.6)
        logger.error("Gmail API error for job %d: %s", job_id, str(exc))
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        )

    return DraftResponse(
        job_id=job_id,
        message="Email successfully pushed to Gmail Drafts.",
        status="draft_created",
    )
