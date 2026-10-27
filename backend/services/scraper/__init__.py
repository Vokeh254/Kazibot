"""
ScraperOrchestrator — coordinates all registered board plugins.

Responsibilities:
- Runs each board plugin via `scrape_with_retry()`
- Deduplicates results against the database using the (title, company, board_source) unique constraint
- Persists newly discovered listings
- Returns the count of newly added listings

Requirements: 1.7, 1.8, 1.9
"""

from __future__ import annotations

import logging
from typing import List, Type

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.job_listing import JobListing, JobStatus
from backend.schemas.job_listing import JobListingCreate
from backend.services.scraper.base import BaseScraper
from backend.services.scraper.brighter_monday import BrighterMondayScraper
from backend.services.scraper.fuzu import FuzuScraper
from backend.services.scraper.my_job_mag import MyJobMagScraper

logger = logging.getLogger(__name__)

# ── Registered board plugins ──────────────────────────────────────────────────
_BOARD_PLUGINS: List[Type[BaseScraper]] = [
    FuzuScraper,
    BrighterMondayScraper,
    MyJobMagScraper,
]


class ScraperOrchestrator:
    """Coordinates all registered scraper plugins for a single scraping session."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def run(self) -> int:
        """Execute all board scrapers and persist new listings.

        Returns:
            Number of newly persisted job listings.
        """
        all_listings: List[JobListingCreate] = []

        for plugin_cls in _BOARD_PLUGINS:
            plugin = plugin_cls()
            logger.info("Starting scrape for board: %s", plugin.board_name)
            listings = await plugin.scrape_with_retry()
            logger.info(
                "Board '%s' returned %d listings", plugin.board_name, len(listings)
            )
            all_listings.extend(listings)

        return await self._persist(all_listings)

    async def _persist(self, listings: List[JobListingCreate]) -> int:
        """Persist listings to the database, skipping duplicates.

        Uses INSERT OR IGNORE semantics so the unique constraint on
        (title, company, board_source) is respected without raising errors.

        Returns:
            Number of rows actually inserted.
        """
        inserted = 0
        for listing in listings:
            try:
                job = JobListing(
                    title=listing.title,
                    company=listing.company,
                    description=listing.description,
                    application_email=listing.application_email,
                    application_url=listing.application_url,
                    deadline=listing.deadline,
                    status=JobStatus.pending_ai,
                    board_source=listing.board_source,
                )
                self._session.add(job)
                await self._session.flush()  # Detect constraint violations early
                inserted += 1
            except IntegrityError:
                await self._session.rollback()
                logger.debug(
                    "Duplicate skipped: '%s' / '%s' on '%s'",
                    listing.title,
                    listing.company,
                    listing.board_source,
                )
            except Exception as exc:
                await self._session.rollback()
                logger.error(
                    "Unexpected error persisting listing '%s': %s", listing.title, exc
                )

        await self._session.commit()
        logger.info("ScraperOrchestrator persisted %d new listings", inserted)
        return inserted
