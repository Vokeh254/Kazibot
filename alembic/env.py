"""
Alembic environment configuration for KaziBot.

Configured for SQLAlchemy 2.0 async engines (aiosqlite / asyncpg).
The database URL is read from application settings rather than alembic.ini
so that it stays consistent with the rest of the backend configuration.
"""

import asyncio
from logging.config import fileConfig

from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlalchemy import pool

from alembic import context

# ── Alembic config object ─────────────────────────────────────────────────────
config = context.config

# Set up Python logging as described in alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ── Import models so their metadata is populated ──────────────────────────────
# Importing backend.models triggers the import of every model module, which
# registers each table on Base.metadata — required for autogenerate.
from backend.database import Base  # noqa: E402
import backend.models  # noqa: E402, F401  # registers all ORM models

target_metadata = Base.metadata

# ── Override sqlalchemy.url from application settings ─────────────────────────
from backend.config import settings  # noqa: E402

config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)


# ── Offline migrations ────────────────────────────────────────────────────────

def run_migrations_offline() -> None:
    """Emit migration SQL to stdout without connecting to the database.

    Useful for generating SQL scripts to review or apply manually.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,  # Required for SQLite ALTER TABLE support
    )

    with context.begin_transaction():
        context.run_migrations()


# ── Online migrations (async) ─────────────────────────────────────────────────

def do_run_migrations(connection) -> None:
    """Execute migrations against an active connection."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=True,  # Required for SQLite ALTER TABLE support
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Create an async engine and run migrations inside a sync adapter."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Entry point for online migrations — delegates to the async runner."""
    asyncio.run(run_async_migrations())


# ── Dispatch ──────────────────────────────────────────────────────────────────

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
