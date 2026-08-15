from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

NonEmpty = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Identifier = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$",
    ),
]


class VisualFormat(StrEnum):
    PRESENTER = "PRESENTER"
    SPLIT = "SPLIT"
    FULL_VISUAL = "FULL_VISUAL"


class Transition(StrEnum):
    CUT = "cut"
    CROSSFADE = "crossfade"


class OutputSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    width: int = Field(default=1920, ge=320, le=7680)
    height: int = Field(default=1080, ge=240, le=4320)
    fps: int = Field(default=30, ge=1, le=120)
    aspect_ratio: Literal["16:9", "9:16", "1:1", "4:3", "4:5"] = "16:9"
    video_codec: Literal["h264", "hevc"] = "h264"
    audio_codec: Literal["aac", "opus"] = "aac"

    @model_validator(mode="after")
    def check_aspect_ratio(self) -> OutputSpec:
        expected = {
            "16:9": 16 / 9,
            "9:16": 9 / 16,
            "1:1": 1.0,
            "4:3": 4 / 3,
            "4:5": 4 / 5,
        }[self.aspect_ratio]
        if abs((self.width / self.height) - expected) > 0.03:
            raise ValueError("width and height do not match aspect_ratio")
        if self.width % 2 or self.height % 2:
            raise ValueError("encoded width and height must be even")
        return self


class ConsentRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    subject_id: Identifier
    permission_type: Literal["avatar", "voice"]
    granted_by: NonEmpty
    granted_at: datetime
    evidence_uri: NonEmpty

    @model_validator(mode="after")
    def require_timezone(self) -> ConsentRecord:
        if self.granted_at.tzinfo is None or self.granted_at.utcoffset() is None:
            raise ValueError("granted_at must include a timezone")
        return self


class Scene(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    scene_id: Identifier
    order: int = Field(ge=1)
    visual_format: VisualFormat
    narration_text: NonEmpty
    visual_description: str | None = None
    avatar_id: str | None = None
    voice_id: NonEmpty
    duration_seconds: float | None = Field(default=None, gt=0, le=3600)
    layout_preset: NonEmpty = "default"
    transition_out: Transition = Transition.CUT
    visual_provider: Literal["image", "video", "retrieval"] = "image"

    @model_validator(mode="after")
    def validate_format_contract(self) -> Scene:
        description = (self.visual_description or "").strip()
        avatar = (self.avatar_id or "").strip()
        if self.visual_format == VisualFormat.PRESENTER:
            if description:
                raise ValueError("visual_description is prohibited for PRESENTER")
            if not avatar:
                raise ValueError("avatar_id is required for PRESENTER")
        elif self.visual_format == VisualFormat.SPLIT:
            if not description:
                raise ValueError("visual_description is required for SPLIT")
            if not avatar:
                raise ValueError("avatar_id is required for SPLIT")
        elif self.visual_format == VisualFormat.FULL_VISUAL:
            if not description:
                raise ValueError("visual_description is required for FULL_VISUAL")
            if avatar:
                raise ValueError("avatar_id is prohibited for FULL_VISUAL")
        return self


class ProjectScript(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    project_id: Identifier
    schema_version: Literal["1.0"]
    channel_template: NonEmpty = "default"
    require_clean_export: bool = Field(
        default=False,
        description="Enforces output generation strictly from authorized unwatermarked providers.",
    )
    approval_state: Literal["draft", "approved"] = "draft"
    output: OutputSpec
    scenes: tuple[Scene, ...] = Field(min_length=1, max_length=1000)
    consent_records: tuple[ConsentRecord, ...] = ()

    @model_validator(mode="after")
    def deterministic_unique_scenes(self) -> ProjectScript:
        ids = [scene.scene_id for scene in self.scenes]
        orders = [scene.order for scene in self.scenes]
        if len(ids) != len(set(ids)):
            raise ValueError("scene_id values must be unique")
        if len(orders) != len(set(orders)):
            raise ValueError("scene order values must be unique")
        ordered = tuple(sorted(self.scenes, key=lambda scene: (scene.order, scene.scene_id)))
        if ordered != self.scenes:
            object.__setattr__(self, "scenes", ordered)
        return self
