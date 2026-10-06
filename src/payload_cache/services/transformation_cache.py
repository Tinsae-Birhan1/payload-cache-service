import asyncio
from collections.abc import Iterable, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from payload_cache.db.models import CachedTransformation
from payload_cache.db.upsert import insert_ignoring_conflicts
from payload_cache.domain.payloads import transformation_key
from payload_cache.domain.transformer import Transformer


class TransformerError(Exception):
    """The external transformer failed for at least one input."""


class TransformationCache:
    """Read-through cache in front of the transformer, persisted in the database.

    Guarantees, in order of cost saved:
    1. a string already in the database is never sent to the transformer again;
    2. a string repeated within one request is transformed once;
    3. concurrent requests needing the same uncached string share one in-flight call
       (within this process - see README for the multi-replica limitation).
    """

    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        transformer: Transformer,
        max_concurrency: int,
    ) -> None:
        self._sessionmaker = sessionmaker
        self._transformer = transformer
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._in_flight: dict[str, asyncio.Task[str]] = {}

    async def transform_many(self, values: Iterable[str]) -> dict[str, str]:
        """Return a mapping of every input value to its transformed value."""
        unique_values = list(dict.fromkeys(values))
        results = await self._load_cached(unique_values)

        missing = [value for value in unique_values if value not in results]
        if not missing:
            return results

        # return_exceptions: one failing input must not discard the results we already
        # paid for - successes are persisted below before the error is raised.
        outcomes = await asyncio.gather(
            *(self._transform_shared(value) for value in missing), return_exceptions=True
        )
        fresh = {
            value: outcome
            for value, outcome in zip(missing, outcomes, strict=True)
            if isinstance(outcome, str)
        }
        await self._store(fresh)

        for outcome in outcomes:
            if isinstance(outcome, BaseException):
                raise TransformerError("transformer failed") from outcome

        results.update(fresh)
        return results

    async def _load_cached(self, values: Sequence[str]) -> dict[str, str]:
        # One round trip for the whole request instead of one query per string.
        # Request size is bounded by settings, so the IN list stays within driver limits.
        keys = {transformation_key(value): value for value in values}
        async with self._sessionmaker() as session:
            rows = await session.execute(
                select(CachedTransformation.input_hash, CachedTransformation.output_text).where(
                    CachedTransformation.input_hash.in_(keys)
                )
            )
            return {keys[input_hash]: output_text for input_hash, output_text in rows}

    async def _store(self, transformed: dict[str, str]) -> None:
        if not transformed:
            return
        rows = [
            {"input_hash": transformation_key(value), "input_text": value, "output_text": output}
            for value, output in transformed.items()
        ]
        async with self._sessionmaker.begin() as session:
            await session.execute(insert_ignoring_conflicts(session, CachedTransformation, rows))

    async def _transform_shared(self, value: str) -> str:
        task = self._in_flight.get(value)
        if task is None:
            task = asyncio.create_task(self._call_transformer(value))
            self._in_flight[value] = task
            task.add_done_callback(lambda _: self._in_flight.pop(value, None))
        # shield: if one waiting request is cancelled (client disconnect), the shared
        # call keeps running for the other requests waiting on it.
        return await asyncio.shield(task)

    async def _call_transformer(self, value: str) -> str:
        async with self._semaphore:
            return await self._transformer(value)
