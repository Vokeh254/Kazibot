"""
UserProfile ORM model.

Maps to the `user_profiles` database table.
This table holds exactly one row (singleton pattern): the local user's
resume, tech stack, GitHub/portfolio URLs, and encrypted LLM credentials.
"""

from sqlalchemy import JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class UserProfile(Base):
    """Singleton row holding the user's profile and encrypted LLM credentials.

    Only one row with id=1 should ever exist.  Application code is responsible
    for enforcing this invariant (upsert on id=1).
    """

    __tablename__ = "user_profiles"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Resume stored as Markdown text so the LLM prompt can embed it verbatim.
    resume_markdown: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Tech stack is a JSON array of skill strings, e.g. ["Python", "React"].
    tech_stack: Mapped[list | None] = mapped_column(JSON, nullable=True)

    github_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    portfolio_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)

    # LLM provider identifier: "openai" or "anthropic"
    llm_provider: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # The LLM API key is stored Fernet-encrypted; never in plain text.
    llm_api_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<UserProfile id={self.id!r} llm_provider={self.llm_provider!r}>"
