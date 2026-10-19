from pathlib import Path
import shutil
import subprocess
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from pipeline.core.config import settings
from pipeline.core.enums import ProjectState
from pipeline.core.state_machine import require_transition
from pipeline.director.timeline import plan_timeline, presenter_percentage, PlannedScene
from pipeline.models.entities import Channel, Avatar, Project, Scene, Asset, CostEntry, RenderHistory
from pipeline.assets.service import generate_visual_assets
from pipeline.render.graph import project_dirs, render_mock_project, render_scene
from pipeline.render.composite import compose_presenter_scene
from pipeline.render.ffmpeg import run
from pipeline.presenter.service import generate_presenter_scenes
from pipeline.audio.master import normalize_master_audio
from pipeline.alignment.timestamps import align_script_heuristic, caption_segments, normalize_provider_timestamps, save_timestamps
from pipeline.providers.registry import voice_provider
from pipeline.providers.base import ProviderResult
from pipeline.render.ffmpeg import sha256, write_caption_segments
from pipeline.production.metrics import measure_run
from pipeline.production.storage import directory_size

def transition(db: Session, project: Project, target: ProjectState) -> None:
    require_transition(ProjectState(project.state), target)
    project.state = target.value
    db.add(project); db.commit(); db.refresh(project)

def create_plan(db: Session, project: Project) -> list[Scene]:
    if project.state in {ProjectState.CREATED.value, ProjectState.FAILED.value}:
        transition(db, project, ProjectState.SCRIPT_READY)
    if project.state == ProjectState.SCRIPT_READY.value:
        transition(db, project, ProjectState.VOICE_GENERATING)
        transition(db, project, ProjectState.VOICE_READY)
    if project.state == ProjectState.VOICE_READY.value:
        transition(db, project, ProjectState.PLANNING)
    db.query(Scene).filter(Scene.project_id == project.id).delete()
    planned=plan_timeline(project.script, project.expected_duration, project.presenter_target)
    rows=[]
    for s in planned:
        row=Scene(project_id=project.id, ordinal=s.ordinal, start=s.start, end=s.end, type=s.type, visual_prompt=s.visual_prompt, motion=s.motion)
        db.add(row); rows.append(row)
    project.presenter_actual=presenter_percentage(planned)
    db.commit()
    for row in rows: db.refresh(row)
    return rows

def run_mock_render(db: Session, project: Project) -> dict:
    if not project.scenes: create_plan(db, project); db.refresh(project)
    if project.state == ProjectState.PLANNING.value:
        transition(db, project, ProjectState.ASSETS_READY)
    elif project.state in {ProjectState.SCRIPT_READY.value, ProjectState.VOICE_READY.value}:
        project.state=ProjectState.ASSETS_READY.value; db.commit(); db.refresh(project)
    transition(db, project, ProjectState.RENDERING)
    from pipeline.director.timeline import PlannedScene
    planned=[PlannedScene(s.ordinal,s.start,s.end,s.type,s.visual_prompt,s.motion) for s in project.scenes]
    try:
        with measure_run(db, project, "mock_render", {"mode": "mock"}) as production_run:
            manifest=render_mock_project(settings.aivatar_workspace, project.id, project.script, planned, project.expected_duration)
            transition(db, project, ProjectState.QUALITY_CHECK)
            project.final_duration=manifest["qc"]["duration"]
            project.actual_cost_usd=0.0
            final=Path(manifest["final"])
            project.error=None
            production_run.storage_bytes=directory_size(settings.aivatar_workspace / "projects" / project.id)
            db.add(CostEntry(project_id=project.id, provider="mock", asset_type="final_video", estimated_cost_usd=0, actual_cost_usd=0, metadata_json={"mode":"mock"}))
            db.add(RenderHistory(project_id=project.id, output_path=str(final), duration=manifest["qc"]["duration"], width=manifest["qc"]["width"], height=manifest["qc"]["height"], fps=30.0, qc_json=manifest["qc"]))
            db.commit(); db.refresh(project)
            transition(db, project, ProjectState.COMPLETED)
        return manifest
    except Exception as exc:
        project.state=ProjectState.FAILED.value; project.error=str(exc); db.commit()
        raise


def run_authorized_presenter_render(db: Session, project: Project, *, force: bool = False) -> dict:
    """Generate a real authorized presenter video through the configured provider."""
    if not project.avatar_id:
        raise ValueError("Project has no selected presenter avatar")
    avatar = db.get(Avatar, project.avatar_id)
    voice_provider_name = avatar.voice_provider if avatar and avatar.voice_provider in {"ai33", "69labs", "imported_audio", "mock_voice"} else "ai33"
    voice_id = avatar.voice_id if avatar else None
    if project.state in {ProjectState.CREATED.value, ProjectState.FAILED.value}:
        try:
            generate_master_voice(db, project, voice_provider_name, voice_id=voice_id)
        except Exception as exc:
            # Keep the avatar test independent from an unavailable optional TTS key.
            # macOS speech is local and does not consume provider credits.
            if not shutil.which("say"):
                raise exc
            project.state = ProjectState.CREATED.value
            db.commit()
            dirs = project_dirs(settings.aivatar_workspace, project.id)
            raw = dirs["audio"] / "local_test_voice.aiff"
            subprocess.run(["say", "-o", str(raw), project.script], check=True)
            wav, _mp3, duration = normalize_master_audio(raw, dirs["audio"])
            db.add(Asset(project_id=project.id, kind="master_audio", provider="macos_say", path=str(wav), duration=duration, checksum=sha256(wav), metadata_json={"fallback_for": "ai33"}))
            project.expected_duration = duration
            project.state = ProjectState.VOICE_READY.value
            db.commit()
        create_plan(db, project)
    elif not project.scenes:
        create_plan(db, project)
    if not project.scenes:
        raise ValueError("Project has no planned scenes")

    if project.state in {ProjectState.VOICE_READY.value, ProjectState.PLANNING.value}:
        # Keep the selected avatar voice instead of silently reverting to the default voice.
        master = db.scalars(select(Asset).where(Asset.project_id == project.id, Asset.kind == "master_audio").order_by(Asset.created_at.desc())).first()
        if master is None:
            generate_master_voice(db, project, voice_provider_name, voice_id=voice_id)

    # Materialize real visual assets before composition. Production presenter exports must not
    # silently substitute mock panels when the configured image worker is unavailable.
    visual_assets = {}
    if any(scene.type != "PRESENTER" for scene in project.scenes):
        if settings.aivatar_image_provider == "fal_flux":
            missing_visual_config = ["FAL_API_KEY"] if not settings.fal_api_key else []
            if missing_visual_config:
                raise ValueError("Real supporting-visual generation is unavailable; configure FAL_API_KEY. Mock visual panels are disabled for presenter exports.")
            # fal.ai handles still-image generation; do not plan LTX video scenes on this path.
            from pipeline.assets.service import plan_visual_assets
            plan_visual_assets(db, project, max_ltx_scenes=0)
        else:
            missing_visual_config = [
                name for name, value in {
                    "RUNPOD_API_KEY": settings.runpod_api_key,
                    "RUNPOD_FLUX_ENDPOINT_ID": settings.runpod_flux_endpoint_id,
                    "R2_ACCOUNT_ID": settings.r2_account_id,
                    "R2_ACCESS_KEY_ID": settings.r2_access_key_id,
                    "R2_SECRET_ACCESS_KEY": settings.r2_secret_access_key,
                    "R2_BUCKET": settings.r2_bucket,
                }.items() if not value
            ]
        if missing_visual_config:
            raise ValueError(
                "Real supporting-visual generation is unavailable; configure "
                + ", ".join(missing_visual_config)
                + ". Mock visual panels are disabled for presenter exports."
            )
        generate_visual_assets(db, project, mock=False, force=force)
        visual_assets = {
            asset.scene_id: Path(asset.path)
            for asset in db.scalars(
                select(Asset)
                .where(Asset.project_id == project.id, Asset.kind == "visual")
                .order_by(Asset.created_at.desc())
            ).all()
            if asset.scene_id and Path(asset.path).exists()
        }

    presenter_results = generate_presenter_scenes(
        db,
        project,
        provider_name=settings.aivatar_presenter_provider,
        force=force,
        allow_fallback=False,
    )
    by_scene = {item["scene_id"]: Path(item["path"]) for item in presenter_results}
    dirs = project_dirs(settings.aivatar_workspace, project.id)
    rendered: list[Path] = []
    for scene in project.scenes:
        presenter = by_scene.get(scene.id)
        planned = PlannedScene(
            ordinal=scene.ordinal,
            start=scene.start,
            end=scene.end,
            type=scene.type,
            visual_prompt=scene.visual_prompt or f"Scene {scene.ordinal}",
        )
        visual = None
        if scene.type != "PRESENTER":
            visual = visual_assets.get(scene.id)
            if visual is None:
                raise ValueError(f"No visual asset generated for scene {scene.ordinal}")
        if not presenter:
            if visual is None:
                raise ValueError(f"No presenter clip generated for scene {scene.ordinal}")
            rendered.append(visual)
            continue
        output = dirs["render"] / f"real_scene_{scene.ordinal:03}.mp4"
        compose_presenter_scene(scene.type, presenter, visual, output, scene.end - scene.start)
        rendered.append(output)
    concat = dirs["render"] / "real_concat.txt"
    concat.write_text("\n".join(f"file '{path.resolve()}'" for path in rendered), encoding="utf-8")
    visual = dirs["render"] / "real_timeline.mp4"
    run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(concat), "-c", "copy", str(visual)])
    final = dirs["base"] / "real_final.mp4"
    master = db.scalars(select(Asset).where(Asset.project_id == project.id, Asset.kind == "master_audio").order_by(Asset.created_at.desc())).first()
    if not master:
        raise ValueError("Presenter render has no master audio")
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(visual), "-i", master.path, "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-shortest", str(final)])
    project.state = ProjectState.COMPLETED.value
    project.final_duration = sum(scene.end - scene.start for scene in project.scenes)
    project.error = None
    provider_name = avatar.presenter_provider if avatar else settings.aivatar_presenter_provider
    db.add(RenderHistory(project_id=project.id, output_path=str(final), duration=project.final_duration, width=1920, height=1080, fps=30, qc_json={"mode": provider_name, "voice_provider": voice_provider_name}))
    db.commit()
    return {"final": str(final), "mode": provider_name, "duration": project.final_duration}


def generate_master_voice(db: Session, project: Project, provider_name: str, *, voice_id: str | None = None, source_path: str | None = None) -> dict:
    if project.state == ProjectState.FAILED.value:
        transition(db, project, ProjectState.SCRIPT_READY)
    elif project.state == ProjectState.CREATED.value:
        transition(db, project, ProjectState.SCRIPT_READY)
    if project.state != ProjectState.SCRIPT_READY.value:
        raise ValueError(f"Voice generation requires SCRIPT_READY state; project is {project.state}")
    transition(db, project, ProjectState.VOICE_GENERATING)
    dirs = project_dirs(settings.aivatar_workspace, project.id)
    provider = voice_provider(provider_name)
    kwargs = {"voice_id": voice_id}
    if source_path:
        kwargs["source_path"] = Path(source_path)
    try:
        try:
            result = provider.generate(project.script, project.expected_duration, dirs["audio"], **kwargs)
        except Exception:
            # Keep local production usable when the optional hosted AI33 credential has
            # expired. This is a real macOS TTS export, not a mock/test pattern, and
            # it never sends the script to another provider or creates provider charges.
            if provider_name != "ai33" or not shutil.which("say"):
                raise
            raw = dirs["audio"] / "local_fallback_voice.aiff"
            subprocess.run(["say", "-o", str(raw), project.script], check=True)
            wav, _mp3, duration = normalize_master_audio(raw, dirs["audio"])
            result = ProviderResult(
                path=wav,
                duration=duration,
                provider="macos_say",
                metadata={"fallback_for": "ai33", "reason": "hosted voice provider unavailable"},
            )
        provider_words = (result.metadata or {}).get("provider_word_timestamps")
        words = normalize_provider_timestamps(provider_words, result.duration) if provider_words else []
        source = f"{provider_name}_provider" if words else "heuristic_fallback"
        if not words:
            words = align_script_heuristic(project.script, result.duration)
        timestamps_path = dirs["audio"] / "timestamps.json"
        save_timestamps(timestamps_path, words, source, result.duration)
        segments = caption_segments(words)
        srt = dirs["captions"] / "captions.srt"
        vtt = dirs["captions"] / "captions.vtt"
        write_caption_segments(segments, srt, vtt)
        project.expected_duration = result.duration
        project.error = None
        db.add(Asset(project_id=project.id, kind="master_audio", provider=provider_name, path=str(result.path), duration=result.duration, checksum=sha256(result.path), metadata_json=result.metadata or {}))
        db.add(Asset(project_id=project.id, kind="timestamps", provider=source, path=str(timestamps_path), duration=result.duration, checksum=sha256(timestamps_path), metadata_json={"word_count": len(words)}))
        db.add(Asset(project_id=project.id, kind="captions", provider=source, path=str(srt), duration=result.duration, checksum=sha256(srt), metadata_json={"vtt_path": str(vtt), "segments": len(segments)}))
        db.add(CostEntry(project_id=project.id, provider=provider_name, asset_type="voice", external_cost_usd=result.actual_cost_usd, estimated_cost_usd=result.estimated_cost_usd, actual_cost_usd=result.actual_cost_usd, metadata_json=result.metadata or {}))
        db.commit(); db.refresh(project)
        transition(db, project, ProjectState.VOICE_READY)
        return {"provider": provider_name, "duration": result.duration, "master_audio": str(result.path), "timestamps": str(timestamps_path), "captions_srt": str(srt), "captions_vtt": str(vtt), "timestamp_source": source, "word_count": len(words)}
    except Exception as exc:
        project.state = ProjectState.FAILED.value
        project.error = str(exc)
        db.commit()
        raise
