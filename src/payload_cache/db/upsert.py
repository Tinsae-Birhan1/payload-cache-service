from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import Insert
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from payload_cache.db.models import Base


def insert_ignoring_conflicts(
    session: AsyncSession, model: type[Base], rows: Sequence[Mapping[str, Any]]
) -> Insert:
    """``INSERT ... ON CONFLICT DO NOTHING`` for the session's database.

    Concurrent requests may try to store the same key. The loser must not fail: the row
    it wanted to write already exists with an equivalent value, so the database's unique
    constraint - not a check-then-insert in Python - decides the winner atomically.
    """
    dialect = session.get_bind().dialect.name
    if dialect == "postgresql":
        return postgresql_insert(model).values(list(rows)).on_conflict_do_nothing()
    if dialect == "sqlite":
        return sqlite_insert(model).values(list(rows)).on_conflict_do_nothing()
    raise NotImplementedError(f"unsupported database dialect: {dialect}")
