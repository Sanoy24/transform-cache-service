"""Payload generation with cached transformer results."""

import asyncio
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

# SQLite-specific: ON CONFLICT is dialect syntax, and SQLite is our chosen database.
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from transform_cache.models import Payload, TransformCacheEntry
from transform_cache.payload import build_output, payload_key
from transform_cache.transformer import Transformer


@dataclass(frozen=True)
class PayloadResult:
    id: uuid.UUID
    created: bool


class PayloadService:
    """Creates and reads payloads, reusing cached transformer results.

    Strings found in the cache at lookup time are never re-transformed. Two
    concurrent requests that miss the same string may still both transform it.

    Meant to be shared across requests: the concurrency limit only works if all
    requests go through the same semaphore.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        transformer: Transformer,
        max_concurrency: int,
    ) -> None:
        self._session_factory = session_factory
        self._transformer = transformer
        self._semaphore = asyncio.Semaphore(max_concurrency)

    async def create_payload(
        self, list_1: Sequence[str], list_2: Sequence[str]
    ) -> PayloadResult:
        key = payload_key(list_1, list_2)
        unique_inputs = set(list_1) | set(list_2)

        # Read and write in separate short sessions so no connection or SQLite
        # write lock is held while waiting on the slow transformer.
        async with self._session_factory() as session:
            existing_id = await self._find_payload_id(session, key)
            if existing_id is not None:
                return PayloadResult(id=existing_id, created=False)
            results = await self._load_cached(session, unique_inputs)

        misses = list(unique_inputs - results.keys())
        new_results = dict(zip(misses, await self._transform_all(misses), strict=True))
        results |= new_results

        output = build_output(
            [results[value] for value in list_1], [results[value] for value in list_2]
        )
        new_id = uuid.uuid4()

        async with self._session_factory() as session, session.begin():
            if new_results:
                # Another request may have cached the same strings meanwhile;
                # the transformer is deterministic, so skipping them is safe.
                await session.exec(
                    insert(TransformCacheEntry)
                    .values([{"input": k, "output": v} for k, v in new_results.items()])
                    .on_conflict_do_nothing()
                )
            await session.exec(
                insert(Payload)
                .values(id=new_id, payload_key=key, output=output)
                .on_conflict_do_nothing(index_elements=["payload_key"])
            )
            # Whether our insert won or a concurrent one did, the stored row
            # is the answer.
            stored_id = await self._find_payload_id(session, key)

        if stored_id is None:
            raise RuntimeError(f"Payload {key} missing right after insert")
        return PayloadResult(id=stored_id, created=stored_id == new_id)

    async def get_payload_output(self, payload_id: uuid.UUID) -> str | None:
        async with self._session_factory() as session:
            payload = await session.get(Payload, payload_id)
        return payload.output if payload else None

    @staticmethod
    async def _find_payload_id(session: AsyncSession, key: str) -> uuid.UUID | None:
        result = await session.exec(
            select(Payload.id).where(Payload.payload_key == key)
        )
        return result.first()

    @staticmethod
    async def _load_cached(
        session: AsyncSession, inputs: Iterable[str]
    ) -> dict[str, str]:
        result = await session.exec(
            select(TransformCacheEntry).where(
                col(TransformCacheEntry.input).in_(inputs)
            )
        )
        return {entry.input: entry.output for entry in result}

    async def _transform_all(self, values: Sequence[str]) -> list[str]:
        return await asyncio.gather(*(self._transform(value) for value in values))

    async def _transform(self, value: str) -> str:
        async with self._semaphore:
            return await self._transformer.transform(value)
