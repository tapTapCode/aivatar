from dataclasses import dataclass, asdict
from pipeline.core.enums import SceneType

@dataclass(slots=True)
class PlannedScene:
    ordinal: int
    start: float
    end: float
    type: str
    visual_prompt: str
    motion: str = "static"

    @property
    def duration(self) -> float:
        return self.end - self.start

MOTIONS = ["slow_push_in", "pan_right", "subtle_zoom", "pan_left", "slow_pull_out", "static"]

def plan_timeline(script: str, duration: float, presenter_target: float = 0.30, scene_count: int = 6) -> list[PlannedScene]:
    if duration <= 0 or scene_count < 1:
        raise ValueError("duration and scene_count must be positive")
    presenter_seconds = duration * presenter_target
    # Deterministic editorial pattern: hook presenter, visual, split presenter, then visual-heavy close.
    weights = [0.1333333333, 0.20, 0.1666666667, 0.20, 0.15, 0.15]
    if scene_count != 6:
        weights = [1.0 / scene_count] * scene_count
    boundaries = [0.0]
    for i, weight in enumerate(weights[:-1]):
        boundaries.append(boundaries[-1] + duration * weight)
    boundaries.append(duration)
    types = [SceneType.PRESENTER, SceneType.FULL_VISUAL, SceneType.SPLIT, SceneType.FULL_VISUAL, SceneType.FULL_VISUAL, SceneType.FULL_VISUAL]
    if scene_count != 6:
        types = [SceneType.FULL_VISUAL] * scene_count
        remaining = presenter_seconds
        for i in range(scene_count):
            d = boundaries[i+1] - boundaries[i]
            if remaining > 0:
                types[i] = SceneType.PRESENTER
                remaining -= d
    snippets = [s.strip() for s in script.replace("\n", " ").split(".") if s.strip()]
    scenes: list[PlannedScene] = []
    for i in range(scene_count):
        prompt = snippets[i % len(snippets)] if snippets else f"Documentary visual for scene {i+1}"
        scenes.append(PlannedScene(i + 1, round(boundaries[i], 3), round(boundaries[i+1], 3), str(types[i]), prompt, MOTIONS[i % len(MOTIONS)]))
    validate_timeline(scenes, duration)
    return scenes

def presenter_percentage(scenes: list[PlannedScene]) -> float:
    total = sum(s.duration for s in scenes)
    presenter = sum(s.duration for s in scenes if s.type in {SceneType.PRESENTER, SceneType.SPLIT, SceneType.PIP})
    return presenter / total if total else 0.0

def validate_timeline(scenes: list[PlannedScene], expected_duration: float, tolerance: float = 0.02) -> None:
    if not scenes:
        raise ValueError("Timeline has no scenes")
    if abs(scenes[0].start) > tolerance:
        raise ValueError("Timeline does not start at zero")
    previous_end = 0.0
    for scene in scenes:
        if scene.end <= scene.start:
            raise ValueError(f"Invalid duration for scene {scene.ordinal}")
        if abs(scene.start - previous_end) > tolerance:
            relation = "gap" if scene.start > previous_end else "overlap"
            raise ValueError(f"Timeline {relation} before scene {scene.ordinal}")
        previous_end = scene.end
    if abs(previous_end - expected_duration) > tolerance:
        raise ValueError("Timeline does not cover expected narration duration")

def serialize_timeline(scenes: list[PlannedScene], duration: float) -> dict:
    return {"duration": duration, "scenes": [asdict(s) for s in scenes]}
