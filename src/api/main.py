from __future__ import annotations

import asyncio
import shutil
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.responses import (
    FileResponse,
    JSONResponse,
    PlainTextResponse,
    RedirectResponse,
    Response,
)

from src.api.config import get_settings
from src.api.control_plane_models import ControlPlaneJob, ControlPlaneProject
from src.api.durable_repository import DurableControlPlaneRepository
from src.api.media_registry import AuthorizedMediaRegistry, MediaKind, RegisteredMedia
from src.api.models import (
    CostLedgerResponse,
    CreateVideoResponse,
    HealthResponse,
    HeyGenAvatarOption,
    HeyGenAvatarRequest,
    HeyGenCatalogResponse,
    HeyGenVoiceOption,
)
from src.api.provider_factory import (
    build_provider_set,
    lipsync_mode,
    local_avatar_proof_available,
    resolved_local_avatar_image,
    resolved_local_avatar_proof,
)
from src.api.repository import ControlPlaneRepository
from src.api.security import SlidingWindowRateLimiter
from src.auth.database import AuthDatabase
from src.auth.mailer import AuthMailer
from src.auth.oauth import OAuthService
from src.auth.repository import AuthRepository
from src.auth.router import AuthContext, create_auth_router
from src.dispatch.modal import ModalJobDispatcher, verify_signature
from src.orchestration.consent import missing_consents
from src.orchestration.cost import (
    actual_job_cost_usd,
    build_cost_ledger,
    estimate_control_plane_job,
    job_has_proof_replay,
)
from src.orchestration.heygen_export import (
    HeyGenExportPending,
    export_heygen_presenter,
    is_heygen_presenter_project,
)
from src.orchestration.pipeline import PipelineOrchestrator
from src.orchestration.routing import (
    UnlicensedWatermarkException,
    plan_scene,
    validate_provider_routing,
)
from src.orchestration.state_machine import TERMINAL_STATES, JobStateMachine
from src.orchestration.templates import TemplateLoader
from src.providers.base import ProviderError
from src.providers.common import canonical_hash
from src.providers.heygen import HeyGenLipSyncGenerator, estimate_project_avatar_cost
from src.queue.base import JobMessage
from src.queue.memory import InMemoryJobQueue
from src.queue.redis_queue import RedisJobQueue
from src.rendering import FFmpegSceneRenderer, TimelineAssembler, probe_media, validate_output
from src.schemas.assets import GeneratedAsset, PublicAsset
from src.schemas.jobs import CostEntry, JobRecord, JobState
from src.schemas.scene import ProjectScript
from src.storage.cleanup import cleanup_expired_files
from src.storage.local import LocalAssetStore
from src.storage.repository import AssetRepository
from src.storage.s3 import S3RetentionStore
from src.telemetry.logging import configure_logging, get_logger
from src.telemetry.metrics import MetricsRegistry

settings = get_settings()
configure_logging(settings.log_level)
logger = get_logger("api")

auth_database = AuthDatabase(settings.database_url)
auth_repository = AuthRepository(
    auth_database,
    superadmin_emails={
        email.strip().casefold()
        for email in settings.superadmin_emails.split(",")
        if email.strip()
    },
)
auth_mailer = AuthMailer(
    api_key=settings.resend_api_key,
    from_email=settings.resend_from_email,
    base_url=settings.app_base_url,
)
auth_context = AuthContext(settings, auth_repository)
oauth_service = OAuthService(settings, auth_repository)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if settings.auth_auto_migrate:
        await auth_database.create_schema()
    if isinstance(repository, DurableControlPlaneRepository):
        await repository.ensure_schema()
    yield


app = FastAPI(title="Aivatar Video Pipeline", version="1.0.0", lifespan=lifespan)
app.include_router(
    create_auth_router(
        settings,
        auth_repository,
        auth_mailer,
        oauth_service,
        auth_context,
    )
)


@app.exception_handler(UnlicensedWatermarkException)
async def unlicensed_watermark_handler(
    _request: Request, error: UnlicensedWatermarkException
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"error": error.error, "message": error.message},
    )


def _build_repository() -> ControlPlaneRepository | DurableControlPlaneRepository:
    if settings.control_plane_backend == "database" or settings.database_url.startswith(
        ("postgres://", "postgresql")
    ):
        return DurableControlPlaneRepository(auth_database)
    return ControlPlaneRepository()


repository = _build_repository()
_ = (ControlPlaneProject, ControlPlaneJob)
asset_repository = AssetRepository()
queue = (
    RedisJobQueue(settings.redis_url) if settings.queue_backend == "redis" else InMemoryJobQueue()
)
metrics = MetricsRegistry()
state_machine = JobStateMachine()
template_loader = TemplateLoader(settings.template_root)
asset_store = LocalAssetStore(settings.local_storage_root)
media_registry = AuthorizedMediaRegistry(
    settings.media_registry_root,
    max_bytes=settings.media_upload_max_bytes,
    presenter_root=settings.avatar_registry_root,
    voice_root=settings.voice_registry_root,
)
renderer = FFmpegSceneRenderer()
final_retention_store = (
    S3RetentionStore(
        endpoint_url=settings.s3_endpoint_url,
        bucket=settings.s3_bucket,
        access_key_id=settings.s3_access_key,
        secret_access_key=settings.s3_secret_key,
        prefix=settings.final_video_r2_prefix,
    )
    if settings.storage_backend == "r2"
    else None
)


def public_job_error(error: Exception) -> Exception:
    """Return a customer-safe error while the original stays in server logs."""

    if isinstance(error, ProviderError):
        return RuntimeError("Presenter rendering failed. Please retry the job.")
    return RuntimeError("Video production failed. Please retry the job.")


provider_set = build_provider_set(settings, renderer)
pipeline = PipelineOrchestrator(
    provider_set,
    work_root=settings.work_root,
)
assembler = TimelineAssembler()
limiter = SlidingWindowRateLimiter(settings.api_rate_limit_per_minute)
modal_dispatcher = (
    ModalJobDispatcher(
        endpoint_url=settings.modal_dispatch_url,
        dispatch_secret=settings.modal_dispatch_secret or "",
        callback_url=settings.modal_callback_url,
    )
    if settings.background_runner == "modal"
    else None
)


async def owner_dependency(request: Request) -> str:
    owner_id = await auth_context.owner_id(request)
    limiter.check(owner_id)
    return owner_id


OwnerId = Annotated[str, Depends(owner_dependency)]


def _script_fingerprint(project: ProjectScript) -> str:
    payload = project.model_dump(mode="json")
    payload.pop("approval_state", None)
    return canonical_hash(payload)


def _in_process_local_proof() -> bool:
    return lipsync_mode(settings) == "in_process_approved"


def _runtime_health(status: str) -> HealthResponse:
    return HealthResponse(
        status=status,
        avatar_video_provider=settings.avatar_video_provider,
        lipsync_mode=lipsync_mode(settings),
        local_proof_ready=local_avatar_proof_available(settings),
        control_plane=settings.control_plane_backend
        if not (
            settings.control_plane_backend == "memory"
            and settings.database_url.startswith(("postgres://", "postgresql"))
        )
        else "database",
        cost_billing=_cost_billing(),
        heygen_configured=bool(settings.heygen_api_key),
        heygen_engine=settings.heygen_engine,
        heygen_rate_usd_per_minute=settings.heygen_rate_usd_per_minute,
    )


def _cost_billing() -> str:
    if settings.avatar_video_provider == "heygen_api":
        return "heygen_api"
    if settings.avatar_video_provider == "imported_video":
        return "imported_video"
    if _in_process_local_proof():
        return "local_proof_replay"
    return "gpu_hourly"


async def ensure_packaged_presenter(owner_id: str) -> None:
    """Seed the packaged MuseTalk proof only on the optional local fallback path."""

    if settings.avatar_video_provider != "local_musetalk":
        return
    seed = resolved_local_avatar_proof(settings) or resolved_local_avatar_image(settings)
    if seed is None:
        return
    await media_registry.ensure_default_presenter(
        owner_id, source=seed, media_id=settings.default_avatar_id
    )


def _estimate_job_cost(project: ProjectScript) -> tuple[float, str]:
    return estimate_control_plane_job(
        project.scenes,
        provider=settings.avatar_video_provider,
        heygen_rate_usd_per_minute=settings.heygen_rate_usd_per_minute,
        gpu_hourly_rate_usd=settings.gpu_hourly_rate_usd,
        in_process_local_proof=_in_process_local_proof(),
    )


def _apply_actual_cost(job: JobRecord) -> JobRecord:
    if job.actual_cost_usd is not None:
        return job
    elapsed = max(0.0, (job.updated_at - job.created_at).total_seconds())
    amount, note = actual_job_cost_usd(
        estimated_usd=job.estimated_cost_usd,
        elapsed_seconds=elapsed,
        provider=settings.avatar_video_provider,
        gpu_hourly_rate_usd=settings.gpu_hourly_rate_usd,
        in_process_local_proof=_in_process_local_proof(),
        stored_as_proof_replay=job_has_proof_replay(job),
        heygen_rate_usd_per_minute=settings.heygen_rate_usd_per_minute,
    )
    job.actual_cost_usd = amount
    job.cost_entries.append(
        CostEntry(stage=job.state.value.lower(), amount_usd=amount, note=note)
    )
    return job


def _cost_ledger(jobs: list[JobRecord]) -> CostLedgerResponse:
    return CostLedgerResponse.model_validate(
        build_cost_ledger(
            jobs,
            gpu_hourly_rate_usd=settings.gpu_hourly_rate_usd,
            provider=settings.avatar_video_provider,
            heygen_rate_usd_per_minute=settings.heygen_rate_usd_per_minute,
            heygen_engine=settings.heygen_engine,
        )
    )


async def _enqueue_approved_project(
    project: ProjectScript,
    owner_id: str,
    idempotency_key: str,
    background_tasks: BackgroundTasks,
) -> tuple[JobRecord, bool]:
    watermark_status = validate_provider_routing(project, settings.avatar_video_provider)
    estimated, source = _estimate_job_cost(project)
    job = JobRecord(
        job_id=f"job_{uuid.uuid4().hex}",
        video_id=f"vid_{uuid.uuid4().hex}",
        project_id=project.project_id,
        owner_id=owner_id,
        idempotency_key=idempotency_key,
        request_fingerprint=canonical_hash(project.model_dump(mode="json")),
        watermark_status=watermark_status,
        estimated_cost_usd=estimated,
        cost_entries=[
            CostEntry(stage="preflight", amount_usd=estimated, note=source)
        ],
    )
    stored, created = await repository.create_job(job)
    if created:
        await transition_job(stored, JobState.VALIDATING, stage="schema_validation")
        await transition_job(stored, JobState.QUEUED, stage="queue")
        message = JobMessage(
            job_id=stored.job_id,
            video_id=stored.video_id,
            project_id=stored.project_id,
            owner_id=stored.owner_id,
        )
        if modal_dispatcher is not None:
            await modal_dispatcher.submit(job=message, project=project)
        else:
            await queue.enqueue(message)
            background_tasks.add_task(consume_one_job)
        metrics.increment("video_jobs_queued_total")
    return stored, created


async def transition_job(
    job: JobRecord,
    to_state: JobState,
    *,
    stage: str | None = None,
    error: Exception | None = None,
) -> JobRecord:
    state_machine.transition(job, to_state, stage=stage, error=error)
    await repository.save_job(job)
    return job


@app.get("/")
async def service_root() -> dict[str, str]:
    return {
        "service": "Aivatar Video Pipeline API",
        "status": "ok",
        "documentation": "/docs",
    }


@app.post("/v1/projects", response_model=ProjectScript, status_code=status.HTTP_201_CREATED)
async def create_project(project: ProjectScript, owner_id: OwnerId) -> ProjectScript:
    stored = await repository.save_draft(project, owner_id=owner_id)
    metrics.increment("video_projects_created_total")
    return stored


@app.put("/v1/projects/{project_id}", response_model=ProjectScript)
async def replace_project(
    project_id: str, project: ProjectScript, owner_id: OwnerId
) -> ProjectScript:
    if project.project_id != project_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "project_id does not match the URL")
    existing = await repository.get_project(project_id, owner_id=owner_id)
    if existing is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "project not found")
    return await repository.save_draft(project, owner_id=owner_id)


@app.post("/v1/projects/{project_id}/approve", response_model=ProjectScript)
async def approve_project(project_id: str, owner_id: OwnerId) -> ProjectScript:
    approved = await repository.approve_project(project_id, owner_id=owner_id)
    if approved is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "project not found")
    return approved


@app.get("/v1/projects", response_model=list[ProjectScript])
async def list_projects(owner_id: OwnerId) -> list[ProjectScript]:
    return await repository.list_projects(owner_id=owner_id)


@app.get("/v1/projects/{project_id}", response_model=ProjectScript)
async def get_project(project_id: str, owner_id: OwnerId) -> ProjectScript:
    project = await repository.get_project(project_id, owner_id=owner_id)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "project not found")
    return project


@app.delete("/v1/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(project_id: str, owner_id: OwnerId) -> Response:
    deleted = await repository.delete_project(project_id, owner_id=owner_id)
    if not deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "project not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/v1/costs", response_model=CostLedgerResponse)
async def get_costs(owner_id: OwnerId) -> CostLedgerResponse:
    return _cost_ledger(await repository.list_jobs(owner_id=owner_id))


@app.get("/v1/videos", response_model=list[JobRecord])
async def list_videos(
    owner_id: OwnerId, background_tasks: BackgroundTasks
) -> list[JobRecord]:
    background_tasks.add_task(consume_one_job)
    return await repository.list_jobs(owner_id=owner_id)


@app.post("/v1/videos", response_model=CreateVideoResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_video(
    project: ProjectScript,
    background_tasks: BackgroundTasks,
    owner_id: OwnerId,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=200)],
) -> CreateVideoResponse:
    validate_provider_routing(project, settings.avatar_video_provider)
    stored_project = await repository.get_project(project.project_id, owner_id=owner_id)
    if stored_project is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "save and approve the script before rendering",
        )
    if stored_project.approval_state != "approved":
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "script must be approved before rendering",
        )
    if _script_fingerprint(stored_project) != _script_fingerprint(project):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "script changed since approval; save and approve it again",
        )
    project = stored_project
    await ensure_packaged_presenter(owner_id)
    await asyncio.to_thread(
        cleanup_expired_files,
        (settings.work_root, settings.local_storage_root),
        retention_hours=settings.asset_retention_hours,
    )
    if settings.provider_mode == "workers":
        missing = missing_consents(
            project,
            require_voice=settings.voice_consent_required,
            require_avatar=settings.avatar_consent_required,
        )
        if missing:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"missing consent records: {', '.join(missing)}",
            )
    if (
        settings.avatar_video_provider == "heygen_api"
        and not settings.force_mock_providers
    ):
        estimated_cost = estimate_project_avatar_cost(
            project.scenes,
            rate_usd_per_minute=settings.heygen_rate_usd_per_minute,
        )
        if estimated_cost > settings.heygen_maximum_cost_usd_per_job:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "estimated avatar cost exceeds the configured per-video limit",
            )
    await repository.put_project(project, owner_id=owner_id)
    try:
        stored, created = await _enqueue_approved_project(
            project, owner_id, idempotency_key, background_tasks
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return CreateVideoResponse(
        video_id=stored.video_id,
        job_id=stored.job_id,
        status=stored.state,
        idempotent_replay=not created,
        watermark_status=stored.watermark_status,
    )


@app.post("/v1/internal/modal-jobs/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def receive_modal_job_update(
    job_id: str,
    request: Request,
    signature: Annotated[str | None, Header(alias="X-Aivatar-Signature")] = None,
) -> Response:
    """Accept signed worker state updates; this route is never exposed in the UI."""

    body = await request.body()
    if not verify_signature(body, signature, secret=settings.modal_dispatch_secret or ""):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid worker signature")
    payload = await request.json()
    target_state = JobState(payload["state"])
    job = await repository.get_internal_job(job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "job not found")
    if job.state not in TERMINAL_STATES and target_state != job.state:
        error = (
            RuntimeError("Remote render failed. Please retry the job.")
            if payload.get("failed")
            else None
        )
        await transition_job(
            job,
            target_state,
            stage=str(payload.get("stage") or "modal"),
            error=error,
        )
    if target_state == JobState.COMPLETED and payload.get("output"):
        output = GeneratedAsset.model_validate(payload["output"])
        await asset_repository.put(output, owner_id=job.owner_id)
        await asset_repository.mark_retained(output.asset_id, owner_id=job.owner_id, uri=output.uri)
        job.output_asset_id = output.asset_id
    if job.state in TERMINAL_STATES:
        _apply_actual_cost(job)
    await repository.save_job(job)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


async def _complete_heygen_presenter_job(
    job: JobRecord, project: ProjectScript, owner_id: str
) -> None:
    generator = _heygen_generator()
    if generator is None:
        raise ProviderError("HeyGen export is not configured")
    if job.state == JobState.PREPROCESSING:
        await transition_job(job, JobState.GENERATING_AUDIO, stage="heygen_voice")
    if job.state == JobState.GENERATING_AUDIO:
        await transition_job(job, JobState.GENERATING_AVATAR, stage="heygen_avatar")
    if job.state == JobState.GENERATING_AVATAR:
        await transition_job(job, JobState.LIP_SYNCING, stage="heygen_export")
    try:
        final = await export_heygen_presenter(
            job=job,
            project=project,
            generator=generator,
            work_dir=settings.work_root / project.project_id / job.job_id / "final",
        )
    except HeyGenExportPending as pending:
        job.provider_ref = pending.video_id
        await repository.save_job(job)
        return
    await transition_job(job, JobState.RENDERING_SCENE, stage="heygen_mp4")
    await transition_job(job, JobState.ASSEMBLING_TIMELINE, stage="heygen_mp4")
    await transition_job(job, JobState.VALIDATING_OUTPUT, stage="heygen_mp4")
    await transition_job(job, JobState.UPLOADING, stage="heygen_mp4")
    final = await asset_store.put(final)
    await asset_repository.put(final, owner_id=owner_id)
    if final_retention_store is not None:
        retained_uri = await final_retention_store.put_file(
            Path(final.uri),
            key=f"{owner_id}/{project.project_id}/{job.video_id}/final.mp4",
            metadata={"watermark_status": job.watermark_status.value},
        )
        await asset_repository.mark_retained(
            final.asset_id, owner_id=owner_id, uri=retained_uri
        )
    job.output_asset_id = final.asset_id
    job.provider_ref = str(
        (final.provenance.model_configuration or {}).get("heygen_video_id") or job.provider_ref or ""
    ) or job.provider_ref
    await transition_job(job, JobState.COMPLETED, stage="complete")
    _apply_actual_cost(job)
    await repository.save_job(job)
    metrics.increment("video_jobs_completed_total")


def _heygen_generator() -> HeyGenLipSyncGenerator | None:
    lipsync = provider_set.lipsync
    return lipsync if isinstance(lipsync, HeyGenLipSyncGenerator) else None


def _uses_heygen_presenter_export() -> bool:
    return (
        settings.avatar_video_provider == "heygen_api"
        and not settings.force_mock_providers
        and _heygen_generator() is not None
    )


async def execute_video_job(
    job_id: str, owner_id: str, *, already_claimed: bool = False
) -> None:
    job = await repository.get_job(job_id, owner_id=owner_id)
    if job is None or job.cancellation_requested or job.state in TERMINAL_STATES:
        return
    heygen_resume = {
        JobState.PREPROCESSING,
        JobState.GENERATING_AUDIO,
        JobState.GENERATING_AVATAR,
        JobState.LIP_SYNCING,
    }
    if already_claimed:
        if job.state != JobState.PREPROCESSING and not (
            _uses_heygen_presenter_export() and job.state in heygen_resume
        ):
            return
    elif job.state == JobState.QUEUED:
        claimed = await repository.claim_job(job_id)
        if claimed is None:
            return
        job = claimed
    elif _uses_heygen_presenter_export() and job.provider_ref and job.state in heygen_resume:
        pass
    else:
        return
    project = await repository.get_project(job.project_id, owner_id=owner_id)
    if project is None:
        return
    try:
        if _uses_heygen_presenter_export() and is_heygen_presenter_project(project):
            await _complete_heygen_presenter_job(job, project, owner_id)
            return
        await ensure_packaged_presenter(owner_id)
        template = template_loader.load(project.channel_template, output=project.output)
        await transition_job(job, JobState.GENERATING_AUDIO, stage="speech")
        plans = tuple(plan_scene(scene) for scene in project.scenes)
        if any(plan.avatar_source for plan in plans):
            await transition_job(job, JobState.GENERATING_AVATAR, stage="avatar_source")
        if any(plan.visual for plan in plans):
            await transition_job(job, JobState.GENERATING_VISUAL, stage="visual")
        if any(plan.lipsync for plan in plans):
            await transition_job(job, JobState.LIP_SYNCING, stage="lipsync")
        await transition_job(job, JobState.RENDERING_SCENE, stage="scene_render")
        rendered = await pipeline.render_project(
            project, template, job_id=job.job_id, request_id=f"req_{uuid.uuid4().hex}"
        )
        if job.cancellation_requested:
            if job.state != JobState.CANCELLED:
                await transition_job(
                    job, JobState.CANCELLED, stage="cancelled_after_scene_render"
                )
            _apply_actual_cost(job)
            await repository.save_job(job)
            return
        for asset in rendered:
            stored_scene = await asset_store.put(asset)
            await asset_repository.put(stored_scene, owner_id=owner_id)
        await transition_job(job, JobState.ASSEMBLING_TIMELINE, stage="timeline")
        final = await assembler.assemble(
            rendered,
            project_id=project.project_id,
            output_spec=project.output,
            output_dir=settings.work_root / project.project_id / job.job_id / "final",
            transitions=tuple(scene.transition_out for scene in project.scenes),
        )
        await transition_job(job, JobState.VALIDATING_OUTPUT, stage="ffprobe")
        info = probe_media(final.uri)
        errors = validate_output(
            info,
            width=project.output.width,
            height=project.output.height,
            fps=project.output.fps,
            expected_duration_seconds=final.duration_seconds or 0,
            sample_rate=template.audio.sample_rate,
        )
        if errors:
            raise ValueError("; ".join(errors))
        await transition_job(job, JobState.UPLOADING, stage="local_asset_store")
        final = await asset_store.put(final)
        await asset_repository.put(final, owner_id=owner_id)
        if final_retention_store is not None:
            retained_uri = await final_retention_store.put_file(
                Path(final.uri),
                key=f"{owner_id}/{project.project_id}/{job.video_id}/final.mp4",
                metadata={"watermark_status": job.watermark_status.value},
            )
            await asset_repository.mark_retained(
                final.asset_id,
                owner_id=owner_id,
                uri=retained_uri,
            )
        job.output_asset_id = final.asset_id
        await transition_job(job, JobState.COMPLETED, stage="complete")
        _apply_actual_cost(job)
        await repository.save_job(job)
        metrics.increment("video_jobs_completed_total")
    except Exception as exc:
        if job.state not in TERMINAL_STATES:
            await transition_job(
                job,
                JobState.FAILED,
                stage="job",
                error=public_job_error(exc),
            )
        _apply_actual_cost(job)
        await repository.save_job(job)
        metrics.increment("video_jobs_failed_total")
        logger.exception(
            "video_job_failed",
            job_id=job.job_id,
            video_id=job.video_id,
            project_id=job.project_id,
            error_class=type(exc).__name__,
        )


async def consume_one_job() -> None:
    """Run one queued job from memory/Redis, or recover a Neon-persisted orphan."""
    if modal_dispatcher is not None:
        return
    await repository.requeue_stale_jobs(
        claim_lease_seconds=settings.job_claim_lease_seconds,
        running_lease_seconds=settings.job_running_lease_seconds,
    )
    message = await queue.try_dequeue()
    if message is not None:
        await execute_video_job(message.job_id, message.owner_id)
        return
    claimed = await repository.claim_next_queued_job()
    if claimed is not None:
        await execute_video_job(claimed.job_id, claimed.owner_id, already_claimed=True)


@app.get("/v1/videos/{video_id}", response_model=JobRecord)
async def get_video(
    video_id: str, owner_id: OwnerId, background_tasks: BackgroundTasks
) -> JobRecord:
    job = await repository.get_video_job(video_id, owner_id=owner_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "video not found")
    if job.state not in TERMINAL_STATES:
        if _uses_heygen_presenter_export() and (
            job.provider_ref or job.state == JobState.QUEUED
        ):
            background_tasks.add_task(
                execute_video_job,
                job.job_id,
                owner_id,
                already_claimed=job.state != JobState.QUEUED,
            )
        else:
            background_tasks.add_task(consume_one_job)
    return job


@app.post("/v1/videos/{video_id}/cancel", response_model=JobRecord)
async def cancel_video(video_id: str, owner_id: OwnerId) -> JobRecord:
    job = await repository.get_video_job(video_id, owner_id=owner_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "video not found")
    if job.state in TERMINAL_STATES:
        raise HTTPException(status.HTTP_409_CONFLICT, f"job is already {job.state}")
    job.cancellation_requested = True
    await transition_job(job, JobState.CANCELLED, stage="api_cancel")
    _apply_actual_cost(job)
    await repository.save_job(job)
    metrics.increment("video_jobs_cancelled_total")
    return job


@app.post(
    "/v1/videos/{video_id}/retry",
    response_model=CreateVideoResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def retry_video(
    video_id: str, owner_id: OwnerId, background_tasks: BackgroundTasks
) -> CreateVideoResponse:
    existing = await repository.get_video_job(video_id, owner_id=owner_id)
    if existing is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "video not found")
    if existing.state not in {JobState.FAILED, JobState.CANCELLED}:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "only failed or cancelled jobs can be retried"
        )
    project = await repository.get_project(existing.project_id, owner_id=owner_id)
    if project is None or project.approval_state != "approved":
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "approved script is required to retry",
        )
    stored, _created = await _enqueue_approved_project(
        project,
        owner_id,
        f"retry-{existing.job_id}-{uuid.uuid4().hex}",
        background_tasks,
    )
    return CreateVideoResponse(
        video_id=stored.video_id,
        job_id=stored.job_id,
        status=stored.state,
        idempotent_replay=False,
        watermark_status=stored.watermark_status,
    )


@app.get("/v1/jobs/{job_id}", response_model=JobRecord)
async def get_job(
    job_id: str, owner_id: OwnerId, background_tasks: BackgroundTasks
) -> JobRecord:
    job = await repository.get_job(job_id, owner_id=owner_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "job not found")
    if job.state not in TERMINAL_STATES:
        if _uses_heygen_presenter_export() and (
            job.provider_ref or job.state == JobState.QUEUED
        ):
            background_tasks.add_task(
                execute_video_job,
                job.job_id,
                owner_id,
                already_claimed=job.state != JobState.QUEUED,
            )
        else:
            background_tasks.add_task(consume_one_job)
    return job


@app.get("/v1/assets/{asset_id}", response_model=PublicAsset)
async def get_asset(asset_id: str, owner_id: OwnerId) -> PublicAsset:
    asset = await asset_repository.get(asset_id, owner_id=owner_id)
    if asset is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "asset not found")
    retained_uri = await asset_repository.retained_uri(asset_id, owner_id=owner_id)
    return PublicAsset.from_internal(asset, retained=retained_uri is not None)


@app.get("/v1/assets/{asset_id}/content", response_class=FileResponse)
async def download_asset(asset_id: str, owner_id: OwnerId) -> Response:
    asset = await asset_repository.get(asset_id, owner_id=owner_id)
    if asset is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "asset not found")
    path = Path(asset.uri).resolve()
    if path.is_file():
        return FileResponse(path, media_type=asset.mime_type, filename=f"{asset_id}{path.suffix}")
    heygen_id = str(
        (asset.provenance.model_configuration or {}).get("heygen_video_id")
        or (asset.provenance.model_configuration or {}).get("video_id")
        or ""
    ).strip()
    generator = _heygen_generator()
    if heygen_id and generator is not None:
        try:
            return RedirectResponse(
                await generator.fresh_video_url(heygen_id),
                status_code=status.HTTP_307_TEMPORARY_REDIRECT,
            )
        except ProviderError:
            pass
    retained_uri = await asset_repository.retained_uri(asset_id, owner_id=owner_id)
    if final_retention_store is None or retained_uri is None:
        raise HTTPException(status.HTTP_410_GONE, "asset file has expired")
    signed_url = await final_retention_store.presigned_get_uri(
        retained_uri,
        expires_seconds=settings.retained_download_url_seconds,
    )
    return RedirectResponse(signed_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@app.get("/v1/heygen/catalog", response_model=HeyGenCatalogResponse)
async def heygen_catalog() -> HeyGenCatalogResponse:
    generator = _heygen_generator()
    if generator is None or not settings.heygen_api_key:
        return HeyGenCatalogResponse(configured=False)
    try:
        voices = [
            HeyGenVoiceOption.model_validate(item) for item in await generator.list_voices()
        ]
        english = [
            item
            for item in voices
            if item.language.lower().startswith("en") or "english" in item.name.lower()
        ]
        voices = (english or voices)[:40]
        avatars = [
            HeyGenAvatarOption.model_validate(item) for item in await generator.list_avatars()
        ][:40]
    except ProviderError:
        return HeyGenCatalogResponse(
            configured=True, default_voice_id=settings.heygen_default_voice_id
        )
    default_voice = settings.heygen_default_voice_id
    if not default_voice:
        default_voice = next(
            (item.voice_id for item in voices if item.language.lower().startswith("en")),
            voices[0].voice_id if voices else "",
        )
    return HeyGenCatalogResponse(
        configured=True,
        default_voice_id=default_voice,
        voices=voices,
        avatars=avatars,
    )


@app.post("/v1/heygen-avatars", response_model=RegisteredMedia, status_code=status.HTTP_201_CREATED)
async def register_heygen_avatar(
    payload: HeyGenAvatarRequest,
    owner_id: OwnerId,
    x_media_rights_confirmed: Annotated[str, Header(alias="X-Media-Rights-Confirmed")],
) -> RegisteredMedia:
    if x_media_rights_confirmed.lower() != "true":
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "confirm that you own or have permission to use this HeyGen avatar",
        )
    try:
        return await media_registry.register_heygen_avatar(
            owner_id=owner_id,
            avatar_id=payload.avatar_id,
            label=payload.label,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc


@app.post("/v1/media/{kind}", response_model=RegisteredMedia, status_code=status.HTTP_201_CREATED)
async def upload_authorized_media(
    kind: MediaKind,
    request: Request,
    owner_id: OwnerId,
    x_filename: Annotated[str, Header(alias="X-Filename", min_length=1, max_length=255)],
    x_media_rights_confirmed: Annotated[str, Header(alias="X-Media-Rights-Confirmed")],
) -> RegisteredMedia:
    await asyncio.to_thread(
        cleanup_expired_files,
        (
            settings.media_registry_root,
            settings.avatar_registry_root,
            settings.voice_registry_root,
        ),
        retention_hours=settings.asset_retention_hours,
    )
    if x_media_rights_confirmed.lower() != "true":
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "confirm that you own or have permission to use this media",
        )
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > settings.media_upload_max_bytes:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "upload is too large")
    try:
        return await media_registry.register(
            owner_id=owner_id,
            kind=kind,
            filename=x_filename,
            content_type=request.headers.get("content-type", "application/octet-stream"),
            payload=await request.body(),
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc


@app.get("/v1/media", response_model=list[RegisteredMedia])
async def list_authorized_media(
    owner_id: OwnerId, kind: MediaKind | None = None
) -> list[RegisteredMedia]:
    await ensure_packaged_presenter(owner_id)
    return await media_registry.list(owner_id=owner_id, kind=kind)


@app.get("/v1/media/{media_id}/content")
async def download_authorized_media(media_id: str, owner_id: OwnerId) -> Response:
    stored = await media_registry.get(media_id, owner_id=owner_id)
    if stored is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "media not found")
    record, path = stored
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "media file is missing")
    return FileResponse(path, media_type=record.content_type, filename=record.original_filename)


@app.delete("/v1/media/{media_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_authorized_media(media_id: str, owner_id: OwnerId) -> Response:
    deleted = await media_registry.delete(media_id, owner_id=owner_id)
    if not deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "media not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return _runtime_health("ok")


@app.get("/ready", response_model=HealthResponse)
async def ready() -> HealthResponse:
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe") or not asset_store.ready():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "runtime dependency unavailable")
    return _runtime_health("ready")


@app.get("/metrics", response_class=PlainTextResponse)
async def metrics_endpoint(_: OwnerId) -> str:
    metrics.gauge("video_queue_depth", await queue.depth())
    return metrics.render()


def run() -> None:
    import uvicorn

    uvicorn.run("src.api.main:app", host="0.0.0.0", port=8000)
