import os
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from payload_cache.db.models import Base
from payload_cache.db.session import create_engine, create_sessionmaker
from payload_cache.services.payload_service import PayloadService
from payload_cache.services.transformation_cache import TransformationCache
from tests.fakes import CountingTransformer


@pytest.fixture
def database_url(tmp_path: Path) -> str:
    # TEST_DATABASE_URL runs the suite against Postgres (CI does both); the default is a
    # per-test SQLite file - not :memory:, as every pooled connection must see the same data.
    return os.environ.get("TEST_DATABASE_URL") or f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"


@pytest.fixture
async def sessionmaker(database_url: str) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_engine(database_url)
    # Tests build the schema from the models directly; migrations are exercised separately.
    # Dropping first isolates tests sharing one Postgres database.
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    yield create_sessionmaker(engine)
    await engine.dispose()


@pytest.fixture
def transformer() -> CountingTransformer:
    return CountingTransformer()


@pytest.fixture
def cache(
    sessionmaker: async_sessionmaker[AsyncSession], transformer: CountingTransformer
) -> TransformationCache:
    return TransformationCache(sessionmaker, transformer, max_concurrency=4)


@pytest.fixture
def service(
    sessionmaker: async_sessionmaker[AsyncSession], cache: TransformationCache
) -> PayloadService:
    return PayloadService(sessionmaker, cache)
