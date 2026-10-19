from pathlib import Path
import shutil
import pytest
from pipeline.director.timeline import plan_timeline
from pipeline.render.graph import render_mock_project

@pytest.mark.skipif(shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None, reason="FFmpeg required")
def test_short_mock_render(tmp_path: Path):
    scenes=plan_timeline("A. B. C. D. E. F.",6,0.30)
    manifest=render_mock_project(tmp_path,"short-proof","Test narration",scenes,6)
    assert manifest["qc"]["ok"] is True
    assert manifest["qc"]["width"]==1920
    assert manifest["qc"]["height"]==1080
    assert manifest["qc"]["audio_codec"]=="aac"
    assert Path(manifest["final"]).exists()
