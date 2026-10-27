"""
Property-based test for scraper delay invariant.

# Feature: kazibot, Property 3: Scraper delay invariant

For any sequence of N ≥ 2 requests made by a BaseScraper, the delay between
each consecutive pair of requests is always in the range [3, 7] seconds.

**Validates: Requirements 1.3**
"""

import asyncio
from typing import List
from unittest.mock import AsyncMock, patch

from hypothesis import given, settings
from hypothesis import strategies as st

from backend.schemas.job_listing import JobListingCreate
from backend.services.scraper.base import BaseScraper, _MAX_DELAY, _MIN_DELAY

# ── Shared event loop ─────────────────────────────────────────────────────────

_loop = asyncio.new_event_loop()


def run_async(coro):
    return _loop.run_until_complete(coro)


# ── Minimal concrete subclass for testing ─────────────────────────────────────

class _DelayCaptureScraper(BaseScraper):
    """Minimal concrete subclass that calls _random_delay() N times."""

    board_name = "test_delay_board"

    def __init__(self, n_requests: int) -> None:
        super().__init__()
        self._n_requests = n_requests

    async def scrape(self) -> List[JobListingCreate]:
        for _ in range(self._n_requests):
            await self._random_delay()
        return []


# ── Property 3: Scraper delay invariant ──────────────────────────────────────

@given(n=st.integers(min_value=2, max_value=20))
@settings(max_examples=100)
def test_scraper_delay_invariant(n: int):
    """
    # Feature: kazibot, Property 3: Scraper delay invariant
    **Validates: Requirements 1.3**

    For any sequence of N ≥ 2 requests, every recorded asyncio.sleep call
    made by BaseScraper._random_delay() is in the range [_MIN_DELAY, _MAX_DELAY]
    (i.e. [3.0, 7.0] seconds).
    """
    recorded_delays: List[float] = []

    async def _capturing_sleep(delay: float) -> None:
        recorded_delays.append(delay)

    async def _run():
        scraper = _DelayCaptureScraper(n_requests=n)
        with patch("backend.services.scraper.base.asyncio.sleep", side_effect=_capturing_sleep):
            await scraper.scrape()

    run_async(_run())

    # Exactly N delays should have been recorded (one per request)
    assert len(recorded_delays) == n, (
        f"Expected {n} delay calls, got {len(recorded_delays)}"
    )

    # Every delay must lie within [_MIN_DELAY, _MAX_DELAY]
    for i, delay in enumerate(recorded_delays):
        assert _MIN_DELAY <= delay <= _MAX_DELAY, (
            f"Delay {i} out of range [{_MIN_DELAY}, {_MAX_DELAY}]: got {delay!r} "
            f"(n={n}, all_delays={recorded_delays})"
        )
