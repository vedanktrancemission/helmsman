"""Async event bus with in-memory and Redis Stream backends."""
from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

from app.config import get_settings


class MemoryBus:
    """In-process asyncio pub/sub bus."""
    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue] = set()

    async def publish(self, event: dict) -> None:
        for q in list(self._subscribers):
            await q.put(event)

    async def subscribe(self) -> AsyncIterator[dict]:
        q: asyncio.Queue = asyncio.Queue()
        self._subscribers.add(q)
        try:
            while True:
                yield await q.get()
        finally:
            self._subscribers.discard(q)


class RedisStreamBus:
    """Durable event bus backed by Redis Streams."""
    STREAM = "helmsman:events"

    def __init__(self, url: str) -> None:
        import redis.asyncio as redis

        self._redis = redis.from_url(url, decode_responses=True)

    async def publish(self, event: dict) -> None:
        await self._redis.xadd(self.STREAM, {"data": json.dumps(event)})

    async def subscribe(self) -> AsyncIterator[dict]:
        last_id = "$"
        while True:
            resp = await self._redis.xread({self.STREAM: last_id}, block=0, count=10)
            for _stream, entries in resp:
                for entry_id, fields in entries:
                    last_id = entry_id
                    yield json.loads(fields["data"])


_bus: MemoryBus | RedisStreamBus | None = None


def get_bus() -> MemoryBus | RedisStreamBus:
    """Return the singleton bus, creating it on first call."""
    global _bus
    if _bus is None:
        settings = get_settings()
        if settings.bus_backend == "redis":
            _bus = RedisStreamBus(settings.redis_url)
        else:
            _bus = MemoryBus()
    return _bus
