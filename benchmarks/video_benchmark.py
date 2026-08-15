from __future__ import annotations

from typing import Any

from benchmarks.common import Adapter, run_adapter

PROFILE: dict[str, Any] = {
    "mode": "text-to-video",
    "duration_seconds": 5,
    "width": 1280,
    "height": 720,
    "fps": 24,
    "frames": 120,
    "steps": "8 low-resolution + 3 refinement candidate",
    "seed": 424242,
    "prompt": "A steady documentary shot of waves moving around a tidal-energy turbine",
    "checkpoint": "LTX-2.3 22B with distilled LoRA v1.1 candidate",
    "upscaler": "spatial x2 candidate",
    "audio_enabled": False,
    "precision": "adapter must record actual",
    "quantization": "adapter must record actual",
    "offloading": "adapter must record actual",
}


def run(
    adapter: Adapter,
    *,
    device: str,
    cold_runs: int,
    warmup_runs: int,
    measured_runs: int,
) -> list[dict[str, Any]]:
    results = run_adapter(
        "video",
        adapter,
        device=device,
        cold_runs=cold_runs,
        warmup_runs=warmup_runs,
        measured_runs=measured_runs,
    )
    for result in results:
        result["profile"] = PROFILE
    return results
