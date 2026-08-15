from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from src.providers.base import ProviderError, ProviderNotConfiguredError
from src.providers.common import file_sha256
from src.providers.heygen import (
    HeyGenAvatarSourceProvider,
    HeyGenLipSyncGenerator,
    estimate_project_avatar_cost,
)
from src.rendering import MediaInfo
from src.schemas.assets import AssetKind, GeneratedAsset, Provenance
from src.schemas.requests import AvatarSourceRequest, GenerationContext, LipSyncRequest


def context(tmp_path: Path, *, scene_id: str = "presenter-01") -> GenerationContext:
    return GenerationContext(
        project_id="history-channel",
        scene_id=scene_id,
        request_id="request-01",
        job_id="job-01",
        work_dir=str(tmp_path / scene_id),
    )


def audio_asset(tmp_path: Path, ctx: GenerationContext, duration: float = 30.0) -> GeneratedAsset:
    audio = tmp_path / "narration.wav"
    audio.write_bytes(b"RIFF-fake-audio")
    digest = file_sha256(audio)
    return GeneratedAsset(
        asset_id="aud_test",
        kind=AssetKind.AUDIO,
        uri=str(audio),
        content_hash=digest,
        project_id=ctx.project_id,
        scene_id=ctx.scene_id,
        duration_seconds=duration,
        sample_rate=48000,
        mime_type="audio/wav",
        provenance=Provenance(
            provider="test-speech",
            model_identifier="test",
            checkpoint_revision="test",
        ),
    )


async def avatar_asset(tmp_path: Path, ctx: GenerationContext, duration: float = 30.0):
    return await HeyGenAvatarSourceProvider().resolve(
        AvatarSourceRequest(
            context=ctx,
            avatar_id="authorized_avatar_01",
            duration_seconds=duration,
            width=1920,
            height=1080,
            fps=30,
        )
    )


@pytest.mark.asyncio
async def test_heygen_generates_downloads_and_retains_mp4(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/v3/videos" and request.method == "POST":
            return httpx.Response(200, json={"data": {"video_id": "video-01"}})
        if request.url.path == "/v3/videos/video-01":
            return httpx.Response(
                200,
                json={
                    "data": {
                        "status": "completed",
                        "video_url": "https://files.heygen.test/video-01.mp4",
                    }
                },
            )
        if request.url.host == "files.heygen.test":
            return httpx.Response(200, content=b"fake-mp4")
        return httpx.Response(404)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    retention = SimpleNamespace(put_file=AsyncMock(return_value="s3://bucket/render.mp4"))
    ctx = context(tmp_path)
    avatar = await avatar_asset(tmp_path, ctx)
    request = LipSyncRequest(
        context=ctx,
        avatar=avatar,
        narration_text="A short native presenter test.",
        voice_id="authorized_voice_01",
        duration_seconds=30.0,
        fps=30,
    )
    media = MediaInfo(
        duration_seconds=30.0,
        width=1920,
        height=1080,
        fps=30.0,
        video_codec="h264",
        pixel_format="yuv420p",
        has_audio=True,
        audio_codec="aac",
        sample_rate=48000,
        channels=2,
        video_duration_seconds=30.0,
        audio_duration_seconds=30.0,
    )
    provider = HeyGenLipSyncGenerator(
        api_key="test-key",
        client=client,
        retention_store=retention,
        poll_interval_seconds=0.001,
        sleep=AsyncMock(),
    )
    with patch("src.providers.heygen.probe_media", return_value=media):
        result = await provider.generate(request)
    await client.aclose()

    assert result.kind == AssetKind.LIPSYNC_VIDEO
    assert result.provenance.provider == "heygen_api"
    assert result.provenance.model_configuration["retained_uri"] == "s3://bucket/render.mp4"
    assert Path(result.uri).read_bytes() == b"fake-mp4"
    create_request = next(
        item for item in requests if item.url.path == "/v3/videos" and item.method == "POST"
    )
    create_payload = json.loads(create_request.content)
    assert create_payload["script"] == "A short native presenter test."
    assert create_payload["voice_id"] == "authorized_voice_01"
    assert create_payload["avatar_id"] == "authorized_avatar_01"
    assert create_payload["type"] == "avatar"
    assert b"test-key" not in create_request.content
    assert all(item.url.path != "/v3/assets" for item in requests)
    retention.put_file.assert_awaited_once()


@pytest.mark.asyncio
async def test_heygen_requires_api_key_at_generate_time(tmp_path: Path) -> None:
    ctx = context(tmp_path)
    avatar = await avatar_asset(tmp_path, ctx)
    provider = HeyGenLipSyncGenerator(api_key="")
    with pytest.raises(ProviderNotConfiguredError, match="HEYGEN_API_KEY"):
        await provider.generate(
            LipSyncRequest(
                context=ctx,
                avatar=avatar,
                audio=None,
                narration_text="Hello",
                voice_id="provider_voice",
                duration_seconds=2.0,
                fps=30,
            )
        )
    await provider.client.aclose()


@pytest.mark.asyncio
async def test_heygen_rejects_job_before_api_when_cost_guard_is_exceeded(
    tmp_path: Path,
) -> None:
    ctx = context(tmp_path)
    avatar = await avatar_asset(tmp_path, ctx, duration=600.0)
    request = LipSyncRequest(
        context=ctx,
        avatar=avatar,
        audio=audio_asset(tmp_path, ctx, duration=600.0),
        duration_seconds=600.0,
        fps=30,
    )
    provider = HeyGenLipSyncGenerator(
        api_key="test-key",
        rate_usd_per_minute=4.0,
        maximum_cost_usd_per_job=25.0,
    )
    with pytest.raises(ProviderError, match="cost guard"):
        await provider.generate(request)
    await provider.client.aclose()


def test_project_cost_counts_only_presenter_formats() -> None:
    scenes = [
        SimpleNamespace(
            visual_format="PRESENTER",
            duration_seconds=120.0,
            narration_text="presenter",
        ),
        SimpleNamespace(
            visual_format="SPLIT",
            duration_seconds=60.0,
            narration_text="split",
        ),
        SimpleNamespace(
            visual_format="FULL_VISUAL",
            duration_seconds=600.0,
            narration_text="visual",
        ),
    ]
    assert estimate_project_avatar_cost(scenes, rate_usd_per_minute=4.0) == 12.0
