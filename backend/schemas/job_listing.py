"""
Pydantic schemas for job listing requests and responses.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict

from backend.models.job_listing import JobStatus


class JobListingCreate(BaseModel):
    """Used internally by scrapers to create new job listings."""

    title: str
    company: str
    description: Optional[str] = None
    application_email: Optional[str] = None
    application_url: Optional[str] = None
    deadline: Optional[date] = None
    board_source: str


class JobListingResponse(BaseModel):
    """Full job listing returned by the API.

    ``generated_email`` is the plain email body string (if any has been
    generated for this listing), not a nested object — keeping the shape
    flat and simple for frontend consumption.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    company: str
    description: Optional[str]
    application_email: Optional[str]
    application_url: Optional[str]
    deadline: Optional[date]
    status: JobStatus
    scraped_at: datetime
    board_source: str
    # The email body text, populated only when a GeneratedEmail row exists.
    generated_email: Optional[str] = None


class JobStatusUpdate(BaseModel):
    """Payload for PATCH /api/jobs/{id}/status.

    Only the two user-actionable terminal transitions are accepted here;
    ``draft_created`` is set automatically by Draft_Service and
    ``pending_ai`` is the implicit initial state.
    """

    status: Literal["applied", "skipped"]
