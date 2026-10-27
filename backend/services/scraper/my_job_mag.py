"""
MyJobMagScraper — scrapes IT/internship listings from myjobmag.co.ke.

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

_BOARD_URL = "https://www.myjobmag.co.ke/jobs-by-field/it-telecom-internet"
_BOARD_NAME = "my_job_mag"


class MyJobMagScraper(BaseScraper):
    """Scraper for MyJobMag Kenya IT/Telecom listings."""

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
                await page.wait_for_selector(
                    "article, .job-list, [class*='job']", timeout=15_000
                )

                job_links = await page.eval_on_selector_all(
                    "a[href*='/job/'], a[href*='/jobs/']",
                    "els => [...new Set(els.map(e => e.href))]",
                )

                for idx, url in enumerate(job_links[:20]):
                    if idx > 0:
                        await self._random_delay()
                    try:
                        job = await self._scrape_detail(context, url)
                        if job:
                            listings.append(job)
                    except Exception as exc:
                        logger.warning(
                            "Failed to scrape MyJobMag job at %s: %s", url, exc
                        )
            except PlaywrightTimeout:
                logger.error("MyJobMag: timed out loading %s", _BOARD_URL)
            except Exception as exc:
                logger.error("MyJobMag scrape error: %s", exc, exc_info=True)
            finally:
                await context.close()
                await browser.close()

        return listings

    async def _scrape_detail(self, context, url: str) -> Optional[JobListingCreate]:
        detail_page = await context.new_page()
        try:
            await detail_page.goto(url, wait_until="domcontentloaded", timeout=30_000)

            title = await _extract_text(detail_page, "h1, .job-title, [itemprop='title']")
            if not title:
                return None

            company = await _extract_text(
                detail_page, ".company-name, [itemprop='hiringOrganization'], h2"
            )

            description = await _extract_text(
                detail_page,
                ".job-description, [itemprop='description'], #job-description",
            )

            page_text = await detail_page.inner_text("body")
            application_email = _extract_email(page_text)
            application_url = url

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


async def _extract_text(page, selector: str) -> Optional[str]:
    try:
        el = await page.query_selector(selector)
        if el:
            return await el.inner_text()
    except Exception:
        pass
    return None


def _extract_email(text: str) -> Optional[str]:
    match = re.search(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", text)
    return match.group(0) if match else None


def _extract_deadline(text: str) -> Optional[str]:
    match = re.search(
        r"(deadline|closing date|apply by)[:\s]+([A-Za-z0-9, /\-]+)",
        text,
        re.IGNORECASE,
    )
    return match.group(2).strip() if match else None
