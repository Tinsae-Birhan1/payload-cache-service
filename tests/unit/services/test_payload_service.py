import asyncio
import uuid

from payload_cache.services.payload_service import PayloadService
from tests.fakes import CountingTransformer

LIST_1 = ["first string", "second string", "third string"]
LIST_2 = ["other string", "another string", "last string"]


async def test_create_then_read_returns_spec_output(service: PayloadService) -> None:
    ref = await service.create(LIST_1, LIST_2)

    assert ref.created is True
    assert await service.get_output(ref.id) == (
        "FIRST STRING, OTHER STRING, SECOND STRING, ANOTHER STRING, THIRD STRING, LAST STRING"
    )


async def test_identical_request_reuses_payload_without_transforming(
    service: PayloadService, transformer: CountingTransformer
) -> None:
    first = await service.create(LIST_1, LIST_2)
    transformer.calls.clear()

    second = await service.create(LIST_1, LIST_2)

    assert second.id == first.id
    assert second.created is False
    assert transformer.calls == []


async def test_new_payload_only_transforms_unseen_strings(
    service: PayloadService, transformer: CountingTransformer
) -> None:
    await service.create(LIST_1, LIST_2)
    transformer.calls.clear()

    ref = await service.create(["first string", "brand new"], ["last string", "other string"])

    assert ref.created is True
    assert transformer.calls == ["brand new"]
    assert await service.get_output(ref.id) == (
        "FIRST STRING, LAST STRING, BRAND NEW, OTHER STRING"
    )


async def test_concurrent_identical_requests_converge_on_one_payload(
    service: PayloadService,
) -> None:
    refs = await asyncio.gather(*(service.create(LIST_1, LIST_2) for _ in range(5)))

    assert len({ref.id for ref in refs}) == 1
    assert sum(ref.created for ref in refs) == 1


async def test_unknown_payload_returns_none(service: PayloadService) -> None:
    assert await service.get_output(uuid.uuid4()) is None
