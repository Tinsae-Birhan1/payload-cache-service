import uuid
from datetime import datetime

from sqlalchemy import CHAR, DateTime, MetaData, Text, Uuid, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    # Deterministic constraint names: migrations can reference them by name, which
    # Alembic needs to alter or drop constraints (and SQLite batch mode requires).
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(column_0_label)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


class CachedTransformation(Base):
    """One result of the external transformer, keyed by a hash of its input.

    Hashing rather than indexing the raw text keeps the key fixed-width: Postgres btree
    entries are capped at ~2.7 KB, so a unique index on arbitrary user text would reject
    long inputs, and a 64-char key keeps the index small regardless of input size.
    """

    __tablename__ = "transformation_cache"

    input_hash: Mapped[str] = mapped_column(CHAR(64), primary_key=True)
    input_text: Mapped[str] = mapped_column(Text)
    output_text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Payload(Base):
    """A generated payload.

    The rendered output is stored rather than rebuilt from the cache on every read:
    GET becomes a single primary-key lookup, and a payload stays stable even if the
    transformation cache is later pruned.
    """

    __tablename__ = "payloads"

    # Random UUIDs rather than sequential ints so identifiers do not reveal volume or
    # let clients enumerate other users' payloads.
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    # Unique so concurrent requests for the same input converge on one row.
    fingerprint: Mapped[str] = mapped_column(CHAR(64), unique=True)
    output: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
