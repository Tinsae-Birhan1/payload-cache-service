import asyncio
from collections.abc import Iterable


class CountingTransformer:
    """Fake external service: records every call so tests can assert on call counts.

    ``gate`` lets a test hold calls in flight; ``failing`` lists inputs that raise.
    """

    def __init__(self, gate: asyncio.Event | None = None, failing: Iterable[str] = ()) -> None:
        self.calls: list[str] = []
        self._gate = gate
        self._failing = set(failing)

    def fail_on(self, value: str) -> None:
        self._failing.add(value)

    async def __call__(self, value: str) -> str:
        self.calls.append(value)
        if self._gate is not None:
            await self._gate.wait()
        if value in self._failing:
            raise RuntimeError(f"transformer unavailable for {value!r}")
        return value.upper()
