from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from src.api.media_registry import AuthorizedMediaRegistry


@pytest.mark.media
@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg is required")
@pytest.mark.asyncio
async def test_registry_validates_and_scopes_presenter_media(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    subprocess.run(
        [
            shutil.which("ffmpeg") or "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=64x64",
            "-frames:v",
            "1",
            str(source),
        ],
        check=True,
    )
    registry = AuthorizedMediaRegistry(tmp_path / "registry", max_bytes=2_000_000)
    record = await registry.register(
        owner_id="owner-a",
        kind="presenter",
        filename="portrait.png",
        content_type="image/png",
        payload=source.read_bytes(),
    )
    assert record.original_filename == "portrait.png"
    assert await registry.path_for(record.media_id, owner_id="owner-a")
    assert await registry.path_for(record.media_id, owner_id="owner-b") is None
    stored = await registry.get(record.media_id, owner_id="owner-a")
    assert stored is not None
    assert stored[0].media_id == record.media_id
    assert await registry.delete(record.media_id, owner_id="owner-b") is False
    assert await registry.delete(record.media_id, owner_id="owner-a") is True
    assert await registry.get(record.media_id, owner_id="owner-a") is None


@pytest.mark.asyncio
async def test_registry_rejects_invalid_media(tmp_path: Path) -> None:
    registry = AuthorizedMediaRegistry(tmp_path / "registry", max_bytes=1024)
    with pytest.raises(ValueError, match="not valid"):
        await registry.register(
            owner_id="owner",
            kind="voice",
            filename="voice.wav",
            content_type="audio/wav",
            payload=b"not-a-wave",
        )


@pytest.mark.asyncio
async def test_registry_rejects_invalid_presenter_video_uploads(tmp_path: Path) -> None:
    registry = AuthorizedMediaRegistry(tmp_path / "registry", max_bytes=1024)
    with pytest.raises(ValueError, match="not valid"):
        await registry.register(
            owner_id="owner",
            kind="presenter",
            filename="presenter.mp4",
            content_type="video/mp4",
            payload=b"not-a-video",
        )


@pytest.mark.media
@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg is required")
@pytest.mark.asyncio
async def test_registry_accepts_presenter_video_with_audio(tmp_path: Path) -> None:
    source = tmp_path / "heygen-export.mp4"
    subprocess.run(
        [
            shutil.which("ffmpeg") or "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=64x64:d=1",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=1",
            "-shortest",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(source),
        ],
        check=True,
    )
    registry = AuthorizedMediaRegistry(tmp_path / "registry", max_bytes=2_000_000)
    record = await registry.register(
        owner_id="owner-a",
        kind="presenter",
        filename="heygen-export.mp4",
        content_type="video/mp4",
        payload=source.read_bytes(),
    )
    assert record.original_filename == "heygen-export.mp4"
    stored = await registry.get(record.media_id, owner_id="owner-a")
    assert stored is not None
    assert stored[1].suffix == ".mp4"


@pytest.mark.asyncio
async def test_registry_registers_heygen_avatar_id(tmp_path: Path) -> None:
    registry = AuthorizedMediaRegistry(tmp_path / "registry", max_bytes=1024)
    record = await registry.register_heygen_avatar(
        owner_id="owner-a",
        avatar_id="Angela-inblack-20220820",
        label="Channel A",
    )
    again = await registry.register_heygen_avatar(
        owner_id="owner-a",
        avatar_id="Angela-inblack-20220820",
        label="Ignored",
    )
    assert record.media_id == "Angela-inblack-20220820"
    assert record.original_filename == "Channel A"
    assert record.content_type == "application/json"
    assert again.media_id == record.media_id
    stored = await registry.get("Angela-inblack-20220820", owner_id="owner-a")
    assert stored is not None
    assert stored[1].suffix == ".json"


@pytest.mark.asyncio
async def test_registry_rejects_invalid_heygen_avatar_id(tmp_path: Path) -> None:
    registry = AuthorizedMediaRegistry(tmp_path / "registry", max_bytes=1024)
    with pytest.raises(ValueError, match="HeyGen avatar ID"):
        await registry.register_heygen_avatar(owner_id="owner", avatar_id="not a valid id")
