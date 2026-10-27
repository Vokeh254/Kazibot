"""
GeneratedEmail ORM model.

Maps to the `generated_emails` database table.
Each row is associated with exactly one JobListing (one-to-one relationship).
"""

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base


class GeneratedEmail(Base):
    """Stores the LLM-generated cover letter email for a given job listing.

    The unique constraint on `job_listing_id` enforces the one-to-one
    relationship with JobListing at the database level.
    """

    __tablename__ = "generated_emails"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    job_listing_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("job_listings.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    email_body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    job_listing: Mapped["JobListing"] = relationship(  # noqa: F821
        "JobListing",
        back_populates="generated_email",
    )

    def __repr__(self) -> str:
        return (
            f"<GeneratedEmail id={self.id!r} "
            f"job_listing_id={self.job_listing_id!r}>"
        )


# Local import to satisfy the forward reference in the relationship above;
# only needed here to keep the circular-import chain consistent.
from backend.models.job_listing import JobListing  # noqa: E402, F401
