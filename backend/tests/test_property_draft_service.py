"""
Property-based tests for Draft_Service correctness properties.

Properties covered:
  Property 5: Draft_Service never calls the Gmail send endpoint
  Property 6: Draft creation updates job status to Draft Created
  Property 7: Draft "To" field matches application email

**Validates: Requirements 3.3, 3.4, 3.7**
"""

from __future__ import annotations

import asyncio
import base64
import email as email_lib
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

from hypothesis import given, settings
from hypothesis import strategies as st
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import select

from backend.database import Base
from backend.models.job_listing import JobListing, JobStatus
from backend.services.draft_service import DraftService

# ── Shared event loop ─────────────────────────────────────────────────────────

_loop = asyncio.new_event_loop()


def run_async(coro):
    return _loop.run_until_complete(coro)


# ── In-memory DB helpers ──────────────────────────────────────────────────────

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


def _make_engine():
    return create_async_engine(TEST_DB_URL, connect_args={"check_same_thread": False})


def _make_factory(engine):
    return async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


async def _setup_db(engine):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def _teardown_db(engine):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


async def _create_job(factory, email: Optional[str] = None) -> int:
    """Insert a minimal JobListing and return its id."""
    async with factory() as session:
        job = JobListing(
            title="Test Engineer",
            company="Test Corp",
            description="Test description",
            application_email=email,
            status=JobStatus.pending_ai,
            board_source="test",
        )
        session.add(job)
        await session.commit()
        await session.refresh(job)
        return job.id


# ── Mock Gmail API builder ────────────────────────────────────────────────────

def _make_mock_gmail():
    """Return a mock Gmail API client that records all method calls."""
    mock_gmail = MagicMock()
    # drafts().create().execute() returns a dummy response
    mock_gmail.users.return_value.drafts.return_value.create.return_value.execute.return_value = {"id": "draft123"}
    return mock_gmail


def _make_draft_service_with_mock_gmail(mock_gmail) -> DraftService:
    """Build a DraftService whose Gmail client is replaced with a mock."""
    token_dict = {
        "token": "fake-token",
        "refresh_token": "fake-refresh",
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": "fake-client-id",
        "client_secret": "fake-secret",
        "scopes": ["https://www.googleapis.com/auth/gmail.compose"],
    }
    mock_token_store = MagicMock()
    mock_token_store.exists.return_value = True
    mock_token_store.load.return_value = token_dict

    svc = DraftService(token_store=mock_token_store)

    # Patch the static method that builds the Gmail client
    with patch.object(DraftService, "_build_gmail_client", return_value=mock_gmail):
        return svc, mock_gmail


# ── Hypothesis strategies ─────────────────────────────────────────────────────

_printable = st.characters(whitelist_categories=("L", "N", "P", "Z"))
_non_empty_text = st.text(alphabet=_printable, min_size=1, max_size=300)

_ascii_local = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._%+-"
_ascii_domain = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-"

_email_st = st.builds(
    lambda local, domain, tld: f"{local}@{domain}.{tld}",
    local=st.text(alphabet=_ascii_local, min_size=1, max_size=20).filter(
        lambda s: s and s[0] not in "._%+-" and s[-1] not in "._%+-"
    ),
    domain=st.text(alphabet=_ascii_domain, min_size=2, max_size=15).filter(
        lambda s: s and s[0] != "-" and s[-1] != "-"
    ),
    tld=st.sampled_from(["com", "co.ke", "org", "net", "io"]),
)


# ── Property 5: Draft_Service never calls the Gmail send endpoint ─────────────

@given(email_body=_non_empty_text, to_address=st.one_of(st.none(), _email_st))
@settings(max_examples=100, deadline=None)
def test_draft_service_never_calls_send_endpoint(
    email_body: str, to_address: Optional[str]
):
    """
    # Feature: kazibot, Property 5: Draft_Service never calls the Gmail send endpoint
    **Validates: Requirements 3.3**

    For any email body and any to_address, push_to_draft() must:
    - Call drafts.create exactly once
    - Never call messages.send
    """
    engine = _make_engine()
    factory = _make_factory(engine)

    mock_gmail = _make_mock_gmail()

    async def _run():
        await _setup_db(engine)
        try:
            job_id = await _create_job(factory, email=to_address)
            async with factory() as session:
                svc = DraftService(token_store=MagicMock(
                    exists=MagicMock(return_value=True),
                    load=MagicMock(return_value={
                        "token": "t", "refresh_token": "r",
                        "token_uri": "https://oauth2.googleapis.com/token",
                        "client_id": "c", "client_secret": "s",
                        "scopes": ["https://www.googleapis.com/auth/gmail.compose"],
                    })
                ))
                with patch.object(DraftService, "_build_gmail_client", return_value=mock_gmail):
                    await svc.push_to_draft(
                        job_id=job_id,
                        email_body=email_body,
                        to_address=to_address,
                        session=session,
                    )
        finally:
            await _teardown_db(engine)

    run_async(_run())

    # drafts.create must be called exactly once
    assert mock_gmail.users().drafts().create.call_count == 1, (
        f"Expected 1 call to drafts.create, got {mock_gmail.users().drafts().create.call_count}"
    )

    # messages.send must NEVER be called
    assert mock_gmail.users().messages().send.call_count == 0, (
        "Draft_Service called messages.send — this must never happen!"
    )


# ── Property 6: Draft creation updates job status to Draft Created ────────────

@given(email_body=_non_empty_text)
@settings(max_examples=50, deadline=None)
def test_draft_creation_updates_status_to_draft_created(email_body: str):
    """
    # Feature: kazibot, Property 6: Draft creation updates job status to Draft Created
    **Validates: Requirements 3.4**

    After push_to_draft() returns successfully, the persisted job status
    must be exactly draft_created.
    """
    engine = _make_engine()
    factory = _make_factory(engine)
    mock_gmail = _make_mock_gmail()

    async def _run():
        await _setup_db(engine)
        try:
            job_id = await _create_job(factory)
            async with factory() as session:
                svc = DraftService(token_store=MagicMock(
                    exists=MagicMock(return_value=True),
                    load=MagicMock(return_value={
                        "token": "t", "refresh_token": "r",
                        "token_uri": "https://oauth2.googleapis.com/token",
                        "client_id": "c", "client_secret": "s",
                        "scopes": ["https://www.googleapis.com/auth/gmail.compose"],
                    })
                ))
                with patch.object(DraftService, "_build_gmail_client", return_value=mock_gmail):
                    await svc.push_to_draft(
                        job_id=job_id,
                        email_body=email_body,
                        to_address=None,
                        session=session,
                    )

            # Verify persisted status
            async with factory() as session:
                result = await session.execute(
                    select(JobListing).where(JobListing.id == job_id)
                )
                job = result.scalar_one()
                assert job.status == JobStatus.draft_created, (
                    f"Expected status draft_created, got {job.status!r}"
                )
        finally:
            await _teardown_db(engine)

    run_async(_run())


# ── Property 7: Draft "To" field matches application email ───────────────────

@given(to_address=_email_st, email_body=_non_empty_text)
@settings(max_examples=100, deadline=None)
def test_draft_to_field_matches_application_email(to_address: str, email_body: str):
    """
    # Feature: kazibot, Property 7: Draft "To" field matches application email
    **Validates: Requirements 3.7**

    For any job listing with a non-null application_email, the draft payload
    passed to drafts.create must have a "To" header set to that email address.
    """
    engine = _make_engine()
    factory = _make_factory(engine)
    mock_gmail = _make_mock_gmail()
    captured_payloads: list[str] = []

    # Intercept the raw payload passed to drafts.create
    def _capture_create(userId, body):
        raw = body["message"]["raw"]
        captured_payloads.append(raw)
        mock_execute = MagicMock()
        mock_execute.execute.return_value = {"id": "draft123"}
        return mock_execute

    mock_gmail.users.return_value.drafts.return_value.create.side_effect = _capture_create

    async def _run():
        await _setup_db(engine)
        try:
            job_id = await _create_job(factory, email=to_address)
            async with factory() as session:
                svc = DraftService(token_store=MagicMock(
                    exists=MagicMock(return_value=True),
                    load=MagicMock(return_value={
                        "token": "t", "refresh_token": "r",
                        "token_uri": "https://oauth2.googleapis.com/token",
                        "client_id": "c", "client_secret": "s",
                        "scopes": ["https://www.googleapis.com/auth/gmail.compose"],
                    })
                ))
                with patch.object(DraftService, "_build_gmail_client", return_value=mock_gmail):
                    await svc.push_to_draft(
                        job_id=job_id,
                        email_body=email_body,
                        to_address=to_address,
                        session=session,
                    )
        finally:
            await _teardown_db(engine)

    run_async(_run())

    assert len(captured_payloads) == 1, "Expected exactly one call to drafts.create"

    # Decode the base64url payload and parse the MIME message
    raw_bytes = base64.urlsafe_b64decode(captured_payloads[0] + "==")
    msg = email_lib.message_from_bytes(raw_bytes)
    to_header = msg.get("To", "")

    assert to_address in to_header, (
        f"Expected To header to contain '{to_address}', got '{to_header}'"
    )
