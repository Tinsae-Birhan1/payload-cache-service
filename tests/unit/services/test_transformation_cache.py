import asyncio

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from payload_cache.services.transformation_cache import TransformationCache, TransformerError
from tests.fakes import CountingTransformer


async def test_cold_cache_transforms_each_value(
    cache: TransformationCache, transformer: CountingTransformer
) -> None:
    result = await cache.transform_many(["a", "b"])

    assert result == {"a": "A", "b": "B"}
    assert sorted(transformer.calls) == ["a", "b"]


async def test_duplicates_within_request_are_transformed_once(
    cache: TransformationCache, transformer: CountingTransformer
) -> None:
    await cache.transform_many(["a", "a", "b", "a"])

    assert sorted(transformer.calls) == ["a", "b"]


async def test_cached_values_are_not_transformed_again(
    cache: TransformationCache, transformer: CountingTransformer
) -> None:
    await cache.transform_many(["a", "b"])
    transformer.calls.clear()

    result = await cache.transform_many(["b", "c", "a"])

    assert result == {"a": "A", "b": "B", "c": "C"}
    assert transformer.calls == ["c"]


async def test_cache_survives_new_cache_instance(
    sessionmaker: async_sessionmaker[AsyncSession], transformer: CountingTransformer
) -> None:
    # Persistence is the point of the database: a restarted service keeps its cache.
    await TransformationCache(sessionmaker, transformer, max_concurrency=1).transform_many(["a"])
    transformer.calls.clear()

    await TransformationCache(sessionmaker, transformer, max_concurrency=1).transform_many(["a"])

    assert transformer.calls == []


async def test_concurrent_requests_share_one_in_flight_call(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    gate = asyncio.Event()
    transformer = CountingTransformer(gate=gate)
    cache = TransformationCache(sessionmaker, transformer, max_concurrency=4)

    first = asyncio.create_task(cache.transform_many(["a"]))
    second = asyncio.create_task(cache.transform_many(["a"]))
    # Give both requests time to miss the database and reach the transformer stage
    # while the first call is held open by the gate.
    await asyncio.sleep(0.2)
    gate.set()

    assert await first == await second == {"a": "A"}
    assert transformer.calls == ["a"]


async def test_failure_keeps_successful_results_cached(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    transformer = CountingTransformer(failing={"bad"})
    cache = TransformationCache(sessionmaker, transformer, max_concurrency=4)

    with pytest.raises(TransformerError):
        await cache.transform_many(["good", "bad"])
    transformer.calls.clear()

    assert await cache.transform_many(["good"]) == {"good": "GOOD"}
    assert transformer.calls == []


async def test_failed_value_is_retried_on_next_request(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    transformer = CountingTransformer(failing={"bad"})
    cache = TransformationCache(sessionmaker, transformer, max_concurrency=4)

    for _ in range(2):
        with pytest.raises(TransformerError):
            await cache.transform_many(["bad"])

    # Failures are not cached: a transient outage must not poison the cache.
    assert transformer.calls == ["bad", "bad"]
