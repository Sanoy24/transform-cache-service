"""Database engine and session setup."""

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

# Importing the models registers their tables on SQLModel.metadata; without it
# create_all() would depend on someone else having imported them first.
from transform_cache import models  # noqa: F401


def create_engine(database_url: str) -> AsyncEngine:
    return create_async_engine(database_url)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    # Keep loaded objects usable after commit; otherwise reading an attribute
    # would trigger a lazy refresh, which async sessions cannot do implicitly.
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db(engine: AsyncEngine) -> None:
    """Create missing tables. Stands in for migrations (see README)."""
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
