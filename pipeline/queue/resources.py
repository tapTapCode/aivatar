from __future__ import annotations

from contextlib import contextmanager
from threading import BoundedSemaphore, Lock

from pipeline.core.config import settings


class ResourceLimits:
    def __init__(self) -> None:
        self.capacities = {
            "project": settings.aivatar_max_project_jobs,
            "image_gpu": settings.aivatar_max_image_gpu_jobs,
            "video_gpu": settings.aivatar_max_video_gpu_jobs,
            "presenter": settings.aivatar_max_presenter_jobs,
            "ffmpeg": settings.aivatar_max_ffmpeg_jobs,
        }
        self.semaphores = {name: BoundedSemaphore(value) for name, value in self.capacities.items()}
        self._active = {name: 0 for name in self.capacities}
        self._lock = Lock()

    @contextmanager
    def reserve(self, name: str):
        semaphore = self.semaphores[name]
        semaphore.acquire()
        with self._lock:
            self._active[name] += 1
        try:
            yield
        finally:
            with self._lock:
                self._active[name] -= 1
            semaphore.release()

    def snapshot(self) -> dict[str, dict[str, int]]:
        with self._lock:
            return {
                name: {"active": self._active[name], "capacity": capacity, "available": capacity - self._active[name]}
                for name, capacity in self.capacities.items()
            }


resource_limits = ResourceLimits()
