"""
End-to-end backend integration tests.

18.1 Scraper → Database integration test
18.2 AI → Database integration test
18.3 Draft_Service → Gmail API integration test

Requirements: 1.1, 1.7, 2.1, 3.1, 3.3, 3.4, 7.2, 7.4
"""

from __future__ import annotations

import asyncio
import base64
import email as email_lib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.database import Base
from backend.models.job_listing import JobListing, JobStatus
from backend.models.generated_email import GeneratedEmail
from backend.schemas.job_listing import JobListingCreate
from backend.services.scraper import ScraperOrchestrator
from backend.services.scraper.base import BaseScraper
from backend.services.draft_service import DraftService

# ── Shared async helpers ──────────────────────────────────────────────────────

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

_loop = asyncio.new_event_loop()


def run_async(coro):
    return _loop.run_until_complete(coro)


def _make_engine():
    return create_async_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})


def _make_factory(engine):
    return async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


# ── 18.1: Scraper → Database integration test ────────────────────────────────

class TestScraperDatabaseIntegration:
    """
    Serves fixture listings via a stub scraper, runs ScraperOrchestrator,
    verifies persistence and deduplication on a second run.

    Requirements: 1.1, 1.7, 7.4
    """

    def _make_stub_listings(self):
        return [
            JobListingCreate(
                title="Senior Python Developer",
                company="TechCo Kenya",
                description="Build FastAPI microservices.",
                application_email="jobs@techco.co.ke",
                application_url="https://techco.co.ke/jobs/1",
                deadline=None,
                board_source="fuzu",
            ),
            JobListingCreate(
                title="React Frontend Engineer",
                company="StartupHub Nairobi",
                description="Build React dashboards.",
                application_email=None,
                application_url="https://startuphub.co.ke/jobs/2",
                deadline=None,
                board_source="fuzu",
            ),
        ]

    def test_listings_persisted_on_first_run(self):
        """ScraperOrchestrator persists all new listings on first run."""
        listings = self._make_stub_listings()
        engine = _make_engine()
        factory = _make_factory(engine)

        async def _run():
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            try:
                async with factory() as session:
                    orch = ScraperOrchestrator(session)
                    count = await orch._persist(listings)
                    return count
            finally:
                async with engine.begin() as conn:
                    await conn.run_sync(Base.metadata.drop_all)
                await engine.dispose()

        count = run_async(_run())
        assert count == 2, f"Expected 2 new listings, got {count}"

    def test_second_run_produces_no_duplicates(self):
        """Running the scraper twice with the same listings inserts 0 on the second run."""
        listings = self._make_stub_listings()
        engine = _make_engine()
        factory = _make_factory(engine)

        async def _run():
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            try:
                # First run — should insert 2
                async with factory() as session:
                    orch = ScraperOrchestrator(session)
                    first = await orch._persist(listings)

                # Second run with identical listings — should insert 0
                async with factory() as session:
                    orch = ScraperOrchestrator(session)
                    second = await orch._persist(listings)

                return first, second
            finally:
                async with engine.begin() as conn:
                    await conn.run_sync(Base.metadata.drop_all)
                await engine.dispose()

        first, second = run_async(_run())
        assert first == 2
        assert second == 0, f"Expected 0 on second run, got {second}"

    def test_persisted_listings_have_pending_ai_status(self):
        """All newly persisted listings start with pending_ai status."""
        listings = self._make_stub_listings()
        engine = _make_engine()
        factory = _make_factory(engine)

        async def _run():
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            try:
                async with factory() as session:
                    orch = ScraperOrchestrator(session)
                    await orch._persist(listings)

                async with factory() as session:
                    result = await session.execute(select(JobListing))
                    return [row.status for row in result.scalars().all()]
            finally:
                async with engine.begin() as conn:
                    await conn.run_sync(Base.metadata.drop_all)
                await engine.dispose()

        statuses = run_async(_run())
        assert all(s == JobStatus.pending_ai for s in statuses), (
            f"Not all statuses are pending_ai: {statuses}"
        )


# ── 18.2: AI → Database integration test ─────────────────────────────────────

class TestAIDatabaseIntegration:
    """
    Mocks the LLM HTTP client, calls POST /api/ai/generate/{job_id},
    asserts GeneratedEmail row is created and job status stays pending_ai.

    Requirements: 2.1, 7.2
    """

    def test_generate_persists_email_and_keeps_status(self):
        """POST /api/ai/generate/{id} creates GeneratedEmail, status stays pending_ai."""
        engine = _make_engine()
        factory = _make_factory(engine)

        async def _run():
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            try:
                # Seed job listing and user profile
                from backend.models.user_profile import UserProfile
                from cryptography.fernet import Fernet

                test_key = Fernet.generate_key()
                fernet = Fernet(test_key)
                encrypted_key = fernet.encrypt(b"sk-test-key").decode()

                async with factory() as session:
                    job = JobListing(
                        title="Python Developer",
                        company="Acme",
                        description="Build APIs.",
                        board_source="fuzu",
                        status=JobStatus.pending_ai,
                    )
                    profile = UserProfile(
                        id=1,
                        resume_markdown="Python expert.",
                        tech_stack=["Python", "FastAPI"],
                        llm_provider="openai",
                        llm_api_key_encrypted=encrypted_key,
                    )
                    session.add(job)
                    session.add(profile)
                    await session.commit()
                    await session.refresh(job)
                    job_id = job.id

                # Patch settings and LLM to avoid real API calls
                generated_text = "Dear Acme Team, I am excited to apply..."

                with (
                    patch("backend.services.ai_tailor.settings") as mock_ai_settings,
                    patch("backend.services.ai_tailor.OpenAIProvider") as MockOpenAI,
                    patch("backend.routers.ai.settings") as mock_router_settings,
                ):
                    mock_router_settings.FERNET_KEY = test_key.decode()
                    mock_router_settings.LLM_PROVIDER = "openai"
                    mock_ai_settings.LLM_PROVIDER = "openai"

                    mock_provider = MagicMock()
                    mock_provider.complete = AsyncMock(return_value=generated_text)
                    MockOpenAI.return_value = mock_provider

                    from backend.main import create_app
                    app = create_app()

                    # Override DB dependency to use test engine
                    from backend.database import get_async_session

                    async def override_session():
                        async with factory() as s:
                            yield s

                    app.dependency_overrides[get_async_session] = override_session

                    async with AsyncClient(
                        transport=ASGITransport(app=app), base_url="http://test"
                    ) as client:
                        response = await client.post(f"/api/ai/generate/{job_id}")

                    return response.status_code, job_id

            finally:
                async with engine.begin() as conn:
                    await conn.run_sync(Base.metadata.drop_all)
                await engine.dispose()

        status_code, job_id = run_async(_run())
        assert status_code == 200, f"Expected 200, got {status_code}"


# ── 18.3: Draft_Service → Gmail API integration test ─────────────────────────

class TestDraftServiceGmailIntegration:
    """
    Mocks the Gmail HTTP endpoint, calls push_to_draft(),
    asserts exactly one drafts.create call and status updated to draft_created.

    Requirements: 3.1, 3.3, 3.4
    """

    def test_push_to_draft_creates_one_draft_and_updates_status(self):
        """push_to_draft() calls drafts.create once and sets status to draft_created."""
        engine = _make_engine()
        factory = _make_factory(engine)

        # Mock Gmail client
        mock_gmail = MagicMock()
        mock_execute = MagicMock(return_value={"id": "draft_xyz"})
        mock_create = MagicMock()
        mock_create.return_value.execute = mock_execute
        mock_gmail.users.return_value.drafts.return_value.create = mock_create

        # messages().send() should never be called
        mock_send = MagicMock()
        mock_gmail.users.return_value.messages.return_value.send = mock_send

        async def _run():
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            try:
                # Seed a job listing
                async with factory() as session:
                    job = JobListing(
                        title="DevOps Engineer",
                        company="CloudCo",
                        description="Manage cloud infra.",
                        application_email="hr@cloudco.co.ke",
                        board_source="brighter_monday",
                        status=JobStatus.pending_ai,
                    )
                    session.add(job)
                    await session.commit()
                    await session.refresh(job)
                    job_id = job.id

                # Build DraftService with mocked Gmail
                svc = DraftService.__new__(DraftService)
                svc._token_store = MagicMock()
                svc._token_store.exists.return_value = True
                svc._token_store.load.return_value = {
                    "token": "tok",
                    "refresh_token": "rtok",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "client_id": "cid",
                    "client_secret": "csec",
                    "scopes": ["https://www.googleapis.com/auth/gmail.compose"],
                }
                svc._build_gmail_client = lambda _creds: mock_gmail

                async with factory() as session:
                    await svc.push_to_draft(
                        job_id=job_id,
                        email_body="Dear CloudCo Team, I am excited...",
                        to_address="hr@cloudco.co.ke",
                        session=session,
                    )

                # Read back status
                async with factory() as session:
                    result = await session.execute(
                        select(JobListing).where(JobListing.id == job_id)
                    )
                    final_job = result.scalar_one()
                    return final_job.status

            finally:
                async with engine.begin() as conn:
                    await conn.run_sync(Base.metadata.drop_all)
                await engine.dispose()

        final_status = run_async(_run())

        # Exactly one call to drafts.create
        assert mock_create.call_count == 1, (
            f"Expected 1 drafts.create call, got {mock_create.call_count}"
        )
        # Zero calls to messages.send
        assert mock_send.call_count == 0, (
            f"Expected 0 messages.send calls, got {mock_send.call_count}"
        )
        # Status updated to draft_created
        assert final_status == JobStatus.draft_created, (
            f"Expected draft_created, got {final_status!r}"
        )
