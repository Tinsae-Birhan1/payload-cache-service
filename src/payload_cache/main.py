import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from payload_cache.api.errors import register_error_handlers
from payload_cache.api.routes import router
from payload_cache.config import Settings, get_settings
from payload_cache.db.session import create_engine, create_sessionmaker
from payload_cache.domain.transformer import Transformer, UppercaseTransformer
from payload_cache.services.payload_service import PayloadService
from payload_cache.services.transformation_cache import TransformationCache


def create_app(settings: Settings | None = None, transformer: Transformer | None = None) -> FastAPI:
    """Application factory.

    Dependencies are parameters so tests can inject a database URL and a fake transformer
    without patching module globals. Run with ``uvicorn payload_cache.main:create_app --factory``.
    """
    settings = settings or get_settings()
    logging.basicConfig(
        level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_engine(settings.database_url)
        sessionmaker = create_sessionmaker(engine)
        cache = TransformationCache(
            sessionmaker,
            transformer or UppercaseTransformer(settings.transformer_delay_seconds),
            max_concurrency=settings.transformer_max_concurrency,
        )
        app.state.sessionmaker = sessionmaker
        app.state.payload_service = PayloadService(sessionmaker, cache)
        try:
            yield
        finally:
            await engine.dispose()

    app = FastAPI(
        title="Payload Cache Service",
        version="0.1.0",
        description="Builds payloads from transformed strings, caching every transformer result.",
        lifespan=lifespan,
    )
    app.include_router(router)
    register_error_handlers(app)
    return app
