from __future__ import annotations

from pathlib import Path

from pipeline.core.config import settings
from pipeline.gpu.runpod import RunPodServerlessClient
from pipeline.gpu.scheduler import GpuProfile, choose_gpu, infer_vram_gb
from pipeline.providers.base import ProviderResult, ProviderUnavailable, VideoProvider
from pipeline.storage.r2 import R2Storage


class LTXProvider(VideoProvider):
    name = "ltx_2_3"

    @property
    def model_family(self) -> str:
        return settings.aivatar_ltx_model

    def generate(self, prompt: str, duration: float, output_dir: Path, **kwargs) -> ProviderResult:
        endpoint_id = settings.runpod_ltx_endpoint_id
        if not endpoint_id:
            raise ProviderUnavailable("RUNPOD_LTX_ENDPOINT_ID is not configured")
        selection = choose_gpu(
            [GpuProfile(
                settings.runpod_ltx_gpu_model, infer_vram_gb(settings.runpod_ltx_gpu_model), settings.runpod_a100_hourly_usd,
                frozenset({"video"}), endpoint_id, benchmark=True,
            )],
            workload="video", min_vram_gb=48, estimated_seconds=0.0,
        )
        endpoint_id = selection.profile.endpoint_id or endpoint_id
        project_id = str(kwargs.get("project_id") or "unassigned")
        scene_id = str(kwargs.get("scene_id") or "asset")
        filename = str(kwargs.get("filename") or f"{scene_id}.mp4")
        r2 = R2Storage(settings.r2_account_id, settings.r2_access_key_id, settings.r2_secret_access_key, settings.r2_bucket)
        if not r2.configured:
            raise ProviderUnavailable("R2 must be configured for remote LTX asset persistence")
        key = r2.project_key(project_id, "videos", filename)
        client = RunPodServerlessClient(settings.runpod_api_key, settings.runpod_base_url)
        result = client.run(
            endpoint_id,
            {
                "prompt": prompt,
                "model_id": self.model_family,
                "checkpoint": settings.aivatar_ltx_checkpoint,
                "duration": duration,
                "width": int(kwargs.get("width", 1280)),
                "height": int(kwargs.get("height", 720)),
                "fps": int(kwargs.get("fps", 24)),
                "seed": int(kwargs.get("seed", 0)),
                "pipeline": settings.aivatar_ltx_pipeline,
                "quantization": settings.aivatar_ltx_quantization,
                "offload": settings.aivatar_ltx_offload,
                "r2_bucket": settings.r2_bucket,
                "r2_key": key,
            },
            timeout=settings.runpod_job_timeout_seconds,
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        local_path = output_dir / filename
        r2.download_file(result.output.get("r2_key", key), local_path)
        runtime_seconds = float(result.output.get("runtime_seconds") or ((result.execution_ms or 0.0) / 1000.0))
        estimated_cost = runtime_seconds / 3600.0 * settings.runpod_a100_hourly_usd if runtime_seconds else 0.0
        return ProviderResult(
            local_path,
            duration,
            self.name,
            estimated_cost_usd=round(estimated_cost, 6),
            metadata={
                **result.output,
                "runpod_job_id": result.job_id,
                "gpu_seconds": runtime_seconds,
                "gpu_model": result.output.get("gpu_model") or settings.runpod_ltx_gpu_model,
                "estimated_compute_cost_usd": round(estimated_cost, 6),
                "pipeline": settings.aivatar_ltx_pipeline,
                "model": self.model_family,
                "checkpoint": settings.aivatar_ltx_checkpoint,
            },
        )
