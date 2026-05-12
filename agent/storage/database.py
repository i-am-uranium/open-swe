"""Database configuration and session helpers."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from .models import Base

DATABASE_URL_ENV = "OPEN_SWE_DATABASE_URL"


def get_database_url() -> str:
    return os.environ.get(DATABASE_URL_ENV, "").strip()


def create_async_engine_from_url(url: str) -> AsyncEngine:
    if not url:
        raise RuntimeError(f"{DATABASE_URL_ENV} must be set for durable job storage")
    return create_async_engine(url)


def sessionmaker_for(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def init_models(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


async def iter_session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine_from_url(get_database_url())
    sessionmaker = sessionmaker_for(engine)
    try:
        async with sessionmaker() as session:
            yield session
    finally:
        await engine.dispose()
