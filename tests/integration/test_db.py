import uuid

import pytest
from sqlalchemy import Connection, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from transform_cache.models import Payload, TransformCacheEntry


async def test_init_db_creates_tables(engine: AsyncEngine) -> None:
    def table_names(connection: Connection) -> set[str]:
        return set(inspect(connection).get_table_names())

    async with engine.connect() as connection:
        tables = await connection.run_sync(table_names)

    assert {"transform_cache", "payload"} <= tables


async def test_cache_entry_round_trip(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        session.add(TransformCacheEntry(input="abc", output="ABC"))
        await session.commit()

    async with session_factory() as session:
        entry = await session.get(TransformCacheEntry, "abc")

    assert entry is not None
    assert entry.output == "ABC"


async def test_cache_input_is_unique(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        session.add(TransformCacheEntry(input="abc", output="ABC"))
        await session.commit()

    async with session_factory() as session:
        session.add(TransformCacheEntry(input="abc", output="ABC"))
        with pytest.raises(IntegrityError):
            await session.commit()


async def test_payload_gets_uuid_and_round_trips(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        payload = Payload(payload_key="key", output="A, B")
        session.add(payload)
        await session.commit()

    async with session_factory() as session:
        stored = (
            await session.exec(select(Payload).where(Payload.payload_key == "key"))
        ).one()

    assert isinstance(stored.id, uuid.UUID)
    assert stored.id == payload.id
    assert stored.output == "A, B"


async def test_payload_key_is_unique(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        session.add(Payload(payload_key="key", output="A"))
        await session.commit()

    async with session_factory() as session:
        session.add(Payload(payload_key="key", output="A"))
        with pytest.raises(IntegrityError):
            await session.commit()
