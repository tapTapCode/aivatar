from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable

from pipeline.director.timeline import PlannedScene

MOTION_TERMS = {
    "running", "walking", "driving", "flying", "explosion", "water", "waves", "crowd", "traffic",
    "moving", "movement", "spinning", "rotating", "falling", "pouring", "smoke", "fire", "storm",
    "dance", "dancing", "chase", "tracking", "camera", "orbit", "timelapse", "time-lapse", "action",
}
STATIC_TERMS = {"document", "chart", "diagram", "portrait", "map", "quote", "headline", "photo", "archive"}


@dataclass(slots=True)
class CostModel:
    # Historical Aivatar proof estimates. These are planning estimates only and must be replaced by
    # measured CostEntry data as production observations accumulate.
    flux_image_usd: float = 0.04
    ltx_video_usd_per_second: float = 0.034
    ffmpeg_motion_usd: float = 0.0
    cache_hit_usd: float = 0.0


@dataclass(slots=True)
class VisualDecision:
    scene_ordinal: int
    strategy: str
    motion_score: float
    estimated_cost_usd: float
    reason: str
    cache_key: str | None = None
    template: str | None = None

    def as_dict(self) -> dict:
        return asdict(self)


def motion_score(prompt: str, duration: float) -> float:
    words = {w.strip(".,:;!?()[]{}\"'").lower() for w in prompt.split()}
    dynamic = len(words & MOTION_TERMS)
    static = len(words & STATIC_TERMS)
    score = 0.18 + min(0.62, dynamic * 0.18)
    if duration <= 8:
        score += 0.08
    elif duration > 14:
        score -= 0.08
    score -= min(0.22, static * 0.11)
    return max(0.0, min(1.0, round(score, 3)))


def _graphic_template(prompt: str) -> str | None:
    text = prompt.lower()
    if any(token in text for token in ("title", "section", "chapter", "opening")):
        return "section_header"
    if any(token in text for token in ("statistic", "number", "cost", "percent", "%")):
        return "callout"
    if any(token in text for token in ("quote", "keyword", "important", "key point")):
        return "keyword_highlight"
    return None


def choose_visual_strategies(
    scenes: Iterable[PlannedScene],
    *,
    total_budget_usd: float,
    visual_budget_fraction: float = 0.60,
    max_ltx_scenes: int = 3,
    ltx_threshold: float = 0.64,
    max_ltx_scene_seconds: float = 12.0,
    cached_scene_ordinals: set[int] | None = None,
    cost_model: CostModel | None = None,
) -> list[VisualDecision]:
    model = cost_model or CostModel()
    visual_budget = max(0.0, total_budget_usd * visual_budget_fraction)
    spent = 0.0
    ltx_count = 0
    cached = cached_scene_ordinals or set()
    decisions: list[VisualDecision] = []

    for scene in scenes:
        if scene.type == "PRESENTER":
            decisions.append(VisualDecision(scene.ordinal, "presenter_only", 0.0, 0.0, "Presenter fills the frame"))
            continue
        if scene.ordinal in cached:
            decisions.append(VisualDecision(scene.ordinal, "cache", 0.0, model.cache_hit_usd, "Matching reusable asset already exists"))
            continue

        template = _graphic_template(scene.visual_prompt)
        score = motion_score(scene.visual_prompt, scene.duration)
        ltx_estimate = round(scene.duration * model.ltx_video_usd_per_second, 4)
        can_afford_ltx = spent + ltx_estimate <= visual_budget
        eligible_ltx = (
            score >= ltx_threshold
            and scene.duration <= max_ltx_scene_seconds
            and ltx_count < max_ltx_scenes
            and can_afford_ltx
        )

        if template and score < ltx_threshold:
            cost = round(model.flux_image_usd, 4)
            decisions.append(
                VisualDecision(scene.ordinal, "motion_graphic", score, cost, "Template-driven graphic is cheaper and clearer", template=template)
            )
            spent += cost
        elif eligible_ltx:
            decisions.append(
                VisualDecision(scene.ordinal, "ltx_video", score, ltx_estimate, "High motion value and scene fits the visual budget")
            )
            spent += ltx_estimate
            ltx_count += 1
        else:
            cost = round(model.flux_image_usd + model.ffmpeg_motion_usd, 4)
            reason = "FLUX still plus FFmpeg motion is the lower-cost default"
            if score >= ltx_threshold and not can_afford_ltx:
                reason = "LTX would exceed the allocated visual budget"
            elif score >= ltx_threshold and scene.duration > max_ltx_scene_seconds:
                reason = "Scene is too long for selective LTX policy; use still motion or split into shots"
            decisions.append(VisualDecision(scene.ordinal, "flux_motion", score, cost, reason, template=template))
            spent += cost

    return decisions


def strategy_summary(decisions: Iterable[VisualDecision]) -> dict:
    rows = list(decisions)
    counts: dict[str, int] = {}
    for row in rows:
        counts[row.strategy] = counts.get(row.strategy, 0) + 1
    return {
        "estimated_visual_cost_usd": round(sum(row.estimated_cost_usd for row in rows), 4),
        "counts": counts,
        "ltx_scenes": [row.scene_ordinal for row in rows if row.strategy == "ltx_video"],
        "cache_hits": [row.scene_ordinal for row in rows if row.strategy == "cache"],
    }
