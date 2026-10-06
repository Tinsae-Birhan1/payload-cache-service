import io
import json
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest
from pydantic_settings import CliApp

from payload_cache.cli.app import EXIT_INVALID_INPUT, EXIT_REQUEST_FAILED, main, run
from payload_cache.cli.settings import CliSettings

PAYLOAD = {"list_1": ["a", "b"], "list_2": ["c", "d"]}
PAYLOAD_ID = "6f1c2a52-0d8e-4d36-9b8f-3c8e0a0b6d11"


def _parse(*args: str) -> CliSettings:
    return CliApp.run(CliSettings, cli_args=list(args))


def _fake_server(created_status: Callable[[int], int]) -> httpx.Client:
    """In-memory stand-in for the API: no network, deterministic responses."""
    posts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal posts
        if request.method == "POST":
            posts += 1
            assert json.loads(request.content) == PAYLOAD
            return httpx.Response(created_status(posts), json={"id": PAYLOAD_ID, "message": ""})
        return httpx.Response(200, json={"output": "A, C, B, D"})

    return httpx.Client(transport=httpx.MockTransport(handler), base_url="http://test")


def test_short_and_long_options_are_equivalent() -> None:
    short = _parse("-H", "http://svc:9000", "-r", "3", "-j", "{}", "-o", "out.json")
    long = _parse(
        "--host", "http://svc:9000", "--repeat", "3", "--json", "{}", "--output", "out.json"
    )

    assert short == long
    assert str(short.host) == "http://svc:9000/"
    assert short.repeat == 3


def test_environment_does_not_leak_into_arguments(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOST", "http://wrong:1")

    assert str(_parse("-j", "{}").host) == "http://localhost:8000/"


@pytest.mark.parametrize(
    ("args", "message"),
    [
        ([], "exactly one of --input or --json"),
        (["-j", "{}", "-i", "-"], "exactly one of --input or --json"),
        (["-j", "{}", "-r", "0"], "-r: Input should be greater than 0"),
        (["-j", "{}", "-H", "ftp://svc"], "-H: URL scheme should be 'http' or 'https'"),
        (["-i", "missing.json"], "input file not found"),
        (["-j", "not json"], "not valid JSON"),
        (["-j", '{"list_1": ["a"], "list_2": []}'], "invalid payload"),
    ],
)
def test_invalid_arguments_exit_with_usage_error(
    args: list[str], message: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(args) == EXIT_INVALID_INPUT
    assert message in capsys.readouterr().err


def test_reads_payload_from_file(tmp_path: Path) -> None:
    source = tmp_path / "payload.json"
    source.write_text(json.dumps(PAYLOAD))

    assert _parse("-i", str(source)).load_payload().model_dump() == PAYLOAD


def test_reads_payload_from_stdin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(PAYLOAD)))

    assert _parse("-i", "-").load_payload().model_dump() == PAYLOAD


def test_repeat_reports_first_created_then_reused() -> None:
    settings = _parse("-j", json.dumps(PAYLOAD), "-r", "3")

    with _fake_server(lambda post: 201 if post == 1 else 200) as http:
        results = run(settings, http)

    assert [result.created for result in results] == [True, False, False]
    assert {str(result.id) for result in results} == {PAYLOAD_ID}
    assert results[-1].output == "A, C, B, D"


def test_server_error_exits_non_zero(capsys: pytest.CaptureFixture[str]) -> None:
    failing = httpx.MockTransport(lambda _: httpx.Response(502, json={"detail": "down"}))

    assert main(["-j", json.dumps(PAYLOAD)], transport=failing) == EXIT_REQUEST_FAILED
    assert "server returned 502" in capsys.readouterr().err


def test_writes_output_file(tmp_path: Path) -> None:
    destination = tmp_path / "result.json"
    server = httpx.MockTransport(
        lambda request: (
            httpx.Response(201, json={"id": PAYLOAD_ID, "message": ""})
            if request.method == "POST"
            else httpx.Response(200, json={"output": "A, C, B, D"})
        )
    )

    exit_code = main(["-j", json.dumps(PAYLOAD), "-o", str(destination)], transport=server)

    assert exit_code == 0
    document = json.loads(destination.read_text())
    assert document["id"] == PAYLOAD_ID
    assert document["output"] == "A, C, B, D"
    assert [iteration["created"] for iteration in document["iterations"]] == [True]
