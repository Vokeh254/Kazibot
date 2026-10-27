"""
Jobs router — listing, retrieving, and updating job statuses.

Endpoints:
  GET  /api/jobs           — List all job listings (optional ?status= filter)
  GET  /api/jobs/{id}      — Get a single listing with its generated email
  PATCH /api/jobs/{id}/status — Update status to 'applied' or 'skipped'

Requirements: 4.1, 4.5, 4.6
"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.database import get_async_session
from backend.models.job_listing import JobListing, JobStatus
from backend.schemas.job_listing import JobListingResponse, JobStatusUpdate

router = APIRouter(tags=["jobs"])


@router.get("/jobs", response_model=List[JobListingResponse])
async def list_jobs(
    status: Optional[str] = Query(None, description="Filter by job status"),
    session: AsyncSession = Depends(get_async_session),
) -> List[JobListingResponse]:
    """Return all job listings, optionally filtered by status."""
    query = select(JobListing).options(selectinload(JobListing.generated_email))

    if status:
        try:
            status_enum = JobStatus(status)
            query = query.where(JobListing.status == status_enum)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status value: {status!r}",
            )

    result = await session.execute(query.order_by(JobListing.scraped_at.desc()))
    jobs = result.scalars().all()
    return [JobListingResponse.model_validate(j) for j in jobs]


@router.get("/jobs/{job_id}", response_model=JobListingResponse)
async def get_job(
    job_id: int,
    session: AsyncSession = Depends(get_async_session),
) -> JobListingResponse:
    """Return a single job listing including its generated email if available."""
    result = await session.execute(
        select(JobListing)
        .options(selectinload(JobListing.generated_email))
        .where(JobListing.id == job_id)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail=f"Job listing {job_id} not found")
    return JobListingResponse.model_validate(job)


@router.patch("/jobs/{job_id}/status", response_model=JobListingResponse)
async def update_job_status(
    job_id: int,
    payload: JobStatusUpdate,
    session: AsyncSession = Depends(get_async_session),
) -> JobListingResponse:
    """Update a job listing's status to 'applied' or 'skipped'."""
    result = await session.execute(
        select(JobListing)
        .options(selectinload(JobListing.generated_email))
        .where(JobListing.id == job_id)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail=f"Job listing {job_id} not found")

    job.status = JobStatus(payload.status)
    await session.commit()
    await session.refresh(job)
    return JobListingResponse.model_validate(job)
