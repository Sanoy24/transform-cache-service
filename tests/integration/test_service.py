import asyncio
import uuid

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from tests.fakes import CountingTransformer
from transform_cache.models import TransformCacheEntry
from transform_cache.service import PayloadService


@pytest.fixture
def transformer() -> CountingTransformer:
    return CountingTransformer()


@pytest.fixture
def service(
    session_factory: async_sessionmaker[AsyncSession],
    transformer: CountingTransformer,
) -> PayloadService:
    return PayloadService(session_factory, transformer, max_concurrency=10)


async def test_spec_example(
    service: PayloadService, transformer: CountingTransformer
) -> None:
    result = await service.create_payload(
        ["first string", "second string", "third string"],
        ["other string", "another string", "last string"],
    )

    assert result.created
    assert await service.get_payload_output(result.id) == (
        "FIRST STRING, OTHER STRING, SECOND STRING, "
        "ANOTHER STRING, THIRD STRING, LAST STRING"
    )
    assert len(transformer.calls) == 6


async def test_duplicates_in_one_request_are_transformed_once(
    service: PayloadService, transformer: CountingTransformer
) -> None:
    result = await service.create_payload(["a", "a", "b"], ["b", "a", "c"])

    assert sorted(transformer.calls) == ["a", "b", "c"]
    # Every occurrence is still in the output.
    assert await service.get_payload_output(result.id) == "A, B, A, A, B, C"


async def test_cached_strings_are_not_transformed_again(
    service: PayloadService, transformer: CountingTransformer
) -> None:
    await service.create_payload(["a", "b"], ["c", "d"])
    transformer.calls.clear()

    result = await service.create_payload(["a", "x"], ["c", "y"])

    assert sorted(transformer.calls) == ["x", "y"]
    assert await service.get_payload_output(result.id) == "A, C, X, Y"


async def test_identical_request_reuses_payload_id(
    service: PayloadService, transformer: CountingTransformer
) -> None:
    first = await service.create_payload(["a"], ["b"])
    transformer.calls.clear()

    second = await service.create_payload(["a"], ["b"])

    assert second.id == first.id
    assert not second.created
    assert transformer.calls == []


async def test_swapped_lists_are_a_new_payload_from_cache(
    service: PayloadService, transformer: CountingTransformer
) -> None:
    first = await service.create_payload(["a"], ["b"])
    transformer.calls.clear()

    swapped = await service.create_payload(["b"], ["a"])

    assert swapped.id != first.id
    assert swapped.created
    assert transformer.calls == []
    assert await service.get_payload_output(swapped.id) == "B, A"


async def test_empty_lists(
    service: PayloadService, transformer: CountingTransformer
) -> None:
    first = await service.create_payload([], [])
    second = await service.create_payload([], [])

    assert await service.get_payload_output(first.id) == ""
    assert second.id == first.id
    assert transformer.calls == []


async def test_unknown_payload_id_returns_none(service: PayloadService) -> None:
    assert await service.get_payload_output(uuid.uuid4()) is None


async def test_misses_run_concurrently_up_to_the_limit(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    transformer = CountingTransformer(delay_seconds=0.01)
    service = PayloadService(session_factory, transformer, max_concurrency=2)

    await service.create_payload(["a", "b", "c"], ["d", "e", "f"])

    assert len(transformer.calls) == 6
    assert transformer.max_in_flight == 2


async def test_concurrent_identical_requests_share_one_payload(
    service: PayloadService,
) -> None:
    results = await asyncio.gather(
        *(service.create_payload(["a", "b"], ["c", "d"]) for _ in range(5))
    )

    assert len({result.id for result in results}) == 1
    assert sum(result.created for result in results) == 1


# The gate keeps the first calls running, so nothing reaches the cache until
# it opens: other requests can only avoid the transformer by joining those
# calls. The pause before opening gives them time to get there; it decides how
# much overlap is exercised, never whether a correct implementation passes.
OVERLAP_PAUSE_SECONDS = 0.05


async def test_concurrent_identical_requests_transform_each_string_once(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    gate = asyncio.Event()
    transformer = CountingTransformer(gate=gate)
    service = PayloadService(session_factory, transformer, max_concurrency=10)

    requests = [
        asyncio.create_task(service.create_payload(["a", "b"], ["c", "d"]))
        for _ in range(5)
    ]
    await transformer.wait_for_calls(4)
    await asyncio.sleep(OVERLAP_PAUSE_SECONDS)
    gate.set()
    results = await asyncio.gather(*requests)

    assert sorted(transformer.calls) == ["a", "b", "c", "d"]
    assert len({result.id for result in results}) == 1


async def test_concurrent_overlapping_requests_transform_shared_string_once(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    gate = asyncio.Event()
    transformer = CountingTransformer(gate=gate)
    service = PayloadService(session_factory, transformer, max_concurrency=10)

    first = asyncio.create_task(service.create_payload(["a"], ["b"]))
    second = asyncio.create_task(service.create_payload(["b"], ["c"]))
    await transformer.wait_for_calls(3)
    await asyncio.sleep(OVERLAP_PAUSE_SECONDS)
    gate.set()
    first_result, second_result = await asyncio.gather(first, second)

    assert sorted(transformer.calls) == ["a", "b", "c"]
    assert await service.get_payload_output(first_result.id) == "A, B"
    assert await service.get_payload_output(second_result.id) == "B, C"


async def test_cancelled_request_does_not_cancel_shared_call(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    gate = asyncio.Event()
    transformer = CountingTransformer(gate=gate)
    service = PayloadService(session_factory, transformer, max_concurrency=10)

    cancelled = asyncio.create_task(service.create_payload(["a"], ["b"]))
    await transformer.wait_for_calls(2)
    cancelled.cancel()
    with pytest.raises(asyncio.CancelledError):
        await cancelled

    # Either joins the still-running calls or finds their cached results;
    # without shielding they would have died with the first request.
    retry = asyncio.create_task(service.create_payload(["a"], ["b"]))
    gate.set()
    result = await retry

    assert sorted(transformer.calls) == ["a", "b"]
    assert await service.get_payload_output(result.id) == "A, B"


async def test_cached_result_is_persisted_before_in_flight_entry_is_released(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # "b" finishes long before the slow "a", so the first request is still
    # running when the second needs "b"; it must find it in the cache.
    slow_gate = asyncio.Event()

    class PartlyGatedTransformer(CountingTransformer):
        async def transform(self, value: str) -> str:
            if value == "a":
                self.calls.append(value)
                await slow_gate.wait()
                return value.upper()
            return await super().transform(value)

    transformer = PartlyGatedTransformer()
    service = PayloadService(session_factory, transformer, max_concurrency=10)

    first = asyncio.create_task(service.create_payload(["a"], ["b"]))
    await transformer.wait_for_calls(2)
    async with asyncio.timeout(1):  # "b" is cached while "a" is still running
        while not await _is_cached(session_factory, "b"):
            await asyncio.sleep(0.001)

    await service.create_payload(["b"], ["c"])
    slow_gate.set()
    await first

    assert sorted(transformer.calls) == ["a", "b", "c"]


async def _is_cached(
    session_factory: async_sessionmaker[AsyncSession], value: str
) -> bool:
    async with session_factory() as session:
        return await session.get(TransformCacheEntry, value) is not None
