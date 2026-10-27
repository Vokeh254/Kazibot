"""
Pydantic schemas for job listing requests and responses.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel

from backend.models.job_listing import JobStatus


class JobListingCreate(BaseModel):
    """Used internally by scrapers to create new job listings."""

    title: str
    company: str
    description: Optional[str] = None
    application_email: Optional[str] = None
    application_url: Optional[str] = None
    deadline: Optional[datetime] = None
    board_source: str


class GeneratedEmailNested(BaseModel):
    """Minimal nested representation of a generated email inside a job listing."""

    id: int
    email_body: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class JobListingResponse(BaseModel):
    """Full job listing returned by the API."""

    id: int
    title: str
    company: str
    description: Optional[str]
    application_email: Optional[str]
    application_url: Optional[str]
    deadline: Optional[datetime]
    status: JobStatus
    board_source: str
    scraped_at: datetime
    generated_email: Optional[GeneratedEmailNested] = None

    model_config = {"from_attributes": True}


class JobStatusUpdate(BaseModel):
    """Payload for PATCH /api/jobs/{id}/status — only allows user-actionable transitions."""

    status: Literal["applied", "skipped"]
