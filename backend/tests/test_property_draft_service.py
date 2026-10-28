"""
Property-based tests for Draft_Service.

Covers three correctness properties:

Property 5: Draft_Service never calls the Gmail send endpoint
  # Feature: kazibot, Property 5: Draft_Service never calls the Gmail send endpoint
  Validates: Requirements 3.3

Property 6: Draft creation updates job status to Draft Created
  # Feature: kazibot, Property 6: Draft creation updates job status to Draft Created
  Validates: Requirements 3.4

Property 7: Draft "To" field matches application email
  # Feature: kazibot, Property 7: Draft "To" field matches application email
  Validates: Requirements 3.7
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

from backend.database import Base
from backend.models.job_listing import JobListing, JobStatus
from backend.services.draft_service import DraftService

# ── Async helpers ─────────────────────────────────────────────────────────────

_loop = asyncio.new_event_loop()


def run_async(coro):
    return _loop.run_until_complete(coro)


TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


def _make_engine():
    return create_async_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})


def _make_factory(engine):
    return async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


async def _seed_job(factory, email: Optional[str] = None, status: JobStatus = JobStatus.pending_ai) -> int:
    """Insert a JobListing and return its id."""
    async with factory() as session:
        job = JobListing(
            title="Test Job",
            company="Test Corp",
            description="A job.",
            application_email=email,
            board_source="fuzu",
            status=status,
        )
        session.add(job)
        await session.commit()
        await session.refresh(job)
        return job.id


# ── Mock Gmail API client factory ─────────────────────────────────────────────

def _make_mock_gmail_client():
    """Return a mock Gmail API client that tracks calls."""
    mock_client = MagicMock()
    # drafts().create().execute() chain
    mock_execute = MagicMock(return_value={"id": "draft_abc123"})
    mock_create = MagicMock()
    mock_create.return_value.execute = mock_execute
    mock_client.users.return_value.drafts.return_value.create = mock_create

    # messages().send() should never be called — set it up so we can assert
    mock_send = MagicMock()
    mock_client.users.return_value.messages.return_value.send = mock_send

    return mock_client, mock_create, mock_send


# ── Hypothesis strategies ─────────────────────────────────────────────────────

_printable = st.characters(whitelist_categories=("L", "N", "P", "Z"))
_non_empty = st.text(alphabet=_printable, min_size=1, max_size=300)

_ASCII = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
_email_local = st.text(alphabet=_ASCII + "._%+-", min_size=1, max_size=20).filter(
    lambda s: s and s[0] not in "._%+-" and s[-1] not in "._%+-"
)
_email_domain = st.text(alphabet=_ASCII + "-", min_size=2, max_size=15).filter(
    lambda s: s and s[0] != "-" and s[-1] != "-"
)
_email_tld = st.sampled_from(["com", "co.ke", "org", "net", "io"])

_valid_email_st = st.builds(
    lambda local, domain, tld: f"{local}@{domain}.{tld}",
    local=_email_local,
    domain=_email_domain,
    tld=_email_tld,
)

_non_final_statuses = st.sampled_from([
    JobStatus.pending_ai,
    JobStatus.applied,
    JobStatus.skipped,
])


def _make_draft_service_with_mock_gmail(mock_gmail_client) -> DraftService:
    """Return a DraftService whose Gmail client is pre-mocked."""
    svc = DraftService.__new__(DraftService)
    svc._token_store = MagicMock()
    svc._token_store.exists.return_value = True
    svc._token_store.load.return_value = {
        "token": "fake-token",
        "refresh_token": "fake-refresh",
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": "fake-client-id",
        "client_secret": "fake-client-secret",
        "scopes": ["https://www.googleapis.com/auth/gmail.compose"],
    }
    # Patch _build_gmail_client to return our mock
    svc._build_gmail_client = lambda _creds: mock_gmail_client
    return svc


# ── Property 5: Draft_Service never calls the Gmail send endpoint ─────────────

@given(email_body=_non_empty)
@settings(max_examples=100, deadline=None)
def test_draft_service_never_calls_send_endpoint(email_body: str) -> None:
    """
    # Feature: kazibot, Property 5: Draft_Service never calls the Gmail send endpoint
    **Validates: Requirements 3.3**

    For any email body, push_to_draft() results in exactly one call to
    drafts.create and zero calls to messages.send.
    """
    mock_gmail, mock_create, mock_send = _make_mock_gmail_client()
    svc = _make_draft_service_with_mock_gmail(mock_gmail)

    engine = _make_engine()
    factory = _make_factory(engine)

    async def _run():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        try:
            job_id = await _seed_job(factory)
            async with factory() as session:
                await svc.push_to_draft(
                    job_id=job_id,
                    email_body=email_body,
                    to_address=None,
                    session=session,
                )
        finally:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.drop_all)
            await engine.dispose()

    run_async(_run())

    # Exactly one call to drafts.create
    assert mock_create.call_count == 1, (
        f"Expected 1 call to drafts.create, got {mock_create.call_count}"
    )
    # Zero calls to messages.send
    assert mock_send.call_count == 0, (
        f"Expected 0 calls to messages.send, got {mock_send.call_count}"
    )


# ── Property 6: Draft creation updates job status to Draft Created ─────────────

@given(initial_status=_non_final_statuses, email_body=_non_empty)
@settings(max_examples=100, deadline=None)
def test_draft_creation_updates_status_to_draft_created(
    initial_status: JobStatus,
    email_body: str,
) -> None:
    """
    # Feature: kazibot, Property 6: Draft creation updates job status to Draft Created
    **Validates: Requirements 3.4**

    For any job in any non-final status, after push_to_draft() succeeds,
    the persisted Job_Status is exactly draft_created.
    """
    from sqlalchemy import select

    mock_gmail, _, _ = _make_mock_gmail_client()
    svc = _make_draft_service_with_mock_gmail(mock_gmail)

    engine = _make_engine()
    factory = _make_factory(engine)

    async def _run():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        try:
            job_id = await _seed_job(factory, status=initial_status)
            async with factory() as session:
                await svc.push_to_draft(
                    job_id=job_id,
                    email_body=email_body,
                    to_address=None,
                    session=session,
                )
            # Read back status
            async with factory() as session:
                result = await session.execute(
                    select(JobListing).where(JobListing.id == job_id)
                )
                job = result.scalar_one()
                return job.status
        finally:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.drop_all)
            await engine.dispose()

    final_status = run_async(_run())

    assert final_status == JobStatus.draft_created, (
        f"Expected draft_created, got {final_status!r} "
        f"(initial_status={initial_status!r})"
    )


# ── Property 7: Draft "To" field matches application email ────────────────────

@given(application_email=_valid_email_st, email_body=_non_empty)
@settings(max_examples=100, deadline=None)
def test_draft_to_field_matches_application_email(
    application_email: str,
    email_body: str,
) -> None:
    """
    # Feature: kazibot, Property 7: Draft "To" field matches application email
    **Validates: Requirements 3.7**

    For any job with a non-null application_email, the Gmail draft payload
    passed to drafts.create has its "To" header set to exactly that address.
    """
    mock_gmail, mock_create, _ = _make_mock_gmail_client()
    svc = _make_draft_service_with_mock_gmail(mock_gmail)

    engine = _make_engine()
    factory = _make_factory(engine)

    async def _run():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        try:
            job_id = await _seed_job(factory, email=application_email)
            async with factory() as session:
                await svc.push_to_draft(
                    job_id=job_id,
                    email_body=email_body,
                    to_address=application_email,
                    session=session,
                )
        finally:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.drop_all)
            await engine.dispose()

    run_async(_run())

    # Extract the raw MIME payload from the drafts.create call
    call_kwargs = mock_create.call_args
    assert call_kwargs is not None, "drafts.create was never called"

    body_arg = call_kwargs.kwargs.get("body") or call_kwargs.args[0] if call_kwargs.args else call_kwargs.kwargs.get("body")
    raw_b64 = body_arg["message"]["raw"]
    raw_bytes = base64.urlsafe_b64decode(raw_b64 + "==")  # pad for safety
    msg = email_lib.message_from_bytes(raw_bytes)

    to_header = msg.get("To", "")
    assert to_header == application_email, (
        f"Draft 'To' header mismatch: expected {application_email!r}, got {to_header!r}"
    )
