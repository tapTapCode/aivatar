from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def runtime_path(relative_path: str, *, local_path: str | None = None) -> Path:
    """Return a writable runtime path on ephemeral serverless deployments."""

    if os.getenv("VERCEL") or os.getenv("VERCEL_ENV"):
        return Path("/tmp/aivatar") / relative_path
    return Path(local_path or "artifacts") / relative_path


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=()
        if os.getenv("VERCEL") or os.getenv("VERCEL_ENV")
        else (".env",),
        extra="ignore",
    )

    app_env: str = "development"
    app_base_url: str = "http://localhost:3000"
    log_level: str = "INFO"
    api_key: str | None = None
    auth_required: bool = True
    auth_auto_migrate: bool = True
    database_url: str = "sqlite+aiosqlite:///artifacts/auth.db"
    session_cookie_name: str = "aivatar_session"
    session_cookie_secure: bool = False
    session_ttl_hours: int = Field(default=168, ge=1, le=2160)
    auth_token_ttl_minutes: int = Field(default=30, ge=5, le=1440)
    allowed_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    google_oauth_client_id: str | None = None
    google_oauth_client_secret: str | None = None
    apple_client_id: str | None = None
    apple_team_id: str | None = None
    apple_key_id: str | None = None
    apple_private_key: str | None = None
    apple_sso_enabled: bool = False
    auth_callback_url: str = ""
    resend_api_key: str | None = None
    resend_from_email: str = "Aivatar <auth@localhost>"
    superadmin_identities: str = "Jumar Juaton,Jorge Luis"
    superadmin_emails: str = "jumar.designer@gmail.com,motivaciondiaria630@gmail.com"
    api_rate_limit_per_minute: int = Field(default=60, ge=1)
    queue_backend: Literal["memory", "redis"] = "memory"
    control_plane_backend: Literal["memory", "database"] = "memory"
    job_claim_lease_seconds: float = Field(default=60.0, ge=1)
    job_running_lease_seconds: float = Field(default=600.0, ge=1)
    background_runner: Literal["inline", "modal"] = "inline"
    modal_dispatch_url: str = ""
    modal_dispatch_secret: str | None = None
    modal_callback_url: str = ""
    redis_url: str = "redis://localhost:6379/0"
    local_storage_root: Path = Field(default_factory=lambda: runtime_path("assets"))
    storage_backend: Literal["local", "r2"] = "local"
    work_root: Path = Field(default_factory=lambda: runtime_path("work"))
    template_root: Path = Path("templates")
    provider_mode: Literal["mock", "workers"] = "mock"
    image_worker_url: str = "http://image-worker:8080"
    video_worker_url: str = "http://video-worker:8080"
    tts_worker_url: str = "http://tts-worker:8080"
    lipsync_worker_url: str = "http://lipsync-worker:8080"
    render_worker_url: str = "http://render-worker:8080"
    avatar_registry_root: Path = Field(
        default_factory=lambda: runtime_path("avatars", local_path="assets")
    )
    voice_registry_root: Path = Field(
        default_factory=lambda: runtime_path("voices", local_path="assets")
    )
    media_registry_root: Path = Field(default_factory=lambda: runtime_path("authorized-media"))
    media_upload_max_bytes: int = Field(default=250 * 1024 * 1024, ge=1024)
    asset_retention_hours: float = Field(default=24.0, gt=0)
    avatar_video_provider: Literal["imported_video", "local_musetalk", "heygen_api"] = (
        "heygen_api"
    )
    local_avatar_proof: Path = Path("packaged/local-avatar/avatar_quality_proof.mp4")
    local_avatar_image: Path = Path("packaged/local-avatar/presenter.png")
    default_avatar_id: str = "presenter-01"  # used only when local_musetalk seeding is on
    force_mock_providers: bool = False
    heygen_api_key: str | None = None
    heygen_api_base: str = "https://api.heygen.com"
    heygen_engine: Literal["avatar_iii", "avatar_iv", "avatar_v"] = "avatar_iv"
    heygen_voice_mode: Literal["native", "audio"] = "native"
    heygen_default_voice_id: str = ""
    heygen_resolution: Literal["720p", "1080p", "4k"] = "1080p"
    heygen_rate_usd_per_minute: float = Field(default=4.0, gt=0)
    heygen_maximum_cost_usd_per_job: float = Field(default=25.0, gt=0)
    gpu_hourly_rate_usd: float = Field(default=0.22, ge=0)
    heygen_poll_interval_seconds: float = Field(default=10.0, gt=0)
    heygen_timeout_seconds: float = Field(default=7200.0, gt=0)
    heygen_r2_retention_enabled: bool = False
    heygen_r2_prefix: str = "retained/heygen"
    s3_endpoint_url: str = ""
    s3_bucket: str = ""
    s3_access_key: str = ""
    s3_secret_key: str = ""
    final_video_r2_prefix: str = "videos"
    retained_download_url_seconds: int = Field(default=900, ge=1, le=604_800)
    voice_consent_required: bool = True
    avatar_consent_required: bool = True
    max_retries: int = Field(default=2, ge=0, le=10)


@lru_cache
def get_settings() -> Settings:
    return Settings()
