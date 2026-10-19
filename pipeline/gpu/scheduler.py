from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable


@dataclass(frozen=True, slots=True)
class GpuProfile:
    name: str
    vram_gb: int
    hourly_usd: float | None
    capabilities: frozenset[str]
    endpoint_id: str | None = None
    benchmark: bool = False

    def supports(self, workload: str, min_vram_gb: int) -> bool:
        return workload in self.capabilities and self.vram_gb >= min_vram_gb


@dataclass(frozen=True, slots=True)
class GpuSelection:
    profile: GpuProfile
    workload: str
    estimated_seconds: float

    @property
    def estimated_cost_usd(self) -> float | None:
        if self.profile.hourly_usd is None:
            return None
        return self.estimated_seconds / 3600.0 * self.profile.hourly_usd


def choose_gpu(
    profiles: Iterable[GpuProfile],
    *,
    workload: str,
    min_vram_gb: int,
    estimated_seconds: float,
) -> GpuSelection:
    candidates = [p for p in profiles if p.supports(workload, min_vram_gb) and p.endpoint_id]
    if not candidates:
        raise RuntimeError(f"No configured GPU profile supports {workload} with {min_vram_gb}GB VRAM")

    # Prefer a known lower hourly rate; when pricing is unknown, prefer the smallest sufficient VRAM.
    def score(profile: GpuProfile) -> tuple[float, int, str]:
        hourly = profile.hourly_usd if profile.hourly_usd is not None else float("inf")
        return hourly, profile.vram_gb, profile.name

    selected = min(candidates, key=score)
    return GpuSelection(selected, workload, estimated_seconds)


def infer_vram_gb(name: str, default: int = 80) -> int:
    matches = [int(value) for value in re.findall(r"(\d+)\s*GB", name, flags=re.IGNORECASE)]
    return max(matches) if matches else default
