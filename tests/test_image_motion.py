from pathlib import Path
import shutil
import pytest
from pipeline.render.ffmpeg import run, ffprobe
from pipeline.render.graph import render_still_with_motion


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="FFmpeg required")
def test_still_motion_renders_duration_correct_video(tmp_path: Path):
    image = tmp_path / "image.png"
    run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=navy:s=640x360", "-frames:v", "1", str(image)])
    out = tmp_path / "motion.mp4"
    render_still_with_motion(image, out, 1.0, "pan_right", 640, 360, 15)
    data = ffprobe(out)
    assert out.exists()
    assert abs(float(data["format"]["duration"]) - 1.0) < 0.2
