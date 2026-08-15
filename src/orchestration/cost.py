from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

PROOF_REPLAY_NOTE = "local_proof_replay"
GPU_ESTIMATE_NOTE = "gpu_estimate"
GPU_ACTUAL_NOTE = "wall_clock_gpu_rate"
HEYGEN_ESTIMATE_NOTE = "heygen_estimate"
HEYGEN_ACTUAL_NOTE = "heygen_avatar_iv"
COST_POLICY = "Packaged replay is $0; GPU $0.22/hr only without proof"
HEYGEN_COST_POLICY = "HeyGen Avatar IV is billed at the configured per-minute rate."
IMPORTED_COST_POLICY = "Imported HeyGen website exports are $0. The source watermark is preserved."


def heygen_avatar_iv_cost(duration_seconds: float, rate_usd_per_minute: float) -> float:
    if rate_usd_per_minute <= 0:
        raise ValueError("HeyGen Avatar IV rate must be positive")
    return round(max(0.0, float(duration_seconds)) / 60.0 * float(rate_usd_per_minute), 4)


def cost_policy_for(provider: str) -> str:
    if provider == "heygen_api":
        return HEYGEN_COST_POLICY
    if provider == "imported_video":
        return IMPORTED_COST_POLICY
    return COST_POLICY


@dataclass(frozen=True)
class CloudCostInputs:
    billable_gpu_seconds: float
    gpu_hourly_rate: float
    startup_billable_seconds: float = 0
    minimum_billable_seconds: float = 0
    storage_cost: float = 0
    bandwidth_cost: float = 0
    model_download_cost: float = 0
    retry_cost: float = 0
    failed_job_cost: float = 0
    idle_worker_cost: float = 0


def cloud_generation_cost(inputs: CloudCostInputs) -> float:
    billable = max(
        inputs.minimum_billable_seconds,
        inputs.billable_gpu_seconds + inputs.startup_billable_seconds,
    )
    return (billable / 3600) * inputs.gpu_hourly_rate + sum(
        (
            inputs.storage_cost,
            inputs.bandwidth_cost,
            inputs.model_download_cost,
            inputs.retry_cost,
            inputs.failed_job_cost,
            inputs.idle_worker_cost,
        )
    )


@dataclass(frozen=True)
class LocalCostInputs:
    gpu_seconds: float
    average_power_watts: float
    electricity_per_kwh: float
    hardware_cost: float
    amortization_hours: float
    maintenance_fraction: float = 0
    utilization: float = 1


def local_generation_cost(inputs: LocalCostInputs) -> float:
    if not 0 < inputs.utilization <= 1:
        raise ValueError("utilization must be in (0, 1]")
    if inputs.amortization_hours <= 0:
        raise ValueError("amortization_hours must be positive")
    hours = inputs.gpu_seconds / 3600
    electricity = hours * inputs.average_power_watts / 1000 * inputs.electricity_per_kwh
    amortization = hours * (inputs.hardware_cost / inputs.amortization_hours) / inputs.utilization
    maintenance = amortization * inputs.maintenance_fraction
    return electricity + amortization + maintenance


def scene_duration_seconds(scene: Any) -> float:
    duration = getattr(scene, "duration_seconds", None)
    if duration is not None:
        return float(duration)
    text = getattr(scene, "narration_text", "") or ""
    return max(1.0, len(str(text).split()) / 2.6)


def estimate_control_plane_job(
    scenes: list[Any] | tuple[Any, ...],
    *,
    provider: str,
    heygen_rate_usd_per_minute: float,
    gpu_hourly_rate_usd: float,
    in_process_local_proof: bool = False,
) -> tuple[float, str]:
    if provider == "heygen_api":
        from src.providers.heygen import estimate_project_avatar_cost

        amount = estimate_project_avatar_cost(
            list(scenes), rate_usd_per_minute=heygen_rate_usd_per_minute
        )
        return round(float(amount), 4), HEYGEN_ESTIMATE_NOTE
    if provider == "local_musetalk" and in_process_local_proof:
        return 0.0, PROOF_REPLAY_NOTE
    seconds = sum(scene_duration_seconds(scene) for scene in scenes)
    return round((seconds / 3600.0) * gpu_hourly_rate_usd, 4), GPU_ESTIMATE_NOTE


def _job_notes(job: Any) -> list[str]:
    return [
        str(getattr(entry, "note", "") or "")
        for entry in getattr(job, "cost_entries", []) or ()
    ]


def job_has_proof_replay(job: Any) -> bool:
    return PROOF_REPLAY_NOTE in _job_notes(job)


def job_billing_kind(job: Any, provider: str) -> str:
    notes = _job_notes(job)
    if PROOF_REPLAY_NOTE in notes:
        return "proof"
    if any(note.startswith("heygen") for note in notes) or provider == "heygen_api":
        return "heygen"
    return "gpu"


def actual_job_cost_usd(
    *,
    estimated_usd: float,
    elapsed_seconds: float,
    provider: str,
    gpu_hourly_rate_usd: float,
    in_process_local_proof: bool = False,
    stored_as_proof_replay: bool = False,
    heygen_rate_usd_per_minute: float = 4.0,
    billable_seconds: float | None = None,
) -> tuple[float, str]:
    if provider == "heygen_api":
        if billable_seconds is not None:
            return heygen_avatar_iv_cost(billable_seconds, heygen_rate_usd_per_minute), HEYGEN_ACTUAL_NOTE
        return round(float(estimated_usd), 4), HEYGEN_ACTUAL_NOTE
    if stored_as_proof_replay or (provider == "local_musetalk" and in_process_local_proof):
        return 0.0, PROOF_REPLAY_NOTE
    return (
        round((max(0.0, elapsed_seconds) / 3600.0) * gpu_hourly_rate_usd, 4),
        GPU_ACTUAL_NOTE,
    )


def build_cost_ledger(
    jobs: Iterable[Any],
    *,
    gpu_hourly_rate_usd: float,
    provider: str = "heygen_api",
    heygen_rate_usd_per_minute: float = 4.0,
    heygen_engine: str = "avatar_iv",
) -> dict[str, Any]:
    by_project: dict[str, dict[str, Any]] = {}
    estimated = 0.0
    actual = 0.0
    completed = 0
    failed = 0
    proof_count = 0
    gpu_count = 0
    gpu_estimated = 0.0
    gpu_actual = 0.0
    heygen_count = 0
    heygen_estimated = 0.0
    heygen_actual = 0.0
    job_list = list(jobs)
    for job in job_list:
        job_estimated = float(getattr(job, "estimated_cost_usd", 0.0) or 0.0)
        recorded = getattr(job, "actual_cost_usd", None)
        job_actual = float(recorded or 0.0)
        estimated += job_estimated
        actual += job_actual
        state = getattr(job, "state", None)
        state_value = getattr(state, "value", state)
        if state_value == "COMPLETED":
            completed += 1
        elif state_value == "FAILED":
            failed += 1
        kind = job_billing_kind(job, provider)
        if kind == "proof":
            proof_count += 1
        elif kind == "heygen":
            heygen_count += 1
            heygen_estimated += job_estimated
            heygen_actual += job_actual
        else:
            gpu_count += 1
            gpu_estimated += job_estimated
            gpu_actual += job_actual
        project_id = getattr(job, "project_id", "")
        summary = by_project.get(project_id)
        if summary is None:
            summary = {
                "project_id": project_id,
                "estimated_usd": 0.0,
                "actual_usd": 0.0,
                "job_count": 0,
            }
            by_project[project_id] = summary
        summary["estimated_usd"] = round(summary["estimated_usd"] + job_estimated, 4)
        summary["actual_usd"] = round(summary["actual_usd"] + job_actual, 4)
        summary["job_count"] += 1
    return {
        "estimated_usd": round(estimated, 4),
        "actual_usd": round(actual, 4),
        "job_count": len(job_list),
        "completed_count": completed,
        "failed_count": failed,
        "projects": sorted(by_project.values(), key=lambda item: item["project_id"]),
        "gpu_hourly_rate_usd": gpu_hourly_rate_usd,
        "heygen_rate_usd_per_minute": heygen_rate_usd_per_minute,
        "heygen_engine": heygen_engine,
        "billing_policy": cost_policy_for(provider),
        "proof_replay_job_count": proof_count,
        "gpu_job_count": gpu_count,
        "heygen_job_count": heygen_count,
        "heygen_estimated_usd": round(heygen_estimated, 4),
        "heygen_actual_usd": round(heygen_actual, 4),
        "proof_replay_usd": 0.0,
        "gpu_estimated_usd": round(gpu_estimated, 4),
        "gpu_actual_usd": round(gpu_actual, 4),
    }
