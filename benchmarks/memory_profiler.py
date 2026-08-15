from __future__ import annotations

import contextlib
from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class MemorySnapshot:
    allocated_bytes: int | None = None
    reserved_bytes: int | None = None
    max_allocated_bytes: int | None = None
    max_reserved_bytes: int | None = None
    driver_used_bytes: int | None = None

    def to_dict(self) -> dict[str, int | None]:
        return asdict(self)


class CudaMemoryProfiler(contextlib.AbstractContextManager["CudaMemoryProfiler"]):
    def __init__(self, device: str = "cuda:0") -> None:
        self.device = device
        self.before = MemorySnapshot()
        self.after = MemorySnapshot()
        self.available = False
        self._torch: Any = None

    def __enter__(self) -> CudaMemoryProfiler:
        try:
            import torch

            if not torch.cuda.is_available():
                return self
            self._torch = torch
            torch.cuda.set_device(self.device)
            torch.cuda.empty_cache()
            torch.cuda.reset_peak_memory_stats(self.device)
            torch.cuda.synchronize(self.device)
            self.before = self._snapshot()
            self.available = True
        except (ImportError, RuntimeError):
            self.available = False
        return self

    def __exit__(self, *args: object) -> None:
        if self.available:
            self._torch.cuda.synchronize(self.device)
            self.after = self._snapshot()

    def _snapshot(self) -> MemorySnapshot:
        torch = self._torch
        return MemorySnapshot(
            allocated_bytes=torch.cuda.memory_allocated(self.device),
            reserved_bytes=torch.cuda.memory_reserved(self.device),
            max_allocated_bytes=torch.cuda.max_memory_allocated(self.device),
            max_reserved_bytes=torch.cuda.max_memory_reserved(self.device),
            driver_used_bytes=_nvml_used_memory(self.device),
        )


def _nvml_used_memory(device: str) -> int | None:
    try:
        import pynvml

        pynvml.nvmlInit()
        index = int(device.rsplit(":", 1)[-1])
        handle = pynvml.nvmlDeviceGetHandleByIndex(index)
        used = int(pynvml.nvmlDeviceGetMemoryInfo(handle).used)
        pynvml.nvmlShutdown()
        return used
    except (ImportError, ValueError, RuntimeError, Exception):
        # NVML raises package-specific exception subclasses; absence must not break capture.
        return None
