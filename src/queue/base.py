from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, ConfigDict


class JobMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    job_id: str
    video_id: str
    project_id: str
    owner_id: str


class JobQueue(Protocol):
    async def enqueue(self, message: JobMessage) -> None: ...

    async def dequeue(self, *, timeout_seconds: int = 5) -> JobMessage | None: ...

    async def try_dequeue(self) -> JobMessage | None: ...

    async def depth(self) -> int: ...
