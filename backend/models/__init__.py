# SQLAlchemy ORM models
#
# All models are imported here so that Alembic's autogenerate can discover
# every table when it inspects `Base.metadata`.  Any new model module MUST
# be added to this file.

from backend.models.generated_email import GeneratedEmail
from backend.models.job_listing import JobListing, JobStatus
from backend.models.user_profile import UserProfile

__all__ = [
    "GeneratedEmail",
    "JobListing",
    "JobStatus",
    "UserProfile",
]
