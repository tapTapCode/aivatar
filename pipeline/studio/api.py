"""Local Channel Studio API: persisted profiles, review, approval and exports."""
import json
import math
import shutil
from pathlib import Path
from threading import Lock
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from pipeline.core.config import settings
from pipeline.models.entities import Channel, Avatar, Project, Job, RenderHistory, CostEntry
from pipeline.storage.db import get_db
from pipeline.models.schemas import AvatarCreate
from pipeline.studio.planning import ProductionOptions, build_plan
from pipeline.studio.commercial import router as commercial_router, commercial_status

router = APIRouter(prefix="/studio", tags=["Channel Studio"])
_submission_lock = Lock()
router.include_router(commercial_router)


def row(item):
    return {column.name: getattr(item, column.name) for column in item.__table__.columns}


def preflight(options: ProductionOptions, db: Session) -> dict:
    channel = db.get(Channel, options.channel_id)
    if not channel:
        raise HTTPException(404, "Channel not found")
    avatar = db.get(Avatar, options.avatar_id) if options.avatar_id else None
    if options.avatar_id and (not avatar or avatar.channel_id != channel.id):
        raise HTTPException(422, "Choose a character belonging to this channel")
    plan = build_plan(options)
    blockers, warnings = [], []
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        blockers.append("Install FFmpeg and ffprobe on the machine running Aivatar.")
    if options.music_path and not Path(options.music_path).is_file():
        blockers.append("The selected music file is missing on the Aivatar machine.")
    if options.mode == "demo":
        warnings.append("Demo renders use test patterns and a tone, not AI speech or realistic characters. No provider calls.")
    else:
        if options.narration_path:
            if not Path(options.narration_path).is_file():
                blockers.append("The narration file is missing.")
        else:
            voice = avatar.voice_provider if avatar else (channel.settings_json or {}).get("voice_provider", "ai33")
            voice_ready = {"ai33": bool(settings.ai33_api_key and settings.ai33_api_base_url),
                           "69labs": bool(settings.sixty_nine_labs_api_key and settings.sixty_nine_labs_api_base_url)}
            if not voice_ready.get(voice):
                blockers.append(f"Configure {voice} speech credentials and endpoint, or upload narration.")
        if plan["presenter_seconds"] > 0 and avatar:
            if not (avatar.settings_json or {}).get("consent_confirmed"):
                blockers.append("Save the character with permission to use its likeness and voice confirmed.")
            if avatar.presenter_provider == "authorized_heygen":
                if not settings.heygen_api_key or not avatar.provider_avatar_id:
                    blockers.append("Configure HeyGen and set a valid account avatar ID.")
            elif avatar.presenter_provider == "authorized_higgsfield":
                if not settings.higgsfield_api_key:
                    blockers.append("Configure HIGGSFIELD_API_KEY on the server.")
                if not avatar.reference_image_path or not Path(avatar.reference_image_path).is_file():
                    blockers.append("Upload a character reference image.")
            else:
                blockers.append("Automatic production currently supports HeyGen or Higgsfield presenters.")
        if any(s["type"] != "PRESENTER" for s in plan["scenes"]):
            if settings.aivatar_image_provider == "fal_flux":
                ready = bool(settings.fal_api_key)
            else:
                ready = bool(settings.runpod_api_key and settings.runpod_flux_endpoint_id and settings.r2_account_id
                             and settings.r2_access_key_id and settings.r2_secret_access_key)
            if not ready:
                blockers.append("Configure the selected supporting-image provider (fal.ai or RunPod with R2).")
        warnings.append("Provider pricing and duration can vary. Budget is a local planning guard, not a provider billing cap.")
    # Existing presenter adapter uses a conservative per-call minute estimate. Never label it a quotation.
    presenter_estimate = sum(4 * math.ceil((s['end'] - s['start']) / 60)
                             for s in plan['scenes'] if s['type'] != 'FULL_VISUAL') if options.mode == 'production' else 0
    if presenter_estimate > options.budget_usd:
        blockers.append(f"The existing presenter guard estimates ${presenter_estimate:.2f}; increase the budget or reduce presenter coverage.")
    return {**plan, "blockers": blockers, "warnings": warnings, "ready": not blockers,
            "presenter_guard_estimate_usd": presenter_estimate,
            "total_cost_usd": None, "cost_note": "Voice and visual costs are not quoted. Actual usage appears when providers report it."}


@router.get("/workspace")
def workspace(db: Session = Depends(get_db)):
    projects = list(db.scalars(select(Project).order_by(Project.created_at.desc())).all())
    commercial = commercial_status(db)
    return {"channels": [row(c) for c in db.scalars(select(Channel).order_by(Channel.created_at)).all()],
            "characters": [row(a) for a in db.scalars(select(Avatar).order_by(Avatar.created_at)).all()],
            "projects": [row(p) for p in projects],
            "jobs": [row(j) for j in db.scalars(select(Job).order_by(Job.created_at.desc()).limit(100)).all()],
            "usage": {"finished_minutes": round(sum((p.final_duration or 0) / 60 for p in projects if p.state == "COMPLETED"), 2),
                      "reported_cost_usd": round(sum(c.actual_cost_usd for c in db.scalars(select(CostEntry)).all()), 4),
                      "cost_note": "Provider-reported amounts only; zero can mean unreported.",
                      "concurrent_projects": settings.aivatar_max_project_jobs},
            "deployment": "local", "billing_enabled": commercial["features"]["stripe_subscriptions"],
            "remote_team_access": commercial["features"]["team_roles"], "commercial": commercial}


@router.post("/plan")
def review(options: ProductionOptions, db: Session = Depends(get_db)):
    return preflight(options, db)


@router.post("/productions")
def save_production(options: ProductionOptions, db: Session = Depends(get_db)):
    review = preflight(options, db)
    # Drafts may be saved before credentials are configured; no provider requests happen here.
    p = Project(channel_id=options.channel_id, avatar_id=options.avatar_id, name=options.name,
                script=options.script, expected_duration=review["duration"], presenter_target=options.presenter_target,
                resolution=options.resolution, aspect_ratio=options.aspect_ratio, budget_usd=options.budget_usd,
                production_json=options.model_dump(), state="CREATED")
    db.add(p); db.commit(); db.refresh(p)
    return {"project": row(p), "review": review}


class Approval(BaseModel):
    approved: bool


@router.post("/productions/{project_id}/generate")
def generate(project_id: str, approval: Approval, db: Session = Depends(get_db)):
    from pipeline.queue.manager import job_manager
    if not approval.approved:
        raise HTTPException(422, "Review and approve the production first")
    with _submission_lock:
        p = db.get(Project, project_id)
        if not p or not p.production_json:
            raise HTTPException(404, "Channel Studio production not found")
        active = db.scalars(select(Job).where(Job.project_id == p.id, Job.state.in_(["QUEUED", "RUNNING"]))).first()
        if active:
            return {"job_id": active.id, "state": active.state, "reused": True}
        if p.state == "COMPLETED":
            raise HTTPException(409, "This production is complete. Save a new draft to create another version.")
        review = preflight(ProductionOptions(**p.production_json), db)
        if review["blockers"]:
            raise HTTPException(409, "; ".join(review["blockers"]))
        return {"job_id": job_manager.enqueue_studio_render(p.id), "state": "QUEUED", "reused": False}


@router.get("/productions/{project_id}")
def production(project_id: str, db: Session = Depends(get_db)):
    p = db.get(Project, project_id)
    if not p:
        raise HTTPException(404, "Project not found")
    return {"project": row(p), "scenes": [row(s) for s in p.scenes],
            "jobs": [row(j) for j in db.scalars(select(Job).where(Job.project_id == p.id).order_by(Job.created_at.desc())).all()],
            "renders": [row(r) for r in db.scalars(select(RenderHistory).where(RenderHistory.project_id == p.id).order_by(RenderHistory.created_at.desc())).all()]}


@router.get("/productions/{project_id}/files/{kind}")
def download(project_id: str, kind: str, db: Session = Depends(get_db)):
    if not db.get(Project, project_id):
        raise HTTPException(404, "Project not found")
    allowed = {"video": ("final.mp4", "video/mp4"), "captions": ("captions/captions.srt", "application/x-subrip"),
               "plan": ("production-plan.json", "application/json")}
    if kind not in allowed:
        raise HTTPException(404, "Unknown export")
    relative, media_type = allowed[kind]
    base = (settings.aivatar_workspace / "projects" / project_id).resolve()
    path = base / relative
    if not path.is_file():
        raise HTTPException(404, "Export is not ready")
    return FileResponse(path, media_type=media_type, filename=f"aivatar-{project_id[:8]}-{path.name}")


class ProfileUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    settings_json: dict = Field(default_factory=dict)


@router.patch("/channels/{channel_id}")
def update_channel(channel_id: str, payload: ProfileUpdate, db: Session = Depends(get_db)):
    c = db.get(Channel, channel_id)
    if not c: raise HTTPException(404, "Channel not found")
    c.name = payload.name.strip()
    if not c.name: raise HTTPException(422, "Channel name is required")
    c.settings_json = {**(c.settings_json or {}), **payload.settings_json}
    try: db.commit()
    except Exception as exc:
        db.rollback(); raise HTTPException(409, "Channel name is already used") from exc
    return row(c)


@router.post("/uploads/{kind}")
async def upload(kind: str, request: Request):
    """Stream locally, validate the media, return a managed path. No third party transfer."""
    from uuid import uuid4
    from pipeline.render.ffmpeg import ffprobe
    extensions = {"image": {".png", ".jpg", ".jpeg", ".webp"}, "music": {".mp3", ".wav", ".m4a"},
                  "narration": {".mp3", ".wav", ".m4a"}}
    if kind not in extensions: raise HTTPException(422, "Unsupported upload kind")
    suffix = Path(request.headers.get("X-Filename", "")).suffix.lower()
    if suffix not in extensions[kind]: raise HTTPException(422, "Unsupported media extension")
    directory = settings.aivatar_workspace / "uploads"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (str(uuid4()) + suffix)
    size = 0
    try:
        with path.open("wb") as handle:
            async for chunk in request.stream():
                size += len(chunk)
                if size > 100 * 1024 * 1024: raise HTTPException(413, "Media must be smaller than 100 MB")
                handle.write(chunk)
        info = ffprobe(path)
        expected = "video" if kind == "video" else ("audio" if kind in {"music", "narration"} else "image")
        streams = [s for s in info.get("streams", []) if s.get("codec_type") == expected]
        if not streams or (kind == "image" and not all(s.get("width", 0) > 0 and s.get("height", 0) > 0 for s in streams)):
            raise ValueError("Wrong media type")
    except Exception as exc:
        path.unlink(missing_ok=True)
        if isinstance(exc, HTTPException): raise
        raise HTTPException(422, "The file is not valid supported media") from exc
    return {"path": str(path.resolve()), "name": request.headers.get("X-Filename", path.name), "size": size}


@router.put("/characters/{character_id}")
def update_character(character_id: str, payload: AvatarCreate, db: Session = Depends(get_db)):
    avatar = db.get(Avatar, character_id)
    if not avatar: raise HTTPException(404, "Character not found")
    if avatar.channel_id != payload.channel_id:
        raise HTTPException(422, "A character cannot be moved between channels")
    project_ids = select(Project.id).where(Project.avatar_id == avatar.id)
    if db.scalars(select(Job).where(Job.project_id.in_(project_ids), Job.state.in_(["QUEUED", "RUNNING"]))).first():
        raise HTTPException(409, "Wait until this character's running productions finish before editing it")
    for key, value in payload.model_dump().items(): setattr(avatar, key, value)
    db.commit(); db.refresh(avatar)
    return row(avatar)


class CharacterImage(BaseModel):
    prompt: str = Field(min_length=10, max_length=2000)
    approved: bool


@router.post("/character-image")
def generate_character_image(payload: CharacterImage):
    from uuid import uuid4
    from pipeline.providers.registry import image_provider
    from pipeline.queue.resources import resource_limits
    if not payload.approved: raise HTTPException(422, "Approve the image provider charge first")
    if settings.aivatar_image_provider not in {"fal_flux", "flux_klein"}:
        raise HTTPException(409, "Configure a production image provider")
    output = settings.aivatar_workspace / "characters" / str(uuid4())
    try:
        with resource_limits.reserve("image_gpu"):
            result = image_provider(settings.aivatar_image_provider).generate(
                f"{payload.prompt}. Single original adult character, front-facing portrait, clear face, natural skin texture, no text, no watermark.",
                output, width=1024, height=1024)
    except Exception as exc:
        raise HTTPException(409, "Character generation failed. Check the configured image provider and server logs.") from exc
    return {"path": str(result.path.resolve()), "provider": result.provider,
            "reported_cost_usd": result.actual_cost_usd}


@router.get("/characters/{character_id}/image")
def character_image(character_id: str, db: Session = Depends(get_db)):
    avatar = db.get(Avatar, character_id)
    if not avatar or not avatar.reference_image_path:
        raise HTTPException(404, "Character has no reference image")
    path = Path(avatar.reference_image_path)
    if not path.is_file() or path.suffix.lower() not in {'.png','.jpg','.jpeg','.webp'}:
        raise HTTPException(404, "Reference image is unavailable")
    return FileResponse(path)

