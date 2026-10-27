"""
KaziBot FastAPI application factory.

All routes are registered in their respective router modules and included here.
Startup / shutdown logic lives in the lifespan context manager.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.database import Base, engine
from backend.routers import ai, drafts, jobs, profile, scrape


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application-level resources.

    Startup:
      - Create all database tables (idempotent; Alembic handles schema changes)

    Shutdown:
      - Dispose the async database engine connection pool
    """
    # ── Startup ───────────────────────────────────────────────────────────────
    async with engine.begin() as conn:
        # create_all is safe to call every startup — it is idempotent.
        # In production, Alembic migrations should be run separately.
        await conn.run_sync(Base.metadata.create_all)

    yield

    # ── Shutdown ──────────────────────────────────────────────────────────────
    await engine.dispose()


def create_app() -> FastAPI:
    """Construct and return the FastAPI application instance."""
    app = FastAPI(
        title="KaziBot API",
        description=(
            "Semi-automated, Human-in-the-Loop job application assistant "
            "for the Kenyan job market."
        ),
        version="0.1.0",
        lifespan=lifespan,
    )

    # ── CORS ──────────────────────────────────────────────────────────────────
    # Allow the Vite dev server (port 5173) and any localhost origin
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://localhost:3000",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Routers ───────────────────────────────────────────────────────────────
    app.include_router(profile.router, prefix="/api")
    app.include_router(scrape.router, prefix="/api")
    app.include_router(ai.router, prefix="/api")
    app.include_router(drafts.router, prefix="/api")
    app.include_router(jobs.router, prefix="/api")

    return app


# Expose `app` at module level so `uvicorn backend.main:app` works out of the box.
app = create_app()
