import asyncio
import uuid

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from tests.fakes import CountingTransformer
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
