from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from src.schemas.jobs import JobState, WatermarkStatus


class CreateVideoResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    video_id: str
    job_id: str
    status: JobState
    idempotent_replay: bool = False
    watermark_status: WatermarkStatus


class HealthResponse(BaseModel):
    status: str
    avatar_video_provider: str | None = None
    lipsync_mode: str | None = None
    local_proof_ready: bool | None = None
    control_plane: str | None = None
    cost_billing: str | None = None
    heygen_configured: bool | None = None
    heygen_engine: str | None = None
    heygen_rate_usd_per_minute: float | None = None


class HeyGenAvatarRequest(BaseModel):
    avatar_id: str
    label: str = ""


class HeyGenVoiceOption(BaseModel):
    voice_id: str
    name: str
    language: str = ""


class HeyGenAvatarOption(BaseModel):
    avatar_id: str
    name: str


class HeyGenCatalogResponse(BaseModel):
    configured: bool
    default_voice_id: str = ""
    voices: list[HeyGenVoiceOption] = []
    avatars: list[HeyGenAvatarOption] = []


class ProjectCostSummary(BaseModel):
    project_id: str
    estimated_usd: float
    actual_usd: float
    job_count: int


class CostLedgerResponse(BaseModel):
    estimated_usd: float
    actual_usd: float
    job_count: int
    completed_count: int
    failed_count: int
    projects: list[ProjectCostSummary]
    gpu_hourly_rate_usd: float = 0.22
    heygen_rate_usd_per_minute: float = 4.0
    heygen_engine: str = "avatar_iv"
    billing_policy: str = "HeyGen Avatar IV is billed at the configured per-minute rate."
    proof_replay_job_count: int = 0
    gpu_job_count: int = 0
    heygen_job_count: int = 0
    heygen_estimated_usd: float = 0.0
    heygen_actual_usd: float = 0.0
    proof_replay_usd: float = 0.0
    gpu_estimated_usd: float = 0.0
    gpu_actual_usd: float = 0.0


class AuthProviderStatus(BaseModel):
    name: str
    enabled: bool


class AuthConfigurationResponse(BaseModel):
    providers: list[AuthProviderStatus]
    superadmin_display_names: list[str]
    superadmin_email_count: int
