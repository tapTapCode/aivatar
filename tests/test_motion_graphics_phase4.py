from pathlib import Path
import shutil

import pytest

from pipeline.motion_graphics.templates import MotionGraphicSpec, apply_motion_graphic
from pipeline.providers.mock import MockVideoProvider
from pipeline.render.ffmpeg import ffprobe


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="FFmpeg required")
def test_template_motion_graphic_renders_silent_1080p(tmp_path: Path):
    source = MockVideoProvider().generate("background", 2.0, tmp_path / "src").path
    output = apply_motion_graphic(
        source,
        tmp_path / "graphic.mp4",
        2.0,
        MotionGraphicSpec("lower_third", "Key finding", "Template-driven and cheap", start=0.1, hold=1.5),
        preset="ultrafast",
    )
    data = ffprobe(output)
    video = next(s for s in data["streams"] if s["codec_type"] == "video")
    assert (video["width"], video["height"]) == (1920, 1080)
    assert not any(s["codec_type"] == "audio" for s in data["streams"])
