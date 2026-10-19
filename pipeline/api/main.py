from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.orm import Session
from pipeline.core.config import settings
from pipeline.core.diagnostics import diagnostics
from pipeline.core.services import create_plan, generate_master_voice
from pipeline.assets.service import plan_visual_assets
from pipeline.models.entities import Channel, Avatar, Project, Scene, Job, CostEntry, RenderHistory, AssetCacheEntry, ProductionRun
from pipeline.models.schemas import ChannelCreate, AvatarCreate, ProjectCreate, SceneUpdate, VoiceGenerateRequest, PresenterGenerateRequest, PresenterBatchRequest, ScenePreviewRequest, VisualPlanRequest, AssetGenerateRequest, ProjectLockRequest, ProjectUnlockRequest, CleanupRequest, CachePruneRequest
from pipeline.queue.manager import job_manager
from pipeline.storage.db import get_db
from pipeline.storage.migrate import migrate
from pipeline.render.scene_preview import render_scene_preview
from pipeline.queue.resources import resource_limits
from pipeline.production.locks import acquire_project_lock, release_project_lock, assert_project_editable
from pipeline.production.storage import cleanup_project_intermediates, prune_asset_cache, workspace_usage
from pipeline.activation.readiness import activation_status
from pipeline.reference.profiles import get_reference_profile, list_reference_profiles

@asynccontextmanager
async def lifespan(app: FastAPI):
    migrate(); job_manager.recover_interrupted(); yield

app=FastAPI(title="Aivatar Pipeline API", version="0.6.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:1420","http://127.0.0.1:1420"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

def obj(x):
    if x is None: return None
    keys=[c.name for c in x.__table__.columns]
    return {k:getattr(x,k) for k in keys}

@app.get("/health")
def health(): return {"ok": True, "service": "aivatar-pipeline", "version": "0.6.0", "mode": "production-activation"}

@app.get("/diagnostics")
def get_diagnostics(): return diagnostics()

@app.get("/activation/status")
def get_activation_status():
    return activation_status()

@app.get("/reference-profiles")
def reference_profiles():
    return list_reference_profiles()

@app.get("/reference-profiles/{profile_id}")
def reference_profile(profile_id: str):
    try:
        return get_reference_profile(profile_id)
    except KeyError as exc:
        raise HTTPException(404, "Reference profile not found") from exc

@app.get("/providers")
def providers():
    return {
      "voice":[{"id":"ai33","status":"configured" if settings.ai33_api_key and settings.ai33_api_base_url else "not_configured","role":"primary"},{"id":"69labs","status":"configured" if settings.sixty_nine_labs_api_key and settings.sixty_nine_labs_api_base_url else "not_configured","role":"alternate"},{"id":"imported_audio","status":"ready","role":"local"},{"id":"mock_voice","status":"ready","role":"development"}],
      "presenter":[{"id":"authorized_higgsfield","status":"configured" if settings.higgsfield_api_key else "not_configured","role":"primary","model":settings.higgsfield_model},{"id":"authorized_heygen","status":"configured" if settings.heygen_api_key else "not_configured","role":"fallback","api_mode":settings.heygen_api_mode},{"id":"musetalk_fallback","status":"remote_worker_required","role":"fallback"},{"id":"manual_presenter_import","status":"ready","role":"fallback"},{"id":"mock_presenter","status":"ready","role":"development"}],
      "images":[{"id":"fal_flux","status":"configured" if settings.fal_api_key else "configuration_required","model_family":settings.fal_model},{"id":"flux_klein","status":"configured" if settings.runpod_api_key and settings.runpod_flux_endpoint_id and settings.r2_account_id else "configuration_required","model_family":settings.aivatar_flux_model},{"id":"mock_image","status":"ready"}],
      "video":[{"id":"ltx_2_3","status":"configured" if settings.runpod_api_key and settings.runpod_ltx_endpoint_id and settings.r2_account_id else "configuration_required","model_family":settings.aivatar_ltx_model,"checkpoint":settings.aivatar_ltx_checkpoint},{"id":"mock_video","status":"ready"}],
    }


@app.get("/infrastructure")
def infrastructure():
    return {
        "heygen": {
            "configured": bool(settings.heygen_api_key),
            "api_mode": settings.heygen_api_mode,
            "v3_engine": settings.heygen_v3_engine,
        },
        "higgsfield": {
            "configured": bool(settings.higgsfield_api_key),
            "model": settings.higgsfield_model,
            "api_base_url": settings.higgsfield_api_base_url,
            "selected_presenter_provider": settings.aivatar_presenter_provider,
        },
        "runpod": {
            "configured": bool(settings.runpod_api_key),
            "flux_endpoint_configured": bool(settings.runpod_flux_endpoint_id),
            "ltx_endpoint_configured": bool(settings.runpod_ltx_endpoint_id),
            "musetalk_endpoint_configured": bool(settings.runpod_musetalk_endpoint_id),
        },
        "r2": {
            "configured": bool(settings.r2_account_id and settings.r2_access_key_id and settings.r2_secret_access_key),
            "bucket": settings.r2_bucket,
        },
        "models": {
            "flux": settings.aivatar_flux_model,
            "ltx": settings.aivatar_ltx_model,
            "ltx_checkpoint": settings.aivatar_ltx_checkpoint,
            "ltx_pipeline": settings.aivatar_ltx_pipeline,
            "ltx_quantization": settings.aivatar_ltx_quantization,
        },
        "optimization": {
            "default_project_budget_usd": settings.aivatar_default_project_budget_usd,
            "visual_budget_fraction": settings.aivatar_visual_budget_fraction,
            "ltx_motion_threshold": settings.aivatar_ltx_motion_threshold,
            "max_ltx_scenes": settings.aivatar_max_ltx_scenes,
            "max_ltx_scene_seconds": settings.aivatar_max_ltx_scene_seconds,
            "asset_cache_enabled": settings.aivatar_asset_cache_enabled,
        },
        "resource_usage": resource_limits.snapshot(),
        "limits": {
            "projects": settings.aivatar_max_project_jobs,
            "image_gpu": settings.aivatar_max_image_gpu_jobs,
            "video_gpu": settings.aivatar_max_video_gpu_jobs,
            "presenter": settings.aivatar_max_presenter_jobs,
            "ffmpeg": settings.aivatar_max_ffmpeg_jobs,
        },
    }

@app.post("/channels")
def create_channel(payload: ChannelCreate, db: Session=Depends(get_db)):
    c=Channel(name=payload.name, style_preset=payload.style_preset, settings_json=payload.settings_json); db.add(c)
    try: db.commit()
    except Exception as exc: db.rollback(); raise HTTPException(409,"Channel name already exists") from exc
    db.refresh(c); return obj(c)

@app.get("/channels")
def channels(db: Session=Depends(get_db)):
    return [obj(x) for x in db.scalars(select(Channel).order_by(Channel.created_at.desc())).all()]

@app.post("/avatars")
def create_avatar(payload: AvatarCreate, db: Session=Depends(get_db)):
    if not db.get(Channel,payload.channel_id): raise HTTPException(404,"Channel not found")
    a=Avatar(**payload.model_dump()); db.add(a); db.commit(); db.refresh(a); return obj(a)

@app.get("/avatars")
def avatars(channel_id: str | None=None, db: Session=Depends(get_db)):
    q=select(Avatar).order_by(Avatar.created_at.desc())
    if channel_id: q=q.where(Avatar.channel_id==channel_id)
    return [obj(x) for x in db.scalars(q).all()]

@app.post("/projects")
def create_project(payload: ProjectCreate, db: Session=Depends(get_db)):
    if not db.get(Channel,payload.channel_id): raise HTTPException(404,"Channel not found")
    if payload.avatar_id:
        avatar = db.get(Avatar,payload.avatar_id)
        if not avatar: raise HTTPException(404,"Avatar not found")
        if avatar.channel_id != payload.channel_id: raise HTTPException(422,"Avatar belongs to another channel")
    p=Project(**payload.model_dump(), state="CREATED"); db.add(p); db.commit(); db.refresh(p); return obj(p)

@app.get("/projects")
def projects(db: Session=Depends(get_db)):
    return [obj(x) for x in db.scalars(select(Project).order_by(Project.created_at.desc())).all()]

@app.get("/projects/{project_id}")
def project(project_id: str, db: Session=Depends(get_db)):
    p=db.get(Project,project_id)
    if not p: raise HTTPException(404,"Project not found")
    data=obj(p); data["scenes"]=[obj(s) for s in p.scenes]; data["final_mp4"]=str(settings.aivatar_workspace/"projects"/p.id/"final.mp4") if (settings.aivatar_workspace/"projects"/p.id/"final.mp4").exists() else None
    return data

@app.post("/projects/{project_id}/voice")
def generate_voice(project_id: str, payload: VoiceGenerateRequest, db: Session=Depends(get_db)):
    p=db.get(Project,project_id)
    if not p: raise HTTPException(404,"Project not found")
    try:
        return generate_master_voice(db,p,payload.provider,voice_id=payload.voice_id,source_path=payload.source_path)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(409,str(exc)) from exc

@app.post("/projects/{project_id}/plan")
def plan(project_id: str, db: Session=Depends(get_db)):
    p=db.get(Project,project_id)
    if not p: raise HTTPException(404,"Project not found")
    try: rows=create_plan(db,p)
    except ValueError as exc: raise HTTPException(409,str(exc)) from exc
    return {"project_id":p.id,"presenter_actual":p.presenter_actual,"scenes":[obj(s) for s in rows]}

@app.post("/projects/{project_id}/visual-plan")
def visual_plan(project_id: str, payload: VisualPlanRequest, db: Session=Depends(get_db)):
    p=db.get(Project,project_id)
    if not p: raise HTTPException(404,"Project not found")
    if payload.budget_usd is not None:
        p.budget_usd=payload.budget_usd; db.commit(); db.refresh(p)
    try:
        return plan_visual_assets(db,p,max_ltx_scenes=payload.max_ltx_scenes)
    except ValueError as exc:
        raise HTTPException(409,str(exc)) from exc

@app.post("/projects/{project_id}/assets")
def generate_assets(project_id: str, payload: AssetGenerateRequest, db: Session=Depends(get_db)):
    p=db.get(Project,project_id)
    if not p: raise HTTPException(404,"Project not found")
    if not p.scenes: raise HTTPException(409,"Project must be planned first")
    return {"job_id":job_manager.enqueue_asset_batch(project_id,mock=payload.mock,force=payload.force),"state":"QUEUED"}

@app.get("/projects/{project_id}/optimization")
def optimization(project_id: str, db: Session=Depends(get_db)):
    p=db.get(Project,project_id)
    if not p: raise HTTPException(404,"Project not found")
    scenes=[obj(s) for s in p.scenes]
    return {
        "project_id":p.id,"budget_usd":p.budget_usd,"estimated_cost_usd":p.estimated_cost_usd,
        "actual_cost_usd":p.actual_cost_usd,"resource_usage":resource_limits.snapshot(),"scenes":scenes
    }

@app.get("/cache")
def cache_entries(db: Session=Depends(get_db)):
    rows=db.scalars(select(AssetCacheEntry).order_by(AssetCacheEntry.last_used_at.desc()).limit(200)).all()
    return {
        "count":len(rows),
        "size_bytes":sum(row.size_bytes for row in rows),
        "saved_generations":sum(row.hit_count for row in rows),
        "entries":[obj(row) for row in rows],
    }

@app.patch("/scenes/{scene_id}")
def update_scene(scene_id: str, payload: SceneUpdate, x_aivatar_operator: str | None = Header(default=None), db: Session=Depends(get_db)):
    s=db.get(Scene,scene_id)
    if not s: raise HTTPException(404,"Scene not found")
    project=db.get(Project,s.project_id)
    if not project: raise HTTPException(404,"Project not found")
    try:
        assert_project_editable(project,x_aivatar_operator)
    except ValueError as exc:
        raise HTTPException(423,str(exc)) from exc
    for k,v in payload.model_dump(exclude_none=True).items(): setattr(s,k,v)
    if s.end <= s.start: raise HTTPException(422,"Scene end must be greater than start")
    db.commit(); db.refresh(s); return obj(s)


@app.post("/projects/{project_id}/presenters")
def generate_presenters(project_id: str, payload: PresenterBatchRequest, db: Session=Depends(get_db)):
    project=db.get(Project,project_id)
    if not project: raise HTTPException(404,"Project not found")
    if not project.avatar_id and (payload.provider or "") not in {"mock_presenter"}:
        raise HTTPException(409,"Project has no selected avatar")
    return {
        "job_id": job_manager.enqueue_presenter_batch(
            project_id, provider=payload.provider, force=payload.force, allow_fallback=payload.allow_fallback
        ),
        "state": "QUEUED",
    }

@app.post("/scenes/{scene_id}/presenter")
def generate_scene_presenter(scene_id: str, payload: PresenterGenerateRequest, db: Session=Depends(get_db)):
    scene=db.get(Scene,scene_id)
    if not scene: raise HTTPException(404,"Scene not found")
    project=db.get(Project,scene.project_id)
    if not project: raise HTTPException(404,"Project not found")
    if scene.type not in {"PRESENTER","SPLIT","PIP"}:
        raise HTTPException(409,"Scene does not contain a presenter")
    return {
        "job_id": job_manager.enqueue_presenter_scene(
            project.id, scene.id, provider=payload.provider, force=payload.force,
            allow_fallback=payload.allow_fallback, manual_clip_path=payload.manual_clip_path
        ),
        "state": "QUEUED",
    }

@app.post("/scenes/{scene_id}/preview")
def preview_scene(scene_id: str, payload: ScenePreviewRequest, db: Session=Depends(get_db)):
    scene=db.get(Scene,scene_id)
    if not scene: raise HTTPException(404,"Scene not found")
    project=db.get(Project,scene.project_id)
    if not project: raise HTTPException(404,"Project not found")
    try:
        path=render_scene_preview(db,project,scene,visual_path=payload.visual_path,force=payload.force)
    except (ValueError,FileNotFoundError) as exc:
        raise HTTPException(409,str(exc)) from exc
    return {"scene_id":scene.id,"preview":str(path),"render_hash":scene.render_hash}

@app.post("/projects/{project_id}/render-mock")
def render_mock(project_id: str, db: Session=Depends(get_db)):
    if not db.get(Project,project_id): raise HTTPException(404,"Project not found")
    return {"job_id":job_manager.enqueue_mock_render(project_id),"state":"QUEUED"}

@app.post("/projects/{project_id}/render-presenter")
def render_presenter(project_id: str, force: bool = False, db: Session=Depends(get_db)):
    if not db.get(Project, project_id):
        raise HTTPException(404, "Project not found")
    return {"job_id": job_manager.enqueue_presenter_render(project_id, force=force), "state": "QUEUED", "force": force}

@app.get("/jobs")
def jobs(db: Session=Depends(get_db)):
    rows = []
    for job in db.scalars(select(Job).order_by(Job.created_at.desc()).limit(100)).all():
        payload = obj(job)
        if job.state == "COMPLETED" and job.project_id:
            render = db.scalars(
                select(RenderHistory)
                .where(RenderHistory.project_id == job.project_id)
                .order_by(RenderHistory.created_at.desc())
            ).first()
            if render:
                payload["output_asset_id"] = render.id
        rows.append(payload)
    return rows

@app.get("/assets/{asset_id}")
def asset_content(asset_id: str, db: Session=Depends(get_db)):
    render = db.get(RenderHistory, asset_id)
    if not render:
        raise HTTPException(404, "Asset not found")
    path = Path(render.output_path)
    if not path.is_absolute():
        # Render history stores paths relative to the process working directory
        # (for example, ``workspace/projects/...``), while the configured
        # workspace may itself point at that ``workspace`` directory.
        path = (settings.aivatar_workspace.parent / path
                if path.parts and path.parts[0] == settings.aivatar_workspace.name
                else settings.aivatar_workspace / path)
    if not path.exists():
        raise HTTPException(404, "Rendered file not found")
    return FileResponse(path, media_type="video/mp4", filename=f"{render.id}.mp4")

@app.get("/projects/{project_id}/costs")
def costs(project_id: str, db: Session=Depends(get_db)):
    return [obj(x) for x in db.scalars(select(CostEntry).where(CostEntry.project_id==project_id).order_by(CostEntry.created_at.desc())).all()]

@app.get("/projects/{project_id}/renders")
def renders(project_id: str, db: Session=Depends(get_db)):
    return [obj(x) for x in db.scalars(select(RenderHistory).where(RenderHistory.project_id==project_id).order_by(RenderHistory.created_at.desc())).all()]


@app.post("/projects/{project_id}/lock")
def lock_project(project_id: str, payload: ProjectLockRequest, db: Session=Depends(get_db)):
    project=db.get(Project,project_id)
    if not project: raise HTTPException(404,"Project not found")
    try:
        return acquire_project_lock(db,project,payload.owner,payload.ttl_seconds)
    except ValueError as exc:
        raise HTTPException(409,str(exc)) from exc


@app.post("/projects/{project_id}/unlock")
def unlock_project(project_id: str, payload: ProjectUnlockRequest, db: Session=Depends(get_db)):
    project=db.get(Project,project_id)
    if not project: raise HTTPException(404,"Project not found")
    try:
        release_project_lock(db,project,payload.owner,force=payload.force)
    except ValueError as exc:
        raise HTTPException(409,str(exc)) from exc
    return {"project_id":project.id,"locked":False}


@app.post("/projects/{project_id}/cleanup")
def cleanup_project(project_id: str, payload: CleanupRequest, db: Session=Depends(get_db)):
    project=db.get(Project,project_id)
    if not project: raise HTTPException(404,"Project not found")
    report=cleanup_project_intermediates(settings.aivatar_workspace,project.id,keep_final=payload.keep_final)
    return {"project_id":project.id,**report.as_dict()}


@app.get("/storage")
def storage_status(db: Session=Depends(get_db)):
    return workspace_usage(db,settings.aivatar_workspace)


@app.post("/cache/prune")
def prune_cache(payload: CachePruneRequest, db: Session=Depends(get_db)):
    report=prune_asset_cache(db,older_than_days=payload.older_than_days,max_bytes=payload.max_bytes,dry_run=payload.dry_run)
    return report.as_dict()


@app.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str):
    if not job_manager.cancel(job_id):
        raise HTTPException(409,"Job could not be cancelled")
    return {"job_id":job_id,"cancel_requested":True}


@app.post("/jobs/{job_id}/retry")
def retry_job(job_id: str):
    if not job_manager.retry(job_id):
        raise HTTPException(409,"Job is not retryable or has reached its retry limit")
    return {"job_id":job_id,"state":"QUEUED"}


@app.get("/projects/{project_id}/production-runs")
def production_runs(project_id: str, db: Session=Depends(get_db)):
    if not db.get(Project,project_id): raise HTTPException(404,"Project not found")
    rows=db.scalars(select(ProductionRun).where(ProductionRun.project_id==project_id).order_by(ProductionRun.started_at.desc())).all()
    return [obj(x) for x in rows]

from pipeline.studio.api import router as studio_router
app.include_router(studio_router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("pipeline.api.main:app", host="127.0.0.1", port=8765, reload=False)
