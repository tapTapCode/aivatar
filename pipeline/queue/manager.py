from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timezone
from threading import Event, Lock, Thread

from sqlalchemy import select

from pipeline.assets.service import generate_visual_assets
from pipeline.core.config import settings
from pipeline.core.enums import JobState
from pipeline.core.services import run_authorized_presenter_render, run_mock_render
from pipeline.models.entities import Job, Project, Scene
from pipeline.presenter.service import generate_presenter_for_scene, generate_presenter_scenes
from pipeline.queue.resources import resource_limits
from pipeline.storage.db import SessionLocal
from pipeline.studio.production import run_production


class JobManager:
    """Durable local job runner.

    SQLite stores authoritative job state. ThreadPoolExecutor is only the current-process
    execution transport; queued/running jobs can be recovered after application restart.
    """

    def __init__(self) -> None:
        self.executor = ThreadPoolExecutor(
            max_workers=max(
                6,
                settings.aivatar_max_project_jobs
                + settings.aivatar_max_ffmpeg_jobs
                + settings.aivatar_max_presenter_jobs
                + settings.aivatar_max_image_gpu_jobs
                + settings.aivatar_max_video_gpu_jobs,
            )
        )
        self.semaphores = resource_limits.semaphores
        self._lock = Lock()
        self._submitted: set[str] = set()

    def recover_interrupted(self) -> dict[str, int]:
        """Requeue resumable work rather than permanently failing every interrupted job."""
        recovered = 0
        failed = 0
        queued: list[str] = []
        with SessionLocal() as db:
            jobs = list(db.scalars(select(Job).where(Job.state.in_([JobState.RUNNING.value, JobState.QUEUED.value]))).all())
            for job in jobs:
                if job.state == JobState.RUNNING.value:
                    if settings.aivatar_requeue_interrupted_jobs and job.retryable and job.attempts < job.max_attempts:
                        job.state = JobState.QUEUED.value
                        job.resume_count += 1
                        job.error = "Recovered after application restart"
                        job.started_at = None
                        job.finished_at = None
                        job.heartbeat_at = None
                        recovered += 1
                    else:
                        job.state = JobState.FAILED.value
                        job.error = "Application restarted while job was running; retry limit reached or job is not retryable"
                        job.finished_at = datetime.now(timezone.utc)
                        failed += 1
                if job.state == JobState.QUEUED.value and not job.cancel_requested:
                    queued.append(job.id)
            db.commit()
        for job_id in queued:
            self._dispatch(job_id)
        return {"requeued": recovered, "failed": failed, "submitted": len(queued)}

    def _create_job(self, project_id: str, kind: str, payload: dict | None = None, *, retryable: bool = True) -> str:
        with SessionLocal() as db:
            job = Job(
                project_id=project_id,
                kind=kind,
                state=JobState.QUEUED.value,
                payload_json=payload or {},
                retryable=retryable,
                max_attempts=settings.aivatar_job_max_attempts,
            )
            db.add(job); db.commit(); db.refresh(job)
            return job.id

    def _submit(self, job_id: str) -> None:
        with self._lock:
            if job_id in self._submitted:
                return
            self._submitted.add(job_id)
        self.executor.submit(self._run_dispatched, job_id)

    def _run_dispatched(self, job_id: str) -> None:
        try:
            self._dispatch(job_id, direct=True)
        finally:
            with self._lock:
                self._submitted.discard(job_id)

    def _dispatch(self, job_id: str, *, direct: bool = False) -> None:
        if not direct:
            self._submit(job_id)
            return
        with SessionLocal() as db:
            job = db.get(Job, job_id)
            if not job or job.state != JobState.QUEUED.value or job.cancel_requested:
                return
            project_id = job.project_id
            payload = dict(job.payload_json or {})
            kind = job.kind
        if not project_id:
            return
        if kind == "mock_render":
            self._run_mock_render(job_id, project_id)
        elif kind == "studio_render":
            self._run_studio_render(job_id, project_id)
        elif kind == "presenter_render":
            self._run_presenter_render(job_id, project_id)
        elif kind == "asset_batch":
            self._run_asset_batch(job_id, project_id, payload)
        elif kind == "presenter_batch":
            self._run_presenter_batch(job_id, project_id, payload)
        elif kind == "presenter_scene":
            scene_id = payload.get("scene_id")
            if scene_id:
                self._run_presenter_scene(job_id, project_id, scene_id, payload)
        else:
            with SessionLocal() as db:
                job = db.get(Job, job_id)
                if job:
                    self._fail_job(db, job, RuntimeError(f"Unknown resumable job kind: {kind}"))

    def enqueue_mock_render(self, project_id: str) -> str:
        job_id = self._create_job(project_id, "mock_render")
        self._submit(job_id)
        return job_id

    def enqueue_studio_render(self, project_id: str) -> str:
        """Queue an approved Channel Studio production run."""
        job_id = self._create_job(project_id, "studio_render")
        self._submit(job_id)
        return job_id

    def enqueue_presenter_render(self, project_id: str, *, force: bool = False) -> str:
        job_id = self._create_job(project_id, "presenter_render", {"force": force})
        self._submit(job_id)
        return job_id

    def enqueue_presenter_batch(self, project_id: str, *, provider: str | None = None, force: bool = False, allow_fallback: bool = True) -> str:
        payload = {"provider": provider, "force": force, "allow_fallback": allow_fallback}
        job_id = self._create_job(project_id, "presenter_batch", payload)
        self._submit(job_id)
        return job_id

    def enqueue_presenter_scene(self, project_id: str, scene_id: str, *, provider: str | None = None, force: bool = False, allow_fallback: bool = True, manual_clip_path: str | None = None) -> str:
        payload = {"scene_id": scene_id, "provider": provider, "force": force, "allow_fallback": allow_fallback, "manual_clip_path": manual_clip_path}
        job_id = self._create_job(project_id, "presenter_scene", payload)
        self._submit(job_id)
        return job_id

    def enqueue_asset_batch(self, project_id: str, *, mock: bool = True, force: bool = False) -> str:
        payload = {"mock": mock, "force": force}
        job_id = self._create_job(project_id, "asset_batch", payload)
        self._submit(job_id)
        return job_id

    def cancel(self, job_id: str) -> bool:
        with SessionLocal() as db:
            job = db.get(Job, job_id)
            if not job or job.state in {JobState.COMPLETED.value, JobState.FAILED.value, JobState.CANCELLED.value}:
                return False
            job.cancel_requested = True
            if job.state == JobState.QUEUED.value:
                job.state = JobState.CANCELLED.value
                job.finished_at = datetime.now(timezone.utc)
            db.commit()
            return True

    def retry(self, job_id: str) -> bool:
        with SessionLocal() as db:
            job = db.get(Job, job_id)
            if not job or job.state not in {JobState.FAILED.value, JobState.CANCELLED.value}:
                return False
            if not job.retryable or job.attempts >= job.max_attempts:
                return False
            job.state = JobState.QUEUED.value
            job.cancel_requested = False
            job.error = None
            job.started_at = None
            job.finished_at = None
            job.heartbeat_at = None
            job.resume_count += 1
            db.commit()
        self._submit(job_id)
        return True

    @staticmethod
    def _start_job(db, job: Job) -> None:
        if job.cancel_requested:
            job.state = JobState.CANCELLED.value
            job.finished_at = datetime.now(timezone.utc)
            db.commit()
            raise RuntimeError("Job cancelled before start")
        job.state = JobState.RUNNING.value
        job.started_at = datetime.now(timezone.utc)
        job.heartbeat_at = job.started_at
        job.attempts += 1
        job.progress = 0.05
        job.error = None
        db.commit()

    @staticmethod
    def _complete_job(db, job: Job) -> None:
        if job.cancel_requested:
            job.state = JobState.CANCELLED.value
        else:
            job.state = JobState.COMPLETED.value
            job.progress = 1.0
        job.heartbeat_at = datetime.now(timezone.utc)
        job.finished_at = datetime.now(timezone.utc)
        db.commit()

    @staticmethod
    def _fail_job(db, job: Job, exc: Exception) -> None:
        if job.cancel_requested:
            job.state = JobState.CANCELLED.value
        else:
            job.state = JobState.FAILED.value
        job.error = str(exc)
        job.heartbeat_at = datetime.now(timezone.utc)
        job.finished_at = datetime.now(timezone.utc)
        db.commit()

    @contextmanager
    def _heartbeat(self, job_id: str):
        stop = Event()

        def pulse() -> None:
            interval = max(2, settings.aivatar_job_heartbeat_seconds)
            while not stop.wait(interval):
                with SessionLocal() as heartbeat_db:
                    job = heartbeat_db.get(Job, job_id)
                    if not job or job.state != JobState.RUNNING.value:
                        return
                    job.heartbeat_at = datetime.now(timezone.utc)
                    heartbeat_db.commit()

        thread = Thread(target=pulse, daemon=True)
        thread.start()
        try:
            yield
        finally:
            stop.set()
            thread.join(timeout=1)

    def _run_mock_render(self, job_id: str, project_id: str) -> None:
        with resource_limits.reserve("project"), resource_limits.reserve("ffmpeg"):
            with SessionLocal() as db:
                job = db.get(Job, job_id); project = db.get(Project, project_id)
                if not job or not project: return
                try:
                    self._start_job(db, job)
                    with self._heartbeat(job_id):
                        run_mock_render(db, project)
                    self._complete_job(db, job)
                except Exception as exc:
                    self._fail_job(db, job, exc)

    def _run_studio_render(self, job_id: str, project_id: str) -> None:
        with resource_limits.reserve("project"):
            with SessionLocal() as db:
                job = db.get(Job, job_id); project = db.get(Project, project_id)
                if not job or not project: return
                try:
                    self._start_job(db, job)
                    with self._heartbeat(job_id):
                        result = run_production(
                            db,
                            project,
                            progress=lambda stage, fraction: self._update_progress(job_id, stage, fraction),
                        )
                    job.payload_json = {**(job.payload_json or {}), "result": result}
                    self._complete_job(db, job)
                except Exception as exc:
                    self._fail_job(db, job, exc)

    def _update_progress(self, job_id: str, stage: str, fraction: float) -> None:
        with SessionLocal() as db:
            job = db.get(Job, job_id)
            if job and job.state == JobState.RUNNING.value:
                job.progress = max(0.05, min(0.99, float(fraction)))
                job.payload_json = {**(job.payload_json or {}), "stage": stage}
                db.commit()

    def _run_presenter_render(self, job_id: str, project_id: str) -> None:
        with resource_limits.reserve("presenter"):
            with SessionLocal() as db:
                job = db.get(Job, job_id); project = db.get(Project, project_id)
                if not job or not project: return
                try:
                    self._start_job(db, job)
                    with self._heartbeat(job_id):
                        result = run_authorized_presenter_render(db, project, force=bool((job.payload_json or {}).get("force", False)))
                    job.payload_json = {**(job.payload_json or {}), **result}
                    self._complete_job(db, job)
                except Exception as exc:
                    self._fail_job(db, job, exc)

    def _run_asset_batch(self, job_id: str, project_id: str, payload: dict) -> None:
        with resource_limits.reserve("project"):
            with SessionLocal() as db:
                job = db.get(Job, job_id); project = db.get(Project, project_id)
                if not job or not project: return
                try:
                    self._start_job(db, job)
                    with self._heartbeat(job_id):
                        results = generate_visual_assets(db, project, mock=bool(payload.get("mock", True)), force=bool(payload.get("force", False)))
                    job.payload_json = {**payload, "generated": len(results), "cache_hits": sum(1 for r in results if r["cache_hit"])}
                    self._complete_job(db, job)
                except Exception as exc:
                    self._fail_job(db, job, exc)

    def _run_presenter_batch(self, job_id: str, project_id: str, payload: dict) -> None:
        with resource_limits.reserve("presenter"):
            with SessionLocal() as db:
                job = db.get(Job, job_id); project = db.get(Project, project_id)
                if not job or not project: return
                try:
                    self._start_job(db, job)
                    with self._heartbeat(job_id):
                        results = generate_presenter_scenes(db, project, provider_name=payload.get("provider"), force=bool(payload.get("force")), allow_fallback=bool(payload.get("allow_fallback", True)))
                    job.payload_json = {**payload, "generated": len(results)}
                    self._complete_job(db, job)
                except Exception as exc:
                    self._fail_job(db, job, exc)

    def _run_presenter_scene(self, job_id: str, project_id: str, scene_id: str, payload: dict) -> None:
        with resource_limits.reserve("presenter"):
            with SessionLocal() as db:
                job = db.get(Job, job_id); project = db.get(Project, project_id); scene = db.get(Scene, scene_id)
                if not job or not project or not scene: return
                try:
                    self._start_job(db, job)
                    with self._heartbeat(job_id):
                        result = generate_presenter_for_scene(db, project, scene, provider_name=payload.get("provider"), force=bool(payload.get("force")), allow_fallback=bool(payload.get("allow_fallback", True)), manual_clip_path=payload.get("manual_clip_path"))
                    job.payload_json = {**payload, "result": {"path": result["path"], "provider": result["provider"]}}
                    self._complete_job(db, job)
                except Exception as exc:
                    self._fail_job(db, job, exc)


job_manager = JobManager()
