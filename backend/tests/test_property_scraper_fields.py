"""
Property-based test for scraper field completeness.

# Feature: kazibot, Property 2: Scraper field completeness

For any valid job listing, the parsed output from a BaseScraper implementation
always includes non-null values for the required fields (title, company,
description), and optional fields (application_email, deadline) are extracted
when present in the source text.

**Validates: Requirements 1.1**
"""

import re

from hypothesis import given, settings
from hypothesis import strategies as st

from backend.schemas.job_listing import JobListingCreate
from backend.services.scraper.fuzu import _extract_email, _extract_deadline

# ── Hypothesis strategies ─────────────────────────────────────────────────────

# Printable text that avoids empty strings for required fields
_printable = st.characters(whitelist_categories=("L", "N", "P", "Z"))
_non_empty_text = st.text(alphabet=_printable, min_size=1, max_size=200).filter(
    lambda s: s.strip() != ""
)

# Valid email local parts and domains (ASCII-only, matching _extract_email regex)
_ASCII_ALPHA = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
_ASCII_DIGIT = "0123456789"
_LOCAL_CHARS = _ASCII_ALPHA + _ASCII_DIGIT + "._%+-"
_DOMAIN_CHARS = _ASCII_ALPHA + _ASCII_DIGIT + "-"

_local_part = st.text(
    alphabet=_LOCAL_CHARS,
    min_size=1,
    max_size=20,
).filter(lambda s: s and s[0] not in "._%+-" and s[-1] not in "._%+-")

_domain_label = st.text(
    alphabet=_DOMAIN_CHARS,
    min_size=1,
    max_size=15,
).filter(lambda s: s and s[0] != "-" and s[-1] != "-")

_tld = st.sampled_from(["com", "org", "net", "io", "co", "ke"])


@st.composite
def valid_email_st(draw) -> str:
    local = draw(_local_part)
    domain = draw(_domain_label)
    tld = draw(_tld)
    return f"{local}@{domain}.{tld}"


# Optional email: either a valid email string or None
_optional_email = st.one_of(st.none(), valid_email_st())

# Optional deadline: either a plausible deadline string or None
_deadline_words = st.sampled_from([
    "31 December 2025",
    "15 Jan 2026",
    "2025-12-31",
    "December 31, 2025",
    "01/31/2026",
])
_optional_deadline = st.one_of(st.none(), _deadline_words)

_board_sources = st.sampled_from(["fuzu", "brighter_monday", "my_job_mag"])


# ── Property 2a: Required fields are always non-null and non-empty ────────────

@given(
    title=_non_empty_text,
    company=_non_empty_text,
    description=_non_empty_text,
    application_email=_optional_email,
    deadline_str=_optional_deadline,
    board_source=_board_sources,
)
@settings(max_examples=100)
def test_required_fields_always_present(
    title: str,
    company: str,
    description: str,
    application_email,
    deadline_str,
    board_source: str,
):
    """
    # Feature: kazibot, Property 2: Scraper field completeness
    **Validates: Requirements 1.1**

    For any arbitrary combination of job listing data, the JobListingCreate
    object always has non-null, non-empty values for the required fields
    (title, company, description).

    When application_email is provided, it must match the email regex pattern.
    """
    listing = JobListingCreate(
        title=title,
        company=company,
        description=description,
        application_email=application_email,
        application_url=None,
        deadline=None,
        board_source=board_source,
    )

    # Required fields must always be present and non-empty
    assert listing.title is not None, "title must not be None"
    assert listing.title.strip() != "", "title must not be empty"

    assert listing.company is not None, "company must not be None"
    assert listing.company.strip() != "", "company must not be empty"

    assert listing.description is not None, "description must not be None"
    assert listing.description.strip() != "", "description must not be empty"

    # When application_email is provided, it must match the email pattern
    if application_email is not None:
        email_pattern = re.compile(
            r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"
        )
        assert email_pattern.fullmatch(listing.application_email) is not None, (
            f"application_email '{listing.application_email}' does not match email pattern"
        )


# ── Property 2b: _extract_email returns email when present, None otherwise ────

@st.composite
def text_with_optional_email_st(draw):
    """Generate text that either contains a valid email or does not."""
    has_email = draw(st.booleans())
    padding_before = draw(st.text(alphabet=_printable, min_size=0, max_size=50))
    padding_after = draw(st.text(alphabet=_printable, min_size=0, max_size=50))

    if has_email:
        email = draw(valid_email_st())
        text = f"{padding_before} {email} {padding_after}"
        return text, email
    else:
        # Ensure no accidental email pattern appears in the padding
        safe_padding = re.sub(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", "", padding_before + padding_after)
        return safe_padding, None


@given(text_and_email=text_with_optional_email_st())
@settings(max_examples=100)
def test_extract_email_returns_email_when_present(text_and_email):
    """
    # Feature: kazibot, Property 2: Scraper field completeness
    **Validates: Requirements 1.1**

    _extract_email returns the email address when one is present in the text,
    and returns None when no email address is present.
    """
    text, expected_email = text_and_email

    result = _extract_email(text)

    if expected_email is not None:
        assert result is not None, (
            f"_extract_email should have found '{expected_email}' in text: {text!r}"
        )
        # The extracted email must match the expected email regex
        email_pattern = re.compile(
            r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"
        )
        assert email_pattern.fullmatch(result) is not None, (
            f"Extracted email '{result}' does not match email pattern"
        )
    else:
        assert result is None, (
            f"_extract_email should return None for text with no email, got: {result!r}"
        )


# ── Property 2c: _extract_deadline returns string when pattern present ─────────

_deadline_labels = st.sampled_from(["Deadline", "deadline", "Closing Date", "closing date", "Apply By", "apply by"])
_deadline_dates = st.sampled_from([
    "31 December 2025",
    "January 15 2026",
    "2025-12-31",
    "December 31 2025",
    "15/01/2026",
    "March 1, 2026",
])


@st.composite
def text_with_optional_deadline_st(draw):
    """Generate text that either contains a deadline pattern or does not."""
    has_deadline = draw(st.booleans())
    padding = draw(st.text(alphabet=_printable, min_size=0, max_size=50))

    if has_deadline:
        label = draw(_deadline_labels)
        date_str = draw(_deadline_dates)
        text = f"{padding} {label}: {date_str} {padding}"
        return text, date_str
    else:
        # Use padding that won't accidentally trigger the deadline regex
        safe_padding = re.sub(
            r"(deadline|closing date|apply by)[:\s]+",
            "",
            padding,
            flags=re.IGNORECASE,
        )
        return safe_padding, None


@given(text_and_deadline=text_with_optional_deadline_st())
@settings(max_examples=100)
def test_extract_deadline_returns_string_when_present(text_and_deadline):
    """
    # Feature: kazibot, Property 2: Scraper field completeness
    **Validates: Requirements 1.1**

    _extract_deadline returns a non-empty string when a deadline pattern is
    present in the text, and returns None when no deadline pattern is present.
    """
    text, expected_deadline = text_and_deadline

    result = _extract_deadline(text)

    if expected_deadline is not None:
        assert result is not None, (
            f"_extract_deadline should have found a deadline in text: {text!r}"
        )
        assert isinstance(result, str), (
            f"_extract_deadline should return a string, got: {type(result)}"
        )
        assert len(result.strip()) > 0, (
            f"_extract_deadline should return a non-empty string"
        )
    else:
        assert result is None, (
            f"_extract_deadline should return None for text with no deadline pattern, "
            f"got: {result!r} for text: {text!r}"
        )
