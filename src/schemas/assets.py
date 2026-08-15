from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AssetKind(StrEnum):
    AUDIO = "audio"
    AVATAR_SOURCE = "avatar_source"
    LIPSYNC_VIDEO = "lipsync_video"
    IMAGE = "image"
    VIDEO = "video"
    SCENE_VIDEO = "scene_video"
    FINAL_VIDEO = "final_video"
    CAPTIONS = "captions"


class Provenance(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: str
    model_identifier: str
    checkpoint_revision: str
    model_configuration: dict[str, Any] = Field(default_factory=dict)
    seed: int | None = None
    prompt: str | None = None
    negative_prompt: str | None = None
    generation_latency_seconds: float = 0
    preprocessing_latency_seconds: float = 0
    postprocessing_latency_seconds: float = 0
    peak_allocated_vram_bytes: int | None = None
    peak_reserved_vram_bytes: int | None = None
    driver_peak_vram_bytes: int | None = None
    retry_count: int = 0
    warnings: tuple[str, ...] = ()


class GeneratedAsset(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    asset_id: str
    kind: AssetKind
    uri: str
    content_hash: str
    project_id: str
    scene_id: str | None = None
    parent_asset_ids: tuple[str, ...] = ()
    duration_seconds: float | None = None
    width: int | None = None
    height: int | None = None
    fps: float | None = None
    sample_rate: int | None = None
    mime_type: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    provenance: Provenance


class PublicAsset(BaseModel):
    """Customer-safe metadata; internal providers and storage paths stay private."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    asset_id: str
    kind: AssetKind
    project_id: str
    scene_id: str | None = None
    duration_seconds: float | None = None
    width: int | None = None
    height: int | None = None
    fps: float | None = None
    sample_rate: int | None = None
    mime_type: str
    created_at: datetime
    retained: bool = False

    @classmethod
    def from_internal(cls, asset: GeneratedAsset, *, retained: bool = False) -> PublicAsset:
        return cls(
            asset_id=asset.asset_id,
            kind=asset.kind,
            project_id=asset.project_id,
            scene_id=asset.scene_id,
            duration_seconds=asset.duration_seconds,
            width=asset.width,
            height=asset.height,
            fps=asset.fps,
            sample_rate=asset.sample_rate,
            mime_type=asset.mime_type,
            created_at=asset.created_at,
            retained=retained,
        )
