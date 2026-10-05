"""Test doubles shared across test modules."""

import asyncio


class CountingTransformer:
    """Uppercases like the real one and records every call.

    Call counts are the key assertion: the service exists to minimize them.
    """

    def __init__(self, delay_seconds: float = 0) -> None:
        self.calls: list[str] = []
        self.max_in_flight = 0
        self._in_flight = 0
        self._delay_seconds = delay_seconds

    async def transform(self, value: str) -> str:
        self.calls.append(value)
        self._in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self._in_flight)
        try:
            await asyncio.sleep(self._delay_seconds)
            return value.upper()
        finally:
            self._in_flight -= 1
