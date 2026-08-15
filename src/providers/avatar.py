from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from src.providers.base import ProviderNotConfiguredError
from src.providers.common import asset_id, file_sha256
from src.schemas.assets import AssetKind, GeneratedAsset, Provenance
from src.schemas.requests import AvatarSourceRequest


class FileAvatarSourceProvider:
    """Resolves pre-authorized avatar images or clips from an operator-managed registry."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()

    async def resolve(self, request: AvatarSourceRequest) -> GeneratedAsset:
        if not request.avatar_id or any(
            character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
            for character in request.avatar_id
        ):
            raise ValueError("invalid avatar_id")
        candidates = [
            self.root / f"{request.avatar_id}{suffix}"
            for suffix in (".mp4", ".mov", ".mkv", ".png", ".jpg", ".jpeg", ".webp")
        ]
        source = next((candidate for candidate in candidates if candidate.is_file()), None)
        if source is None:
            raise ProviderNotConfiguredError(
                f"authorized avatar source was not found for {request.avatar_id}"
            )
        resolved = source.resolve()
        if not resolved.is_relative_to(self.root):
            raise ValueError("avatar path escapes the authorized registry")
        if source.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
            resolved = self._make_video(source, request)
        digest = file_sha256(resolved)
        return GeneratedAsset(
            asset_id=asset_id("avatar", digest),
            kind=AssetKind.AVATAR_SOURCE,
            uri=str(resolved),
            content_hash=digest,
            project_id=request.context.project_id,
            scene_id=request.context.scene_id,
            duration_seconds=request.duration_seconds,
            width=request.width,
            height=request.height,
            fps=request.fps,
            mime_type="video/mp4",
            provenance=Provenance(
                provider="authorized-file-avatar-registry",
                model_identifier="client-supplied-avatar",
                checkpoint_revision="content-hash",
                model_configuration={
                    "avatar_id": request.avatar_id,
                    "source_type": "image" if source != resolved else "video",
                },
            ),
        )

    @staticmethod
    def _make_video(source: Path, request: AvatarSourceRequest) -> Path:
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise RuntimeError("ffmpeg is required to prepare presenter images")
        output = Path(request.context.work_dir) / f"{request.context.scene_id}-avatar-source.mp4"
        output.parent.mkdir(parents=True, exist_ok=True)
        filtergraph = (
            f"scale={request.width}:{request.height}:force_original_aspect_ratio=decrease,"
            f"pad={request.width}:{request.height}:(ow-iw)/2:(oh-ih)/2:color=black,format=yuv420p"
        )
        subprocess.run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-loop",
                "1",
                "-framerate",
                str(request.fps),
                "-i",
                str(source),
                "-t",
                f"{request.duration_seconds:.6f}",
                "-vf",
                filtergraph,
                "-an",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                str(output),
            ],
            check=True,
            capture_output=True,
        )
        return output.resolve()
