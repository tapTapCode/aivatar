from pathlib import Path
from unittest.mock import patch

import pytest

from src.providers.imported import ImportedPresenterVideoGenerator
from src.rendering import MediaInfo
from src.schemas.assets import AssetKind, GeneratedAsset, Provenance
from src.schemas.requests import GenerationContext, LipSyncRequest


@pytest.mark.asyncio
async def test_imported_presenter_preserves_authorized_mp4(tmp_path: Path) -> None:
    source = tmp_path / "presenter.mp4"
    source.write_bytes(b"licensed-presenter-video")
    context = GenerationContext(
        project_id="project",
        scene_id="presenter",
        request_id="request",
        job_id="job",
        work_dir=str(tmp_path),
    )
    avatar = GeneratedAsset(
        asset_id="avatar_source",
        kind=AssetKind.AVATAR_SOURCE,
        uri=str(source),
        content_hash="a" * 64,
        project_id="project",
        scene_id="presenter",
        duration_seconds=10,
        width=1920,
        height=1080,
        fps=30,
        mime_type="video/mp4",
        provenance=Provenance(
            provider="registry", model_identifier="import", checkpoint_revision="hash"
        ),
    )
    media = MediaInfo(
        duration_seconds=10,
        width=1920,
        height=1080,
        fps=30,
        video_codec="h264",
        pixel_format="yuv420p",
        has_audio=True,
        audio_codec="aac",
        sample_rate=48000,
        channels=2,
        video_duration_seconds=10,
        audio_duration_seconds=10,
    )
    request = LipSyncRequest(
        context=context,
        avatar=avatar,
        narration_text="Matching transcript.",
        voice_id="embedded_voice",
        duration_seconds=10,
        fps=30,
    )
    with patch("src.providers.imported.probe_media", return_value=media):
        result = await ImportedPresenterVideoGenerator().generate(request)

    assert result.uri == str(source)
    assert result.kind == AssetKind.LIPSYNC_VIDEO
    assert result.duration_seconds == 10
    assert result.parent_asset_ids == ("avatar_source",)
