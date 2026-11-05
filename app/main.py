"""FastAPI application entrypoint for the helpdesk service."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import init_db


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Create database tables before the application starts serving requests."""
    await init_db()
    yield


app = FastAPI(
    title="Helpdesk Service",
    description="AI-powered helpdesk assistant backed by a knowledge base of SaaS product articles.",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health() -> dict[str, str]:
    """Return service liveness status (must respond with 200 OK)."""
    return {"status": "ok"}

