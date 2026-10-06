"""``cache-cli``: exercise the payload service from the command line.

Results go to ``--output`` as JSON; diagnostics go to stderr, so stdout stays pipeable
(e.g. ``cache-cli -j '...' | jq .output``).
"""

import json
import sys
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path

import httpx
from pydantic import ValidationError
from pydantic_settings import CliApp

from payload_cache.cli.client import IterationResult, PayloadClient
from payload_cache.cli.settings import STDIO, CliSettings, InputError

EXIT_OK = 0
EXIT_REQUEST_FAILED = 1
EXIT_INVALID_INPUT = 2  # same code argparse uses for usage errors


def run(settings: CliSettings, http: httpx.Client) -> list[IterationResult]:
    payload = settings.load_payload()
    client = PayloadClient(http)
    results = []
    for iteration in range(1, settings.repeat + 1):
        result = client.create_and_read(payload, iteration)
        print(
            f"[{iteration}/{settings.repeat}] "
            f"{'created' if result.created else 'reused '} {result.id} "
            f"in {result.elapsed_ms} ms",
            file=sys.stderr,
        )
        results.append(result)
    return results


def write_output(results: list[IterationResult], destination: str) -> None:
    document = {
        "id": str(results[-1].id),
        "output": results[-1].output,
        "iterations": [
            {key: value for key, value in asdict(result).items() if key not in {"id", "output"}}
            for result in results
        ],
    }
    text = json.dumps(document, indent=2, ensure_ascii=False) + "\n"
    if destination == STDIO:
        sys.stdout.write(text)
    else:
        Path(destination).write_text(text, encoding="utf-8")


def main(argv: Sequence[str] | None = None, transport: httpx.BaseTransport | None = None) -> int:
    """Run the CLI and return its exit code. ``transport`` lets tests swap the network."""
    try:
        settings = CliApp.run(CliSettings, cli_args=list(sys.argv[1:] if argv is None else argv))
    except ValidationError as exc:
        # Cross-field and value checks run after argparse; report them the same terse way.
        for error in exc.errors():
            option = "".join(str(part) for part in error["loc"])
            prefix = f"{'-' if len(option) == 1 else '--'}{option}: " if option else ""
            message = error["msg"].removeprefix("Value error, ")
            print(f"cache-cli: error: {prefix}{message}", file=sys.stderr)
        return EXIT_INVALID_INPUT

    try:
        with httpx.Client(base_url=str(settings.host), timeout=30, transport=transport) as http:
            results = run(settings, http)
    except InputError as exc:
        print(f"cache-cli: {exc}", file=sys.stderr)
        return EXIT_INVALID_INPUT
    except httpx.HTTPStatusError as exc:
        print(
            f"cache-cli: server returned {exc.response.status_code}: {exc.response.text}",
            file=sys.stderr,
        )
        return EXIT_REQUEST_FAILED
    except httpx.HTTPError as exc:
        print(f"cache-cli: cannot reach {settings.host}: {exc}", file=sys.stderr)
        return EXIT_REQUEST_FAILED

    write_output(results, settings.output)
    return EXIT_OK


def entrypoint() -> None:
    sys.exit(main())


if __name__ == "__main__":
    entrypoint()
