"""The string transformer, standing in for an external service."""

import asyncio
from typing import Protocol


class Transformer(Protocol):
    """What the service needs from a transformer; implementations are swappable."""

    async def transform(self, value: str) -> str: ...


class SimulatedTransformer:
    """Uppercases input after a delay.

    The delay makes the cost of each call visible, which is what the cache saves.
    """

    def __init__(self, latency_seconds: float) -> None:
        self._latency_seconds = latency_seconds

    async def transform(self, value: str) -> str:
        await asyncio.sleep(self._latency_seconds)
        return value.upper()
