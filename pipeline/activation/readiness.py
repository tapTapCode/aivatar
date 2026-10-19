from __future__ import annotations

import shutil
from dataclasses import dataclass, asdict
from pathlib import Path

from sqlalchemy import text

from pipeline.core.config import settings
from pipeline.storage.db import engine


@dataclass(slots=True)
class ActivationCheck:
    id: str
    label: str
    ready: bool
    required: bool
    detail: str
    action: str | None = None

    def as_dict(self) -> dict:
        return asdict(self)


def _writable(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".aivatar-write-probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True
    except OSError:
        return False


def activation_status() -> dict:
    checks: list[ActivationCheck] = []

    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    checks.append(ActivationCheck(
        "ffmpeg", "FFmpeg + ffprobe", bool(ffmpeg and ffprobe), True,
        "Authoritative local compositor and QC tools.",
        "Install FFmpeg with Homebrew." if not (ffmpeg and ffprobe) else None,
    ))

    writable = _writable(settings.aivatar_workspace)
    checks.append(ActivationCheck(
        "workspace", "Writable local workspace", writable, True,
        str(settings.aivatar_workspace),
        "Choose a writable AIVATAR_WORKSPACE." if not writable else None,
    ))

    db_ready = False
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_ready = True
    except Exception:
        db_ready = False
    checks.append(ActivationCheck(
        "database", "Local SQLite state", db_ready, True,
        "Durable project/job state and restart recovery.",
        "Check AIVATAR_DATABASE_URL and run migrations." if not db_ready else None,
    ))

    archive_rotated = bool(settings.aivatar_archive_credentials_rotated)
    checks.append(ActivationCheck(
        "credential_rotation", "Archive credentials rotated", archive_rotated, True,
        "The WhatsApp archive contained credentials; Aivatar refuses to treat those historical values as production-ready.",
        "Rotate exposed provider/account credentials, then set AIVATAR_ARCHIVE_CREDENTIALS_ROTATED=true." if not archive_rotated else None,
    ))

    voice_ready = bool(
        (settings.ai33_api_key and settings.ai33_api_base_url)
        or (settings.sixty_nine_labs_api_key and settings.sixty_nine_labs_api_base_url)
    )
    checks.append(ActivationCheck(
        "voice", "Real narration provider", voice_ready, True,
        "AI33 Pro is preferred; 69Labs can be configured as alternate.",
        "Configure a fresh authorized AI33 or 69Labs API key and documented endpoint." if not voice_ready else None,
    ))

    higgsfield_ready = bool(settings.higgsfield_api_key)
    checks.append(ActivationCheck(
        "higgsfield", "Authorized Higgsfield presenter", higgsfield_ready, True,
        f"Configured model: {settings.higgsfield_model}. Presenter generation remains isolated behind PresenterProvider.",
        "Configure a fresh authorized HIGGSFIELD_API_KEY." if not higgsfield_ready else None,
    ))

    r2_ready = bool(
        settings.r2_account_id
        and settings.r2_access_key_id
        and settings.r2_secret_access_key
        and settings.r2_bucket
    )
    checks.append(ActivationCheck(
        "r2", "Cloudflare R2 media store", r2_ready, True,
        f"Bucket: {settings.r2_bucket}",
        "Configure bucket-scoped R2 read/write credentials." if not r2_ready else None,
    ))

    runpod_core = bool(settings.runpod_api_key)
    flux_ready = bool(runpod_core and settings.runpod_flux_endpoint_id)
    ltx_ready = bool(runpod_core and settings.runpod_ltx_endpoint_id)
    checks.append(ActivationCheck(
        "runpod_flux", "RunPod FLUX worker", flux_ready, True,
        settings.aivatar_flux_model,
        "Deploy/configure the FLUX Serverless endpoint." if not flux_ready else None,
    ))
    checks.append(ActivationCheck(
        "runpod_ltx", "RunPod LTX worker", ltx_ready, True,
        f"{settings.aivatar_ltx_model} · {settings.aivatar_ltx_checkpoint}",
        "Deploy/configure the LTX Serverless endpoint." if not ltx_ready else None,
    ))

    musetalk_ready = bool(runpod_core and settings.runpod_musetalk_endpoint_id)
    checks.append(ActivationCheck(
        "musetalk", "MuseTalk fallback worker", musetalk_ready, False,
        "Optional local/remote fallback; Higgsfield is the primary presenter.",
        "Configure RUNPOD_MUSETALK_ENDPOINT_ID if fallback coverage is wanted." if not musetalk_ready else None,
    ))

    hf_ready = bool(settings.hf_token)
    checks.append(ActivationCheck(
        "huggingface", "Hugging Face worker token", hf_ready, True,
        "Used by ephemeral workers for licensed/gated model acquisition when required.",
        "Configure a least-privilege HF_TOKEN for the worker environment." if not hf_ready else None,
    ))

    required = [check for check in checks if check.required]
    blockers = [check.as_dict() for check in required if not check.ready]
    ready_count = sum(1 for check in required if check.ready)
    readiness_percent = round((ready_count / len(required)) * 100) if required else 100
    return {
        "ready_for_real_reference_test": not blockers,
        "readiness_percent": readiness_percent,
        "required_ready": ready_count,
        "required_total": len(required),
        "blockers": blockers,
        "checks": [check.as_dict() for check in checks],
        "next_milestone": "Real 60–90 second reference-quality end-to-end video",
        "reference_profile": settings.aivatar_reference_profile,
        "safety_boundary": "Authorized provider integrations only; no billing, quota, credit, session, or access-control bypasses.",
    }
