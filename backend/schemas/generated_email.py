"""
Pydantic schemas for generated email responses.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class GeneratedEmailResponse(BaseModel):
    """Full generated email returned by the API."""

    id: int
    job_listing_id: int
    email_body: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
