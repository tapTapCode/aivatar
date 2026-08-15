from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.schemas.scene import OutputSpec, ProjectScript, Scene, VisualFormat


def base_scene(**updates: object) -> dict[str, object]:
    scene: dict[str, object] = {
        "scene_id": "scene_1",
        "order": 1,
        "visual_format": "PRESENTER",
        "narration_text": "Valid narration",
        "avatar_id": "avatar_1",
        "voice_id": "voice_1",
    }
    scene.update(updates)
    return scene


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        ({"narration_text": ""}, "at least 1 character"),
        ({"visual_description": "should not exist"}, "prohibited for PRESENTER"),
        ({"avatar_id": None}, "required for PRESENTER"),
        ({"visual_format": "SPLIT", "visual_description": None}, "required for SPLIT"),
        (
            {"visual_format": "FULL_VISUAL", "visual_description": "Visual", "avatar_id": "avatar"},
            "prohibited for FULL_VISUAL",
        ),
    ],
)
def test_invalid_scene_combinations_fail(updates: dict[str, object], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        Scene.model_validate(base_scene(**updates))


def test_unknown_fields_are_rejected() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        Scene.model_validate(base_scene(secret_option=True))


def test_path_unsafe_identifiers_are_rejected() -> None:
    with pytest.raises(ValidationError, match="String should match pattern"):
        Scene.model_validate(base_scene(scene_id="../escape"))


def test_full_visual_requires_description_and_no_avatar() -> None:
    scene = Scene.model_validate(
        base_scene(
            visual_format=VisualFormat.FULL_VISUAL,
            visual_description="Ocean turbine",
            avatar_id=None,
        )
    )
    assert scene.visual_format == VisualFormat.FULL_VISUAL


def test_project_sorts_scenes_deterministically() -> None:
    second = Scene.model_validate(base_scene(scene_id="second", order=2))
    first = Scene.model_validate(base_scene(scene_id="first", order=1))
    project = ProjectScript(
        project_id="p1",
        schema_version="1.0",
        output=OutputSpec(width=640, height=360),
        scenes=(second, first),
    )
    assert [scene.scene_id for scene in project.scenes] == ["first", "second"]
    assert project.approval_state == "draft"


def test_project_rejects_duplicate_order() -> None:
    one = Scene.model_validate(base_scene(scene_id="one"))
    two = Scene.model_validate(base_scene(scene_id="two"))
    with pytest.raises(ValidationError, match="scene order values must be unique"):
        ProjectScript(
            project_id="p1",
            schema_version="1.0",
            output=OutputSpec(width=640, height=360),
            scenes=(one, two),
        )
