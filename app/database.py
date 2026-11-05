"""Async database engine, session factory and declarative base."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import declarative_base

from app.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,
)

async_session = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

Base = declarative_base()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding an async database session.

    The session is opened inside a context manager and committed/closed by
    the caller via ``await session.commit()`` / ``await session.close()``.
    """
    async with async_session() as session:
        yield session


async def init_db() -> None:
    """Create all database tables on application startup.

    Runs ``Base.metadata.create_all`` — a no-op for tables that already exist.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


# Import model modules so their tables are registered on ``Base.metadata``
# before ``init_db()`` executes ``create_all``.
from app import models  # noqa: E402, F401
