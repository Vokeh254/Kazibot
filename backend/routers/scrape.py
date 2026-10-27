"""
Scrape router — triggers a new scraping session.

Endpoint:
  POST /api/scrape — Run ScraperOrchestrator and return count of new listings.

Requirements: 1.7, 1.8
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_async_session
from backend.services.scraper import ScraperOrchestrator

router = APIRouter(tags=["scrape"])


class ScrapeResult(BaseModel):
    new_listings: int
    message: str


@router.post("/scrape", response_model=ScrapeResult)
async def trigger_scrape(
    session: AsyncSession = Depends(get_async_session),
) -> ScrapeResult:
    """Trigger a full scraping session across all registered job boards.

    Returns the number of new listings persisted to the database.
    """
    orchestrator = ScraperOrchestrator(session)
    new_count = await orchestrator.run()
    return ScrapeResult(
        new_listings=new_count,
        message=f"Scrape complete. {new_count} new listing(s) added.",
    )
