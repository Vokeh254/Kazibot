"""
Integration tests for database-level constraints.

Validates: Requirements 7.4

Covers:
  1. Unique constraint on (title, company, board_source): inserting a duplicate
     triple must raise an IntegrityError.
  2. Foreign-key constraint on GeneratedEmail.job_listing_id: inserting a
     GeneratedEmail with a non-existent parent must raise an IntegrityError.
"""

import asyncio
from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.database import Base
from backend.models.generated_email import GeneratedEmail
from backend.models.job_listing import JobListing, JobStatus

# ── Shared event loop & helpers ───────────────────────────────────────────────

_loop = asyncio.new_event_loop()


def run_async(coro):
    return _loop.run_until_complete(coro)


TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


def _make_engine():
    return create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
    )


def _make_factory(engine):
    return async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _base_job_kwargs(**overrides) -> dict:
    """Return a minimal valid set of kwargs for a JobListing."""
    defaults = dict(
        title="Software Engineer",
        company="Acme Corp",
        board_source="fuzu",
        status=JobStatus.pending_ai,
        scraped_at=_now(),
    )
    defaults.update(overrides)
    return defaults


# ── Test 1: Unique constraint (title, company, board_source) ──────────────────


def test_duplicate_job_listing_raises_integrity_error():
    """Inserting two JobListings with the same (title, company, board_source)
    must raise an IntegrityError (Requirement 7.4).
    """
    engine = _make_engine()
    factory = _make_factory(engine)

    async def _run():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        try:
            # Insert the first listing — must succeed.
            async with factory() as session:
                job1 = JobListing(**_base_job_kwargs())
                session.add(job1)
                await session.commit()

            # Insert a duplicate — same title + company + board_source.
            async with factory() as session:
                job2 = JobListing(**_base_job_kwargs())
                session.add(job2)
                with pytest.raises(IntegrityError):
                    await session.commit()
        finally:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.drop_all)
            await engine.dispose()

    run_async(_run())


def test_different_board_source_is_not_duplicate():
    """Two listings that share title+company but differ in board_source are
    distinct and both inserts must succeed.
    """
    engine = _make_engine()
    factory = _make_factory(engine)

    async def _run():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        try:
            async with factory() as session:
                job1 = JobListing(**_base_job_kwargs(board_source="fuzu"))
                job2 = JobListing(**_base_job_kwargs(board_source="brighter_monday"))
                session.add_all([job1, job2])
                # Should not raise.
                await session.commit()
                assert job1.id is not None
                assert job2.id is not None
        finally:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.drop_all)
            await engine.dispose()

    run_async(_run())


def test_different_company_is_not_duplicate():
    """Two listings that share title+board_source but differ in company are
    distinct and both inserts must succeed.
    """
    engine = _make_engine()
    factory = _make_factory(engine)

    async def _run():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        try:
            async with factory() as session:
                job1 = JobListing(**_base_job_kwargs(company="Acme Corp"))
                job2 = JobListing(**_base_job_kwargs(company="Other Ltd"))
                session.add_all([job1, job2])
                await session.commit()
                assert job1.id is not None
                assert job2.id is not None
        finally:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.drop_all)
            await engine.dispose()

    run_async(_run())


# ── Test 2: Foreign-key constraint on GeneratedEmail ─────────────────────────


def test_generated_email_without_parent_raises_integrity_error():
    """Inserting a GeneratedEmail whose job_listing_id references a
    non-existent JobListing must raise an IntegrityError (Requirement 7.4).
    """
    engine = _make_engine()
    factory = _make_factory(engine)

    async def _run():
        # Enable FK enforcement for SQLite (off by default).
        async with engine.connect() as conn:
            await conn.exec_driver_sql("PRAGMA foreign_keys = ON")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        try:
            async with factory() as session:
                # Bind FK enforcement to this connection too.
                await session.exec_driver_sql("PRAGMA foreign_keys = ON")
                orphan = GeneratedEmail(
                    job_listing_id=999_999,  # No such parent exists.
                    email_body="Hello!",
                    created_at=_now(),
                    updated_at=_now(),
                )
                session.add(orphan)
                with pytest.raises(IntegrityError):
                    await session.commit()
        finally:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.drop_all)
            await engine.dispose()

    run_async(_run())


def test_generated_email_with_valid_parent_succeeds():
    """Inserting a GeneratedEmail that references an existing JobListing must
    succeed without error.
    """
    engine = _make_engine()
    factory = _make_factory(engine)

    async def _run():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        try:
            async with factory() as session:
                job = JobListing(**_base_job_kwargs())
                session.add(job)
                await session.flush()  # Populate job.id before using it.

                email = GeneratedEmail(
                    job_listing_id=job.id,
                    email_body="Dear Hiring Manager …",
                    created_at=_now(),
                    updated_at=_now(),
                )
                session.add(email)
                await session.commit()
                assert email.id is not None
        finally:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.drop_all)
            await engine.dispose()

    run_async(_run())
