from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine

from payload_cache.db.models import Base

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _alembic_config(database_url: str) -> Config:
    config = Config(PROJECT_ROOT / "alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)
    config.attributes["configure_logger"] = False
    return config


# Sync tests on purpose: migrations/env.py calls asyncio.run(), which cannot run inside
# the event loop pytest-asyncio provides for async tests.
def test_migrations_match_models(tmp_path: Path) -> None:
    """Fails when a model changes without a migration - the drift that bites in production."""
    db_path = tmp_path / "migrated.db"
    command.upgrade(_alembic_config(f"sqlite+aiosqlite:///{db_path}"), "head")

    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as connection:
        diff = compare_metadata(MigrationContext.configure(connection), Base.metadata)
    engine.dispose()

    assert diff == []


def test_migrations_downgrade_cleanly(tmp_path: Path) -> None:
    config = _alembic_config(f"sqlite+aiosqlite:///{tmp_path / 'roundtrip.db'}")

    command.upgrade(config, "head")
    command.downgrade(config, "base")
    command.upgrade(config, "head")
