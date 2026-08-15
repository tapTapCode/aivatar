from benchmarks.common import run_adapter


def test_benchmark_keeps_verified_cold_and_warm_phases_separate() -> None:
    phases: list[str] = []

    def adapter(phase: str, _: int) -> dict[str, object]:
        phases.append(phase)
        return {"container_restarted": phase == "cold_container"}

    results = run_adapter(
        "image",
        adapter,
        device="cuda:0",
        cold_runs=1,
        warmup_runs=1,
        measured_runs=1,
    )
    assert phases == ["cold_container", "warmup", "steady_state"]
    assert [result["phase"] for result in results] == [
        "cold_container",
        "warm_loaded_steady_state",
    ]
    assert all(result["status"] == "MEASURED" for result in results)


def test_unverified_cold_start_is_invalid() -> None:
    def adapter(_: str, __: int) -> dict[str, object]:
        return {}

    result = run_adapter(
        "image",
        adapter,
        device="cuda:0",
        cold_runs=1,
        warmup_runs=0,
        measured_runs=0,
    )[0]
    assert result["status"] == "INVALID"
