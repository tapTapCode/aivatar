from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import uuid
from pathlib import Path

from src.orchestration.pipeline import PipelineOrchestrator, ProviderSet
from src.orchestration.templates import TemplateLoader
from src.providers.mock import (
    MockAvatarSourceProvider,
    MockImageGenerator,
    MockLipSyncGenerator,
    MockSpeechGenerator,
    MockVideoGenerator,
)
from src.rendering import FFmpegSceneRenderer, TimelineAssembler, probe_media, validate_output
from src.schemas.scene import ProjectScript


async def generate(project_path: Path, output_dir: Path) -> dict[str, object]:
    project = ProjectScript.model_validate_json(project_path.read_text())
    template = TemplateLoader("templates").load(project.channel_template, output=project.output)
    job_id = f"demo_{uuid.uuid4().hex[:10]}"
    pipeline = PipelineOrchestrator(
        ProviderSet(
            speech=MockSpeechGenerator(),
            avatar_source=MockAvatarSourceProvider(),
            lipsync=MockLipSyncGenerator(),
            image=MockImageGenerator(),
            video=MockVideoGenerator(),
            renderer=FFmpegSceneRenderer(),
        ),
        work_root=output_dir / "work",
    )
    scenes = await pipeline.render_project(project, template, job_id=job_id, request_id=job_id)
    output_dir.mkdir(parents=True, exist_ok=True)
    scene_outputs: dict[str, str] = {}
    validations: dict[str, list[str]] = {}
    expected_names = {
        "PRESENTER": "presenter-scene.mp4",
        "SPLIT": "split-scene.mp4",
        "FULL_VISUAL": "full-visual-scene.mp4",
    }
    for scene, asset in zip(project.scenes, scenes, strict=True):
        target = output_dir / expected_names[scene.visual_format.value]
        shutil.copy2(asset.uri, target)
        scene_outputs[scene.visual_format.value] = str(target.resolve())
        validations[scene.scene_id] = list(
            validate_output(
                probe_media(str(target)),
                width=project.output.width,
                height=project.output.height,
                fps=project.output.fps,
                expected_duration_seconds=asset.duration_seconds or 0,
                sample_rate=template.audio.sample_rate,
            )
        )
    final = await TimelineAssembler().assemble(
        scenes,
        project_id=project.project_id,
        output_spec=project.output,
        output_dir=output_dir / "work" / "final",
        transitions=tuple(scene.transition_out for scene in project.scenes),
    )
    final_target = output_dir / "three-format-combined.mp4"
    shutil.copy2(final.uri, final_target)
    total_duration = final.duration_seconds or 0
    validations["combined"] = list(
        validate_output(
            probe_media(str(final_target)),
            width=project.output.width,
            height=project.output.height,
            fps=project.output.fps,
            expected_duration_seconds=total_duration,
            sample_rate=template.audio.sample_rate,
        )
    )
    manifest: dict[str, object] = {
        "status": "VERIFIED" if not any(validations.values()) else "FAILED_VALIDATION",
        "classification": "MOCK DEMONSTRATION — not an AI model quality sample",
        "project_id": project.project_id,
        "job_id": job_id,
        "scene_outputs": scene_outputs,
        "combined_output": str(final_target.resolve()),
        "expected_duration_seconds": total_duration,
        "validation_errors": validations,
        "model_benchmarks": "NOT TESTED",
    }
    (output_dir / "demo-manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest


def run() -> None:
    parser = argparse.ArgumentParser(description="Generate a mock exact-format demonstration")
    parser.add_argument("--project", type=Path, default=Path("examples/three-format-project.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/demo"))
    args = parser.parse_args()
    print(json.dumps(asyncio.run(generate(args.project, args.output_dir)), indent=2))


if __name__ == "__main__":
    run()
