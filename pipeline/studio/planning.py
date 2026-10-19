"""Deterministic, inspectable planning. No paid calls and no script rewriting."""
import math
from pydantic import BaseModel, Field, ConfigDict, model_validator
from typing import Literal

class ProductionOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    channel_id: str
    avatar_id: str | None = None
    name: str = Field(min_length=1, max_length=220)
    script: str = Field(min_length=1, max_length=100000)
    words_per_minute: int = Field(default=145, ge=80, le=220)
    scene_seconds: int = Field(default=12, ge=5, le=15)
    presenter_target: float = Field(default=.30, ge=0, le=1)
    aspect_ratio: Literal["16:9", "9:16", "1:1", "4:5"] = "16:9"
    resolution: Literal["720p", "1080p"] = "1080p"
    budget_usd: float = Field(default=50, gt=0, le=1000)
    visual_style: str = Field(default="Cinematic documentary, natural lighting", max_length=1000)
    captions: bool = True
    caption_size: int = Field(default=22, ge=14, le=40)
    background_color: str = Field(default="#f4d2dc", pattern=r"^#[0-9a-fA-F]{6}$")
    music_path: str | None = None
    narration_path: str | None = None
    music_volume: float = Field(default=.12, ge=0, le=.4)
    music_strategy: Literal["off", "automatic", "uploaded"] = "off"
    music_mood: str = Field(default="calm documentary", min_length=2, max_length=120)
    transition_style: Literal["cut", "crossfade", "fade", "wipeleft", "slideright"] = "crossfade"
    scene_direction_mode: Literal["manual", "assisted"] = "assisted"
    mode: Literal["production", "demo"] = "production"

    @model_validator(mode="after")
    def validate_text(self):
        self.name = self.name.strip()
        self.script = self.script.strip()
        if not self.name or not self.script:
            raise ValueError("A title and non-empty script are required")
        if len(self.script.split()) / self.words_per_minute * 60 > 7200:
            raise ValueError("Split scripts longer than two hours into separate productions")
        if self.presenter_target > 0 and not self.avatar_id and self.mode != "demo":
            raise ValueError("Choose a character or set presenter coverage to zero")
        return self


def build_plan(options: ProductionOptions, duration: float | None = None) -> dict:
    words = options.script.split()
    duration = duration or max(2.0, len(words) / options.words_per_minute * 60)
    count = min(len(words), max(1, math.ceil(duration / options.scene_seconds)))
    presenter_count = min(count, max(0, round(count * options.presenter_target)))
    if options.presenter_target > 0:
        presenter_count = max(1, presenter_count)
    # Distribute presenter beats across the whole story instead of only its opening.
    presenter_indices = {round(i * (count - 1) / max(1, presenter_count - 1)) for i in range(presenter_count)}
    scenes = []
    for i in range(count):
        start_word, end_word = i * len(words) // count, (i + 1) * len(words) // count
        narration = " ".join(words[start_word:end_word])
        kind = "FULL_VISUAL"
        if i in presenter_indices:
            kind = "PRESENTER" if i == 0 or i == count - 1 else "SPLIT"
        scenes.append({
            "ordinal": i + 1, "start": round(start_word / len(words) * duration, 3),
            "end": round(end_word / len(words) * duration, 3), "type": kind,
            "narration": narration,
            "visual_prompt": f"{options.visual_style}. Illustrate: {narration}",
            "motion": ["slow_push_in", "pan_right", "slow_pull_out", "pan_left"][i % 4],
        })
    presenter_seconds = sum(s["end"] - s["start"] for s in scenes if s["type"] != "FULL_VISUAL")
    return {"duration": round(duration, 2), "word_count": len(words), "scenes": scenes,
            "presenter_seconds": round(presenter_seconds, 2),
            "timing_note": "Estimated at the selected speaking rate; timing is rebuilt from generated narration. Script is preserved."}

