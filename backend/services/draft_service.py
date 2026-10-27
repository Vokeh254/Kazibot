"""
Draft_Service — creates Gmail Drafts via the Gmail API.

IMPORTANT: This service ONLY uses `drafts.create`. It NEVER calls
`messages.send` or any SMTP socket (Requirement 3.3).

OAuth2 tokens are persisted via TokenStore (encrypted at rest).
Automatic token refresh is handled by google-auth (Requirement 8.4).

Requirements: 3.1–3.7, 8.1, 8.4
"""

from __future__ import annotations

import base64
import email as email_lib
import logging
from email.mime.text import MIMEText
from typing import Any, Dict, Optional

from google.auth.exceptions import RefreshError, TransportError
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from backend.models.job_listing import JobStatus
from backend.services.token_store import TokenStore

logger = logging.getLogger(__name__)

# Only the compose scope is requested — this does NOT permit sending email.
_GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.compose"]


class DraftServiceError(Exception):
    """Base error for Draft_Service failures."""


class AuthenticationError(DraftServiceError):
    """Raised when OAuth2 tokens are invalid or expired beyond refresh."""


class GmailAPIError(DraftServiceError):
    """Raised when the Gmail API returns a non-authentication error."""


class DraftService:
    """Creates Gmail Drafts from generated cover letter emails.

    The service authenticates using stored OAuth2 credentials (loaded from
    TokenStore). If the access token has expired, google-auth automatically
    refreshes it using the stored refresh token.
    """

    def __init__(self, token_store: Optional[TokenStore] = None) -> None:
        self._token_store = token_store or TokenStore()

    # ── Public interface ──────────────────────────────────────────────────────

    async def push_to_draft(
        self,
        job_id: int,
        email_body: str,
        to_address: Optional[str],
        session,  # SQLAlchemy AsyncSession
    ) -> None:
        """Create a Gmail Draft for the given job and update job status.

        Args:
            job_id: Database ID of the JobListing.
            email_body: The cover letter text to place in the draft body.
            to_address: The application email (pre-populates the To field).
            session: Active SQLAlchemy async session for status update.

        Raises:
            AuthenticationError: If OAuth2 tokens are missing or unrefreshable.
            GmailAPIError: If Gmail API returns a non-auth error.
        """
        credentials = self._load_credentials()
        gmail = self._build_gmail_client(credentials)

        draft_payload = self._build_draft_payload(email_body, to_address)

        try:
            # drafts.create — the ONLY Gmail API method this service calls
            gmail.users().drafts().create(
                userId="me",
                body={"message": {"raw": draft_payload}},
            ).execute()
        except HttpError as exc:
            status_code = exc.resp.status
            if status_code in (401, 403):
                logger.error("Gmail auth error (HTTP %d)", status_code)
                raise AuthenticationError(
                    f"Gmail authentication failed: HTTP {status_code}"
                ) from exc
            logger.error("Gmail API error (HTTP %d): %s", status_code, exc)
            raise GmailAPIError(f"Gmail API error: HTTP {status_code}") from exc
        except (RefreshError, TransportError) as exc:
            logger.error("OAuth2 refresh failed: %s", type(exc).__name__)
            raise AuthenticationError("OAuth2 token refresh failed") from exc

        # Update job status to draft_created in the database (Requirement 3.4)
        await self._update_job_status(session, job_id, JobStatus.draft_created)
        logger.info("Draft created for job_id=%d; status updated to draft_created", job_id)

    def is_authenticated(self) -> bool:
        """Return True if stored OAuth2 tokens are present."""
        return self._token_store.exists()

    # ── Private helpers ───────────────────────────────────────────────────────

    def _load_credentials(self) -> Credentials:
        """Load and return Google OAuth2 credentials from the token store.

        Raises:
            AuthenticationError: If no token file exists.
        """
        if not self._token_store.exists():
            raise AuthenticationError(
                "No Gmail OAuth2 tokens found. Please authenticate via /api/auth/gmail."
            )
        token_dict = self._token_store.load()
        return Credentials(
            token=token_dict.get("token"),
            refresh_token=token_dict.get("refresh_token"),
            token_uri=token_dict.get("token_uri", "https://oauth2.googleapis.com/token"),
            client_id=token_dict.get("client_id"),
            client_secret=token_dict.get("client_secret"),
            scopes=token_dict.get("scopes", _GMAIL_SCOPES),
        )

    @staticmethod
    def _build_gmail_client(credentials: Credentials):
        """Build and return an authenticated Gmail API client."""
        return build("gmail", "v1", credentials=credentials, cache_discovery=False)

    @staticmethod
    def _build_draft_payload(body: str, to_address: Optional[str]) -> str:
        """Encode the email as a base64url-safe string for the Gmail API."""
        mime_message = MIMEText(body, "plain", "utf-8")
        if to_address:
            mime_message["To"] = to_address
        raw = base64.urlsafe_b64encode(mime_message.as_bytes()).decode("utf-8")
        return raw

    @staticmethod
    async def _update_job_status(session, job_id: int, new_status: JobStatus) -> None:
        """Persist the new job status to the database."""
        from sqlalchemy import select
        from backend.models.job_listing import JobListing

        result = await session.execute(
            select(JobListing).where(JobListing.id == job_id)
        )
        job = result.scalar_one_or_none()
        if job:
            job.status = new_status
            await session.commit()


# Module-level singleton
draft_service = DraftService()
