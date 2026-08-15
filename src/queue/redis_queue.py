from __future__ import annotations

from redis.asyncio import Redis

from src.queue.base import JobMessage


class RedisJobQueue:
    def __init__(self, redis_url: str, *, queue_name: str = "video:jobs") -> None:
        self.redis = Redis.from_url(redis_url, decode_responses=True)
        self.queue_name = queue_name

    async def enqueue(self, message: JobMessage) -> None:
        await self.redis.rpush(self.queue_name, message.model_dump_json())

    async def dequeue(self, *, timeout_seconds: int = 5) -> JobMessage | None:
        result = await self.redis.blpop(self.queue_name, timeout=timeout_seconds)
        if result is None:
            return None
        _, payload = result
        return JobMessage.model_validate_json(payload)

    async def try_dequeue(self) -> JobMessage | None:
        payload = await self.redis.lpop(self.queue_name)
        if payload is None:
            return None
        return JobMessage.model_validate_json(payload)

    async def depth(self) -> int:
        return await self.redis.llen(self.queue_name)

    async def close(self) -> None:
        await self.redis.aclose()
