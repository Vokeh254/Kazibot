"""
JobListing ORM model and JobStatus enum.

Maps to the `job_listings` database table.
"""

from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import DateTime, Enum as SAEnum, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base


class JobStatus(str, Enum):
    """Lifecycle status of a job listing.

    Mirrors the front-end status labels and drives UI badge colouring.
    """

    pending_ai = "pending_ai"
    draft_created = "draft_created"
    applied = "applied"
    skipped = "skipped"


class JobListing(Base):
    """Represents a single job post scraped from a Kenyan job board.

    The unique constraint on (title, company, board_source) prevents duplicate
    records across scraping sessions (Requirement 7.4).
    """

    __tablename__ = "job_listings"

    __table_args__ = (
        UniqueConstraint("title", "company", "board_source", name="uq_job_title_company_board"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    company: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    application_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    application_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    deadline: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[JobStatus] = mapped_column(
        SAEnum(JobStatus, values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
        default=JobStatus.pending_ai,
        server_default=JobStatus.pending_ai.value,
    )
    board_source: Mapped[str] = mapped_column(String(100), nullable=False)
    scraped_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    generated_email: Mapped["GeneratedEmail | None"] = relationship(  # noqa: F821
        "GeneratedEmail",
        back_populates="job_listing",
        uselist=False,
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return (
            f"<JobListing id={self.id!r} title={self.title!r} "
            f"company={self.company!r} status={self.status!r}>"
        )


# Avoid circular import: import here after JobListing is defined
from backend.models.generated_email import GeneratedEmail  # noqa: E402, F401
