from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from src.orchestration.pipeline import PipelineOrchestrator, ProviderSet
from src.schemas.assets import AssetKind, GeneratedAsset, Provenance
from src.schemas.scene import OutputSpec, ProjectScript, VisualFormat
from tests.conftest import make_scene


def generated(kind: AssetKind, scene_id: str) -> GeneratedAsset:
    mime = "audio/wav" if kind == AssetKind.AUDIO else "video/mp4"
    return GeneratedAsset(
        asset_id=f"{kind}_{scene_id}",
        kind=kind,
        uri=f"/tmp/{kind}-{scene_id}",
        content_hash="b" * 64,
        project_id="project",
        scene_id=scene_id,
        duration_seconds=2,
        width=640 if kind != AssetKind.AUDIO else None,
        height=360 if kind != AssetKind.AUDIO else None,
        fps=30 if kind != AssetKind.AUDIO else None,
        sample_rate=48000 if kind == AssetKind.AUDIO else None,
        mime_type=mime,
        provenance=Provenance(provider="test", model_identifier="test", checkpoint_revision="test"),
    )


def providers(scene_id: str) -> ProviderSet:
    speech = AsyncMock()
    speech.generate.return_value = generated(AssetKind.AUDIO, scene_id)
    avatar = AsyncMock()
    avatar.resolve.return_value = generated(AssetKind.AVATAR_SOURCE, scene_id)
    lipsync = AsyncMock()
    lipsync.generate.return_value = generated(AssetKind.LIPSYNC_VIDEO, scene_id)
    image = AsyncMock()
    image.generate.return_value = generated(AssetKind.IMAGE, scene_id)
    video = AsyncMock()
    video.generate.return_value = generated(AssetKind.VIDEO, scene_id)
    renderer = AsyncMock()
    renderer.render.return_value = generated(AssetKind.SCENE_VIDEO, scene_id)
    return ProviderSet(speech, avatar, lipsync, image, video, renderer)


async def run_scene(visual_format: VisualFormat, template, tmp_path: Path):
    scene = make_scene(visual_format).model_copy(update={"duration_seconds": 2})
    project = ProjectScript(
        project_id="project",
        schema_version="1.0",
        output=OutputSpec(width=640, height=360),
        scenes=(scene,),
    )
    provider_set = providers(scene.scene_id)
    await PipelineOrchestrator(provider_set, work_root=tmp_path).render_project(project, template)
    return provider_set


@pytest.mark.asyncio
async def test_presenter_exact_provider_contract(template, tmp_path) -> None:
    provider_set = await run_scene(VisualFormat.PRESENTER, template, tmp_path)
    provider_set.speech.generate.assert_awaited_once()
    provider_set.avatar_source.resolve.assert_awaited_once()
    provider_set.lipsync.generate.assert_awaited_once()
    provider_set.image.generate.assert_not_awaited()
    provider_set.video.generate.assert_not_awaited()
    render_request = provider_set.renderer.render.await_args.args[0]
    assert render_request.avatar_video is not None
    assert render_request.visual is None


@pytest.mark.asyncio
async def test_native_presenter_voice_skips_speech_provider(template, tmp_path) -> None:
    scene = make_scene(VisualFormat.PRESENTER).model_copy(update={"duration_seconds": 2})
    project = ProjectScript(
        project_id="project",
        schema_version="1.0",
        output=OutputSpec(width=640, height=360),
        scenes=(scene,),
    )
    provider_set = providers(scene.scene_id)
    provider_set = replace(provider_set, native_presenter_voice=True)
    orchestrator = PipelineOrchestrator(provider_set, work_root=tmp_path)
    with patch.object(
        orchestrator,
        "_extract_audio",
        return_value=generated(AssetKind.AUDIO, scene.scene_id),
    ):
        await orchestrator.render_project(project, template)

    provider_set.speech.generate.assert_not_awaited()
    lipsync_request = provider_set.lipsync.generate.await_args.args[0]
    assert lipsync_request.audio is None
    assert lipsync_request.narration_text == scene.narration_text
    assert lipsync_request.voice_id == scene.voice_id


@pytest.mark.asyncio
async def test_split_exact_provider_contract(template, tmp_path) -> None:
    provider_set = await run_scene(VisualFormat.SPLIT, template, tmp_path)
    provider_set.speech.generate.assert_awaited_once()
    provider_set.avatar_source.resolve.assert_awaited_once()
    provider_set.lipsync.generate.assert_awaited_once()
    provider_set.image.generate.assert_awaited_once()
    render_request = provider_set.renderer.render.await_args.args[0]
    assert render_request.avatar_video is not None
    assert render_request.visual is not None


@pytest.mark.asyncio
async def test_full_visual_exact_provider_contract(template, tmp_path) -> None:
    provider_set = await run_scene(VisualFormat.FULL_VISUAL, template, tmp_path)
    provider_set.speech.generate.assert_awaited_once()
    provider_set.avatar_source.resolve.assert_not_awaited()
    provider_set.lipsync.generate.assert_not_awaited()
    provider_set.image.generate.assert_awaited_once()
    render_request = provider_set.renderer.render.await_args.args[0]
    assert render_request.avatar_video is None
    assert render_request.visual is not None
