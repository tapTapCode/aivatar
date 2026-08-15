from __future__ import annotations

import os
from pathlib import Path

import pytest

from src.orchestration.templates import TemplateLoader
from src.schemas.scene import OutputSpec, Scene, VisualFormat
from src.schemas.templates import ChannelTemplate


def pytest_configure() -> None:
    os.environ["AUTH_REQUIRED"] = "false"
    os.environ["AUTH_AUTO_MIGRATE"] = "false"
    os.environ["PROVIDER_MODE"] = "mock"
    os.environ["FORCE_MOCK_PROVIDERS"] = "true"
    os.environ["AVATAR_VIDEO_PROVIDER"] = "heygen_api"
    os.environ["HEYGEN_API_KEY"] = ""
    os.environ["CONTROL_PLANE_BACKEND"] = "memory"


@pytest.fixture
def output_spec() -> OutputSpec:
    return OutputSpec(width=640, height=360, fps=30, aspect_ratio="16:9")


@pytest.fixture
def template(output_spec: OutputSpec) -> ChannelTemplate:
    return TemplateLoader(Path(__file__).parents[1] / "templates").load(
        "default", output=output_spec
    )


def make_scene(visual_format: VisualFormat) -> Scene:
    common = {
        "scene_id": f"scene_{visual_format.value.lower()}",
        "order": 1,
        "visual_format": visual_format,
        "narration_text": "Narration",
        "voice_id": "voice_1",
    }
    if visual_format == VisualFormat.PRESENTER:
        return Scene(**common, avatar_id="avatar_1")
    if visual_format == VisualFormat.SPLIT:
        return Scene(**common, avatar_id="avatar_1", visual_description="Visual")
    return Scene(**common, visual_description="Visual")
