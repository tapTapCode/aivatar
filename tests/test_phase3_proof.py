from pathlib import Path
import shutil

import pytest

from scripts.render_phase3_mock_project import render


@pytest.mark.skipif(shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None, reason="FFmpeg required")
def test_phase3_short_proof(tmp_path: Path):
    manifest = render(tmp_path, duration=6.0, project_id="phase3-short")
    assert manifest["qc"]["ok"] is True
    assert manifest["presenter_percentage"] == pytest.approx(0.30)
    assert {x["type"] for x in manifest["presenter_scenes"]} == {"PRESENTER", "SPLIT", "PIP"}
    assert Path(manifest["final"]).exists()
