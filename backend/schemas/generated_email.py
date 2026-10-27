"""
Pydantic schemas for generated email responses.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class GeneratedEmailResponse(BaseModel):
    """Full generated email returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    job_listing_id: int
    email_body: str
    created_at: datetime
    updated_at: datetime
