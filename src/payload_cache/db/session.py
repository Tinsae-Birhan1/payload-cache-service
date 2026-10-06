from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def create_engine(database_url: str) -> AsyncEngine:
    if not database_url.startswith("sqlite"):
        return create_async_engine(database_url, pool_pre_ping=True)

    # SQLite allows one writer at a time; wait for the lock instead of failing fast.
    engine = create_async_engine(database_url, connect_args={"timeout": 30})

    @event.listens_for(engine.sync_engine, "connect")
    def _enable_wal(dbapi_connection: Any, _: Any) -> None:
        # WAL lets readers proceed while a write is in progress, which matters because
        # every request reads the cache while others may be storing results.
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()

    return engine


def create_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)
