from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from src.schemas.jobs import WatermarkStatus
from src.schemas.scene import ProjectScript, Scene, VisualFormat


class ProviderCapabilityTier(StrEnum):
    IMPORTED_FREE = "IMPORTED_FREE"
    HEYGEN_API = "HEYGEN_API"
    LOCAL_MUSE_TALK = "LOCAL_MUSE_TALK"


PROVIDER_CAPABILITIES = {
    "imported_video": ProviderCapabilityTier.IMPORTED_FREE,
    "heygen_api": ProviderCapabilityTier.HEYGEN_API,
    "local_musetalk": ProviderCapabilityTier.LOCAL_MUSE_TALK,
}


class UnlicensedWatermarkException(ValueError):
    error = "UNLICENSED_WATERMARK_REJECTION"
    message = (
        "Cannot satisfy clean export request with watermarked free source media. "
        "Please select an authorized provider (HeyGen API or local GPU)."
    )


def validate_provider_routing(job_config: ProjectScript, selected_provider: str) -> WatermarkStatus:
    """Validate export rights before queueing any render work."""

    try:
        capability = PROVIDER_CAPABILITIES[selected_provider]
    except KeyError as exc:
        raise ValueError(f"unsupported avatar video provider: {selected_provider}") from exc
    if job_config.require_clean_export and capability == ProviderCapabilityTier.IMPORTED_FREE:
        raise UnlicensedWatermarkException
    if capability == ProviderCapabilityTier.IMPORTED_FREE:
        return WatermarkStatus.PRESERVED
    return WatermarkStatus.CLEAN_AUTHORIZED


class SceneGenerationPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    speech: bool
    avatar_source: bool
    lipsync: bool
    visual: bool
    split_composite: bool
    full_visual_composite: bool


PLANS = {
    VisualFormat.PRESENTER: SceneGenerationPlan(
        speech=True,
        avatar_source=True,
        lipsync=True,
        visual=False,
        split_composite=False,
        full_visual_composite=False,
    ),
    VisualFormat.SPLIT: SceneGenerationPlan(
        speech=True,
        avatar_source=True,
        lipsync=True,
        visual=True,
        split_composite=True,
        full_visual_composite=False,
    ),
    VisualFormat.FULL_VISUAL: SceneGenerationPlan(
        speech=True,
        avatar_source=False,
        lipsync=False,
        visual=True,
        split_composite=False,
        full_visual_composite=True,
    ),
}


def plan_scene(scene: Scene) -> SceneGenerationPlan:
    return PLANS[scene.visual_format]
