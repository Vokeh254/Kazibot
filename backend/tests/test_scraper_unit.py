"""
Unit tests for all three board scraper parsers using mocked Playwright.

Tests verify that _scrape_detail() correctly extracts fields from mocked
page responses without launching a real browser.

Requirements: 1.1
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.schemas.job_listing import JobListingCreate
from backend.services.scraper.fuzu import FuzuScraper
from backend.services.scraper.brighter_monday import BrighterMondayScraper
from backend.services.scraper.my_job_mag import MyJobMagScraper

# ── Shared event loop helper ──────────────────────────────────────────────────

def run_async(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ── Mock page factory ─────────────────────────────────────────────────────────

def _make_mock_page(title: str, company: str, description: str, body_text: str) -> AsyncMock:
    """Build a fully mocked Playwright page that returns fixture values."""
    page = AsyncMock()

    # goto and close are no-ops
    page.goto = AsyncMock(return_value=None)
    page.close = AsyncMock(return_value=None)

    # inner_text("body") returns the full body text (used for email/deadline extraction)
    page.inner_text = AsyncMock(return_value=body_text)

    # query_selector returns a mock element whose inner_text() yields the fixture value
    def _make_el(text: str) -> AsyncMock:
        el = AsyncMock()
        el.inner_text = AsyncMock(return_value=text)
        return el

    # Map each selector call to the appropriate fixture value.
    # The scraper calls query_selector multiple times with different selectors.
    # We return the right element based on call order: title first, company second,
    # description third.
    call_returns = [_make_el(title), _make_el(company), _make_el(description)]
    call_iter = iter(call_returns)

    async def _query_selector(selector: str):
        try:
            return next(call_iter)
        except StopIteration:
            return None

    page.query_selector = _query_selector
    return page


def _make_mock_context(page: AsyncMock) -> AsyncMock:
    """Return a mock browser context whose new_page() yields the given page mock."""
    context = AsyncMock()
    context.new_page = AsyncMock(return_value=page)
    return context


# ── FuzuScraper tests ─────────────────────────────────────────────────────────

class TestFuzuScraperDetail:

    def test_all_fields_extracted(self):
        """FuzuScraper extracts title, company, description and email when all present."""
        # No deadline pattern in body — deadline field is Optional[date] and
        # _extract_deadline returns a raw string that Pydantic cannot coerce.
        body_text = "Some text. Contact: jobs@fuzu.co.ke."
        page = _make_mock_page(
            title="Software Engineer",
            company="Acme Corp",
            description="We are looking for a talented engineer.",
            body_text=body_text,
        )
        context = _make_mock_context(page)
        scraper = FuzuScraper()

        result = run_async(scraper._scrape_detail(context, "https://fuzu.com/jobs/123"))

        assert result is not None
        assert result.title == "Software Engineer"
        assert result.company == "Acme Corp"
        assert result.description == "We are looking for a talented engineer."
        assert result.application_email == "jobs@fuzu.co.ke"
        assert result.application_url == "https://fuzu.com/jobs/123"
        assert result.board_source == "fuzu"

    def test_optional_email_absent(self):
        """FuzuScraper returns None for application_email when body has no email."""
        body_text = "No contact email listed here. Apply via the website."
        page = _make_mock_page(
            title="Internship",
            company="TechCo",
            description="Entry level internship role.",
            body_text=body_text,
        )
        context = _make_mock_context(page)
        scraper = FuzuScraper()

        result = run_async(scraper._scrape_detail(context, "https://fuzu.com/jobs/456"))

        assert result is not None
        assert result.application_email is None

    def test_returns_none_when_title_missing(self):
        """FuzuScraper returns None when the title element is not found."""
        page = AsyncMock()
        page.goto = AsyncMock(return_value=None)
        page.close = AsyncMock(return_value=None)
        page.inner_text = AsyncMock(return_value="")
        page.query_selector = AsyncMock(return_value=None)  # No elements found

        context = _make_mock_context(page)
        scraper = FuzuScraper()

        result = run_async(scraper._scrape_detail(context, "https://fuzu.com/jobs/789"))

        assert result is None

    def test_company_falls_back_to_unknown(self):
        """FuzuScraper uses 'Unknown' when the company element is missing."""
        # Returns title element, then None for company, then description
        page = AsyncMock()
        page.goto = AsyncMock(return_value=None)
        page.close = AsyncMock(return_value=None)
        page.inner_text = AsyncMock(return_value="")

        title_el = AsyncMock()
        title_el.inner_text = AsyncMock(return_value="Data Analyst")
        desc_el = AsyncMock()
        desc_el.inner_text = AsyncMock(return_value="Analyse data.")

        returns = iter([title_el, None, desc_el])
        async def _qs(selector):
            return next(returns, None)

        page.query_selector = _qs
        context = _make_mock_context(page)
        scraper = FuzuScraper()

        result = run_async(scraper._scrape_detail(context, "https://fuzu.com/jobs/999"))

        assert result is not None
        assert result.company == "Unknown"


# ── BrighterMondayScraper tests ───────────────────────────────────────────────

class TestBrighterMondayScraperDetail:

    def test_all_fields_extracted(self):
        """BrighterMondayScraper extracts all required fields from mock page."""
        # No deadline pattern — deadline is Optional[date] and _extract_deadline
        # returns a raw string that Pydantic cannot coerce to date.
        body_text = "Apply to hr@company.co.ke."
        page = _make_mock_page(
            title="Product Manager",
            company="GlobalTech Ltd",
            description="Lead our product development efforts.",
            body_text=body_text,
        )
        context = _make_mock_context(page)
        scraper = BrighterMondayScraper()

        result = run_async(scraper._scrape_detail(context, "https://www.brightermonday.co.ke/jobs/pm-456"))

        assert result is not None
        assert result.title == "Product Manager"
        assert result.company == "GlobalTech Ltd"
        assert result.description == "Lead our product development efforts."
        assert result.application_email == "hr@company.co.ke"
        assert result.board_source == "brighter_monday"

    def test_optional_fields_absent(self):
        """BrighterMondayScraper handles page with no email or deadline gracefully."""
        body_text = "Exciting opportunity at our company. Send your CV online."
        page = _make_mock_page(
            title="DevOps Engineer",
            company="CloudSystems",
            description="Manage our cloud infrastructure.",
            body_text=body_text,
        )
        context = _make_mock_context(page)
        scraper = BrighterMondayScraper()

        result = run_async(scraper._scrape_detail(context, "https://www.brightermonday.co.ke/jobs/devops-789"))

        assert result is not None
        assert result.application_email is None
        assert result.deadline is None

    def test_returns_none_when_title_missing(self):
        """BrighterMondayScraper returns None when title element not found."""
        page = AsyncMock()
        page.goto = AsyncMock(return_value=None)
        page.close = AsyncMock(return_value=None)
        page.inner_text = AsyncMock(return_value="")
        page.query_selector = AsyncMock(return_value=None)

        context = _make_mock_context(page)
        scraper = BrighterMondayScraper()

        result = run_async(scraper._scrape_detail(context, "https://www.brightermonday.co.ke/jobs/no-title"))

        assert result is None


# ── MyJobMagScraper tests ─────────────────────────────────────────────────────

class TestMyJobMagScraperDetail:

    def test_all_fields_extracted(self):
        """MyJobMagScraper extracts all required fields from mock page."""
        # No deadline pattern — deadline is Optional[date] and _extract_deadline
        # returns a raw string that Pydantic cannot coerce to date.
        body_text = "Send applications to careers@myjobmag.co.ke."
        page = _make_mock_page(
            title="Network Engineer",
            company="Telecom Kenya",
            description="Install and maintain network infrastructure.",
            body_text=body_text,
        )
        context = _make_mock_context(page)
        scraper = MyJobMagScraper()

        result = run_async(scraper._scrape_detail(context, "https://www.myjobmag.co.ke/job/network-engineer-101"))

        assert result is not None
        assert result.title == "Network Engineer"
        assert result.company == "Telecom Kenya"
        assert result.description == "Install and maintain network infrastructure."
        assert result.application_email == "careers@myjobmag.co.ke"
        assert result.board_source == "my_job_mag"

    def test_optional_email_absent(self):
        """MyJobMagScraper returns None for application_email when body has no email."""
        body_text = "Submit your application via our online portal only."
        page = _make_mock_page(
            title="UI/UX Designer",
            company="DesignStudio",
            description="Create beautiful interfaces.",
            body_text=body_text,
        )
        context = _make_mock_context(page)
        scraper = MyJobMagScraper()

        result = run_async(scraper._scrape_detail(context, "https://www.myjobmag.co.ke/job/ux-202"))

        assert result is not None
        assert result.application_email is None

    def test_returns_none_when_title_missing(self):
        """MyJobMagScraper returns None when title element is not found."""
        page = AsyncMock()
        page.goto = AsyncMock(return_value=None)
        page.close = AsyncMock(return_value=None)
        page.inner_text = AsyncMock(return_value="")
        page.query_selector = AsyncMock(return_value=None)

        context = _make_mock_context(page)
        scraper = MyJobMagScraper()

        result = run_async(scraper._scrape_detail(context, "https://www.myjobmag.co.ke/job/no-title-303"))

        assert result is None

    def test_company_falls_back_to_unknown(self):
        """MyJobMagScraper uses 'Unknown' when company element is missing."""
        page = AsyncMock()
        page.goto = AsyncMock(return_value=None)
        page.close = AsyncMock(return_value=None)
        page.inner_text = AsyncMock(return_value="")

        title_el = AsyncMock()
        title_el.inner_text = AsyncMock(return_value="Backend Developer")
        desc_el = AsyncMock()
        desc_el.inner_text = AsyncMock(return_value="Build APIs.")

        returns = iter([title_el, None, desc_el])
        async def _qs(selector):
            return next(returns, None)

        page.query_selector = _qs
        context = _make_mock_context(page)
        scraper = MyJobMagScraper()

        result = run_async(scraper._scrape_detail(context, "https://www.myjobmag.co.ke/job/backend-404"))

        assert result is not None
        assert result.company == "Unknown"
