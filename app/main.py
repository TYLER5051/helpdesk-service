"""FastAPI application entrypoint for the helpdesk service."""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import init_db
from app.routers.health import router as health_router
from app.routers.webhooks import router as webhooks_router

# Surface application-level logs (duplicate detection, background tasks) on
# stderr alongside uvicorn's own output. The root logger defaults to WARNING
# inside uvicorn, which would silently drop our INFO messages otherwise.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
    """Create database tables before the application starts serving requests."""
    await init_db()
    yield


app = FastAPI(
    title="Helpdesk Service",
    description="AI-powered helpdesk assistant backed by a knowledge base of SaaS product articles.",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(health_router)
app.include_router(webhooks_router)



