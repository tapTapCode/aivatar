from pathlib import Path
import shutil

import pytest

from scripts.render_phase4_mock_project import render


@pytest.mark.skipif(shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None, reason="FFmpeg required")
def test_phase4_short_proof_exercises_cache_ltx_and_graphics(tmp_path: Path):
    manifest = render(tmp_path, duration=6.0, project_id="phase4-short")
    assert manifest["qc"]["ok"] is True
    assert manifest["presenter_percentage"] == pytest.approx(0.30)
    assert manifest["visual_strategy"]["counts"]["ltx_video"] >= 1
    assert manifest["visual_strategy"]["counts"]["cache"] == 1
    assert any(asset["template"] for asset in manifest["assets"])
    assert any(asset["cache_hit"] for asset in manifest["assets"])
    assert Path(manifest["final"]).exists()
