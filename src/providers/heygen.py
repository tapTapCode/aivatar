from __future__ import annotations

import asyncio
import json
import os
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, Protocol

import httpx

from src.providers.base import ProviderError, ProviderNotConfiguredError
from src.providers.common import asset_id, file_sha256
from src.rendering import probe_media
from src.schemas.assets import AssetKind, GeneratedAsset, Provenance
from src.schemas.requests import AvatarSourceRequest, LipSyncRequest


class RetentionStore(Protocol):
    async def put_file(self, source: Path, *, key: str) -> str: ...


class HeyGenAvatarSourceProvider:
    """Resolves a HeyGen avatar ID without exposing provider controls to the UI."""

    async def resolve(self, request: AvatarSourceRequest) -> GeneratedAsset:
        avatar_id_value = request.avatar_id.strip()
        if not avatar_id_value or any(character.isspace() for character in avatar_id_value):
            raise ValueError("invalid avatar_id")
        output = Path(request.context.work_dir) / "avatar-provider-reference.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        payload = {"avatar_id": avatar_id_value, "provider": "heygen_api"}
        temporary = output.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(payload, sort_keys=True) + "\n")
        os.replace(temporary, output)
        digest = file_sha256(output)
        return GeneratedAsset(
            asset_id=asset_id("avatar", digest),
            kind=AssetKind.AVATAR_SOURCE,
            uri=str(output.resolve()),
            content_hash=digest,
            project_id=request.context.project_id,
            scene_id=request.context.scene_id,
            duration_seconds=request.duration_seconds,
            width=request.width,
            height=request.height,
            fps=request.fps,
            mime_type="application/json",
            provenance=Provenance(
                provider="heygen-api-avatar-registry",
                model_identifier="workspace-avatar",
                checkpoint_revision="provider-managed",
                model_configuration={"avatar_id": avatar_id_value},
            ),
        )


class HeyGenLipSyncGenerator:
    RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}

    def __init__(
        self,
        *,
        api_key: str,
        api_base: str = "https://api.heygen.com",
        engine: str = "avatar_iv",
        voice_mode: str = "native",
        resolution: str = "1080p",
        default_voice_id: str = "",
        rate_usd_per_minute: float = 4.0,
        maximum_cost_usd_per_job: float = 25.0,
        poll_interval_seconds: float = 10.0,
        timeout_seconds: float = 7200.0,
        maximum_download_bytes: int = 2 * 1024**3,
        retention_store: RetentionStore | None = None,
        client: httpx.AsyncClient | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if engine not in {"avatar_iii", "avatar_iv", "avatar_v"}:
            raise ValueError("unsupported HeyGen engine")
        if resolution not in {"720p", "1080p", "4k"}:
            raise ValueError("unsupported HeyGen resolution")
        if voice_mode not in {"native", "audio"}:
            raise ValueError("unsupported presenter voice mode")
        if rate_usd_per_minute <= 0 or maximum_cost_usd_per_job <= 0:
            raise ValueError("HeyGen cost settings must be positive")
        self.api_key = api_key
        self.api_base = api_base.rstrip("/")
        self.engine = engine
        self.voice_mode = voice_mode
        self.resolution = resolution
        self.default_voice_id = default_voice_id.strip()
        self.rate_usd_per_minute = rate_usd_per_minute
        self.maximum_cost_usd_per_job = maximum_cost_usd_per_job
        self.poll_interval_seconds = poll_interval_seconds
        self.timeout_seconds = timeout_seconds
        self.maximum_download_bytes = maximum_download_bytes
        self.retention_store = retention_store
        self.client = client or httpx.AsyncClient(timeout=httpx.Timeout(120.0))
        self.sleep = sleep
        self._reserved_costs: dict[str, float] = {}
        self._budget_lock = asyncio.Lock()

    async def generate(self, request: LipSyncRequest) -> GeneratedAsset:
        if not self.api_key:
            raise ProviderNotConfiguredError("HEYGEN_API_KEY is required")
        started = time.perf_counter()
        estimated_cost = self.estimate_cost(request.duration_seconds)
        await self._reserve_budget(request.context.job_id, estimated_cost)
        avatar_id_value = str(
            request.avatar.provenance.model_configuration.get("avatar_id", "")
        ).strip()
        if not avatar_id_value:
            raise ProviderError("HeyGen avatar source is missing avatar_id")
        uploaded_asset_id = None
        if self.voice_mode == "audio":
            if request.audio is None:
                raise ProviderError("external-audio presenter mode requires narration audio")
            audio = Path(request.audio.uri).resolve()
            if not audio.is_file():
                raise ProviderError(f"narration audio is unavailable: {audio}")
            uploaded_asset_id = await self._upload_audio(audio)
        video_id = await self._create_video(
            avatar_id_value=avatar_id_value,
            audio_asset_id=uploaded_asset_id,
            request=request,
        )
        details = await self._wait_for_video(video_id)
        video_url = str(details.get("video_url") or "").strip()
        if not video_url:
            raise ProviderError("completed HeyGen render did not include video_url")
        output = Path(request.context.work_dir) / f"{request.context.scene_id}-presenter.mp4"
        await self._download(video_url, output)
        media = probe_media(str(output))
        if media.width is None or media.height is None or not media.has_audio:
            raise ProviderError("downloaded HeyGen MP4 failed media validation")
        tolerance = max(1.0, request.duration_seconds * 0.05)
        if abs(media.duration_seconds - request.duration_seconds) > tolerance:
            raise ProviderError(
                "downloaded HeyGen MP4 duration differs from narration by "
                f"{abs(media.duration_seconds - request.duration_seconds):.2f}s"
            )
        digest = file_sha256(output)
        retained_uri = None
        if self.retention_store is not None:
            retained_uri = await self.retention_store.put_file(
                output,
                key=(
                    f"{request.context.project_id}/{request.context.job_id}/"
                    f"{request.context.scene_id}/{digest}.mp4"
                ),
            )
        return GeneratedAsset(
            asset_id=asset_id("lip", digest),
            kind=AssetKind.LIPSYNC_VIDEO,
            uri=str(output.resolve()),
            content_hash=digest,
            project_id=request.context.project_id,
            scene_id=request.context.scene_id,
            parent_asset_ids=(request.avatar.asset_id,)
            if request.audio is None
            else (request.avatar.asset_id, request.audio.asset_id),
            duration_seconds=media.duration_seconds,
            width=media.width,
            height=media.height,
            fps=media.fps,
            mime_type="video/mp4",
            provenance=Provenance(
                provider="heygen_api",
                model_identifier=self.engine,
                checkpoint_revision="provider-managed-v3",
                model_configuration={
                    "resolution": self.resolution,
                    "video_id": video_id,
                    "estimated_cost_usd": round(estimated_cost, 4),
                    "retained_uri": retained_uri,
                },
                generation_latency_seconds=time.perf_counter() - started,
            ),
        )

    def estimate_cost(self, duration_seconds: float) -> float:
        from src.orchestration.cost import heygen_avatar_iv_cost

        return heygen_avatar_iv_cost(duration_seconds, self.rate_usd_per_minute)

    async def list_voices(self) -> list[dict[str, str]]:
        if not self.api_key:
            raise ProviderNotConfiguredError("HEYGEN_API_KEY is required")
        payload = await self._request_json("GET", "/v2/voices")
        data = payload.get("data") or payload
        raw = data.get("voices") if isinstance(data, dict) else data
        voices: list[dict[str, str]] = []
        for item in raw or []:
            if not isinstance(item, dict):
                continue
            voice_id = str(item.get("voice_id") or item.get("id") or "").strip()
            if not voice_id:
                continue
            voices.append(
                {
                    "voice_id": voice_id,
                    "name": str(item.get("name") or voice_id),
                    "language": str(item.get("language") or item.get("locale") or ""),
                }
            )
        return voices

    async def list_avatars(self) -> list[dict[str, str]]:
        if not self.api_key:
            raise ProviderNotConfiguredError("HEYGEN_API_KEY is required")
        payload = await self._request_json("GET", "/v2/avatars")
        data = payload.get("data") or payload
        raw = []
        if isinstance(data, dict):
            raw = list(data.get("talking_photos") or []) + list(data.get("avatars") or [])
        avatars: list[dict[str, str]] = []
        for item in raw or []:
            if not isinstance(item, dict):
                continue
            avatar_id = str(
                item.get("avatar_id") or item.get("talking_photo_id") or item.get("id") or ""
            ).strip()
            if not avatar_id:
                continue
            avatars.append(
                {
                    "avatar_id": avatar_id,
                    "name": str(item.get("avatar_name") or item.get("name") or avatar_id),
                }
            )
        return avatars

    async def resolve_voice_id(self, requested: str) -> str:
        voice_id = requested.strip()
        if voice_id and voice_id != "provider_voice":
            return voice_id
        if self.default_voice_id:
            return self.default_voice_id
        voices = await self.list_voices()
        for item in voices:
            haystack = f"{item.get('language', '')} {item.get('name', '')}".lower()
            if haystack.startswith("en") or "english" in haystack:
                return item["voice_id"]
        if voices:
            return voices[0]["voice_id"]
        raise ProviderError("native presenter mode requires a HeyGen voice ID")

    async def create_presenter_video(
        self,
        *,
        avatar_id: str,
        script: str,
        voice_id: str,
        job_id: str,
        title: str,
        width: int | None,
        height: int | None,
        duration_seconds: float,
    ) -> str:
        if not self.api_key:
            raise ProviderNotConfiguredError("HEYGEN_API_KEY is required")
        await self._reserve_budget(job_id, self.estimate_cost(duration_seconds))
        resolved_voice = await self.resolve_voice_id(voice_id)
        if not script.strip() or not resolved_voice:
            raise ProviderError("native presenter mode requires script text and a HeyGen voice ID")
        response = await self._request_json(
            "POST",
            "/v3/videos",
            json_body={
                "type": "avatar",
                "avatar_id": avatar_id,
                "title": title,
                "aspect_ratio": self._aspect_ratio(width, height),
                "resolution": self.resolution,
                "output_format": "mp4",
                "engine": {"type": self.engine},
                "script": script.strip(),
                "voice_id": resolved_voice,
            },
        )
        data = response.get("data") or {}
        video_id = str(data.get("video_id") or data.get("id") or "").strip()
        if not video_id:
            raise ProviderError("HeyGen create-video response did not include video_id")
        return video_id

    async def poll_video(self, video_id: str) -> dict[str, Any]:
        if not self.api_key:
            raise ProviderNotConfiguredError("HEYGEN_API_KEY is required")
        payload = await self._request_json("GET", f"/v3/videos/{video_id}")
        data = payload.get("data") or {}
        status = str(data.get("status") or "").lower()
        if status in {"failed", "error"}:
            message = data.get("failure_message") or "provider reported failure"
            raise ProviderError(f"HeyGen render failed: {message}")
        if status and status not in {"completed", "pending", "waiting", "processing"}:
            raise ProviderError(f"HeyGen returned unknown render status: {status}")
        return data

    async def fresh_video_url(self, video_id: str) -> str:
        details = await self.poll_video(video_id)
        if str(details.get("status") or "").lower() != "completed":
            raise ProviderError("HeyGen export is not ready yet", retryable=True)
        video_url = str(details.get("video_url") or "").strip()
        if not video_url:
            raise ProviderError("completed HeyGen render did not include video_url")
        return video_url

    async def download_completed(
        self, video_id: str, destination: Path, *, duration_seconds: float
    ) -> GeneratedAsset:
        video_url = await self.fresh_video_url(video_id)
        await self._download(video_url, destination)
        media = self._media_info(destination, duration_seconds=duration_seconds)
        digest = file_sha256(destination)
        return GeneratedAsset(
            asset_id=asset_id("final", digest),
            kind=AssetKind.FINAL_VIDEO,
            uri=str(destination.resolve()),
            content_hash=digest,
            project_id="",
            scene_id=None,
            duration_seconds=media.duration_seconds,
            width=media.width,
            height=media.height,
            fps=media.fps,
            mime_type="video/mp4",
            provenance=Provenance(
                provider="heygen_api",
                model_identifier=self.engine,
                checkpoint_revision="provider-managed-v3",
                model_configuration={"video_id": video_id, "heygen_video_id": video_id},
            ),
        )

    def _media_info(self, output: Path, *, duration_seconds: float):
        try:
            media = probe_media(str(output))
            if media.width and media.height and media.has_audio:
                return media
        except Exception:
            pass
        from src.rendering import MediaInfo

        return MediaInfo(
            duration_seconds=duration_seconds,
            width=None,
            height=None,
            fps=None,
            video_codec="h264",
            pixel_format=None,
            has_audio=True,
            audio_codec="aac",
            sample_rate=48000,
            channels=2,
            video_duration_seconds=duration_seconds,
            audio_duration_seconds=duration_seconds,
        )

    async def _reserve_budget(self, job_id: str, amount: float) -> None:
        async with self._budget_lock:
            updated = self._reserved_costs.get(job_id, 0.0) + amount
            if updated > self.maximum_cost_usd_per_job + 1e-9:
                raise ProviderError(
                    f"HeyGen job cost guard rejected ${updated:.2f}; "
                    f"maximum is ${self.maximum_cost_usd_per_job:.2f}"
                )
            self._reserved_costs[job_id] = updated

    async def _upload_audio(self, audio: Path) -> str:
        if audio.stat().st_size > 128 * 1024**2:
            raise ProviderError("narration audio exceeds the 128 MiB upload guard")
        content_type = "audio/wav" if audio.suffix.lower() == ".wav" else "audio/mpeg"
        payload = await self._request_json(
            "POST",
            "/v3/assets",
            files={"file": (audio.name, audio.read_bytes(), content_type)},
        )
        data = payload.get("data") or {}
        asset_id_value = str(data.get("asset_id") or data.get("id") or "").strip()
        if not asset_id_value:
            raise ProviderError("HeyGen audio upload did not return an asset ID")
        return asset_id_value

    async def _create_video(
        self,
        *,
        avatar_id_value: str,
        audio_asset_id: str | None,
        request: LipSyncRequest,
    ) -> str:
        if self.voice_mode == "native":
            voice_id = (request.voice_id or "").strip()
            if voice_id == "provider_voice":
                voice_id = self.default_voice_id
            voice = {
                "type": "text",
                "input_text": (request.narration_text or "").strip(),
                "voice_id": voice_id,
            }
            if not voice["input_text"] or not voice["voice_id"]:
                raise ProviderError("native presenter mode requires script text and a HeyGen voice ID")
        else:
            if not audio_asset_id:
                raise ProviderError("external-audio presenter mode requires an uploaded asset")
            voice = {"type": "audio", "audio_asset_id": audio_asset_id}
        payload = {
            "type": "avatar",
            "avatar_id": avatar_id_value,
            "title": f"{request.context.project_id}-{request.context.scene_id}",
            "aspect_ratio": self._aspect_ratio(request.avatar.width, request.avatar.height),
            "resolution": self.resolution,
            "output_format": "mp4",
            "engine": {"type": self.engine},
        }
        if voice["type"] == "text":
            payload["script"] = voice["input_text"]
            payload["voice_id"] = voice["voice_id"]
        else:
            payload["audio_asset_id"] = voice["audio_asset_id"]
        response = await self._request_json("POST", "/v3/videos", json_body=payload)
        data = response.get("data") or {}
        video_id = str(data.get("video_id") or data.get("id") or "").strip()
        if not video_id:
            raise ProviderError("HeyGen create-video response did not include video_id")
        return video_id

    async def _wait_for_video(self, video_id: str) -> dict[str, Any]:
        deadline = time.monotonic() + self.timeout_seconds
        while time.monotonic() < deadline:
            payload = await self._request_json("GET", f"/v3/videos/{video_id}")
            data = payload.get("data") or {}
            status = str(data.get("status") or "").lower()
            if status == "completed":
                return data
            if status in {"failed", "error"}:
                message = data.get("failure_message") or "provider reported failure"
                raise ProviderError(f"HeyGen render failed: {message}")
            if status not in {"pending", "waiting", "processing", ""}:
                raise ProviderError(f"HeyGen returned unknown render status: {status}")
            await self.sleep(self.poll_interval_seconds)
        raise ProviderError("HeyGen render polling timed out", retryable=True)

    @staticmethod
    def _aspect_ratio(width: int | None, height: int | None) -> str:
        if not width or not height:
            return "16:9"
        ratio = width / height
        candidates = {
            "16:9": 16 / 9,
            "9:16": 9 / 16,
            "1:1": 1.0,
            "4:3": 4 / 3,
            "4:5": 4 / 5,
        }
        return min(candidates, key=lambda name: abs(candidates[name] - ratio))

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        files: dict[str, tuple[str, bytes, str]] | None = None,
    ) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                response = await self.client.request(
                    method,
                    f"{self.api_base}{path}",
                    headers={"x-api-key": self.api_key, "accept": "application/json"},
                    json=json_body,
                    files=files,
                )
                if response.status_code in self.RETRYABLE_STATUS_CODES:
                    raise ProviderError(
                        f"HeyGen temporarily returned HTTP {response.status_code}",
                        retryable=True,
                    )
                if response.is_error:
                    raise ProviderError(f"HeyGen request failed with HTTP {response.status_code}")
                payload = response.json()
                if not isinstance(payload, dict):
                    raise ProviderError("HeyGen returned a non-object JSON response")
                if payload.get("error"):
                    raise ProviderError("HeyGen returned an API error")
                return payload
            except (httpx.TransportError, ProviderError) as exc:
                last_error = exc
                retryable = isinstance(exc, httpx.TransportError) or getattr(
                    exc, "retryable", False
                )
                if not retryable or attempt == 2:
                    raise ProviderError(str(exc), retryable=retryable) from exc
                await self.sleep(2.0**attempt)
        raise ProviderError(str(last_error), retryable=True)

    async def _download(self, url: str, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(".mp4.tmp")
        temporary.unlink(missing_ok=True)
        try:
            async with self.client.stream(
                "GET", url, headers={"user-agent": "Siloq/1.0"}
            ) as response:
                if response.is_error:
                    raise ProviderError(
                        f"HeyGen MP4 download failed with HTTP {response.status_code}",
                        retryable=response.status_code in self.RETRYABLE_STATUS_CODES,
                    )
                size = 0
                with temporary.open("wb") as target:
                    async for chunk in response.aiter_bytes():
                        size += len(chunk)
                        if size > self.maximum_download_bytes:
                            raise ProviderError("HeyGen MP4 exceeded the download size guard")
                        target.write(chunk)
            if not temporary.stat().st_size:
                raise ProviderError("HeyGen MP4 download was empty")
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)


def estimate_project_avatar_cost(scenes: list[Any], *, rate_usd_per_minute: float) -> float:
    seconds = 0.0
    for scene in scenes:
        visual_format = getattr(scene.visual_format, "value", scene.visual_format)
        if visual_format not in {"PRESENTER", "SPLIT"}:
            continue
        duration = scene.duration_seconds
        if duration is None:
            duration = max(1.0, len(scene.narration_text.split()) / 2.6)
        seconds += float(duration)
    from src.orchestration.cost import heygen_avatar_iv_cost

    return heygen_avatar_iv_cost(seconds, rate_usd_per_minute)
