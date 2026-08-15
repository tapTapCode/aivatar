from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SplitLayout(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    orientation: Literal["horizontal", "vertical"] = "horizontal"
    avatar_side: Literal["left", "right", "top", "bottom"] = "left"
    avatar_ratio: float = Field(default=0.42, gt=0.1, lt=0.9)
    visual_ratio: float = Field(default=0.58, gt=0.1, lt=0.9)
    divider_width_px: int = Field(default=4, ge=0, le=100)
    divider_color: str = "#FFFFFF"
    safe_margin_px: int = Field(default=48, ge=0, le=500)
    avatar_crop: Literal["closeup", "medium_closeup", "medium"] = "medium_closeup"
    visual_fit: Literal["cover", "contain"] = "cover"

    @model_validator(mode="after")
    def validate_orientation_and_ratios(self) -> SplitLayout:
        if abs((self.avatar_ratio + self.visual_ratio) - 1.0) > 0.001:
            raise ValueError("avatar_ratio and visual_ratio must sum to 1.0")
        valid_sides = {"horizontal": {"left", "right"}, "vertical": {"top", "bottom"}}
        if self.avatar_side not in valid_sides[self.orientation]:
            raise ValueError("avatar_side is invalid for split orientation")
        return self


class CaptionStyle(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    enabled: bool = True
    font: str = "DejaVu Sans"
    size_px: int = Field(default=48, ge=12, le=200)
    color: str = "#FFFFFF"
    stroke_color: str = "#000000"
    stroke_width_px: int = Field(default=3, ge=0, le=20)
    bottom_margin_px: int = Field(default=72, ge=0, le=1000)
    max_chars_per_line: int = Field(default=42, ge=10, le=100)


class AudioStyle(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    target_lufs: float = Field(default=-16.0, ge=-30, le=-5)
    true_peak_db: float = Field(default=-1.5, ge=-9, le=0)
    background_music_lufs: float = Field(default=-28.0, ge=-50, le=-5)
    sample_rate: int = Field(default=48000, ge=8000, le=192000)


class ChannelTemplate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    template_version: str
    name: str
    width: int = Field(ge=320, le=7680)
    height: int = Field(ge=240, le=4320)
    fps: int = Field(ge=1, le=120)
    background_color: str = "#10131A"
    presenter_fit: Literal["cover", "contain"] = "cover"
    presenter_position: Literal["center", "left", "right"] = "center"
    split: SplitLayout
    captions: CaptionStyle
    audio: AudioStyle
    intro_uri: str | None = None
    outro_uri: str | None = None
    logo_uri: str | None = None
    logo_position: Literal["top_left", "top_right", "bottom_left", "bottom_right"] = "top_right"
    transitions: tuple[Literal["cut", "crossfade"], ...] = ("cut",)
    static_visual_motion: Literal["none", "slow_zoom", "slow_pan"] = "slow_zoom"
