from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class JobState(StrEnum):
    PENDING = "PENDING"
    VALIDATING = "VALIDATING"
    QUEUED = "QUEUED"
    DOWNLOADING_MODELS = "DOWNLOADING_MODELS"
    PREPROCESSING = "PREPROCESSING"
    GENERATING_AUDIO = "GENERATING_AUDIO"
    GENERATING_AVATAR = "GENERATING_AVATAR"
    GENERATING_VISUAL = "GENERATING_VISUAL"
    LIP_SYNCING = "LIP_SYNCING"
    RENDERING_SCENE = "RENDERING_SCENE"
    ASSEMBLING_TIMELINE = "ASSEMBLING_TIMELINE"
    VALIDATING_OUTPUT = "VALIDATING_OUTPUT"
    UPLOADING = "UPLOADING"
    COMPLETED = "COMPLETED"
    RETRYING = "RETRYING"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class WatermarkStatus(StrEnum):
    PRESERVED = "PRESERVED"
    CLEAN_AUTHORIZED = "CLEAN_AUTHORIZED"


class StateTransition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    from_state: JobState | None
    to_state: JobState
    at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    stage: str | None = None
    error_class: str | None = None
    error_message: str | None = None


class CostEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage: str
    amount_usd: float
    at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    note: str = ""


class JobRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    video_id: str
    project_id: str
    owner_id: str
    idempotency_key: str
    request_fingerprint: str
    state: JobState = JobState.PENDING
    attempt: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    transitions: list[StateTransition] = Field(default_factory=list)
    output_asset_id: str | None = None
    provider_ref: str | None = None
    error_class: str | None = None
    error_message: str | None = None
    cancellation_requested: bool = False
    watermark_status: WatermarkStatus
    estimated_cost_usd: float = 0.0
    actual_cost_usd: float | None = None
    cost_entries: list[CostEntry] = Field(default_factory=list)
