import asyncio
import logging
from typing import Protocol

logger = logging.getLogger(__name__)


class Transformer(Protocol):
    """A per-string transformation backed by an external (slow, possibly paid) service.

    Modelled as a protocol so the caching layer depends on the contract only; tests
    substitute a fake that counts calls, production could swap in an HTTP or LLM client.
    """

    async def __call__(self, value: str) -> str: ...


class UppercaseTransformer:
    """Stand-in for the external service: upper-cases the input after an artificial delay."""

    def __init__(self, delay_seconds: float = 0.0) -> None:
        self._delay_seconds = delay_seconds

    async def __call__(self, value: str) -> str:
        # Logged so cache hits vs. misses are observable in the service logs.
        logger.info("transformer called for %r", value)
        if self._delay_seconds:
            await asyncio.sleep(self._delay_seconds)
        return value.upper()
