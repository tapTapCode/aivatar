from pydantic import BaseModel, Field

class ChannelCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    style_preset: str = "documentary"
    settings_json: dict = Field(default_factory=dict)

class AvatarCreate(BaseModel):
    channel_id: str
    name: str = Field(min_length=1, max_length=160)
    presenter_provider: str = "authorized_higgsfield"
    voice_provider: str = "ai33"
    provider_avatar_id: str | None = None
    reference_image_path: str | None = None
    voice_id: str | None = None
    settings_json: dict = Field(default_factory=dict)

class ProjectCreate(BaseModel):
    channel_id: str
    avatar_id: str | None = None
    name: str = Field(min_length=1, max_length=220)
    script: str = Field(min_length=1)
    expected_duration: float = Field(default=60.0, gt=0, le=7200)
    presenter_target: float = Field(default=0.30, ge=0, le=1)
    resolution: str = "1080p"
    aspect_ratio: str = "16:9"
    budget_usd: float = Field(default=5.0, gt=0, le=1000)
    visual_density: float = Field(default=0.65, ge=0, le=1)

class SceneUpdate(BaseModel):
    type: str | None = None
    start: float | None = None
    end: float | None = None
    visual_prompt: str | None = None
    motion: str | None = None
    asset_strategy: str | None = None
    graphic_template: str | None = None
    presenter_position: str | None = None
    layout_json: dict | None = None
    locked: bool | None = None

class VoiceGenerateRequest(BaseModel):
    provider: str = "mock_voice"
    voice_id: str | None = None
    source_path: str | None = None


class PresenterGenerateRequest(BaseModel):
    provider: str | None = None
    force: bool = False
    allow_fallback: bool = True
    manual_clip_path: str | None = None


class PresenterBatchRequest(BaseModel):
    provider: str | None = None
    force: bool = False
    allow_fallback: bool = True


class ScenePreviewRequest(BaseModel):
    force: bool = False
    visual_path: str | None = None


class VisualPlanRequest(BaseModel):
    budget_usd: float | None = Field(default=None, gt=0, le=1000)
    max_ltx_scenes: int | None = Field(default=None, ge=0, le=100)
    force_replan: bool = False


class AssetGenerateRequest(BaseModel):
    force: bool = False
    mock: bool = True



class ProjectLockRequest(BaseModel):
    owner: str = Field(min_length=1, max_length=160)
    ttl_seconds: int = Field(default=900, ge=60, le=86400)


class ProjectUnlockRequest(BaseModel):
    owner: str = Field(min_length=1, max_length=160)
    force: bool = False


class CleanupRequest(BaseModel):
    keep_final: bool = True


class CachePruneRequest(BaseModel):
    older_than_days: int = Field(default=30, ge=0, le=3650)
    max_bytes: int | None = Field(default=None, ge=0)
    dry_run: bool = False
