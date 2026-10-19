from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from pipeline.production.longform import assemble_longform_proof


def run_three_project_concurrency(output_dir: Path, *, minutes: int = 1) -> dict:
    """Run three complete synthetic project assemblies at the same time.

    This proves the application-level concurrency contract independently from asset-level GPU limits.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            executor.submit(assemble_longform_proof, output_dir / f"project_{index}", minutes): index
            for index in range(1, 4)
        }
        for future in as_completed(futures):
            result = future.result()
            results.append({"project": futures[future], "output": result["output"], "qc": result["qc"], "wall_seconds": result["wall_seconds"]})
    elapsed = time.monotonic() - started
    results.sort(key=lambda item: item["project"])
    proof = {
        "phase": 5,
        "kind": "three_project_concurrency_proof",
        "project_count": 3,
        "minutes_each": minutes,
        "all_qc_passed": all(item["qc"]["ok"] for item in results),
        "wall_seconds": elapsed,
        "projects": results,
    }
    manifest = output_dir / "concurrency_manifest.json"
    manifest.write_text(json.dumps(proof, indent=2), encoding="utf-8")
    return {**proof, "manifest": str(manifest)}
