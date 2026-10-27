"""
Application configuration loaded from environment variables / .env file.
Uses pydantic-settings for validation and type coercion.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All sensitive configuration is read from environment variables or a .env file.

    Never hard-code values here — add them to .env (development) or inject
    them via the deployment environment (production).
    """

    # Database — sqlite+aiosqlite:///./kazibot.db  OR  postgresql+asyncpg://...
    DATABASE_URL: str

    # LLM provider selection: "openai" or "anthropic"
    LLM_PROVIDER: str = "openai"

    # Fernet symmetric key for encrypting OAuth2 tokens and LLM API keys at rest.
    # Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    FERNET_KEY: str

    # Google OAuth2 credentials (from Google Cloud Console)
    GOOGLE_CLIENT_ID: str
    GOOGLE_CLIENT_SECRET: str

    # Custom User-Agent string sent by the scraper to simulate a real browser
    CUSTOM_USER_AGENT: str = (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        # Extra fields in .env are silently ignored so downstream additions
        # do not break existing deployments.
        extra="ignore",
    )


# Module-level singleton — import `settings` everywhere instead of re-creating.
settings = Settings()
