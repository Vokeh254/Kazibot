"""
Property-based tests for data persistence round-trip.

# Feature: kazibot, Property 11: Data persistence round-trip

For any JobListing, GeneratedEmail, or UserProfile object, writing it to
the database and reading it back shall yield an object with all fields
equal to the original (including all nullable fields).

Validates: Requirements 7.1, 7.2, 7.3
"""

import asyncio
from datetime import datetime, timezone

from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.models.job_listing import JobListing, JobStatus
from backend.models.generated_email import GeneratedEmail
from backend.models.user_profile import UserProfile
from backend.database import Base

# ── Shared event loop ─────────────────────────────────────────────────────────
# Re-use one event loop for all Hypothesis examples to avoid per-example loop
# creation overhead.

_loop = asyncio.new_event_loop()


def run_async(coro):
    return _loop.run_until_complete(coro)


# ── Shared in-memory engine (one per test function) ───────────────────────────
# We create/drop tables around each top-level @given call, but reuse the
# engine and session factory inside all 100 examples of that call so that
# schema creation is done only once.

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


def _make_engine():
    return create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
    )


def _make_factory(engine):
    return async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


# ── Hypothesis strategies ─────────────────────────────────────────────────────

_printable = st.characters(whitelist_categories=("L", "N", "P", "Z"))

short_text = st.text(alphabet=_printable, min_size=1, max_size=80).filter(
    lambda s: s.strip() != ""
)
long_text = st.text(alphabet=_printable, min_size=1, max_size=300).filter(
    lambda s: s.strip() != ""
)
nullable_short = st.one_of(st.none(), short_text)

url_strategy = st.one_of(
    st.none(),
    st.builds(
        lambda h, p: f"https://{h}/{p}",
        h=st.from_regex(r"[a-z]{3,10}\.[a-z]{2,4}", fullmatch=True),
        p=st.from_regex(r"[a-z0-9_-]{0,20}", fullmatch=True),
    ),
)

email_strategy = st.one_of(
    st.none(),
    st.builds(
        lambda u, d: f"{u}@{d}.com",
        u=st.from_regex(r"[a-z]{3,10}", fullmatch=True),
        d=st.from_regex(r"[a-z]{3,10}", fullmatch=True),
    ),
)

utc_dt = st.datetimes(
    min_value=datetime(2020, 1, 1),
    max_value=datetime(2030, 12, 31),
    timezones=st.just(timezone.utc),
)

nullable_utc_dt = st.one_of(st.none(), utc_dt)

job_status_st = st.sampled_from(list(JobStatus))
board_source_st = st.sampled_from(["fuzu", "brighter_monday", "my_job_mag"])

tech_stack_st = st.one_of(
    st.none(),
    st.lists(
        st.from_regex(r"[A-Za-z][A-Za-z0-9+#.]{0,12}", fullmatch=True),
        min_size=0,
        max_size=8,
    ),
)


@st.composite
def job_listing_st(draw):
    return dict(
        title=draw(short_text)[:255],
        company=draw(short_text)[:255],
        description=draw(st.one_of(st.none(), long_text)),
        application_email=draw(email_strategy),
        application_url=draw(url_strategy),
        deadline=draw(nullable_utc_dt),
        status=draw(job_status_st),
        board_source=draw(board_source_st),
        scraped_at=draw(utc_dt),
    )


@st.composite
def user_profile_st(draw):
    return dict(
        resume_markdown=draw(st.one_of(st.none(), long_text)),
        tech_stack=draw(tech_stack_st),
        github_url=draw(url_strategy),
        portfolio_url=draw(url_strategy),
        llm_provider=draw(st.one_of(st.none(), st.sampled_from(["openai", "anthropic"]))),
        llm_api_key_encrypted=draw(nullable_short),
    )


# ── Property 11a: JobListing round-trip ───────────────────────────────────────

@given(data=job_listing_st())
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_job_listing_round_trip(data):
    # Feature: kazibot, Property 11: Data persistence round-trip
    # **Validates: Requirements 7.1**
    engine = _make_engine()
    factory = _make_factory(engine)

    async def _run():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        try:
            async with factory() as session:
                obj = JobListing(**data)
                session.add(obj)
                await session.commit()
                job_id = obj.id

            async with factory() as session:
                result = await session.get(JobListing, job_id)
                assert result is not None
                assert result.title == data["title"]
                assert result.company == data["company"]
                assert result.description == data["description"]
                assert result.application_email == data["application_email"]
                assert result.application_url == data["application_url"]
                assert result.status == data["status"]
                assert result.board_source == data["board_source"]
                # SQLite drops tzinfo on round-trip; compare naive UTC values.
                # We strip tzinfo from both sides and truncate to seconds to
                # handle DB microsecond precision loss.
                def naive_sec(dt):
                    return dt.replace(tzinfo=None, microsecond=0)

                if data["deadline"] is not None:
                    assert result.deadline is not None
                    assert naive_sec(result.deadline) == naive_sec(data["deadline"])
                else:
                    assert result.deadline is None
                assert naive_sec(result.scraped_at) == naive_sec(data["scraped_at"])
        finally:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.drop_all)
            await engine.dispose()

    run_async(_run())


# ── Property 11b: GeneratedEmail round-trip ───────────────────────────────────

@given(job_data=job_listing_st(), email_body=long_text)
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_generated_email_round_trip(job_data, email_body):
    # Feature: kazibot, Property 11: Data persistence round-trip
    # **Validates: Requirements 7.2**
    engine = _make_engine()
    factory = _make_factory(engine)

    async def _run():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        try:
            async with factory() as session:
                job = JobListing(**job_data)
                session.add(job)
                await session.flush()

                now = datetime.now(timezone.utc)
                email = GeneratedEmail(
                    job_listing_id=job.id,
                    email_body=email_body,
                    created_at=now,
                    updated_at=now,
                )
                session.add(email)
                await session.commit()
                email_id = email.id
                parent_id = job.id

            async with factory() as session:
                result = await session.get(GeneratedEmail, email_id)
                assert result is not None
                assert result.email_body == email_body
                assert result.job_listing_id == parent_id
                assert result.created_at is not None
                assert result.updated_at is not None
        finally:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.drop_all)
            await engine.dispose()

    run_async(_run())


# ── Property 11c: UserProfile round-trip ─────────────────────────────────────

@given(data=user_profile_st())
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
def test_user_profile_round_trip(data):
    # Feature: kazibot, Property 11: Data persistence round-trip
    # **Validates: Requirements 7.3**
    engine = _make_engine()
    factory = _make_factory(engine)

    async def _run():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        try:
            async with factory() as session:
                profile = UserProfile(**data)
                session.add(profile)
                await session.commit()
                profile_id = profile.id

            async with factory() as session:
                result = await session.get(UserProfile, profile_id)
                assert result is not None
                assert result.resume_markdown == data["resume_markdown"]
                assert result.tech_stack == data["tech_stack"]
                assert result.github_url == data["github_url"]
                assert result.portfolio_url == data["portfolio_url"]
                assert result.llm_provider == data["llm_provider"]
                assert result.llm_api_key_encrypted == data["llm_api_key_encrypted"]
        finally:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.drop_all)
            await engine.dispose()

    run_async(_run())
