from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class LoadingStrategy(StrEnum):
    KEEP_WARM = "keep_warm"
    LOAD_ON_FIRST_REQUEST = "load_on_first_request"
    UNLOAD_WHEN_IDLE = "unload_when_idle"
    SEQUENTIAL = "sequential"
    CPU_OFFLOAD = "cpu_offload"


@dataclass
class ManagedModel:
    name: str
    loader: Callable[[], Awaitable[Any]]
    unloader: Callable[[Any], Awaitable[None]]
    strategy: LoadingStrategy
    idle_seconds: float
    instance: Any | None = None
    last_used_monotonic: float = 0


class ModelLifecycleManager:
    """Serializes heavyweight model access and owns explicit load/unload behavior."""

    def __init__(self, *, concurrency: int = 1) -> None:
        if concurrency < 1:
            raise ValueError("concurrency must be at least one")
        self._models: dict[str, ManagedModel] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._gpu_slots = asyncio.Semaphore(concurrency)

    def register(self, model: ManagedModel) -> None:
        if model.name in self._models:
            raise ValueError(f"model already registered: {model.name}")
        self._models[model.name] = model
        self._locks[model.name] = asyncio.Lock()

    async def acquire(self, name: str) -> Any:
        model = self._models[name]
        await self._gpu_slots.acquire()
        try:
            async with self._locks[name]:
                if model.instance is None:
                    model.instance = await model.loader()
                model.last_used_monotonic = time.monotonic()
                return model.instance
        except BaseException:
            self._gpu_slots.release()
            raise

    def release(self, name: str) -> None:
        model = self._models[name]
        model.last_used_monotonic = time.monotonic()
        self._gpu_slots.release()

    async def unload(self, name: str) -> None:
        model = self._models[name]
        async with self._locks[name]:
            if model.instance is not None:
                await model.unloader(model.instance)
                model.instance = None

    async def unload_idle(self) -> tuple[str, ...]:
        now = time.monotonic()
        unloaded: list[str] = []
        for name, model in self._models.items():
            if (
                model.strategy == LoadingStrategy.UNLOAD_WHEN_IDLE
                and model.instance is not None
                and now - model.last_used_monotonic >= model.idle_seconds
            ):
                await self.unload(name)
                unloaded.append(name)
        return tuple(unloaded)

    async def shutdown(self) -> None:
        for name in tuple(self._models):
            await self.unload(name)
