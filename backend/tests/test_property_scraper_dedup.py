"""
Property-based test for scraper deduplication.

# Feature: kazibot, Property 1: Scraper deduplication preserves uniqueness

For any set of JobListingCreate objects (including duplicates), running
ScraperOrchestrator._persist() results in no two rows in the database sharing
the same (title, company, board_source) triple.

Validates: Requirements 1.7, 7.4
"""

import asyncio

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import select

from backend.database import Base
from backend.models.job_listing import JobListing
from backend.schemas.job_listing import JobListingCreate
from backend.services.scraper import ScraperOrchestrator

# ── Shared event loop ─────────────────────────────────────────────────────────

_loop = asyncio.new_event_loop()


def run_async(coro):
    return _loop.run_until_complete(coro)


# ── In-memory SQLite engine helpers ──────────────────────────────────────────

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


def _make_engine():
    return create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
    )


def _make_factory(engine):
    return async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


# ── Hypothesis strategies ─────────────────────────────────────────────────────

# Small pools so Hypothesis naturally generates duplicates
_TITLES = st.sampled_from(["Software Engineer", "Data Analyst", "Product Manager", "DevOps Engineer"])
_COMPANIES = st.sampled_from(["Acme Corp", "Globex Ltd", "Initech", "Umbrella Inc"])
_BOARD_SOURCES = st.sampled_from(["fuzu", "brighter_monday", "my_job_mag"])

_printable = st.characters(whitelist_categories=("L", "N", "P", "Z"))
_nullable_text = st.one_of(st.none(), st.text(alphabet=_printable, min_size=1, max_size=100))


@st.composite
def job_listing_create_st(draw):
    """Generate a JobListingCreate from a small pool to ensure duplicates occur."""
    return JobListingCreate(
        title=draw(_TITLES),
        company=draw(_COMPANIES),
        board_source=draw(_BOARD_SOURCES),
        description=draw(_nullable_text),
        application_email=None,
        application_url=None,
        deadline=None,
    )


@st.composite
def listings_list_st(draw):
    """Generate a list of JobListingCreate objects, with likely duplicates."""
    return draw(st.lists(job_listing_create_st(), min_size=1, max_size=20))


# ── Property 1: Scraper deduplication preserves uniqueness ───────────────────

@given(listings=listings_list_st())
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
def test_scraper_dedup_preserves_uniqueness(listings):
    """
    **Property 1: Scraper deduplication preserves uniqueness**
    **Validates: Requirements 1.7, 7.4**

    For any set of JobListingCreate objects (including duplicates), after
    calling ScraperOrchestrator._persist(), no two rows in the database share
    the same (title, company, board_source) triple.
    """
    engine = _make_engine()
    factory = _make_factory(engine)

    async def _run():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        try:
            async with factory() as session:
                orchestrator = ScraperOrchestrator(session)
                await orchestrator._persist(listings)

            # Query all rows and verify uniqueness of (title, company, board_source)
            async with factory() as session:
                result = await session.execute(select(JobListing))
                rows = result.scalars().all()

                triples = [(row.title, row.company, row.board_source) for row in rows]
                # Assert no duplicates: set length must equal list length
                assert len(triples) == len(set(triples)), (
                    f"Duplicate (title, company, board_source) triples found in DB: "
                    f"{[t for t in triples if triples.count(t) > 1]}"
                )
        finally:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.drop_all)
            await engine.dispose()

    run_async(_run())
