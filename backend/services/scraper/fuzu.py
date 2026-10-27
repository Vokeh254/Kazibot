"""
FuzuScraper — scrapes IT/internship job listings from fuzu.com.

Uses Playwright for JavaScript-rendered page navigation.
Requirements: 1.1, 1.2, 1.6
"""

from __future__ import annotations

import logging
import re
from typing import List, Optional

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

from backend.schemas.job_listing import JobListingCreate
from backend.services.scraper.base import BaseScraper

logger = logging.getLogger(__name__)

_BOARD_URL = "https://fuzu.com/kenya/jobs?category=technology"
_BOARD_NAME = "fuzu"


class FuzuScraper(BaseScraper):
    """Scraper for Fuzu Kenya tech/internship listings."""

    board_name = _BOARD_NAME

    async def scrape(self) -> List[JobListingCreate]:
        listings: List[JobListingCreate] = []

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(**self._browser_launch_options())
            context = await browser.new_context(
                user_agent=self._user_agent,
                extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
            )
            page = await context.new_page()

            try:
                await page.goto(_BOARD_URL, wait_until="domcontentloaded", timeout=30_000)
                await page.wait_for_selector("[class*='job'], .job-card, article", timeout=15_000)

                # Gather all job card links on the listing page
                job_links = await page.eval_on_selector_all(
                    "a[href*='/jobs/']",
                    "els => [...new Set(els.map(e => e.href))].filter(h => /\\/jobs\\/\\d/.test(h))",
                )

                for idx, url in enumerate(job_links[:20]):  # Limit to 20 per session
                    if idx > 0:
                        await self._random_delay()
                    try:
                        job = await self._scrape_detail(context, url)
                        if job:
                            listings.append(job)
                    except Exception as exc:
                        logger.warning("Failed to scrape Fuzu job at %s: %s", url, exc)
            except PlaywrightTimeout:
                logger.error("Fuzu: timed out loading %s", _BOARD_URL)
            except Exception as exc:
                logger.error("Fuzu scrape error: %s", exc, exc_info=True)
            finally:
                await context.close()
                await browser.close()

        return listings

    async def _scrape_detail(self, context, url: str) -> Optional[JobListingCreate]:
        """Navigate to a job detail page and extract required fields."""
        detail_page = await context.new_page()
        try:
            await detail_page.goto(url, wait_until="domcontentloaded", timeout=30_000)

            title = await self._extract_text(detail_page, "h1")
            if not title:
                return None

            company = await self._extract_text(
                detail_page,
                "[class*='company'], [class*='employer'], [data-testid='company']",
            )

            description = await self._extract_text(
                detail_page,
                "[class*='description'], [class*='job-details'], .job-description",
            )

            # Try to find application email in the page text
            page_text = await detail_page.inner_text("body")
            application_email = _extract_email(page_text)
            application_url = url  # Fuzu uses URL-based applications

            deadline = _extract_deadline(page_text)

            return JobListingCreate(
                title=title.strip(),
                company=(company or "Unknown").strip(),
                description=description,
                application_email=application_email,
                application_url=application_url,
                deadline=deadline,
                board_source=self.board_name,
            )
        finally:
            await detail_page.close()

    @staticmethod
    async def _extract_text(page, selector: str) -> Optional[str]:
        try:
            el = await page.query_selector(selector)
            if el:
                return await el.inner_text()
        except Exception:
            pass
        return None


def _extract_email(text: str) -> Optional[str]:
    """Return the first email address found in *text*, or None."""
    match = re.search(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", text)
    return match.group(0) if match else None


def _extract_deadline(text: str) -> Optional[str]:
    """Return a rough deadline string if one can be found in the page text."""
    match = re.search(
        r"(deadline|closing date|apply by)[:\s]+([A-Za-z0-9, /\-]+)",
        text,
        re.IGNORECASE,
    )
    return match.group(2).strip() if match else None
