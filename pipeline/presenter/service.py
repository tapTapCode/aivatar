from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from pipeline.audio.master import cut_audio_segment
from pipeline.core.config import settings
from pipeline.core.credit_guard import assert_project_budget
from pipeline.models.entities import Asset, Avatar, CostEntry, Project, Scene
from pipeline.providers.base import ProviderUnavailable
from pipeline.providers.registry import presenter_provider
from pipeline.render.ffmpeg import sha256
from pipeline.render.graph import project_dirs

PRESENTER_SCENE_TYPES = {"PRESENTER", "SPLIT", "PIP"}


def _master_audio(db: Session, project_id: str) -> Asset:
    asset = db.scalars(
        select(Asset)
        .where(Asset.project_id == project_id, Asset.kind == "master_audio")
        .order_by(Asset.created_at.desc())
    ).first()
    if not asset:
        raise ValueError("Project has no master_audio asset; generate or import narration first")
    if not Path(asset.path).exists():
        raise FileNotFoundError(asset.path)
    return asset


def _existing_presenter(db: Session, project_id: str, scene_id: str) -> Asset | None:
    return db.scalars(
        select(Asset)
        .where(
            Asset.project_id == project_id,
            Asset.scene_id == scene_id,
            Asset.kind == "presenter_clip",
        )
        .order_by(Asset.created_at.desc())
    ).first()


def _provider_attempts(primary: str, allow_fallback: bool) -> list[str]:
    attempts = [primary]
    if allow_fallback:
        for candidate in ["musetalk_fallback"]:
            if candidate not in attempts:
                attempts.append(candidate)
    return attempts


def generate_presenter_for_scene(
    db: Session,
    project: Project,
    scene: Scene,
    *,
    provider_name: str | None = None,
    force: bool = False,
    allow_fallback: bool = True,
    manual_clip_path: str | None = None,
) -> dict[str, Any]:
    if scene.type not in PRESENTER_SCENE_TYPES:
        raise ValueError(f"Scene {scene.ordinal} ({scene.type}) does not contain a presenter")
    existing = _existing_presenter(db, project.id, scene.id)
    if existing and (existing.locked or scene.locked) and force:
        raise ValueError("Scene or presenter asset is locked; unlock it before regeneration")
    if existing and Path(existing.path).exists() and not force:
        return {
            "scene_id": scene.id,
            "provider": existing.provider,
            "path": existing.path,
            "duration": existing.duration,
            "reused": True,
            "metadata": existing.metadata_json,
        }

    avatar: Avatar | None = db.get(Avatar, project.avatar_id) if project.avatar_id else None
    primary = provider_name or (avatar.presenter_provider if avatar else "mock_presenter")
    if manual_clip_path:
        primary = "manual_presenter_import"
        allow_fallback = False

    master = _master_audio(db, project.id)
    dirs = project_dirs(settings.aivatar_workspace, project.id)
    segment_path = dirs["audio"] / "presenter_segments" / f"scene_{scene.ordinal:03}.wav"
    cut_audio_segment(Path(master.path), scene.start, scene.end, segment_path)

    failures: list[str] = []
    result = None
    resolved_provider = None
    for candidate in _provider_attempts(primary, allow_fallback):
        provider = presenter_provider(candidate)
        try:
            estimated_cost = None
            if candidate in {"authorized_heygen", "authorized_higgsfield"}:
                estimated_cost = assert_project_budget(
                    db,
                    project,
                    scene.end - scene.start,
                )
            result = provider.generate(
                segment_path,
                scene.end - scene.start,
                dirs["presenter"],
                project_id=project.id,
                scene_id=scene.id,
                avatar_id=avatar.provider_avatar_id if avatar else None,
                reference_image_path=avatar.reference_image_path if avatar else None,
                source_path=manual_clip_path,
                resolution=project.resolution,
                aspect_ratio=project.aspect_ratio,
                title=f"{project.name} / scene {scene.ordinal}",
                prompt=((avatar.settings_json if avatar else {}) or {}).get("higgsfield_motion_prompt") or "Natural front-facing presenter speaking to camera with realistic blinking, subtle head movement, natural hair motion, and accurate lip synchronization.",
                model=((avatar.settings_json if avatar else {}) or {}).get("higgsfield_model"),
            )
            if estimated_cost is not None and result.estimated_cost_usd <= 0:
                result.estimated_cost_usd = estimated_cost
            resolved_provider = candidate
            break
        except (ProviderUnavailable, FileNotFoundError, RuntimeError, TimeoutError) as exc:
            failures.append(f"{candidate}: {exc}")
            if not allow_fallback:
                break

    if not result or not resolved_provider:
        raise ProviderUnavailable("Presenter generation failed: " + " | ".join(failures))

    # Replace unlocked previous versions in the active asset set but preserve locked history.
    if existing and not existing.locked:
        db.delete(existing)
    metadata = {
        **(result.metadata or {}),
        "master_start": scene.start,
        "master_end": scene.end,
        "segment_audio": str(segment_path),
        "fallback_failures": failures,
    }
    asset = Asset(
        project_id=project.id,
        scene_id=scene.id,
        kind="presenter_clip",
        provider=resolved_provider,
        path=str(result.path),
        duration=result.duration,
        checksum=sha256(result.path),
        metadata_json=metadata,
    )
    db.add(asset)
    gpu_seconds = float(metadata.get("gpu_seconds") or 0.0)
    db.add(
        CostEntry(
            project_id=project.id,
            provider=resolved_provider,
            asset_type="presenter",
            gpu_seconds=gpu_seconds,
            estimated_cost_usd=result.estimated_cost_usd,
            actual_cost_usd=result.actual_cost_usd,
            external_cost_usd=result.actual_cost_usd,
            metadata_json={"scene_id": scene.id, **metadata},
        )
    )
    # Any existing composite for this scene is now stale.
    scene.render_path = None
    scene.render_hash = None
    db.add(scene)
    db.commit()
    db.refresh(asset)
    return {
        "scene_id": scene.id,
        "provider": resolved_provider,
        "path": str(result.path),
        "duration": result.duration,
        "reused": False,
        "metadata": metadata,
    }


def generate_presenter_scenes(
    db: Session,
    project: Project,
    *,
    provider_name: str | None = None,
    force: bool = False,
    allow_fallback: bool = True,
) -> list[dict[str, Any]]:
    output = []
    for scene in project.scenes:
        if scene.type in PRESENTER_SCENE_TYPES:
            output.append(
                generate_presenter_for_scene(
                    db,
                    project,
                    scene,
                    provider_name=provider_name,
                    force=force,
                    allow_fallback=allow_fallback,
                )
            )
    return output
