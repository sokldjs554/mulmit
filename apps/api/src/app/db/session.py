"""Async engine / session factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.settings import Settings, get_settings

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def create_engine(settings: Settings) -> AsyncEngine:
    return create_async_engine(
        settings.database_url,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_pool_size,
        pool_pre_ping=True,
        pool_recycle=1800,
        echo=settings.db_echo,
        # Cloud Run instances are short-lived; keep statement timeouts tight so one runaway
        # query cannot pin a connection from the Cloud SQL pool.
        connect_args={"server_settings": {"statement_timeout": "30000", "jit": "off"}},
    )


def get_engine() -> AsyncEngine:
    global _engine, _sessionmaker
    if _engine is None:
        _engine = create_engine(get_settings())
        _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    get_engine()
    assert _sessionmaker is not None
    return _sessionmaker


def configure_engine(engine: AsyncEngine) -> None:
    """Tests inject their own engine (pointed at a throwaway database)."""
    global _engine, _sessionmaker
    _engine = engine
    _sessionmaker = async_sessionmaker(engine, expire_on_commit=False)


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """Unit of work for background jobs: commit on success, roll back on error."""
    async with get_sessionmaker()() as session:
        try:
            yield session
            await session.commit()
        except BaseException:
            await session.rollback()
            raise


async def dispose_engine() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None
