from __future__ import annotations

from pathlib import Path

from src.orchestration.cost import scene_duration_seconds
from src.providers.heygen import HeyGenLipSyncGenerator
from src.schemas.assets import AssetKind, GeneratedAsset
from src.schemas.jobs import JobRecord
from src.schemas.scene import ProjectScript, VisualFormat


class HeyGenExportPending(Exception):
    """HeyGen accepted the job but the MP4 is not ready yet."""

    def __init__(self, video_id: str) -> None:
        super().__init__(video_id)
        self.video_id = video_id


def is_heygen_presenter_project(project: ProjectScript) -> bool:
    return bool(project.scenes) and all(
        scene.visual_format == VisualFormat.PRESENTER for scene in project.scenes
    )


async def export_heygen_presenter(
    *,
    job: JobRecord,
    project: ProjectScript,
    generator: HeyGenLipSyncGenerator,
    work_dir: Path,
) -> GeneratedAsset:
    """Create or resume one PRESENTER HeyGen export and return the MP4 when ready."""

    scene = project.scenes[0]
    avatar_id = (scene.avatar_id or "").strip()
    if not avatar_id:
        raise ValueError("HeyGen export requires a registered HeyGen avatar ID")
    duration = scene_duration_seconds(scene)
    video_id = (job.provider_ref or "").strip()
    if not video_id:
        video_id = await generator.create_presenter_video(
            avatar_id=avatar_id,
            script=scene.narration_text,
            voice_id=scene.voice_id,
            job_id=job.job_id,
            title=f"{project.project_id}-{scene.scene_id}",
            width=project.output.width,
            height=project.output.height,
            duration_seconds=duration,
        )
        raise HeyGenExportPending(video_id)
    details = await generator.poll_video(video_id)
    if str(details.get("status") or "").lower() != "completed":
        raise HeyGenExportPending(video_id)
    output = work_dir / f"{job.video_id}.mp4"
    asset = await generator.download_completed(
        video_id, output, duration_seconds=duration
    )
    return asset.model_copy(
        update={
            "kind": AssetKind.FINAL_VIDEO,
            "project_id": project.project_id,
            "scene_id": scene.scene_id,
        }
    )
