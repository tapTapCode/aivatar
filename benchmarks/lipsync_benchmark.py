from __future__ import annotations

from typing import Any

from benchmarks.common import Adapter, run_adapter

PROFILE: dict[str, Any] = {
    "duration_seconds": 10,
    "width": 1280,
    "height": 720,
    "fps": 25,
    "codec": "h264",
    "avatar_source": "client-authorized fixed 10-second fixture required",
    "audio_source": "fixed 10-second WAV fixture required",
    "face_enhancement": False,
    "checkpoint": "MuseTalk 1.5",
    "checkpoint_revision": "PIN_REQUIRED",
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
        "lipsync",
        adapter,
        device=device,
        cold_runs=cold_runs,
        warmup_runs=warmup_runs,
        measured_runs=measured_runs,
    )
    for result in results:
        result["profile"] = PROFILE
        if result["status"] == "MEASURED":
            result["effective_processed_fps"] = 250 / result["end_to_end_seconds"]
    return results
