from __future__ import annotations

import importlib
import math
import statistics
import time
from collections.abc import Callable
from typing import Any

from benchmarks.memory_profiler import CudaMemoryProfiler

Adapter = Callable[[str, int], dict[str, Any]]


def load_adapter(reference: str) -> Adapter:
    module_name, separator, attribute = reference.partition(":")
    if not separator:
        raise ValueError("adapter must use module:function syntax")
    candidate = getattr(importlib.import_module(module_name), attribute)
    if not callable(candidate):
        raise TypeError("adapter target is not callable")
    return candidate


def run_adapter(
    workload: str,
    adapter: Adapter,
    *,
    device: str,
    cold_runs: int,
    warmup_runs: int,
    measured_runs: int,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for run_index in range(cold_runs):
        with CudaMemoryProfiler(device) as memory:
            started = time.perf_counter()
            stages = adapter("cold_container", run_index)
            latency = time.perf_counter() - started
        restarted = stages.get("container_restarted") is True
        results.append(
            {
                "workload": workload,
                "phase": "cold_container",
                "run_index": run_index,
                "status": "MEASURED" if restarted else "INVALID",
                "invalid_reason": None
                if restarted
                else "adapter did not attest container_restarted=true",
                "end_to_end_seconds": latency,
                "stages": stages,
                "memory": memory.after.to_dict(),
            }
        )
    for run_index in range(warmup_runs):
        adapter("warmup", run_index)
    for run_index in range(measured_runs):
        with CudaMemoryProfiler(device) as memory:
            started = time.perf_counter()
            stages = adapter("steady_state", run_index)
            latency = time.perf_counter() - started
        results.append(
            {
                "workload": workload,
                "phase": "warm_loaded_steady_state",
                "run_index": run_index,
                "status": "MEASURED",
                "end_to_end_seconds": latency,
                "stages": stages,
                "memory": memory.after.to_dict(),
            }
        )
    return results


def percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] * (upper - position) + ordered[upper] * (position - lower)


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    values = [
        float(row["end_to_end_seconds"]) for row in results if row.get("status") == "MEASURED"
    ]
    if not values:
        return {"status": "NOT TESTED", "sample_count": 0}
    return {
        "status": "MEASURED",
        "sample_count": len(values),
        "mean_seconds": statistics.fmean(values),
        "p50_seconds": percentile(values, 0.50),
        "p90_seconds": percentile(values, 0.90),
        "p95_seconds": percentile(values, 0.95),
        "p99_seconds": percentile(values, 0.99),
        "highest_observed_seconds": max(values),
        "lowest_observed_seconds": min(values),
        "successful_workloads_per_hour": 3600 / statistics.fmean(values),
    }
