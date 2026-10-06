import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from payload_cache.db.models import Payload
from payload_cache.db.upsert import insert_ignoring_conflicts
from payload_cache.domain.payloads import payload_fingerprint, render_output
from payload_cache.services.transformation_cache import TransformationCache


@dataclass(frozen=True, slots=True)
class PayloadRef:
    id: uuid.UUID
    created: bool


class PayloadService:
    """Creates and reads payloads.

    Database transactions are kept short and never span a transformer call: holding a
    pooled connection (or, on SQLite, the write lock) while waiting on a slow external
    service would starve concurrent requests.
    """

    def __init__(
        self, sessionmaker: async_sessionmaker[AsyncSession], cache: TransformationCache
    ) -> None:
        self._sessionmaker = sessionmaker
        self._cache = cache

    async def create(self, first: Sequence[str], second: Sequence[str]) -> PayloadRef:
        fingerprint = payload_fingerprint(first, second)

        # Fast path: an identical request was served before - no transformer work at all.
        existing_id = await self._find_id(fingerprint)
        if existing_id is not None:
            return PayloadRef(existing_id, created=False)

        transformed = await self._cache.transform_many([*first, *second])
        output = render_output(
            [transformed[value] for value in first], [transformed[value] for value in second]
        )

        row = {"id": uuid.uuid4(), "fingerprint": fingerprint, "output": output}
        async with self._sessionmaker.begin() as session:
            statement = insert_ignoring_conflicts(session, Payload, [row]).returning(Payload.id)
            inserted_id = (await session.execute(statement)).scalar_one_or_none()
        if inserted_id is not None:
            return PayloadRef(inserted_id, created=True)

        # A concurrent request stored the same payload between our lookup and insert;
        # converge on its identifier.
        existing_id = await self._find_id(fingerprint)
        if existing_id is None:
            raise RuntimeError("payload insert conflicted but no row exists")
        return PayloadRef(existing_id, created=False)

    async def get_output(self, payload_id: uuid.UUID) -> str | None:
        async with self._sessionmaker() as session:
            return await session.scalar(select(Payload.output).where(Payload.id == payload_id))

    async def _find_id(self, fingerprint: str) -> uuid.UUID | None:
        async with self._sessionmaker() as session:
            return await session.scalar(
                select(Payload.id).where(Payload.fingerprint == fingerprint)
            )
