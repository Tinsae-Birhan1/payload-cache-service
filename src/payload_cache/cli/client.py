import time
import uuid
from dataclasses import dataclass

import httpx

from payload_cache.api.schemas import PayloadCreate


@dataclass(frozen=True, slots=True)
class IterationResult:
    iteration: int
    id: uuid.UUID
    created: bool
    output: str
    elapsed_ms: float


class PayloadClient:
    """Thin synchronous client for the payload API. Synchronous on purpose: the CLI runs
    iterations one after another to show the cache warming up, so async buys nothing."""

    def __init__(self, http: httpx.Client) -> None:
        self._http = http

    def create_and_read(self, payload: PayloadCreate, iteration: int) -> IterationResult:
        started = time.perf_counter()
        created = self._http.post("/payload", json=payload.model_dump())
        created.raise_for_status()
        payload_id = uuid.UUID(created.json()["id"])

        read = self._http.get(f"/payload/{payload_id}")
        read.raise_for_status()
        elapsed_ms = (time.perf_counter() - started) * 1000

        return IterationResult(
            iteration=iteration,
            id=payload_id,
            created=created.status_code == httpx.codes.CREATED,
            output=read.json()["output"],
            elapsed_ms=round(elapsed_ms, 1),
        )
