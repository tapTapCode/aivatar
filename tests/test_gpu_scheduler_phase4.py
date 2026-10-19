import pytest

from pipeline.gpu.scheduler import GpuProfile, choose_gpu


def test_scheduler_uses_cheapest_configured_sufficient_profile():
    profiles = [
        GpuProfile("big-expensive", 80, 2.0, frozenset({"video"}), "ep-big"),
        GpuProfile("enough-cheap", 64, 1.2, frozenset({"video"}), "ep-cheap"),
        GpuProfile("too-small", 24, 0.5, frozenset({"video"}), "ep-small"),
    ]
    selection = choose_gpu(profiles, workload="video", min_vram_gb=48, estimated_seconds=300)
    assert selection.profile.name == "enough-cheap"
    assert selection.estimated_cost_usd == pytest.approx(0.1)


def test_scheduler_refuses_unsupported_workload():
    with pytest.raises(RuntimeError):
        choose_gpu([GpuProfile("image-only", 80, 1.0, frozenset({"image"}), "ep")], workload="video", min_vram_gb=48, estimated_seconds=1)
