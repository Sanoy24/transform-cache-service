"""Test doubles shared across test modules."""

import asyncio


class CountingTransformer:
    """Uppercases like the real one and records every call.

    Call counts are the key assertion: the service exists to minimize them.
    A gate, when given, holds every call until the test opens it, so tests can
    keep calls in flight for as long as they need instead of guessing with sleeps.
    """

    def __init__(
        self, delay_seconds: float = 0, gate: asyncio.Event | None = None
    ) -> None:
        self.calls: list[str] = []
        self.max_in_flight = 0
        self._in_flight = 0
        self._delay_seconds = delay_seconds
        self._gate = gate

    async def transform(self, value: str) -> str:
        self.calls.append(value)
        self._in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self._in_flight)
        try:
            if self._gate is not None:
                await self._gate.wait()
            await asyncio.sleep(self._delay_seconds)
            return value.upper()
        finally:
            self._in_flight -= 1

    async def wait_for_calls(self, count: int, timeout: float = 1) -> None:
        async with asyncio.timeout(timeout):
            while len(self.calls) < count:
                await asyncio.sleep(0.001)
