from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.schemas.assets import GeneratedAsset
from src.schemas.scene import OutputSpec, Scene
from src.schemas.templates import ChannelTemplate


class GenerationContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    project_id: str
    scene_id: str
    request_id: str
    job_id: str
    work_dir: str


class SpeechGenerationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    context: GenerationContext
    text: str
    voice_id: str
    requested_duration_seconds: float | None = None
    sample_rate: int = 48000


class VisualGenerationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    context: GenerationContext
    prompt: str
    negative_prompt: str | None = None
    width: int
    height: int
    duration_seconds: float | None = None
    fps: int | None = None
    seed: int = Field(ge=0)


class AvatarSourceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    context: GenerationContext
    avatar_id: str
    duration_seconds: float
    width: int
    height: int
    fps: int


class LipSyncRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    context: GenerationContext
    avatar: GeneratedAsset
    audio: GeneratedAsset | None = None
    narration_text: str | None = None
    voice_id: str | None = None
    duration_seconds: float
    fps: int

    @model_validator(mode="after")
    def require_audio_or_native_voice(self) -> LipSyncRequest:
        if self.audio is None and not (
            (self.narration_text or "").strip() and (self.voice_id or "").strip()
        ):
            raise ValueError("lip sync requires audio or narration_text with voice_id")
        return self


class SceneRenderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    context: GenerationContext
    scene: Scene
    output: OutputSpec
    template: ChannelTemplate
    audio: GeneratedAsset
    avatar_video: GeneratedAsset | None = None
    visual: GeneratedAsset | None = None
    duration_seconds: float
    captions_uri: str | None = None
