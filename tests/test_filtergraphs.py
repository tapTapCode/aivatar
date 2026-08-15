from src.rendering.filtergraphs import build_filtergraph
from src.schemas.assets import AssetKind, GeneratedAsset, Provenance
from src.schemas.requests import GenerationContext, SceneRenderRequest
from src.schemas.scene import VisualFormat
from tests.conftest import make_scene


def asset(kind: AssetKind) -> GeneratedAsset:
    return GeneratedAsset(
        asset_id=f"asset_{kind}",
        kind=kind,
        uri="/tmp/asset",
        content_hash="a" * 64,
        project_id="project",
        scene_id="scene",
        mime_type="application/octet-stream",
        provenance=Provenance(provider="test", model_identifier="test", checkpoint_revision="test"),
    )


def request(visual_format, output_spec, template):
    return SceneRenderRequest(
        context=GenerationContext(
            project_id="project",
            scene_id="scene",
            request_id="request",
            job_id="job",
            work_dir="/tmp",
        ),
        scene=make_scene(visual_format),
        output=output_spec,
        template=template,
        audio=asset(AssetKind.AUDIO),
        avatar_video=asset(AssetKind.LIPSYNC_VIDEO)
        if visual_format != VisualFormat.FULL_VISUAL
        else None,
        visual=asset(AssetKind.IMAGE) if visual_format != VisualFormat.PRESENTER else None,
        duration_seconds=2,
    )


def test_presenter_graph_never_references_visual(output_spec, template) -> None:
    graph = build_filtergraph(
        request(VisualFormat.PRESENTER, output_spec, template),
        avatar_input=0,
        visual_input=None,
        audio_input=1,
    )
    assert "[0:v]" in graph.expression
    assert "[1:v]" not in graph.expression


def test_split_graph_stacks_avatar_and_visual(output_spec, template) -> None:
    graph = build_filtergraph(
        request(VisualFormat.SPLIT, output_spec, template),
        avatar_input=0,
        visual_input=1,
        audio_input=2,
    )
    assert "hstack=inputs=3" in graph.expression
    assert "[0:v]" in graph.expression and "[1:v]" in graph.expression


def test_full_visual_graph_never_references_avatar(output_spec, template) -> None:
    graph = build_filtergraph(
        request(VisualFormat.FULL_VISUAL, output_spec, template),
        avatar_input=None,
        visual_input=0,
        audio_input=1,
    )
    assert "[0:v]" in graph.expression
    assert "avatar" not in graph.expression
    assert "zoompan=" in graph.expression
