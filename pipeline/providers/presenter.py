from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Any

import httpx

from pipeline.core.config import settings
from pipeline.gpu.runpod import RunPodServerlessClient
from pipeline.providers.base import PresenterProvider, ProviderResult, ProviderUnavailable
from pipeline.render.ffmpeg import ffprobe, run
from pipeline.storage.r2 import R2Storage


class HeyGenClient:
    """Authorized HeyGen API client.

    Aivatar keeps both the current v3 API and the maintained legacy v2 generation
    path behind this client because Avatar III still lives on the legacy API.
    No browser/session automation is used here.
    """

    def __init__(
        self,
        api_key: str | None,
        *,
        base_url: str = "https://api.heygen.com",
        timeout: float = 60.0,
        poll_interval: float = 5.0,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.poll_interval = poll_interval

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            raise ProviderUnavailable("HEYGEN_API_KEY is not configured")
        return {"x-api-key": self.api_key}

    def _json_request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        with httpx.Client(timeout=self.timeout) as client:
            response = client.request(method, f"{self.base_url}{path}", headers=self._headers(), **kwargs)
            response.raise_for_status()
            data = response.json()
            if isinstance(data, dict) and data.get("error"):
                raise RuntimeError(f"HeyGen API error: {data['error']}")
            return data

    def upload_asset(self, path: Path) -> str:
        if not path.exists():
            raise FileNotFoundError(path)
        headers = self._headers()
        with path.open("rb") as handle, httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                f"{self.base_url}/v3/assets",
                headers=headers,
                files={"file": (path.name, handle, "audio/wav")},
            )
            response.raise_for_status()
            payload = response.json()
        data = payload.get("data") or {}
        asset_id = data.get("id") or data.get("asset_id")
        if not asset_id:
            raise RuntimeError(f"HeyGen asset upload did not return an asset id: {payload}")
        return str(asset_id)

    def create_v3_video(
        self,
        *,
        avatar_id: str,
        audio_asset_id: str,
        title: str,
        resolution: str,
        aspect_ratio: str,
        engine: str,
        remove_background: bool = False,
    ) -> str:
        payload = {
            "type": "avatar",
            "avatar_id": avatar_id,
            "title": title,
            "aspect_ratio": aspect_ratio,
            "resolution": resolution,
            "audio_asset_id": audio_asset_id,
            "output_format": "mp4",
            "remove_background": remove_background,
            "engine": {"type": engine},
        }
        data = self._json_request("POST", "/v3/videos", json=payload)
        body = data.get("data") or {}
        video_id = body.get("id") or body.get("video_id")
        if not video_id:
            raise RuntimeError(f"HeyGen v3 did not return a video id: {data}")
        return str(video_id)

    def create_legacy_v2_video(
        self,
        *,
        avatar_id: str,
        audio_asset_id: str,
        title: str,
        width: int,
        height: int,
    ) -> str:
        # Kept intentionally to fields present in HeyGen's documented v2 Studio payload.
        # Engine selection is account/avatar dependent on the legacy API; Aivatar does not
        # invent undocumented request fields to force a model version.
        payload = {
            "video_inputs": [
                {
                    "character": {
                        "type": "avatar",
                        "avatar_id": avatar_id,
                        "avatar_style": "normal",
                    },
                    "voice": {"type": "audio", "audio_asset_id": audio_asset_id},
                }
            ],
            "dimension": {"width": width, "height": height},
            "title": title,
            "caption": False,
            "test": False,
        }
        data = self._json_request(
            "POST",
            "/v2/video/generate",
            json=payload,
        )
        body = data.get("data") or {}
        video_id = body.get("video_id") or body.get("id")
        if not video_id:
            raise RuntimeError(f"HeyGen v2 did not return a video id: {data}")
        return str(video_id)

    def status_v3(self, video_id: str) -> dict[str, Any]:
        data = self._json_request("GET", f"/v3/videos/{video_id}")
        return data.get("data") or data

    def status_legacy(self, video_id: str) -> dict[str, Any]:
        data = self._json_request("GET", "/v1/video_status.get", params={"video_id": video_id})
        return data.get("data") or data

    def wait(self, video_id: str, *, legacy: bool, timeout: float) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            data = self.status_legacy(video_id) if legacy else self.status_v3(video_id)
            status = str(data.get("status", "")).lower()
            if status == "completed":
                if not data.get("video_url"):
                    raise RuntimeError(f"HeyGen completed without video_url: {data}")
                return data
            if status == "failed":
                raise RuntimeError(f"HeyGen generation failed: {data.get('failure_message') or data.get('error') or data}")
            time.sleep(self.poll_interval)
        raise TimeoutError(f"HeyGen generation {video_id} exceeded {timeout:.0f}s")

    def download(self, url: str, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with httpx.stream("GET", url, timeout=self.timeout, follow_redirects=True) as response:
            response.raise_for_status()
            with destination.open("wb") as handle:
                for chunk in response.iter_bytes():
                    handle.write(chunk)
        return destination


class AuthorizedHeyGenProvider(PresenterProvider):
    name = "authorized_heygen"

    def generate(self, audio_path: Path, duration: float, output_dir: Path, **kwargs: Any) -> ProviderResult:
        if not settings.heygen_api_key:
            raise ProviderUnavailable("HEYGEN_API_KEY is not configured")
        avatar_id = str(kwargs.get("avatar_id") or "").strip()
        if not avatar_id:
            raise ProviderUnavailable("HeyGen requires a configured provider_avatar_id for the selected avatar")

        output_dir.mkdir(parents=True, exist_ok=True)
        client = HeyGenClient(
            settings.heygen_api_key,
            base_url=settings.heygen_api_base_url,
            timeout=settings.heygen_http_timeout_seconds,
            poll_interval=settings.heygen_poll_interval_seconds,
        )
        asset_id = client.upload_asset(audio_path)
        title = str(kwargs.get("title") or f"Aivatar presenter {kwargs.get('scene_id', '')}").strip()
        api_mode = str(kwargs.get("api_mode") or settings.heygen_api_mode).lower()
        legacy = api_mode in {"legacy", "legacy_v2", "v2", "avatar3", "avatar_iii"}
        if legacy:
            video_id = client.create_legacy_v2_video(
                avatar_id=avatar_id,
                audio_asset_id=asset_id,
                title=title,
                width=int(kwargs.get("width", 1920)),
                height=int(kwargs.get("height", 1080)),
            )
            engine = "avatar_iii_expected_legacy"
        else:
            engine = str(kwargs.get("engine") or settings.heygen_v3_engine)
            video_id = client.create_v3_video(
                avatar_id=avatar_id,
                audio_asset_id=asset_id,
                title=title,
                resolution=str(kwargs.get("resolution") or "1080p"),
                aspect_ratio=str(kwargs.get("aspect_ratio") or "16:9"),
                engine=engine,
                remove_background=bool(kwargs.get("remove_background", False)),
            )
        status = client.wait(video_id, legacy=legacy, timeout=settings.heygen_generation_timeout_seconds)
        out = output_dir / f"presenter_{kwargs.get('scene_id', video_id)}.mp4"
        client.download(str(status["video_url"]), out)
        return ProviderResult(
            out,
            duration,
            self.name,
            metadata={
                "video_id": video_id,
                "audio_asset_id": asset_id,
                "api_mode": "legacy_v2" if legacy else "v3",
                "engine": engine,
                "source_video_url_expiring": True,
            },
        )


class HiggsfieldClient:
    """Small server-side client for Higgsfield's documented async REST flow."""

    def __init__(
        self,
        api_key: str | None,
        *,
        base_url: str = "https://api.higgsfield.ai",
        timeout: float = 60.0,
        poll_interval: float = 5.0,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.poll_interval = poll_interval

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            raise ProviderUnavailable("HIGGSFIELD_API_KEY is not configured")
        return {"Authorization": f"Key {self.api_key}"}

    @staticmethod
    def _body(payload: dict[str, Any]) -> dict[str, Any]:
        body = payload.get("data") if isinstance(payload.get("data"), dict) else payload
        return body if isinstance(body, dict) else {}

    def _request(self, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
            response = client.request(method, url, headers=self._headers(), **kwargs)
            response.raise_for_status()
            payload = response.json()
        if isinstance(payload, dict) and payload.get("error"):
            raise RuntimeError(f"Higgsfield API error: {payload['error']}")
        return payload

    def upload_file(self, path: Path, content_type: str) -> str:
        """Upload a local reference through Higgsfield's signed-upload flow."""
        if not path.exists():
            raise FileNotFoundError(path)
        upload = self._request(
            "POST",
            f"{self.base_url}/files/generate-upload-url",
            json={"content_type": content_type},
        )
        body = self._body(upload)
        upload_url = body.get("upload_url")
        public_url = body.get("public_url")
        upload_headers = body.get("upload_headers") or {}
        if not upload_url or not public_url:
            raise RuntimeError(f"Higgsfield upload URL response is incomplete: {upload}")
        with path.open("rb") as handle, httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
            response = client.put(upload_url, headers=upload_headers, content=handle.read())
            response.raise_for_status()
        return str(public_url)

    def submit(self, model: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", f"{self.base_url}/{model.lstrip('/')}", json=payload)

    def wait(self, request: dict[str, Any], timeout: float) -> dict[str, Any]:
        body = self._body(request)
        request_id = body.get("request_id") or request.get("request_id")
        status_url = body.get("status_url") or request.get("status_url")
        if not request_id and not status_url:
            raise RuntimeError(f"Higgsfield did not return request_id/status_url: {request}")
        status_url = status_url or f"{self.base_url}/requests/{request_id}/status"
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            status_payload = self._request("GET", status_url)
            status_body = self._body(status_payload)
            status = str(status_body.get("status") or status_payload.get("status") or "").lower()
            if status == "completed":
                video = status_body.get("video") or status_payload.get("video") or {}
                video_url = video.get("url") if isinstance(video, dict) else video
                video_url = video_url or status_body.get("video_url") or status_payload.get("video_url")
                if not video_url:
                    raise RuntimeError(f"Higgsfield completed without a video URL: {status_payload}")
                return {**status_body, "video_url": str(video_url), "request_id": request_id}
            if status in {"failed", "nsfw", "canceled", "cancelled"}:
                raise RuntimeError(f"Higgsfield generation {status}: {status_body.get('error') or status_body}")
            time.sleep(self.poll_interval)
        raise TimeoutError(f"Higgsfield generation {request_id or status_url} exceeded {timeout:.0f}s")

    def download(self, url: str, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with httpx.stream("GET", url, timeout=self.timeout, follow_redirects=True) as response:
            response.raise_for_status()
            with destination.open("wb") as handle:
                for chunk in response.iter_bytes():
                    handle.write(chunk)
        return destination


class AuthorizedHiggsfieldProvider(PresenterProvider):
    name = "authorized_higgsfield"

    @staticmethod
    def _split_audio(audio_path: Path, output_dir: Path, chunk_seconds: float = 12.0) -> list[Path]:
        """Create provider-safe audio chunks for long-form presenter renders."""
        chunk_dir = output_dir / "higgsfield_chunks"
        chunk_dir.mkdir(parents=True, exist_ok=True)
        pattern = chunk_dir / "audio_%04d.wav"
        if not list(chunk_dir.glob("audio_*.wav")):
            run([
                "ffmpeg", "-y", "-loglevel", "error", "-i", str(audio_path),
                "-f", "segment", "-segment_time", f"{chunk_seconds:.3f}",
                "-reset_timestamps", "1", "-ar", "48000", "-ac", "1", str(pattern),
            ])
        return sorted(chunk_dir.glob("audio_*.wav"))

    @staticmethod
    def _concat_chunks(chunks: list[Path], output: Path) -> Path:
        manifest = output.with_suffix(".concat.txt")
        manifest.write_text("\n".join(f"file '{path.resolve()}'" for path in chunks), encoding="utf-8")
        run([
            "ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
            "-i", str(manifest), "-c", "copy", str(output),
        ])
        return output

    def _generate_clip(
        self,
        client: HiggsfieldClient,
        image_url: str,
        audio_path: Path,
        destination: Path,
        *,
        model: str,
        duration: float,
        resolution: str,
        prompt: str,
        title: str,
        manifest_path: Path,
    ) -> dict[str, Any]:
        if destination.exists() and destination.stat().st_size > 100_000:
            return json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {"reused": True}
        audio_url = client.upload_file(audio_path, "audio/wav")
        payload = {
            "image_url": image_url,
            "audio_url": audio_url,
            "duration": max(2, min(15, int(round(duration)))),
            "resolution": "1080p" if resolution.lower() == "1080p" else "720p",
            "prompt": prompt,
            "negative_prompt": "distortion, frame tearing, duplicate face, extra limbs, text, watermark",
        }
        submitted = client.submit(model, payload)
        status = client.wait(submitted, timeout=settings.higgsfield_generation_timeout_seconds)
        client.download(str(status["video_url"]), destination)
        metadata = {
            "request_id": status.get("request_id"),
            "model": model,
            "audio_url_uploaded": True,
            "reference_image_uploaded": True,
            "title": title,
        }
        manifest_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        return metadata

    def generate(self, audio_path: Path, duration: float, output_dir: Path, **kwargs: Any) -> ProviderResult:
        if not settings.higgsfield_api_key:
            raise ProviderUnavailable("HIGGSFIELD_API_KEY is not configured")
        reference_image = kwargs.get("reference_image_path")
        if not reference_image:
            raise ProviderUnavailable("Higgsfield requires the avatar reference image")
        reference_image = Path(reference_image)
        if not reference_image.exists():
            raise FileNotFoundError(reference_image)

        output_dir.mkdir(parents=True, exist_ok=True)
        client = HiggsfieldClient(
            settings.higgsfield_api_key,
            base_url=settings.higgsfield_api_base_url,
            timeout=settings.higgsfield_http_timeout_seconds,
            poll_interval=settings.higgsfield_poll_interval_seconds,
        )
        image_url = client.upload_file(reference_image, "image/png")
        model = str(kwargs.get("model") or settings.higgsfield_model)
        resolution = str(kwargs.get("resolution", "1080p"))
        prompt = str(kwargs.get("prompt") or "Natural front-facing presenter speaking to camera with realistic blinking, subtle head movement, and accurate lip synchronization.")
        title = str(kwargs.get("title") or f"Aivatar presenter {kwargs.get('scene_id', '')}")
        scene_id = str(kwargs.get("scene_id", "higgsfield"))
        out = output_dir / f"presenter_{scene_id}.mp4"
        metadata: dict[str, Any]
        if duration <= 15:
            metadata = self._generate_clip(
                client, image_url, audio_path, out, model=model, duration=duration,
                resolution=resolution, prompt=prompt, title=title,
                manifest_path=out.with_suffix(".json"),
            )
        else:
            chunk_dir = output_dir / f"{scene_id}_chunks"
            chunk_dir.mkdir(parents=True, exist_ok=True)
            chunk_audio = self._split_audio(audio_path, output_dir)
            rendered_chunks: list[Path] = []
            request_ids: list[str] = []
            for index, chunk in enumerate(chunk_audio):
                chunk_video = chunk_dir / f"chunk_{index:04d}.mp4"
                chunk_manifest = chunk_video.with_suffix(".json")
                chunk_duration = min(12.0, max(2.0, float(ffprobe(chunk).get("format", {}).get("duration", 12.0))))
                chunk_metadata = self._generate_clip(
                    client, image_url, chunk, chunk_video, model=model, duration=chunk_duration,
                    resolution=resolution, prompt=prompt, title=f"{title} / chunk {index + 1}",
                    manifest_path=chunk_manifest,
                )
                rendered_chunks.append(chunk_video)
                if chunk_metadata.get("request_id"):
                    request_ids.append(str(chunk_metadata["request_id"]))
            self._concat_chunks(rendered_chunks, out)
            metadata = {
                "model": model,
                "chunked": True,
                "chunk_count": len(rendered_chunks),
                "request_ids": request_ids,
                "reference_image_uploaded": True,
                "audio_url_uploaded": True,
            }
        return ProviderResult(
            out,
            duration,
            self.name,
            metadata={
                **metadata,
            },
        )


class MuseTalkFallbackProvider(PresenterProvider):
    name = "musetalk_fallback"

    def generate(self, audio_path: Path, duration: float, output_dir: Path, **kwargs: Any) -> ProviderResult:
        endpoint_id = settings.runpod_musetalk_endpoint_id
        if not endpoint_id:
            raise ProviderUnavailable("RUNPOD_MUSETALK_ENDPOINT_ID is not configured")
        reference_image = kwargs.get("reference_image_path")
        if not reference_image:
            raise ProviderUnavailable("MuseTalk fallback requires the avatar reference image")
        reference_image = Path(reference_image)
        if not reference_image.exists():
            raise FileNotFoundError(reference_image)

        project_id = str(kwargs.get("project_id") or "unassigned")
        scene_id = str(kwargs.get("scene_id") or "scene")
        r2 = R2Storage(
            settings.r2_account_id,
            settings.r2_access_key_id,
            settings.r2_secret_access_key,
            settings.r2_bucket,
        )
        if not r2.configured:
            raise ProviderUnavailable("R2 must be configured for MuseTalk remote input/output persistence")
        audio_key = r2.project_key(project_id, "presenter-input", f"{scene_id}.wav")
        image_key = r2.project_key(project_id, "presenter-input", f"{scene_id}{reference_image.suffix.lower() or '.png'}")
        output_key = r2.project_key(project_id, "presenter", f"{scene_id}.mp4")
        r2.upload_file(audio_path, audio_key, "audio/wav")
        r2.upload_file(reference_image, image_key)

        client = RunPodServerlessClient(settings.runpod_api_key, settings.runpod_base_url)
        result = client.run(
            endpoint_id,
            {
                "audio_r2_key": audio_key,
                "reference_image_r2_key": image_key,
                "output_r2_key": output_key,
                "duration": duration,
                "fps": int(kwargs.get("fps", 25)),
            },
            timeout=settings.runpod_job_timeout_seconds,
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        out = output_dir / f"presenter_{scene_id}.mp4"
        resolved_key = str(result.output.get("r2_key") or output_key)
        r2.download_file(resolved_key, out)
        return ProviderResult(
            out,
            duration,
            self.name,
            metadata={
                **result.output,
                "runpod_job_id": result.job_id,
                "gpu_seconds": (result.execution_ms or 0.0) / 1000.0,
                "r2_key": resolved_key,
            },
        )


class ManualPresenterImportProvider(PresenterProvider):
    name = "manual_presenter_import"

    def generate(self, audio_path: Path, duration: float, output_dir: Path, **kwargs: Any) -> ProviderResult:
        source = kwargs.get("source_path") or kwargs.get("clip_path")
        if not source:
            raise ProviderUnavailable("ManualPresenterImportProvider requires an explicit clip path")
        source = Path(source)
        if not source.exists():
            raise FileNotFoundError(source)
        output_dir.mkdir(parents=True, exist_ok=True)
        out = output_dir / f"presenter_{kwargs.get('scene_id', 'manual')}.mp4"
        # Normalize to a silent H.264 clip. The authoritative master narration is mixed later.
        run([
            "ffmpeg", "-y", "-loglevel", "error", "-i", str(source),
            "-t", f"{duration:.3f}", "-an", "-c:v", "libx264", "-preset", "medium",
            "-crf", "20", "-pix_fmt", "yuv420p", str(out),
        ])
        actual = float(ffprobe(out)["format"]["duration"])
        return ProviderResult(out, actual, self.name, metadata={"source_path": str(source)})
