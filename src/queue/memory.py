from __future__ import annotations

import asyncio

from src.queue.base import JobMessage


class InMemoryJobQueue:
    def __init__(self) -> None:
        self._queue: asyncio.Queue[JobMessage] = asyncio.Queue()

    async def enqueue(self, message: JobMessage) -> None:
        await self._queue.put(message)

    async def dequeue(self, *, timeout_seconds: int = 5) -> JobMessage | None:
        try:
            return await asyncio.wait_for(self._queue.get(), timeout_seconds)
        except TimeoutError:
            return None

    async def try_dequeue(self) -> JobMessage | None:
        try:
            return self._queue.get_nowait()
        except asyncio.QueueEmpty:
            return None

    async def depth(self) -> int:
        return self._queue.qsize()
