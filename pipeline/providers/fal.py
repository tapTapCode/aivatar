from __future__ import annotations

import time
from pathlib import Path

import httpx

from pipeline.core.config import settings
from pipeline.providers.base import ImageProvider, ProviderResult, ProviderUnavailable


class FalFluxProvider(ImageProvider):
    """Hosted FLUX image generation through fal.ai's queue API."""

    name = "fal_flux"

    def generate(self, prompt: str, output_dir: Path, **kwargs) -> ProviderResult:
        if not settings.fal_api_key:
            raise ProviderUnavailable("FAL_API_KEY is not configured")

        model = settings.fal_model
        headers = {"Authorization": f"Key {settings.fal_api_key}", "Content-Type": "application/json"}
        payload = {
            "prompt": prompt,
            "image_size": {
                "width": int(kwargs.get("width", 1280)),
                "height": int(kwargs.get("height", 720)),
            },
            "num_images": 1,
            "output_format": "png",
            "enable_safety_checker": True,
            "guidance_scale": float(kwargs.get("guidance_scale", 2.5)),
            "num_inference_steps": int(kwargs.get("steps", 28)),
        }
        base = settings.fal_base_url.rstrip("/")
        with httpx.Client(timeout=settings.fal_http_timeout_seconds) as client:
            submitted = client.post(f"{base}/{model}", headers=headers, json=payload)
            submitted.raise_for_status()
            request = submitted.json()
            request_id = request.get("request_id")
            if not request_id:
                raise ProviderUnavailable("fal.ai did not return a request ID")

            for _ in range(max(1, int(settings.fal_generation_timeout_seconds / settings.fal_poll_interval_seconds))):
                status_url = request.get("status_url") or f"{base}/{model}/requests/{request_id}/status"
                status_response = client.get(status_url, headers=headers)
                status_response.raise_for_status()
                status = status_response.json()
                state = status.get("status")
                if state == "COMPLETED":
                    result_url = request.get("response_url") or f"{base}/{model}/requests/{request_id}"
                    result_response = client.get(result_url, headers=headers)
                    result_response.raise_for_status()
                    result = result_response.json()
                    images = result.get("images") or result.get("data", {}).get("images") or []
                    if not images or not images[0].get("url"):
                        raise ProviderUnavailable("fal.ai completed without an image URL")
                    image_response = client.get(images[0]["url"])
                    image_response.raise_for_status()
                    output_dir.mkdir(parents=True, exist_ok=True)
                    local_path = output_dir / str(kwargs.get("filename") or "image.png")
                    local_path.write_bytes(image_response.content)
                    return ProviderResult(
                        local_path,
                        0.0,
                        self.name,
                        metadata={"request_id": request_id, "model": model, "prompt": prompt},
                    )
                if state in {"FAILED", "CANCELLED"}:
                    raise ProviderUnavailable(f"fal.ai request {state.lower()}: {status.get('error') or 'unknown error'}")
                time.sleep(settings.fal_poll_interval_seconds)

        raise ProviderUnavailable("fal.ai image generation timed out")
