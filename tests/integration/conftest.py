from collections.abc import AsyncIterator

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from payload_cache.config import Settings
from payload_cache.main import create_app
from tests.fakes import CountingTransformer


@pytest.fixture
async def client(
    database_url: str,
    sessionmaker: async_sessionmaker[AsyncSession],  # ensures the schema exists
    transformer: CountingTransformer,
) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(Settings(database_url=database_url), transformer=transformer)
    # httpx's ASGI transport does not run the lifespan, so enter it explicitly.
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
