from __future__ import annotations
from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import Boolean, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pipeline.storage.db import Base

def uid() -> str:
    return str(uuid4())

def now() -> datetime:
    return datetime.now(timezone.utc)

class Channel(Base):
    __tablename__ = "channels"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    style_preset: Mapped[str] = mapped_column(String(80), default="documentary")
    aspect_ratio: Mapped[str] = mapped_column(String(16), default="16:9")
    resolution: Mapped[str] = mapped_column(String(16), default="1080p")
    settings_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(default=now)
    avatars: Mapped[list[Avatar]] = relationship(back_populates="channel", cascade="all, delete-orphan")
    projects: Mapped[list[Project]] = relationship(back_populates="channel", cascade="all, delete-orphan")

class Avatar(Base):
    __tablename__ = "avatars"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    channel_id: Mapped[str] = mapped_column(ForeignKey("channels.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    presenter_provider: Mapped[str] = mapped_column(String(80), default="authorized_higgsfield")
    provider_avatar_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reference_image_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    voice_provider: Mapped[str] = mapped_column(String(80), default="ai33")
    voice_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    settings_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(default=now)
    channel: Mapped[Channel] = relationship(back_populates="avatars")

class Project(Base):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    channel_id: Mapped[str] = mapped_column(ForeignKey("channels.id", ondelete="CASCADE"), index=True)
    avatar_id: Mapped[str | None] = mapped_column(ForeignKey("avatars.id", ondelete="SET NULL"), nullable=True)
    name: Mapped[str] = mapped_column(String(220))
    script: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(String(40), default="CREATED", index=True)
    expected_duration: Mapped[float] = mapped_column(Float, default=0)
    final_duration: Mapped[float | None] = mapped_column(Float, nullable=True)
    presenter_target: Mapped[float] = mapped_column(Float, default=0.30)
    presenter_actual: Mapped[float] = mapped_column(Float, default=0.0)
    resolution: Mapped[str] = mapped_column(String(16), default="1080p")
    aspect_ratio: Mapped[str] = mapped_column(String(16), default="16:9")
    budget_usd: Mapped[float] = mapped_column(Float, default=5.0)
    production_json: Mapped[dict] = mapped_column(JSON, default=dict)
    visual_density: Mapped[float] = mapped_column(Float, default=0.65)
    estimated_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    actual_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=now)
    updated_at: Mapped[datetime] = mapped_column(default=now, onupdate=now)
    lock_owner: Mapped[str | None] = mapped_column(String(160), nullable=True)
    lock_expires_at: Mapped[datetime | None] = mapped_column(nullable=True)
    channel: Mapped[Channel] = relationship(back_populates="projects")
    scenes: Mapped[list[Scene]] = relationship(back_populates="project", cascade="all, delete-orphan", order_by="Scene.ordinal")
    assets: Mapped[list[Asset]] = relationship(back_populates="project", cascade="all, delete-orphan")

class Scene(Base):
    __tablename__ = "scenes"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    ordinal: Mapped[int] = mapped_column(Integer)
    start: Mapped[float] = mapped_column(Float)
    end: Mapped[float] = mapped_column(Float)
    type: Mapped[str] = mapped_column(String(40))
    visual_prompt: Mapped[str] = mapped_column(Text, default="")
    motion: Mapped[str] = mapped_column(String(40), default="static")
    asset_strategy: Mapped[str] = mapped_column(String(40), default="flux_motion")
    motion_score: Mapped[float] = mapped_column(Float, default=0.0)
    estimated_visual_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    graphic_template: Mapped[str | None] = mapped_column(String(60), nullable=True)
    presenter_position: Mapped[str] = mapped_column(String(40), default="left")
    layout_json: Mapped[dict] = mapped_column(JSON, default=dict)
    locked: Mapped[bool] = mapped_column(Boolean, default=False)
    render_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    render_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    project: Mapped[Project] = relationship(back_populates="scenes")

class Asset(Base):
    __tablename__ = "assets"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    scene_id: Mapped[str | None] = mapped_column(ForeignKey("scenes.id", ondelete="SET NULL"), nullable=True)
    kind: Mapped[str] = mapped_column(String(40))
    provider: Mapped[str] = mapped_column(String(80))
    path: Mapped[str] = mapped_column(Text)
    duration: Mapped[float | None] = mapped_column(Float, nullable=True)
    checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    cache_key: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    locked: Mapped[bool] = mapped_column(Boolean, default=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(default=now)
    project: Mapped[Project] = relationship(back_populates="assets")

class AssetCacheEntry(Base):
    __tablename__ = "asset_cache"
    cache_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    kind: Mapped[str] = mapped_column(String(40), index=True)
    provider: Mapped[str] = mapped_column(String(80))
    model: Mapped[str] = mapped_column(String(255), default="")
    path: Mapped[str] = mapped_column(Text)
    checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    hit_count: Mapped[int] = mapped_column(Integer, default=0)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(default=now)
    last_used_at: Mapped[datetime] = mapped_column(default=now)

class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(60), index=True)
    state: Mapped[str] = mapped_column(String(40), default="QUEUED", index=True)
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    retryable: Mapped[bool] = mapped_column(Boolean, default=True)
    resume_count: Mapped[int] = mapped_column(Integer, default=0)
    heartbeat_at: Mapped[datetime | None] = mapped_column(nullable=True)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(default=now)
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)

class CostEntry(Base):
    __tablename__ = "cost_entries"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(80))
    asset_type: Mapped[str] = mapped_column(String(40))
    gpu_model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    gpu_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    external_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    estimated_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    actual_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(default=now)

class RenderHistory(Base):
    __tablename__ = "render_history"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    output_path: Mapped[str] = mapped_column(Text)
    duration: Mapped[float] = mapped_column(Float)
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    fps: Mapped[float] = mapped_column(Float)
    qc_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(default=now)


class ProductionRun(Base):
    __tablename__ = "production_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(60), index=True)
    state: Mapped[str] = mapped_column(String(40), default="RUNNING", index=True)
    wall_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    actual_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    cost_per_finished_minute: Mapped[float] = mapped_column(Float, default=0.0)
    storage_bytes: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    started_at: Mapped[datetime] = mapped_column(default=now)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)


class WorkspaceAccount(Base):
    """Commercial workspace container. Local mode uses one account until auth is configured."""
    __tablename__ = "workspace_accounts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(160), unique=True)
    owner_email: Mapped[str] = mapped_column(String(255), default="editor@aivatar.local")
    created_at: Mapped[datetime] = mapped_column(default=now)


class WorkspaceMember(Base):
    __tablename__ = "workspace_members"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspace_accounts.id", ondelete="CASCADE"), index=True)
    email: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(32), default="editor")
    created_at: Mapped[datetime] = mapped_column(default=now)


class CreditLedger(Base):
    __tablename__ = "credit_ledger"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspace_accounts.id", ondelete="CASCADE"), index=True)
    delta: Mapped[float] = mapped_column(Float)
    reason: Mapped[str] = mapped_column(String(160))
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    provider: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=now)


class WorkspaceSubscription(Base):
    __tablename__ = "workspace_subscriptions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspace_accounts.id", ondelete="CASCADE"), unique=True)
    plan: Mapped[str] = mapped_column(String(80), default="free")
    status: Mapped[str] = mapped_column(String(40), default="inactive")
    provider_customer_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    provider_subscription_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=now)
    updated_at: Mapped[datetime] = mapped_column(default=now, onupdate=now)
