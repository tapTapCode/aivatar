from pathlib import Path

import pytest

from src.orchestration.templates import TemplateLoader, TemplateNotFoundError
from src.schemas.scene import OutputSpec

ROOT = Path(__file__).parents[1] / "templates"


def test_template_output_dimensions_follow_project() -> None:
    template = TemplateLoader(ROOT).load("default", output=OutputSpec(width=640, height=360))
    assert (template.width, template.height) == (640, 360)
    assert template.split.avatar_ratio == pytest.approx(0.42)


def test_template_path_traversal_is_rejected() -> None:
    with pytest.raises(ValueError):
        TemplateLoader(ROOT).load("../secret")


def test_missing_template_fails() -> None:
    with pytest.raises(TemplateNotFoundError):
        TemplateLoader(ROOT).load("missing")
