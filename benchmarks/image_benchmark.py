from __future__ import annotations

from typing import Any

from benchmarks.common import Adapter, run_adapter

PROFILE: dict[str, Any] = {
    "mode": "text-to-image",
    "prompt": "Documentary photograph of a coastal renewable-energy laboratory at sunrise",
    "negative_prompt": None,
    "seed": 424242,
    "width": 1024,
    "height": 1024,
    "steps": 4,
    "guidance": "checkpoint default; adapter must record numeric value",
    "checkpoint": "black-forest-labs/FLUX.2-klein-4B",
    "checkpoint_revision": "PIN_REQUIRED",
    "precision": "bf16 candidate; adapter must record actual",
    "hidden_retries": 0,
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
        "image",
        adapter,
        device=device,
        cold_runs=cold_runs,
        warmup_runs=warmup_runs,
        measured_runs=measured_runs,
    )
    for result in results:
        result["profile"] = PROFILE
    return results
