"""The real CLI against a real server over TCP, with a migrated database: the closest
in-process approximation of ``docker compose up`` followed by ``cache-cli``."""

import json
import socket
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
import uvicorn
from alembic import command
from alembic.config import Config

from payload_cache.cli.app import main
from payload_cache.config import Settings
from payload_cache.main import create_app
from tests.fakes import CountingTransformer

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SAMPLE = {
    "list_1": ["first string", "second string", "third string"],
    "list_2": ["other string", "another string", "last string"],
}


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port: int = sock.getsockname()[1]
        return port


@pytest.fixture
def transformer() -> CountingTransformer:
    return CountingTransformer()


@pytest.fixture
def server_url(tmp_path: Path, transformer: CountingTransformer) -> Iterator[str]:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'e2e.db'}"
    alembic_config = Config(PROJECT_ROOT / "alembic.ini")
    alembic_config.set_main_option("sqlalchemy.url", database_url)
    alembic_config.attributes["configure_logger"] = False
    command.upgrade(alembic_config, "head")

    app = create_app(Settings(database_url=database_url), transformer=transformer)
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("server did not start")
        time.sleep(0.05)

    yield f"http://127.0.0.1:{port}"

    server.should_exit = True
    thread.join(timeout=10)


def test_cli_round_trip_uses_cache_on_repeat(
    server_url: str, transformer: CountingTransformer, tmp_path: Path
) -> None:
    source = tmp_path / "input.json"
    source.write_text(json.dumps(SAMPLE))
    destination = tmp_path / "output.json"

    exit_code = main(["-H", server_url, "-i", str(source), "-r", "3", "-o", str(destination)])

    assert exit_code == 0
    document = json.loads(destination.read_text())
    assert document["output"] == (
        "FIRST STRING, OTHER STRING, SECOND STRING, ANOTHER STRING, THIRD STRING, LAST STRING"
    )
    assert [iteration["created"] for iteration in document["iterations"]] == [True, False, False]
    # Six distinct strings, three iterations: the transformer ran exactly once per string.
    assert sorted(transformer.calls) == sorted(SAMPLE["list_1"] + SAMPLE["list_2"])
