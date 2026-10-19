from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="", extra="ignore")

    aivatar_env: str = "development"
    aivatar_workspace: Path = Path("./workspace")
    aivatar_database_url: str = "sqlite:///./workspace/aivatar.db"
    aivatar_max_project_jobs: int = 3
    aivatar_max_image_gpu_jobs: int = 2
    aivatar_max_video_gpu_jobs: int = 1
    aivatar_max_presenter_jobs: int = 3
    aivatar_max_ffmpeg_jobs: int = 2

    # Phase 4 budget-aware visual planning. These are planning limits, not cost guarantees.
    aivatar_default_project_budget_usd: float = 5.0
    aivatar_visual_budget_fraction: float = 0.60
    aivatar_ltx_motion_threshold: float = 0.64
    aivatar_max_ltx_scenes: int = 3
    aivatar_max_ltx_scene_seconds: float = 12.0
    aivatar_asset_cache_enabled: bool = True
    aivatar_image_provider: str = "fal_flux"

    # Phase 5 production hardening. Jobs are resumable/retryable and workspace cleanup is explicit.
    aivatar_job_max_attempts: int = 3
    aivatar_job_heartbeat_seconds: int = 15
    aivatar_requeue_interrupted_jobs: bool = True
    aivatar_cache_retention_days: int = 30
    aivatar_cache_max_bytes: int = 50 * 1024 * 1024 * 1024
    aivatar_operator_lock_ttl_seconds: int = 900
    aivatar_macos_min_version: str = "12.0"

    # Production activation gates. Historical credentials in the supplied project archive must
    # be rotated before a real provider run is considered production-ready.
    aivatar_archive_credentials_rotated: bool = False
    aivatar_reference_profile: str = "reference_documentary_v1"
    aivatar_music_catalog_dir: Path = Path("./workspace/music")
    aivatar_default_credits: float = 30.0

    # Hosted commercial controls. Empty values keep local mode safe and free.
    aivatar_auth_mode: str = "local"
    aivatar_public_base_url: str = "http://127.0.0.1:1420"
    stripe_secret_key: str | None = None
    stripe_publishable_key: str | None = None
    stripe_webhook_secret: str | None = None
    stripe_price_id: str | None = None
    stripe_credit_price_id: str | None = None


    # Voice providers. Endpoint URLs remain configurable because the supplied requirements do not
    # contain a stable public AI33/69Labs API contract that can safely be hardcoded.
    ai33_api_key: str | None = None
    ai33_api_base_url: str | None = None
    ai33_voice_id: str | None = None
    sixty_nine_labs_api_key: str | None = None
    sixty_nine_labs_api_base_url: str | None = None
    sixty_nine_labs_voice_id: str | None = None

    # Authorized presenter integration only. Avatar III uses the maintained legacy API path;
    # v3 is available for IV/V without affecting the rest of the pipeline.
    heygen_api_key: str | None = None
    heygen_api_base_url: str = "https://api.heygen.com"
    heygen_api_mode: str = "legacy_v2"
    heygen_v3_engine: str = "avatar_iv"
    heygen_http_timeout_seconds: float = 60.0
    heygen_poll_interval_seconds: float = 5.0
    heygen_generation_timeout_seconds: float = 1800.0

    # Higgsfield presenter integration. The key stays server-side; the browser never calls
    # Higgsfield directly. The default model is the documented image-to-video model that accepts
    # an audio_url, while the model path remains configurable as Higgsfield expands its catalog.
    higgsfield_api_key: str | None = None
    higgsfield_api_base_url: str = "https://api.higgsfield.ai"
    higgsfield_model: str = "wan/v2.7/image-to-video"
    higgsfield_http_timeout_seconds: float = 60.0
    higgsfield_poll_interval_seconds: float = 5.0
    higgsfield_generation_timeout_seconds: float = 1800.0
    aivatar_presenter_provider: str = "authorized_higgsfield"

    # Hosted FLUX image generation. fal.ai replaces the RunPod + R2 image worker path.
    fal_api_key: str | None = None
    fal_base_url: str = "https://queue.fal.run"
    fal_model: str = "fal-ai/flux-2"
    fal_poll_interval_seconds: float = 2.0
    fal_http_timeout_seconds: float = 60.0
    fal_generation_timeout_seconds: float = 900.0

    # RunPod Serverless is the default GPU transport; ordinary Pods remain useful for benchmarking.
    runpod_api_key: str | None = None
    runpod_base_url: str = "https://api.runpod.ai/v2"
    runpod_flux_endpoint_id: str | None = None
    runpod_ltx_endpoint_id: str | None = None
    runpod_musetalk_endpoint_id: str | None = None
    runpod_job_timeout_seconds: float = 1800.0

    # Current production-oriented defaults; both remain overrideable from the environment.
    aivatar_flux_model: str = "black-forest-labs/FLUX.2-klein-4B"
    aivatar_ltx_model: str = "Lightricks/LTX-2.3"
    aivatar_ltx_checkpoint: str = "ltx-2.3-22b-distilled-1.1.safetensors"
    aivatar_ltx_spatial_upscaler: str = "ltx-2.3-spatial-upscaler-x2-1.1.safetensors"
    aivatar_ltx_gemma_model: str = "google/gemma-3-12b-it-qat-q4_0-unquantized"
    aivatar_ltx_pipeline: str = "distilled"
    aivatar_ltx_quantization: str = "none"
    aivatar_ltx_offload: str = "none"

    # Endpoint metadata is used for scheduling/cost estimates only; serverless deployment owns
    # the actual GPU inventory. A100 values come from the project's measured benchmark.
    runpod_flux_gpu_model: str = "NVIDIA A100 PCIe 80GB"
    runpod_ltx_gpu_model: str = "NVIDIA A100 PCIe 80GB"
    runpod_musetalk_gpu_model: str = "NVIDIA A100 PCIe 80GB"
    runpod_a100_hourly_usd: float = 1.39

    # Cloudflare R2 persistent project-media storage.
    r2_account_id: str | None = None
    r2_access_key_id: str | None = None
    r2_secret_access_key: str | None = None
    r2_bucket: str = "aivatar"

    # Hugging Face token is passed to workers at runtime for licensed/gated models when required.
    hf_token: str | None = None

    def ensure_dirs(self) -> None:
        self.aivatar_workspace.mkdir(parents=True, exist_ok=True)
        (self.aivatar_workspace / "projects").mkdir(parents=True, exist_ok=True)
        self.aivatar_music_catalog_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
settings.ensure_dirs()
