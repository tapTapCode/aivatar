from __future__ import annotations

import pytest

from src.orchestration.routing import (
    UnlicensedWatermarkException,
    validate_provider_routing,
)
from src.schemas.jobs import WatermarkStatus
from src.schemas.scene import OutputSpec, ProjectScript, Scene


def project(*, require_clean_export: bool) -> ProjectScript:
    return ProjectScript(
        project_id="routing-test",
        schema_version="1.0",
        require_clean_export=require_clean_export,
        output=OutputSpec(width=640, height=360),
        scenes=(
            Scene(
                scene_id="presenter",
                order=1,
                visual_format="PRESENTER",
                narration_text="Routing contract.",
                avatar_id="avatar",
                voice_id="voice",
            ),
        ),
    )


def test_imported_free_preserves_watermark_by_default() -> None:
    status = validate_provider_routing(
        project(require_clean_export=False), "imported_video"
    )
    assert status == WatermarkStatus.PRESERVED


@pytest.mark.parametrize("provider", ["heygen_api", "local_musetalk"])
def test_authorized_provider_satisfies_clean_export(provider: str) -> None:
    status = validate_provider_routing(project(require_clean_export=True), provider)
    assert status == WatermarkStatus.CLEAN_AUTHORIZED


def test_imported_free_rejects_clean_export_before_rendering() -> None:
    with pytest.raises(UnlicensedWatermarkException) as caught:
        validate_provider_routing(project(require_clean_export=True), "imported_video")
    assert caught.value.error == "UNLICENSED_WATERMARK_REJECTION"


def test_unknown_provider_is_rejected() -> None:
    with pytest.raises(ValueError, match="unsupported avatar video provider"):
        validate_provider_routing(project(require_clean_export=False), "unknown")
