import asyncio
import uuid
from typing import Any

import httpx
import pytest

from payload_cache.api.schemas import MAX_ITEMS_PER_LIST, MAX_STRING_LENGTH
from tests.fakes import CountingTransformer

SAMPLE = {
    "list_1": ["first string", "second string", "third string"],
    "list_2": ["other string", "another string", "last string"],
}
SAMPLE_OUTPUT = (
    "FIRST STRING, OTHER STRING, SECOND STRING, ANOTHER STRING, THIRD STRING, LAST STRING"
)


async def test_create_and_read_sample_payload(client: httpx.AsyncClient) -> None:
    created = await client.post("/payload", json=SAMPLE)

    assert created.status_code == 201
    body = created.json()
    assert body["message"] == "Payload created"
    assert created.headers["Location"] == f"/payload/{body['id']}"

    read = await client.get(f"/payload/{body['id']}")

    assert read.status_code == 200
    assert read.json() == {"output": SAMPLE_OUTPUT}


async def test_repeated_post_reuses_identifier(
    client: httpx.AsyncClient, transformer: CountingTransformer
) -> None:
    first = await client.post("/payload", json=SAMPLE)
    transformer.calls.clear()

    second = await client.post("/payload", json=SAMPLE)

    assert second.status_code == 200
    assert second.json() == {"id": first.json()["id"], "message": "Payload already exists"}
    assert transformer.calls == []


async def test_overlapping_payload_only_transforms_new_strings(
    client: httpx.AsyncClient, transformer: CountingTransformer
) -> None:
    await client.post("/payload", json=SAMPLE)
    transformer.calls.clear()

    response = await client.post(
        "/payload", json={"list_1": ["first string", "new"], "list_2": ["last string", "new"]}
    )

    assert response.status_code == 201
    assert transformer.calls == ["new"]


async def test_concurrent_identical_posts_return_one_identifier(
    client: httpx.AsyncClient,
) -> None:
    responses = await asyncio.gather(*(client.post("/payload", json=SAMPLE) for _ in range(5)))

    assert len({response.json()["id"] for response in responses}) == 1
    assert sorted(response.status_code for response in responses) == [200, 200, 200, 200, 201]


@pytest.mark.parametrize(
    "body",
    [
        {"list_1": ["a"], "list_2": ["b", "c"]},  # unequal lengths
        {"list_1": [], "list_2": []},  # empty
        {"list_1": ["a"]},  # missing list
        {"list_1": ["a"], "list_2": [1]},  # non-string item
        {"list_1": ["a"], "list_2": ["b"], "list_3": ["c"]},  # unknown field
        {"list_1": ["a"] * (MAX_ITEMS_PER_LIST + 1), "list_2": ["b"] * (MAX_ITEMS_PER_LIST + 1)},
        {"list_1": ["a" * (MAX_STRING_LENGTH + 1)], "list_2": ["b"]},
    ],
)
async def test_invalid_input_is_rejected_without_transforming(
    client: httpx.AsyncClient, transformer: CountingTransformer, body: dict[str, Any]
) -> None:
    response = await client.post("/payload", json=body)

    assert response.status_code == 422
    assert transformer.calls == []


async def test_unknown_payload_returns_404(client: httpx.AsyncClient) -> None:
    response = await client.get(f"/payload/{uuid.uuid4()}")

    assert response.status_code == 404


async def test_malformed_identifier_returns_422(client: httpx.AsyncClient) -> None:
    response = await client.get("/payload/not-a-uuid")

    assert response.status_code == 422


async def test_transformer_failure_returns_502(
    client: httpx.AsyncClient, transformer: CountingTransformer
) -> None:
    transformer.fail_on("broken")

    response = await client.post("/payload", json={"list_1": ["ok"], "list_2": ["broken"]})

    assert response.status_code == 502


async def test_health_reports_ok(client: httpx.AsyncClient) -> None:
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
