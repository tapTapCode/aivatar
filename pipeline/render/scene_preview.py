from __future__ import annotations

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from pipeline.core.config import settings
from pipeline.models.entities import Asset, Project, Scene
from pipeline.providers.mock import MockVideoProvider
from pipeline.render.composite import compose_presenter_scene
from pipeline.render.ffmpeg import sha256
from pipeline.render.graph import project_dirs, render_scene


def latest_scene_asset(db: Session, scene_id: str, kind: str) -> Asset | None:
    return db.scalars(
        select(Asset)
        .where(Asset.scene_id == scene_id, Asset.kind == kind)
        .order_by(Asset.created_at.desc())
    ).first()


def render_scene_preview(
    db: Session,
    project: Project,
    scene: Scene,
    *,
    visual_path: str | None = None,
    force: bool = False,
) -> Path:
    dirs = project_dirs(settings.aivatar_workspace, project.id)
    output = dirs["render"] / f"preview_scene_{scene.ordinal:03}.mp4"
    if output.exists() and not force and scene.render_hash:
        return output

    duration = scene.end - scene.start
    if scene.type in {"PRESENTER", "SPLIT", "PIP"}:
        presenter = latest_scene_asset(db, scene.id, "presenter_clip")
        if not presenter or not Path(presenter.path).exists():
            raise ValueError("Scene has no presenter_clip; generate the presenter first")
        visual: Path | None = None
        if scene.type in {"SPLIT", "PIP"}:
            if visual_path:
                visual = Path(visual_path)
                if not visual.exists():
                    raise FileNotFoundError(visual)
            else:
                existing_visual = latest_scene_asset(db, scene.id, "visual_clip")
                if existing_visual and Path(existing_visual.path).exists():
                    visual = Path(existing_visual.path)
                else:
                    visual = MockVideoProvider().generate(
                        scene.visual_prompt,
                        duration,
                        dirs["cache"] / f"preview_visual_{scene.id}",
                    ).path
        layout = {"presenter_side": scene.presenter_position, **(scene.layout_json or {})}
        compose_presenter_scene(scene.type, Path(presenter.path), visual, output, duration, layout)
    else:
        from pipeline.director.timeline import PlannedScene

        render_scene(
            PlannedScene(scene.ordinal, scene.start, scene.end, scene.type, scene.visual_prompt, scene.motion),
            output,
        )
    scene.render_path = str(output)
    scene.render_hash = sha256(output)
    db.add(scene)
    db.commit()
    return output
