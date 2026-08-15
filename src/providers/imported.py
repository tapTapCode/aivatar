from __future__ import annotations

from src.providers.base import ProviderError
from src.providers.common import asset_id, file_sha256
from src.rendering import probe_media
from src.schemas.assets import AssetKind, GeneratedAsset, Provenance
from src.schemas.requests import LipSyncRequest


class ImportedPresenterVideoGenerator:
    """Uses an authorized presenter MP4 exactly as supplied, including its audio."""

    async def generate(self, request: LipSyncRequest) -> GeneratedAsset:
        media = probe_media(request.avatar.uri)
        if not media.has_audio:
            raise ProviderError("Imported presenter video must contain an audio track")
        if not media.width or not media.height or media.duration_seconds <= 0:
            raise ProviderError("Imported presenter video failed media validation")
        digest = file_sha256(request.avatar.uri)
        return GeneratedAsset(
            asset_id=asset_id("presenter", digest),
            kind=AssetKind.LIPSYNC_VIDEO,
            uri=request.avatar.uri,
            content_hash=digest,
            project_id=request.context.project_id,
            scene_id=request.context.scene_id,
            parent_asset_ids=(request.avatar.asset_id,),
            duration_seconds=media.duration_seconds,
            width=media.width,
            height=media.height,
            fps=media.fps,
            mime_type="video/mp4",
            provenance=Provenance(
                provider="authorized-import",
                model_identifier="client-supplied-presenter-video",
                checkpoint_revision="content-hash",
            ),
        )
