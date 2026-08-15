import pytest

from src.orchestration.cost import (
    COST_POLICY,
    HEYGEN_ACTUAL_NOTE,
    HEYGEN_COST_POLICY,
    CloudCostInputs,
    LocalCostInputs,
    actual_job_cost_usd,
    build_cost_ledger,
    cloud_generation_cost,
    estimate_control_plane_job,
    heygen_avatar_iv_cost,
    local_generation_cost,
)
from src.schemas.jobs import CostEntry, JobRecord, JobState, WatermarkStatus


def test_heygen_avatar_iv_uses_configured_per_minute_rate() -> None:
    assert heygen_avatar_iv_cost(60, 4.0) == 4.0
    assert heygen_avatar_iv_cost(30, 4.0) == 2.0
    assert heygen_avatar_iv_cost(60, 5.0) == 5.0
    actual, note = actual_job_cost_usd(
        estimated_usd=2.0,
        elapsed_seconds=1800,
        provider="heygen_api",
        gpu_hourly_rate_usd=0.22,
        heygen_rate_usd_per_minute=5.0,
        billable_seconds=30,
    )
    assert actual == 2.5
    assert note == HEYGEN_ACTUAL_NOTE


def test_cloud_cost_uses_billable_seconds_and_extras() -> None:
    result = cloud_generation_cost(
        CloudCostInputs(
            billable_gpu_seconds=1800,
            gpu_hourly_rate=2,
            storage_cost=0.1,
            retry_cost=0.2,
        )
    )
    assert result == pytest.approx(1.3)


def test_local_cost_includes_electricity_and_amortization() -> None:
    result = local_generation_cost(
        LocalCostInputs(
            gpu_seconds=3600,
            average_power_watts=500,
            electricity_per_kwh=0.2,
            hardware_cost=2000,
            amortization_hours=2000,
        )
    )
    assert result == pytest.approx(1.1)


def test_control_plane_estimates_gpu_and_heygen_costs() -> None:
    class Scene:
        def __init__(self, duration: float, visual_format: str = "PRESENTER") -> None:
            self.duration_seconds = duration
            self.visual_format = visual_format
            self.narration_text = "word " * 20

    gpu, gpu_note = estimate_control_plane_job(
        [Scene(3600)],
        provider="imported_video",
        heygen_rate_usd_per_minute=4.0,
        gpu_hourly_rate_usd=0.22,
    )
    assert gpu == pytest.approx(0.22)
    assert gpu_note == "gpu_estimate"
    heygen, heygen_note = estimate_control_plane_job(
        [Scene(60)],
        provider="heygen_api",
        heygen_rate_usd_per_minute=4.0,
        gpu_hourly_rate_usd=0.22,
    )
    assert heygen == pytest.approx(4.0)
    assert heygen_note == "heygen_estimate"
    actual, note = actual_job_cost_usd(
        estimated_usd=4.0,
        elapsed_seconds=1800,
        provider="imported_video",
        gpu_hourly_rate_usd=0.22,
    )
    assert actual == pytest.approx(0.11)
    assert note == "wall_clock_gpu_rate"
    replay, replay_note = estimate_control_plane_job(
        [Scene(3600)],
        provider="local_musetalk",
        heygen_rate_usd_per_minute=4.0,
        gpu_hourly_rate_usd=0.22,
        in_process_local_proof=True,
    )
    assert replay == 0.0
    assert replay_note == "local_proof_replay"
    actual_replay, actual_replay_note = actual_job_cost_usd(
        estimated_usd=0.22,
        elapsed_seconds=1800,
        provider="local_musetalk",
        gpu_hourly_rate_usd=0.22,
        in_process_local_proof=True,
    )
    assert actual_replay == 0.0
    assert actual_replay_note == "local_proof_replay"
    gpu_local, gpu_local_note = estimate_control_plane_job(
        [Scene(3600)],
        provider="local_musetalk",
        heygen_rate_usd_per_minute=4.0,
        gpu_hourly_rate_usd=0.22,
        in_process_local_proof=False,
    )
    assert gpu_local == pytest.approx(0.22)
    assert gpu_local_note == "gpu_estimate"
    locked_replay, locked_note = actual_job_cost_usd(
        estimated_usd=0.0,
        elapsed_seconds=1800,
        provider="local_musetalk",
        gpu_hourly_rate_usd=0.22,
        in_process_local_proof=False,
        stored_as_proof_replay=True,
    )
    assert locked_replay == 0.0
    assert locked_note == "local_proof_replay"


def test_cost_ledger_splits_proof_replay_from_gpu() -> None:
    proof = JobRecord(
        job_id="job_proof",
        video_id="vid_proof",
        project_id="proj_proof",
        owner_id="owner",
        idempotency_key="idem-proof",
        request_fingerprint="fp-proof",
        watermark_status=WatermarkStatus.CLEAN_AUTHORIZED,
        state=JobState.COMPLETED,
        estimated_cost_usd=0.0,
        actual_cost_usd=0.0,
        cost_entries=[CostEntry(stage="preflight", amount_usd=0.0, note="local_proof_replay")],
    )
    gpu = JobRecord(
        job_id="job_gpu",
        video_id="vid_gpu",
        project_id="proj_gpu",
        owner_id="owner",
        idempotency_key="idem-gpu",
        request_fingerprint="fp-gpu",
        watermark_status=WatermarkStatus.CLEAN_AUTHORIZED,
        state=JobState.COMPLETED,
        estimated_cost_usd=0.22,
        actual_cost_usd=0.11,
        cost_entries=[CostEntry(stage="preflight", amount_usd=0.22, note="gpu_estimate")],
    )
    ledger = build_cost_ledger(
        [proof, gpu], gpu_hourly_rate_usd=0.22, provider="local_musetalk"
    )
    assert ledger["billing_policy"] == COST_POLICY
    assert ledger["gpu_hourly_rate_usd"] == 0.22
    assert ledger["proof_replay_job_count"] == 1
    assert ledger["gpu_job_count"] == 1
    assert ledger["proof_replay_usd"] == 0.0
    assert ledger["gpu_estimated_usd"] == pytest.approx(0.22)
    assert ledger["gpu_actual_usd"] == pytest.approx(0.11)
    assert ledger["estimated_usd"] == pytest.approx(0.22)
    assert ledger["actual_usd"] == pytest.approx(0.11)
    heygen_job = gpu.model_copy(
        update={
            "job_id": "job_heygen",
            "video_id": "vid_heygen",
            "project_id": "proj_heygen",
            "estimated_cost_usd": 4.0,
            "actual_cost_usd": 4.0,
            "cost_entries": [CostEntry(stage="preflight", amount_usd=4.0, note="heygen_estimate")],
        }
    )
    heygen_ledger = build_cost_ledger(
        [heygen_job],
        gpu_hourly_rate_usd=0.22,
        provider="heygen_api",
        heygen_rate_usd_per_minute=4.0,
        heygen_engine="avatar_iv",
    )
    assert heygen_ledger["billing_policy"] == HEYGEN_COST_POLICY
    assert heygen_ledger["heygen_rate_usd_per_minute"] == 4.0
    assert heygen_ledger["heygen_engine"] == "avatar_iv"
    assert heygen_ledger["heygen_job_count"] == 1
    assert heygen_ledger["heygen_estimated_usd"] == pytest.approx(4.0)
    assert heygen_ledger["heygen_actual_usd"] == pytest.approx(4.0)
    assert heygen_ledger["gpu_job_count"] == 0
