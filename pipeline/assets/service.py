from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from pipeline.cache.assets import AssetCache, cache_key
from pipeline.core.config import settings
from pipeline.core.enums import ProjectState
from pipeline.director.timeline import PlannedScene
from pipeline.director.visual_strategy import choose_visual_strategies, strategy_summary
from pipeline.models.entities import Asset, AssetCacheEntry, CostEntry, Project, Scene
from pipeline.motion_graphics.templates import MotionGraphicSpec, apply_motion_graphic
from pipeline.providers.registry import image_provider
from pipeline.providers.mock import MockImageProvider, MockVideoProvider
from pipeline.providers.video import LTXProvider
from pipeline.render.ffmpeg import run, sha256
from pipeline.render.graph import project_dirs, render_still_with_motion
from pipeline.queue.resources import resource_limits


def _cache() -> AssetCache:
    return AssetCache(settings.aivatar_workspace / "cache" / "assets")


def _source_contract(scene: Scene, strategy: str) -> tuple[str, str, dict]:
    if strategy == "ltx_video":
        return (
            "video",
            settings.aivatar_ltx_model,
            {
                "checkpoint": settings.aivatar_ltx_checkpoint,
                "duration": round(scene.end - scene.start, 3),
                "width": 1280,
                "height": 720,
                "fps": 24,
                "pipeline": settings.aivatar_ltx_pipeline,
            },
        )
    return (
        "image",
        settings.fal_model if settings.aivatar_image_provider == "fal_flux" else settings.aivatar_flux_model,
        {"width": 1280, "height": 720, "steps": 4, "guidance_scale": 1.0},
    )


def _expected_key(scene: Scene, strategy: str) -> str:
    kind, model, params = _source_contract(scene, strategy)
    provider = "ltx_2_3" if kind == "video" else settings.aivatar_image_provider
    return cache_key(kind=kind, provider=provider, model=model, prompt=scene.visual_prompt, parameters=params)


def _cache_hit_for_scene(scene: Scene) -> tuple[str, str] | None:
    cache = _cache()
    for strategy in ("ltx_video", "flux_motion"):
        key = _expected_key(scene, strategy)
        hit = cache.peek(key)
        if hit:
            return key, strategy
    return None


def plan_visual_assets(db: Session, project: Project, *, max_ltx_scenes: int | None = None) -> dict:
    if not project.scenes:
        raise ValueError("Project must have a scene plan before visual optimization")
    planned = [
        PlannedScene(s.ordinal, s.start, s.end, s.type, s.visual_prompt, s.motion)
        for s in project.scenes
    ]
    cached_ordinals: set[int] = set()
    cache_matches: dict[int, tuple[str, str]] = {}
    if settings.aivatar_asset_cache_enabled:
        for scene in project.scenes:
            if scene.type == "PRESENTER":
                continue
            match = _cache_hit_for_scene(scene)
            if match:
                cached_ordinals.add(scene.ordinal)
                cache_matches[scene.ordinal] = match

    decisions = choose_visual_strategies(
        planned,
        total_budget_usd=project.budget_usd,
        visual_budget_fraction=settings.aivatar_visual_budget_fraction,
        max_ltx_scenes=max_ltx_scenes if max_ltx_scenes is not None else settings.aivatar_max_ltx_scenes,
        ltx_threshold=settings.aivatar_ltx_motion_threshold,
        max_ltx_scene_seconds=settings.aivatar_max_ltx_scene_seconds,
        cached_scene_ordinals=cached_ordinals,
    )
    by_ordinal = {row.scene_ordinal: row for row in decisions}
    for scene in project.scenes:
        decision = by_ordinal[scene.ordinal]
        scene.asset_strategy = decision.strategy
        scene.motion_score = decision.motion_score
        scene.estimated_visual_cost_usd = decision.estimated_cost_usd
        scene.graphic_template = decision.template
        if decision.strategy == "cache":
            key, cached_strategy = cache_matches[scene.ordinal]
            layout = dict(scene.layout_json or {})
            layout["cache_key"] = key
            layout["cached_strategy"] = cached_strategy
            scene.layout_json = layout

    summary = strategy_summary(decisions)
    project.estimated_cost_usd = round(summary["estimated_visual_cost_usd"], 4)
    db.commit()
    return {
        "project_id": project.id,
        "budget_usd": project.budget_usd,
        "visual_budget_usd": round(project.budget_usd * settings.aivatar_visual_budget_fraction, 4),
        **summary,
        "decisions": [row.as_dict() for row in decisions],
    }


def _upsert_cache_row(db: Session, key: str, kind: str, provider: str, model: str, path: Path, metadata: dict) -> None:
    row = db.get(AssetCacheEntry, key)
    now = datetime.now(timezone.utc)
    if row is None:
        row = AssetCacheEntry(
            cache_key=key,
            kind=kind,
            provider=provider,
            model=model,
            path=str(path),
            checksum=sha256(path),
            size_bytes=path.stat().st_size,
            hit_count=0,
            metadata_json=metadata,
            created_at=now,
            last_used_at=now,
        )
        db.add(row)
    else:
        row.path = str(path)
        row.checksum = sha256(path)
        row.size_bytes = path.stat().st_size
        row.last_used_at = now
        row.metadata_json = {**(row.metadata_json or {}), **metadata}


def _record_cache_hit(db: Session, key: str) -> None:
    row = db.get(AssetCacheEntry, key)
    if row:
        row.hit_count += 1
        row.last_used_at = datetime.now(timezone.utc)


def _normalize_video(source: Path, output: Path, duration: float) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    run([
        "ffmpeg", "-y", "-loglevel", "error", "-i", str(source),
        "-vf", "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,fps=30",
        "-t", f"{duration:.3f}", "-an", "-c:v", "libx264", "-preset", "medium",
        "-crf", "20", "-pix_fmt", "yuv420p", str(output),
    ])
    return output


def _render_source(scene: Scene, source: Path, source_kind: str, output: Path) -> Path:
    duration = scene.end - scene.start
    base = output.with_name(output.stem + "_base.mp4")
    if source_kind == "video":
        _normalize_video(source, base, duration)
    else:
        render_still_with_motion(source, base, duration, scene.motion or "subtle_zoom")
    if scene.graphic_template:
        title = scene.visual_prompt.strip()[:72] or f"Scene {scene.ordinal}"
        subtitle = "Aivatar motion graphic"
        apply_motion_graphic(
            base,
            output,
            duration,
            MotionGraphicSpec(scene.graphic_template, title, subtitle),
            preset="ultrafast" if settings.aivatar_env == "test" else "medium",
        )
        return output
    if output.exists():
        output.unlink()
    base.replace(output)
    return output


def generate_visual_assets(db: Session, project: Project, *, mock: bool = True, force: bool = False) -> list[dict]:
    if not project.scenes:
        raise ValueError("Project must be planned first")
    if any(not scene.asset_strategy for scene in project.scenes):
        plan_visual_assets(db, project)
    dirs = project_dirs(settings.aivatar_workspace, project.id)
    cache = _cache()
    results: list[dict] = []

    if project.state == ProjectState.PLANNING.value:
        project.state = ProjectState.ASSETS_GENERATING.value
        db.commit()

    try:
        for scene in project.scenes:
            if scene.type == "PRESENTER" or scene.asset_strategy == "presenter_only":
                continue
            duration = scene.end - scene.start
            strategy = scene.asset_strategy
            cached_strategy = (scene.layout_json or {}).get("cached_strategy") if strategy == "cache" else None
            generation_strategy = cached_strategy or strategy
            source_kind, model, params = _source_contract(scene, generation_strategy)
            provider_name = "ltx_2_3" if source_kind == "video" else settings.aivatar_image_provider
            key = (scene.layout_json or {}).get("cache_key") if strategy == "cache" else _expected_key(scene, generation_strategy)
            key = str(key)
            source_ext = ".mp4" if source_kind == "video" else ".png"
            local_source = dirs["cache"] / f"source_scene_{scene.ordinal:03}{source_ext}"
            cache_hit = None if force or not settings.aivatar_asset_cache_enabled else cache.get(key)
            provider_result = None

            if cache_hit:
                cache.materialize(cache_hit, local_source)
                _record_cache_hit(db, key)
                source_provider = f"cache:{cache_hit.metadata.get('provider', provider_name)}"
            else:
                if source_kind == "video":
                    provider = MockVideoProvider() if mock else LTXProvider()
                    with resource_limits.reserve("video_gpu"):
                        provider_result = provider.generate(
                            scene.visual_prompt,
                            duration,
                            dirs["videos"] / f"scene_{scene.ordinal:03}",
                            project_id=project.id,
                            scene_id=scene.id,
                            width=1280,
                            height=720,
                            fps=24,
                        )
                else:
                    provider = MockImageProvider() if mock else image_provider(settings.aivatar_image_provider)
                    image_prompt = scene.visual_prompt
                    if settings.aivatar_image_provider == "fal_flux":
                        image_prompt = (
                            f"{scene.visual_prompt}. Create a clean cinematic supporting visual with no words, "
                            "no letters, no numbers, no captions, no labels, no logos, no watermark, and no UI text. "
                            "Leave all explanatory text to the video caption layer."
                        )
                    with resource_limits.reserve("image_gpu"):
                        provider_result = provider.generate(
                            image_prompt,
                            dirs["images"] / f"scene_{scene.ordinal:03}",
                            project_id=project.id,
                            scene_id=scene.id,
                            width=1280,
                            height=720,
                        )
                source_provider = provider_result.provider
                local_source.parent.mkdir(parents=True, exist_ok=True)
                local_source.write_bytes(provider_result.path.read_bytes())
                if settings.aivatar_asset_cache_enabled:
                    cache_hit = cache.put(
                        key,
                        local_source,
                        {
                            "kind": source_kind,
                            "provider": source_provider,
                            "model": model,
                            "parameters": params,
                            "prompt": scene.visual_prompt,
                        },
                    )
                    _upsert_cache_row(db, key, source_kind, source_provider, model, cache_hit.path, cache_hit.metadata)

            visual = dirs["videos"] / f"visual_scene_{scene.ordinal:03}.mp4"
            with resource_limits.reserve("ffmpeg"):
                _render_source(scene, local_source, source_kind, visual)
            checksum = sha256(visual)
            db.add(Asset(
                project_id=project.id,
                scene_id=scene.id,
                kind="visual",
                provider=source_provider,
                path=str(visual),
                duration=duration,
                checksum=checksum,
                cache_key=key,
                metadata_json={
                    "strategy": strategy,
                    "generation_strategy": generation_strategy,
                    "source_kind": source_kind,
                    "source_path": str(local_source),
                    "model": model,
                    "cache_hit": provider_result is None,
                    "motion": scene.motion,
                    "graphic_template": scene.graphic_template,
                },
            ))
            if provider_result is not None:
                meta = provider_result.metadata or {}
                db.add(CostEntry(
                    project_id=project.id,
                    provider=provider_result.provider,
                    asset_type=source_kind,
                    gpu_model=meta.get("gpu_model"),
                    gpu_seconds=float(meta.get("gpu_seconds") or meta.get("runtime_seconds") or 0.0),
                    estimated_cost_usd=provider_result.estimated_cost_usd,
                    actual_cost_usd=provider_result.actual_cost_usd,
                    metadata_json={**meta, "strategy": strategy, "scene_id": scene.id},
                ))
            else:
                db.add(CostEntry(
                    project_id=project.id,
                    provider="asset_cache",
                    asset_type=source_kind,
                    estimated_cost_usd=0.0,
                    actual_cost_usd=0.0,
                    metadata_json={"cache_key": key, "scene_id": scene.id, "saved_generation": True},
                ))
            results.append({
                "scene_id": scene.id,
                "ordinal": scene.ordinal,
                "strategy": strategy,
                "source_kind": source_kind,
                "cache_hit": provider_result is None,
                "cache_key": key,
                "visual": str(visual),
                "sha256": checksum,
            })
            db.commit()

        if project.state == ProjectState.ASSETS_GENERATING.value:
            project.state = ProjectState.ASSETS_READY.value
        project.actual_cost_usd = round(sum(x.actual_cost_usd for x in db.scalars(select(CostEntry).where(CostEntry.project_id == project.id)).all()), 4)
        db.commit()
        return results
    except Exception:
        project.state = ProjectState.FAILED.value
        db.commit()
        raise
