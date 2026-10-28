"""
Unit tests for DraftService with mocked Gmail API client.

Tests verify draft payload structure, To field, error handling paths,
and status update behaviour without making real API calls.

Requirements: 3.1, 3.6, 3.7
"""

from __future__ import annotations

import asyncio
import base64
import email as email_lib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from googleapiclient.errors import HttpError

from backend.models.job_listing import JobStatus
from backend.services.draft_service import (
    AuthenticationError,
    DraftService,
    GmailAPIError,
)


def run_async(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ── Mock helpers ──────────────────────────────────────────────────────────────

_FAKE_TOKEN_DICT = {
    "token": "fake-access-token",
    "refresh_token": "fake-refresh-token",
    "token_uri": "https://oauth2.googleapis.com/token",
    "client_id": "fake-client-id",
    "client_secret": "fake-secret",
    "scopes": ["https://www.googleapis.com/auth/gmail.compose"],
}


def _make_token_store(exists: bool = True) -> MagicMock:
    ts = MagicMock()
    ts.exists.return_value = exists
    ts.load.return_value = _FAKE_TOKEN_DICT
    return ts


def _make_gmail_mock() -> MagicMock:
    """Return a mock Gmail client whose drafts().create().execute() succeeds."""
    gmail = MagicMock()
    gmail.users.return_value.drafts.return_value.create.return_value.execute.return_value = {
        "id": "draft_abc123"
    }
    return gmail


def _make_session_mock() -> AsyncMock:
    """Return an async mock for the SQLAlchemy session."""
    session = AsyncMock()
    # Simulate execute returning a result with scalar_one_or_none() -> a mock job
    mock_job = MagicMock()
    mock_job.status = JobStatus.pending_ai
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_job
    session.execute = AsyncMock(return_value=mock_result)
    session.commit = AsyncMock()
    return session, mock_job


def _make_http_error(status: int) -> HttpError:
    resp = MagicMock()
    resp.status = status
    return HttpError(resp=resp, content=b"error")


# ── Draft payload structure tests ─────────────────────────────────────────────

class TestDraftPayloadStructure:

    def test_draft_payload_contains_email_body(self):
        """The raw draft payload contains the email body text."""
        body = "Dear Hiring Team, I am excited to apply for this role."
        raw = DraftService._build_draft_payload(body, to_address=None)
        decoded = base64.urlsafe_b64decode(raw + "==")
        msg = email_lib.message_from_bytes(decoded)
        assert body in msg.get_payload(decode=True).decode("utf-8")

    def test_draft_payload_to_field_set_when_address_provided(self):
        """The To header is set when an application email is provided."""
        body = "Cover letter body."
        to = "jobs@company.co.ke"
        raw = DraftService._build_draft_payload(body, to_address=to)
        decoded = base64.urlsafe_b64decode(raw + "==")
        msg = email_lib.message_from_bytes(decoded)
        assert msg["To"] == to

    def test_draft_payload_no_to_field_when_address_none(self):
        """The To header is absent when application_email is None."""
        raw = DraftService._build_draft_payload("Body text.", to_address=None)
        decoded = base64.urlsafe_b64decode(raw + "==")
        msg = email_lib.message_from_bytes(decoded)
        assert msg["To"] is None


# ── Successful draft creation ─────────────────────────────────────────────────

class TestSuccessfulDraftCreation:

    def test_push_to_draft_calls_drafts_create_once(self):
        """push_to_draft() calls drafts.create exactly once on success."""
        token_store = _make_token_store()
        gmail = _make_gmail_mock()
        session, mock_job = _make_session_mock()
        svc = DraftService(token_store=token_store)

        with patch.object(DraftService, "_build_gmail_client", return_value=gmail):
            run_async(svc.push_to_draft(
                job_id=1,
                email_body="My cover letter.",
                to_address="hr@company.com",
                session=session,
            ))

        assert gmail.users().drafts().create.call_count == 1

    def test_push_to_draft_never_calls_messages_send(self):
        """push_to_draft() never calls messages.send under any circumstances."""
        token_store = _make_token_store()
        gmail = _make_gmail_mock()
        session, _ = _make_session_mock()
        svc = DraftService(token_store=token_store)

        with patch.object(DraftService, "_build_gmail_client", return_value=gmail):
            run_async(svc.push_to_draft(
                job_id=1,
                email_body="My cover letter.",
                to_address=None,
                session=session,
            ))

        assert gmail.users().messages().send.call_count == 0

    def test_push_to_draft_updates_job_status(self):
        """push_to_draft() updates the job status to draft_created on success."""
        token_store = _make_token_store()
        gmail = _make_gmail_mock()
        session, mock_job = _make_session_mock()
        svc = DraftService(token_store=token_store)

        with patch.object(DraftService, "_build_gmail_client", return_value=gmail):
            run_async(svc.push_to_draft(
                job_id=1,
                email_body="My cover letter.",
                to_address=None,
                session=session,
            ))

        assert mock_job.status == JobStatus.draft_created
        session.commit.assert_awaited_once()


# ── Authentication error paths ────────────────────────────────────────────────

class TestAuthenticationErrors:

    def test_raises_auth_error_when_no_token_file(self):
        """push_to_draft() raises AuthenticationError when no tokens are stored."""
        token_store = _make_token_store(exists=False)
        svc = DraftService(token_store=token_store)
        session, _ = _make_session_mock()

        with pytest.raises(AuthenticationError, match="No Gmail OAuth2 tokens"):
            run_async(svc.push_to_draft(
                job_id=1,
                email_body="body",
                to_address=None,
                session=session,
            ))

    def test_raises_auth_error_on_http_401(self):
        """push_to_draft() raises AuthenticationError on HTTP 401 from Gmail."""
        token_store = _make_token_store()
        gmail = _make_gmail_mock()
        gmail.users.return_value.drafts.return_value.create.return_value.execute.side_effect = (
            _make_http_error(401)
        )
        session, _ = _make_session_mock()
        svc = DraftService(token_store=token_store)

        with pytest.raises(AuthenticationError):
            with patch.object(DraftService, "_build_gmail_client", return_value=gmail):
                run_async(svc.push_to_draft(
                    job_id=1,
                    email_body="body",
                    to_address=None,
                    session=session,
                ))

    def test_raises_auth_error_on_http_403(self):
        """push_to_draft() raises AuthenticationError on HTTP 403 from Gmail."""
        token_store = _make_token_store()
        gmail = _make_gmail_mock()
        gmail.users.return_value.drafts.return_value.create.return_value.execute.side_effect = (
            _make_http_error(403)
        )
        session, _ = _make_session_mock()
        svc = DraftService(token_store=token_store)

        with pytest.raises(AuthenticationError):
            with patch.object(DraftService, "_build_gmail_client", return_value=gmail):
                run_async(svc.push_to_draft(
                    job_id=1,
                    email_body="body",
                    to_address=None,
                    session=session,
                ))


# ── Non-auth Gmail API error paths ────────────────────────────────────────────

class TestNonAuthGmailErrors:

    def test_raises_gmail_api_error_on_http_500(self):
        """push_to_draft() raises GmailAPIError on HTTP 500 from Gmail."""
        token_store = _make_token_store()
        gmail = _make_gmail_mock()
        gmail.users.return_value.drafts.return_value.create.return_value.execute.side_effect = (
            _make_http_error(500)
        )
        session, mock_job = _make_session_mock()
        svc = DraftService(token_store=token_store)

        with pytest.raises(GmailAPIError):
            with patch.object(DraftService, "_build_gmail_client", return_value=gmail):
                run_async(svc.push_to_draft(
                    job_id=1,
                    email_body="body",
                    to_address=None,
                    session=session,
                ))

    def test_job_status_not_updated_on_gmail_api_error(self):
        """Job status remains unchanged when Gmail API returns a non-auth error."""
        token_store = _make_token_store()
        gmail = _make_gmail_mock()
        gmail.users.return_value.drafts.return_value.create.return_value.execute.side_effect = (
            _make_http_error(502)
        )
        session, mock_job = _make_session_mock()
        svc = DraftService(token_store=token_store)

        with pytest.raises(GmailAPIError):
            with patch.object(DraftService, "_build_gmail_client", return_value=gmail):
                run_async(svc.push_to_draft(
                    job_id=1,
                    email_body="body",
                    to_address=None,
                    session=session,
                ))

        # Status must NOT be updated to draft_created (Requirement 3.6)
        assert mock_job.status != JobStatus.draft_created
        session.commit.assert_not_awaited()
