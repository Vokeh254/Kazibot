"""
Unit tests for Draft_Service with mocked Gmail API client.

Tests verify draft payload structure, To field population, error paths,
and HTTP status codes returned to the API layer.

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
from backend.services.token_store import TokenStore


# ── Shared async helper ───────────────────────────────────────────────────────

def run_async(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ── Mock factory helpers ──────────────────────────────────────────────────────

def _make_mock_gmail_client(http_error: HttpError | None = None):
    """Return (mock_client, mock_create_fn). If http_error is given, execute() raises it."""
    mock_client = MagicMock()
    if http_error:
        mock_execute = MagicMock(side_effect=http_error)
    else:
        mock_execute = MagicMock(return_value={"id": "draft_123"})

    mock_create = MagicMock()
    mock_create.return_value.execute = mock_execute
    mock_client.users.return_value.drafts.return_value.create = mock_create
    return mock_client, mock_create


def _make_mock_session(job_status_holder: list):
    """Return an AsyncMock session that records status updates."""
    session = AsyncMock()

    async def _commit():
        pass

    session.commit = _commit

    # _update_job_status calls session.execute then commit; we mock it at the
    # DraftService level instead (see tests below).
    return session


def _make_service(mock_gmail_client) -> DraftService:
    """Build a DraftService wired to mock_gmail_client and a fake token store."""
    svc = DraftService.__new__(DraftService)
    svc._token_store = MagicMock(spec=TokenStore)
    svc._token_store.exists.return_value = True
    svc._token_store.load.return_value = {
        "token": "tok",
        "refresh_token": "rtok",
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": "cid",
        "client_secret": "csec",
        "scopes": ["https://www.googleapis.com/auth/gmail.compose"],
    }
    svc._build_gmail_client = lambda _creds: mock_gmail_client
    return svc


def _make_http_error(status: int) -> HttpError:
    resp = MagicMock()
    resp.status = status
    return HttpError(resp=resp, content=b"error")


# ── Draft payload structure tests ─────────────────────────────────────────────

class TestDraftPayloadStructure:

    def test_draft_payload_has_correct_body_text(self):
        """The MIME body of the draft contains the email_body text."""
        mock_gmail, mock_create = _make_mock_gmail_client()
        svc = _make_service(mock_gmail)
        email_body = "Dear Hiring Team, I am excited to apply..."

        # Patch _update_job_status to avoid DB dependency
        svc._update_job_status = AsyncMock()

        run_async(svc.push_to_draft(
            job_id=1,
            email_body=email_body,
            to_address=None,
            session=AsyncMock(),
        ))

        call_kwargs = mock_create.call_args
        raw_b64 = call_kwargs.kwargs["body"]["message"]["raw"]
        raw_bytes = base64.urlsafe_b64decode(raw_b64 + "==")
        msg = email_lib.message_from_bytes(raw_bytes)

        assert email_body in msg.get_payload(decode=True).decode("utf-8")

    def test_draft_to_field_populated_when_email_provided(self):
        """The To header is set to application_email when provided."""
        mock_gmail, mock_create = _make_mock_gmail_client()
        svc = _make_service(mock_gmail)
        svc._update_job_status = AsyncMock()

        run_async(svc.push_to_draft(
            job_id=1,
            email_body="Cover letter body.",
            to_address="hr@example.co.ke",
            session=AsyncMock(),
        ))

        call_kwargs = mock_create.call_args
        raw_b64 = call_kwargs.kwargs["body"]["message"]["raw"]
        raw_bytes = base64.urlsafe_b64decode(raw_b64 + "==")
        msg = email_lib.message_from_bytes(raw_bytes)

        assert msg["To"] == "hr@example.co.ke"

    def test_draft_to_field_absent_when_no_email(self):
        """The To header is absent when to_address is None."""
        mock_gmail, mock_create = _make_mock_gmail_client()
        svc = _make_service(mock_gmail)
        svc._update_job_status = AsyncMock()

        run_async(svc.push_to_draft(
            job_id=1,
            email_body="Cover letter body.",
            to_address=None,
            session=AsyncMock(),
        ))

        call_kwargs = mock_create.call_args
        raw_b64 = call_kwargs.kwargs["body"]["message"]["raw"]
        raw_bytes = base64.urlsafe_b64decode(raw_b64 + "==")
        msg = email_lib.message_from_bytes(raw_bytes)

        assert msg["To"] is None

    def test_drafts_create_called_with_user_id_me(self):
        """drafts.create is called with userId='me'."""
        mock_gmail, mock_create = _make_mock_gmail_client()
        svc = _make_service(mock_gmail)
        svc._update_job_status = AsyncMock()

        run_async(svc.push_to_draft(
            job_id=1,
            email_body="Body.",
            to_address=None,
            session=AsyncMock(),
        ))

        call_kwargs = mock_create.call_args
        assert call_kwargs.kwargs.get("userId") == "me"


# ── Error path tests ──────────────────────────────────────────────────────────

class TestDraftServiceErrorPaths:

    def test_401_raises_authentication_error(self):
        """Gmail HTTP 401 is raised as AuthenticationError."""
        mock_gmail, _ = _make_mock_gmail_client(http_error=_make_http_error(401))
        svc = _make_service(mock_gmail)
        svc._update_job_status = AsyncMock()

        with pytest.raises(AuthenticationError):
            run_async(svc.push_to_draft(1, "Body.", None, AsyncMock()))

    def test_403_raises_authentication_error(self):
        """Gmail HTTP 403 is raised as AuthenticationError."""
        mock_gmail, _ = _make_mock_gmail_client(http_error=_make_http_error(403))
        svc = _make_service(mock_gmail)
        svc._update_job_status = AsyncMock()

        with pytest.raises(AuthenticationError):
            run_async(svc.push_to_draft(1, "Body.", None, AsyncMock()))

    def test_500_raises_gmail_api_error(self):
        """Gmail HTTP 500 is raised as GmailAPIError (not AuthenticationError)."""
        mock_gmail, _ = _make_mock_gmail_client(http_error=_make_http_error(500))
        svc = _make_service(mock_gmail)
        svc._update_job_status = AsyncMock()

        with pytest.raises(GmailAPIError):
            run_async(svc.push_to_draft(1, "Body.", None, AsyncMock()))

    def test_503_raises_gmail_api_error(self):
        """Gmail HTTP 503 is raised as GmailAPIError."""
        mock_gmail, _ = _make_mock_gmail_client(http_error=_make_http_error(503))
        svc = _make_service(mock_gmail)
        svc._update_job_status = AsyncMock()

        with pytest.raises(GmailAPIError):
            run_async(svc.push_to_draft(1, "Body.", None, AsyncMock()))

    def test_missing_token_raises_authentication_error(self):
        """AuthenticationError is raised when no token file exists."""
        svc = DraftService.__new__(DraftService)
        svc._token_store = MagicMock(spec=TokenStore)
        svc._token_store.exists.return_value = False  # No tokens stored

        with pytest.raises(AuthenticationError, match="No Gmail OAuth2 tokens"):
            run_async(svc.push_to_draft(1, "Body.", None, AsyncMock()))

    def test_auth_error_does_not_update_job_status(self):
        """On AuthenticationError, _update_job_status is never called."""
        mock_gmail, _ = _make_mock_gmail_client(http_error=_make_http_error(401))
        svc = _make_service(mock_gmail)
        svc._update_job_status = AsyncMock()

        with pytest.raises(AuthenticationError):
            run_async(svc.push_to_draft(1, "Body.", None, AsyncMock()))

        svc._update_job_status.assert_not_awaited()

    def test_gmail_api_error_does_not_update_job_status(self):
        """On GmailAPIError, _update_job_status is never called (status unchanged)."""
        mock_gmail, _ = _make_mock_gmail_client(http_error=_make_http_error(500))
        svc = _make_service(mock_gmail)
        svc._update_job_status = AsyncMock()

        with pytest.raises(GmailAPIError):
            run_async(svc.push_to_draft(1, "Body.", None, AsyncMock()))

        svc._update_job_status.assert_not_awaited()


# ── Success path tests ────────────────────────────────────────────────────────

class TestDraftServiceSuccessPath:

    def test_successful_draft_calls_update_job_status(self):
        """On success, _update_job_status is called with draft_created."""
        mock_gmail, _ = _make_mock_gmail_client()
        svc = _make_service(mock_gmail)
        svc._update_job_status = AsyncMock()

        run_async(svc.push_to_draft(42, "Email body.", "jobs@corp.com", AsyncMock()))

        svc._update_job_status.assert_awaited_once()
        _, call_kwargs = svc._update_job_status.call_args
        # Third positional arg is new_status
        args = svc._update_job_status.call_args.args
        assert JobStatus.draft_created in args

    def test_is_authenticated_true_when_token_exists(self):
        """is_authenticated() returns True when a token file is present."""
        svc = DraftService.__new__(DraftService)
        svc._token_store = MagicMock(spec=TokenStore)
        svc._token_store.exists.return_value = True
        assert svc.is_authenticated() is True

    def test_is_authenticated_false_when_no_token(self):
        """is_authenticated() returns False when no token file exists."""
        svc = DraftService.__new__(DraftService)
        svc._token_store = MagicMock(spec=TokenStore)
        svc._token_store.exists.return_value = False
        assert svc.is_authenticated() is False
