from pathlib import Path
import shutil

import pytest

from pipeline.director.timeline import PlannedScene, presenter_percentage
from pipeline.providers.mock import MockPresenterProvider, MockVideoProvider
from pipeline.providers.presenter import HeyGenClient, HiggsfieldClient, ManualPresenterImportProvider
from pipeline.render.composite import compose_pip, compose_split
from pipeline.render.ffmpeg import ffprobe, run


class FakeHeyGenClient(HeyGenClient):
    def __init__(self):
        super().__init__("test-key")
        self.requests = []

    def _json_request(self, method, path, **kwargs):
        self.requests.append((method, path, kwargs))
        if path == "/v3/videos":
            return {"data": {"id": "v3-id"}}
        if path == "/v2/video/generate":
            return {"data": {"video_id": "v2-id"}}
        raise AssertionError(path)


def test_heygen_v3_contract_uses_audio_asset_and_engine():
    client = FakeHeyGenClient()
    video_id = client.create_v3_video(
        avatar_id="avatar-1",
        audio_asset_id="asset-1",
        title="Scene",
        resolution="1080p",
        aspect_ratio="16:9",
        engine="avatar_iv",
    )
    assert video_id == "v3-id"
    payload = client.requests[0][2]["json"]
    assert payload["audio_asset_id"] == "asset-1"
    assert payload["engine"] == {"type": "avatar_iv"}
    assert payload["avatar_id"] == "avatar-1"


def test_heygen_legacy_contract_uses_audio_asset():
    client = FakeHeyGenClient()
    video_id = client.create_legacy_v2_video(
        avatar_id="avatar-legacy",
        audio_asset_id="asset-legacy",
        title="Scene",
        width=1920,
        height=1080,
    )
    assert video_id == "v2-id"
    payload = client.requests[0][2]["json"]
    assert payload["video_inputs"][0]["voice"] == {"type": "audio", "audio_asset_id": "asset-legacy"}
    assert payload["video_inputs"][0]["character"]["avatar_id"] == "avatar-legacy"


def test_higgsfield_submit_contract_uses_image_and_audio_urls():
    client = HiggsfieldClient("test-key")
    client._request = lambda method, url, **kwargs: {"request_id": "hf-1", "status_url": "https://api.higgsfield.ai/requests/hf-1/status"}
    result = client.submit("wan/v2.7/image-to-video", {"image_url": "https://image", "audio_url": "https://audio", "duration": 5})
    assert result["request_id"] == "hf-1"


def test_presenter_percentage_counts_pip():
    scenes = [
        PlannedScene(1, 0, 3, "PRESENTER", ""),
        PlannedScene(2, 3, 6, "SPLIT", ""),
        PlannedScene(3, 6, 9, "PIP", ""),
        PlannedScene(4, 9, 12, "FULL_VISUAL", ""),
    ]
    assert presenter_percentage(scenes) == pytest.approx(0.75)


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="FFmpeg required")
def test_split_and_pip_composition(tmp_path: Path):
    audio = tmp_path / "audio.wav"
    run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=220:duration=2", str(audio)])
    presenter = MockPresenterProvider().generate(audio, 2, tmp_path / "presenter").path
    visual = MockVideoProvider().generate("visual", 2, tmp_path / "visual").path
    split = compose_split(presenter, visual, tmp_path / "split.mp4", 2, presenter_side="right", presenter_ratio=0.35, corner_radius=24)
    pip = compose_pip(presenter, visual, tmp_path / "pip.mp4", 2, position="bottom_left", corner_radius=30)
    for path in [split, pip]:
        data = ffprobe(path)
        video = next(s for s in data["streams"] if s["codec_type"] == "video")
        assert video["width"] == 1920
        assert video["height"] == 1080
        assert not any(s["codec_type"] == "audio" for s in data["streams"])


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="FFmpeg required")
def test_manual_presenter_import_is_normalized_and_muted(tmp_path: Path):
    source = tmp_path / "source.mp4"
    audio = tmp_path / "segment.wav"
    run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=size=640x480:rate=25:duration=2", "-f", "lavfi", "-i", "sine=frequency=440:duration=2", "-shortest", "-c:v", "libx264", "-c:a", "aac", str(source)])
    run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=220:duration=1", str(audio)])
    result = ManualPresenterImportProvider().generate(audio, 1, tmp_path / "out", source_path=source, scene_id="one")
    data = ffprobe(result.path)
    assert any(s["codec_type"] == "video" for s in data["streams"])
    assert not any(s["codec_type"] == "audio" for s in data["streams"])
    assert result.duration == pytest.approx(1.0, abs=0.1)
