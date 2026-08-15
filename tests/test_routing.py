from src.orchestration.routing import plan_scene
from src.schemas.scene import VisualFormat
from tests.conftest import make_scene


def test_presenter_plan_skips_visual_generation() -> None:
    plan = plan_scene(make_scene(VisualFormat.PRESENTER))
    assert plan.speech and plan.avatar_source and plan.lipsync
    assert not plan.visual and not plan.split_composite


def test_split_plan_requires_both_paths() -> None:
    plan = plan_scene(make_scene(VisualFormat.SPLIT))
    assert plan.speech and plan.avatar_source and plan.lipsync and plan.visual
    assert plan.split_composite


def test_full_visual_plan_skips_avatar_and_lipsync() -> None:
    plan = plan_scene(make_scene(VisualFormat.FULL_VISUAL))
    assert plan.speech and plan.visual and plan.full_visual_composite
    assert not plan.avatar_source and not plan.lipsync
