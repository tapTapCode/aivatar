"""Modal deployment entrypoint for asynchronous authorized HeyGen presenter exports.

Deploy manually after creating the `aivatar-production` Modal secret:
    modal deploy modal_heygen_worker.py
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from pathlib import Path
from typing import Any

import httpx
import modal
from fastapi import FastAPI, Header, HTTPException, Request, status

from src.dispatch.modal import callback_payload, sign_payload, verify_signature
from src.orchestration.pipeline import PipelineOrchestrator, ProviderSet
from src.orchestration.templates import TemplateLoader
from src.providers.heygen import HeyGenAvatarSourceProvider, HeyGenLipSyncGenerator
from src.rendering import FFmpegSceneRenderer, TimelineAssembler, probe_media, validate_output
from src.schemas.jobs import JobState
from src.schemas.scene import ProjectScript
from src.storage.s3 import S3RetentionStore

app = modal.App("aivatar-heygen")
image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("ffmpeg")
    .pip_install("boto3==1.38.32", "fastapi==0.115.12", "httpx==0.28.1", "pydantic==2.13.4")
    .add_local_dir("src", remote_path="/root/src")
    .add_local_dir("templates", remote_path="/root/templates")
)


class UnusedProvider:
    async def generate(self, _request: object) -> object:
        raise RuntimeError("this presenter-only HeyGen canary does not use this provider")


async def notify(
    payload: dict[str, Any],
    *,
    state: JobState,
    stage: str,
    output: dict[str, Any] | None = None,
    failed: bool = False,
) -> None:
    callback_url = str(payload.get("callback_url") or "").strip()
    if not callback_url:
        return
    secret = os.environ["MODAL_DISPATCH_SECRET"]
    body = callback_payload(state=state, stage=stage, output=output, failed=failed)
    async with httpx.AsyncClient(timeout=30.0) as client:
        await client.post(
            callback_url,
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Aivatar-Signature": sign_payload(body, secret=secret),
            },
        )


@app.function(image=image, secrets=[modal.Secret.from_name("aivatar-production")], timeout=7200)
def export_heygen_presenter(payload: dict[str, Any]) -> dict[str, str]:
    """Run one authorized PRESENT​ER-only job and retain its final MP4 in private R2."""

    try:
        return asyncio.run(_export(payload))
    except Exception:
        asyncio.run(notify(payload, state=JobState.FAILED, stage="modal_job", failed=True))
        raise


async def _export(payload: dict[str, Any]) -> dict[str, str]:
    project = ProjectScript.model_validate(payload["project"])
    if any(scene.visual_format.value != "PRESENTER" for scene in project.scenes):
        raise ValueError("the initial Modal canary supports PRESENTER-only projects")
    job = payload["job"]
    await notify(payload, state=JobState.PREPROCESSING, stage="modal_setup")
    root = Path("/tmp/aivatar") / job["job_id"]
    root.mkdir(parents=True, exist_ok=True)
    renderer = FFmpegSceneRenderer()
    heygen = HeyGenLipSyncGenerator(
        api_key=os.environ["HEYGEN_API_KEY"],
        engine=os.environ.get("HEYGEN_ENGINE", "avatar_iv"),
        voice_mode=os.environ.get("HEYGEN_VOICE_MODE", "native"),
        resolution=os.environ.get("HEYGEN_RESOLUTION", "1080p"),
        rate_usd_per_minute=float(os.environ.get("HEYGEN_RATE_USD_PER_MINUTE", "4")),
        maximum_cost_usd_per_job=float(os.environ.get("HEYGEN_MAXIMUM_COST_USD_PER_JOB", "2")),
    )
    providers = ProviderSet(
        speech=UnusedProvider(),
        avatar_source=HeyGenAvatarSourceProvider(),
        lipsync=heygen,
        image=UnusedProvider(),
        video=UnusedProvider(),
        renderer=renderer,
        native_presenter_voice=True,
    )
    pipeline = PipelineOrchestrator(providers, work_root=root)
    template = TemplateLoader(Path("/root/templates")).load(
        project.channel_template, output=project.output
    )
    await notify(payload, state=JobState.GENERATING_AUDIO, stage="heygen_native_voice")
    await notify(payload, state=JobState.GENERATING_AVATAR, stage="heygen_avatar")
    rendered = await pipeline.render_project(
        project,
        template,
        job_id=job["job_id"],
        request_id=f"modal_{uuid.uuid4().hex}",
    )
    await notify(payload, state=JobState.RENDERING_SCENE, stage="ffmpeg_scene")
    await notify(payload, state=JobState.ASSEMBLING_TIMELINE, stage="ffmpeg_timeline")
    final = await TimelineAssembler().assemble(
        rendered,
        project_id=project.project_id,
        output_spec=project.output,
        output_dir=root / "final",
        transitions=tuple(scene.transition_out for scene in project.scenes),
    )
    await notify(payload, state=JobState.VALIDATING_OUTPUT, stage="ffprobe")
    errors = validate_output(
        probe_media(final.uri),
        width=project.output.width,
        height=project.output.height,
        fps=project.output.fps,
        expected_duration_seconds=final.duration_seconds or 0,
        sample_rate=template.audio.sample_rate,
    )
    if errors:
        raise ValueError("; ".join(errors))
    await notify(payload, state=JobState.UPLOADING, stage="r2_upload")
    retention = S3RetentionStore(
        endpoint_url=os.environ["S3_ENDPOINT_URL"],
        bucket=os.environ["S3_BUCKET"],
        access_key_id=os.environ["S3_ACCESS_KEY"],
        secret_access_key=os.environ["S3_SECRET_KEY"],
        prefix=os.environ.get("FINAL_VIDEO_R2_PREFIX", "videos"),
    )
    uri = await retention.put_file(
        Path(final.uri),
        key=f"{job['owner_id']}/{project.project_id}/{job['video_id']}/final.mp4",
        metadata={"watermark_status": "CLEAN_AUTHORIZED"},
    )
    retained_final = final.model_copy(update={"uri": uri})
    await notify(
        payload,
        state=JobState.COMPLETED,
        stage="complete",
        output=retained_final.model_dump(mode="json"),
    )
    return {"video_id": job["video_id"], "output_uri": uri}


@app.function(image=image, secrets=[modal.Secret.from_name("aivatar-production")])
@modal.asgi_app()
def ingress() -> FastAPI:
    api = FastAPI(title="Aivatar Modal HeyGen ingress")

    @api.post("/enqueue", status_code=status.HTTP_202_ACCEPTED)
    async def enqueue(
        request: Request,
        signature: str | None = Header(alias="X-Aivatar-Signature"),
    ) -> dict[str, str]:
        body = await request.body()
        if not verify_signature(body, signature, secret=os.environ["MODAL_DISPATCH_SECRET"]):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid dispatch signature")
        payload = json.loads(body)
        export_heygen_presenter.spawn(payload)
        return {"status": "accepted", "job_id": payload["job"]["job_id"]}

    return api
