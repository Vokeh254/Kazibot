"""
BaseScraper abstract base class and shared Playwright utilities.

Every job-board scraper must extend BaseScraper and implement `scrape()`.
The base class provides:
  - Configurable User-Agent (from settings.CUSTOM_USER_AGENT)
  - Randomised inter-request delay of 3–7 seconds (Requirement 1.3)
  - Headless/headful toggle from settings (Requirement 1.5)
  - Retry wrapper with logging on failure (Requirement 1.8)

Requirements: 1.2, 1.3, 1.4, 1.5, 1.8, 1.9
"""

from __future__ import annotations

import asyncio
import logging
import random
from abc import ABC, abstractmethod
from typing import List

from backend.config import settings
from backend.schemas.job_listing import JobListingCreate

logger = logging.getLogger(__name__)

_MIN_DELAY: float = 3.0
_MAX_DELAY: float = 7.0
_MAX_RETRIES: int = 3


class BaseScraper(ABC):
    """Abstract base class for all job-board scraper plugins.

    Subclasses must set `board_name` and implement `scrape()`.
    """

    #: Unique identifier for this board (e.g., "fuzu", "brighter_monday")
    board_name: str = ""

    def __init__(self) -> None:
        self._user_agent: str = settings.CUSTOM_USER_AGENT
        self._headless: bool = True  # Override via subclass or config if needed

    # ── Public interface ──────────────────────────────────────────────────────

    @abstractmethod
    async def scrape(self) -> List[JobListingCreate]:
        """Scrape all job listings from this board.

        Returns:
            A list of JobListingCreate objects ready for persistence.
        """
        ...

    async def scrape_with_retry(self) -> List[JobListingCreate]:
        """Run `scrape()` with up to _MAX_RETRIES attempts.

        On exhaustion, logs the failure and returns an empty list so that
        other boards can continue processing (Requirement 1.8).
        """
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                return await self.scrape()
            except Exception as exc:
                logger.error(
                    "Scrape attempt %d/%d failed for board '%s': %s",
                    attempt,
                    _MAX_RETRIES,
                    self.board_name,
                    exc,
                    exc_info=True,
                )
                if attempt < _MAX_RETRIES:
                    await self._random_delay()

        logger.error(
            "All %d scrape attempts exhausted for board '%s'. Skipping.",
            _MAX_RETRIES,
            self.board_name,
        )
        return []

    # ── Helpers available to subclasses ──────────────────────────────────────

    async def _random_delay(self) -> None:
        """Sleep for a random duration between _MIN_DELAY and _MAX_DELAY seconds.

        This mimics human browsing behaviour and avoids triggering rate limits
        (Requirement 1.3).
        """
        delay = random.uniform(_MIN_DELAY, _MAX_DELAY)
        logger.debug(
            "Board '%s': sleeping %.2f s before next request", self.board_name, delay
        )
        await asyncio.sleep(delay)

    def _browser_launch_options(self) -> dict:
        """Return Playwright browser launch options with the configured User-Agent."""
        return {
            "headless": self._headless,
            "args": [f"--user-agent={self._user_agent}"],
        }
