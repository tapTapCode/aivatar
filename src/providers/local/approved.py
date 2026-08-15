from __future__ import annotations

import shutil
import time
from pathlib import Path

from src.providers.common import asset_id, file_sha256
from src.rendering import probe_media
from src.rendering.ffmpeg import FFmpegRunner
from src.schemas.assets import AssetKind, GeneratedAsset, Provenance
from src.schemas.requests import LipSyncRequest

DEFAULT_AVATAR_ID = "presenter-01"


class ApprovedLocalLipSyncGenerator:
    """Serves the approved local MuseTalk take, or the uploaded talking-head, in-process."""

    def __init__(
        self,
        proof_path: str | Path,
        *,
        default_avatar_ids: frozenset[str] | None = None,
    ) -> None:
        self.proof_path = Path(proof_path)
        self.default_avatar_ids = default_avatar_ids or frozenset({DEFAULT_AVATAR_ID})

    async def generate(self, request: LipSyncRequest) -> GeneratedAsset:
        started = time.perf_counter()
        avatar_id = str(
            (request.avatar.provenance.model_configuration or {}).get("avatar_id") or ""
        )
        source, provider, warning = self._select_source(request, avatar_id)
        output = Path(request.context.work_dir) / f"{request.context.scene_id}-lipsync.mp4"
        output.parent.mkdir(parents=True, exist_ok=True)
        duration = request.duration_seconds
        if duration and duration > 0 and duration + 0.05 < (probe_media(str(source)).duration_seconds):
            self._trim(source, output, duration)
        else:
            shutil.copy2(source, output)
            media = probe_media(str(output))
            duration = media.duration_seconds or duration
        digest = file_sha256(output)
        media = probe_media(str(output))
        warnings = (warning,) if warning else ()
        return GeneratedAsset(
            asset_id=asset_id("lip", digest),
            kind=AssetKind.LIPSYNC_VIDEO,
            uri=str(output.resolve()),
            content_hash=digest,
            project_id=request.context.project_id,
            scene_id=request.context.scene_id,
            parent_asset_ids=(request.avatar.asset_id,)
            + ((request.audio.asset_id,) if request.audio is not None else ()),
            duration_seconds=media.duration_seconds or duration,
            width=media.width or request.avatar.width,
            height=media.height or request.avatar.height,
            fps=request.fps,
            mime_type="video/mp4",
            provenance=Provenance(
                provider=provider,
                model_identifier="local-musetalk-approved-proof"
                if provider == "local-musetalk-approved"
                else "client-supplied-presenter-video",
                checkpoint_revision="content-hash",
                model_configuration={"avatar_id": avatar_id, "source": source.name},
                generation_latency_seconds=time.perf_counter() - started,
                warnings=warnings,
            ),
        )

    def _select_source(
        self, request: LipSyncRequest, avatar_id: str
    ) -> tuple[Path, str, str | None]:
        avatar_path = Path(request.avatar.uri)
        media = probe_media(str(avatar_path))
        if media.has_audio and avatar_path.suffix.lower() in {".mp4", ".mov", ".webm", ".mkv"}:
            if self.proof_path.is_file() and avatar_path.resolve() == self.proof_path.resolve():
                return self.proof_path, "local-musetalk-approved", None
            if avatar_id in self.default_avatar_ids and self.proof_path.is_file():
                return self.proof_path, "local-musetalk-approved", None
            return avatar_path, "authorized-import", None
        if avatar_id in self.default_avatar_ids and self.proof_path.is_file():
            return self.proof_path, "local-musetalk-approved", None
        return (
            avatar_path,
            "local-still-fallback",
            "Still image used until GPU MuseTalk can match a new face.",
        )

    @staticmethod
    def _trim(source: Path, output: Path, duration: float) -> None:
        FFmpegRunner().run(
            [
                "-y",
                "-i",
                str(source),
                "-t",
                f"{duration:.6f}",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "18",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-movflags",
                "+faststart",
                str(output),
            ]
        )
