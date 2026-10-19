from __future__ import annotations

import shutil
from pathlib import Path

import httpx

from pipeline.audio.master import normalize_master_audio, write_audio_manifest
from pipeline.core.config import settings
from pipeline.providers.base import ProviderResult, ProviderUnavailable, VoiceProvider


class _ConfiguredHTTPVoiceProvider(VoiceProvider):
    api_key: str | None
    base_url: str | None
    default_voice_id: str | None

    def _generate_http(self, text: str, output_dir: Path, voice_id: str | None = None) -> ProviderResult:
        if not self.api_key or not self.base_url:
            raise ProviderUnavailable(f"{self.name} API key/base URL is not configured")
        output_dir.mkdir(parents=True, exist_ok=True)
        # The exact provider contracts are intentionally configured rather than guessed. This
        # adapter supports the common JSON TTS shape and raw-audio response used by many APIs.
        payload = {"text": text}
        resolved_voice = voice_id or self.default_voice_id
        if resolved_voice:
            payload["voice_id"] = resolved_voice
        headers = {"Authorization": f"Bearer {self.api_key}", "Accept": "audio/mpeg, audio/wav, application/json"}
        with httpx.Client(timeout=300.0) as client:
            response = client.post(self.base_url, headers=headers, json=payload)
            response.raise_for_status()
        content_type = response.headers.get("content-type", "").lower()
        if "application/json" in content_type:
            data = response.json()
            audio_url = data.get("audio_url") or data.get("url") or data.get("output_url")
            if not audio_url:
                raise ProviderUnavailable(f"{self.name} response did not include audio bytes or an audio URL")
            with httpx.Client(timeout=300.0) as client:
                audio_response = client.get(audio_url)
                audio_response.raise_for_status()
            raw = output_dir / "provider_audio.bin"
            raw.write_bytes(audio_response.content)
            metadata = data
        else:
            suffix = ".wav" if "wav" in content_type else ".mp3"
            raw = output_dir / f"provider_audio{suffix}"
            raw.write_bytes(response.content)
            metadata = {}
        wav, _mp3, duration = normalize_master_audio(raw, output_dir)
        write_audio_manifest(output_dir, self.name, duration, metadata)
        timestamps = metadata.get("words") or metadata.get("timestamps") or metadata.get("word_timestamps")
        return ProviderResult(
            path=wav,
            duration=duration,
            provider=self.name,
            metadata={**metadata, "provider_word_timestamps": timestamps} if timestamps else metadata,
        )


class AI33Provider(_ConfiguredHTTPVoiceProvider):
    name = "ai33"

    def __init__(self) -> None:
        self.api_key = settings.ai33_api_key
        self.base_url = settings.ai33_api_base_url
        self.default_voice_id = settings.ai33_voice_id

    def generate(self, text: str, duration: float, output_dir: Path, **kwargs) -> ProviderResult:
        return self._generate_http(text, output_dir, voice_id=kwargs.get("voice_id"))


class SixtyNineLabsProvider(_ConfiguredHTTPVoiceProvider):
    name = "69labs"

    def __init__(self) -> None:
        self.api_key = settings.sixty_nine_labs_api_key
        self.base_url = settings.sixty_nine_labs_api_base_url
        self.default_voice_id = settings.sixty_nine_labs_voice_id

    def generate(self, text: str, duration: float, output_dir: Path, **kwargs) -> ProviderResult:
        return self._generate_http(text, output_dir, voice_id=kwargs.get("voice_id"))


class ImportedAudioProvider(VoiceProvider):
    name = "imported_audio"

    def generate(self, text: str, duration: float, output_dir: Path, **kwargs) -> ProviderResult:
        source_path = kwargs.get("source_path")
        if source_path is None:
            raise ProviderUnavailable("ImportedAudioProvider requires source_path")
        source_path = Path(source_path)
        if not source_path.exists():
            raise FileNotFoundError(source_path)
        output_dir.mkdir(parents=True, exist_ok=True)
        preserved = output_dir / f"imported{source_path.suffix.lower()}"
        shutil.copy2(source_path, preserved)
        wav, _mp3, real_duration = normalize_master_audio(preserved, output_dir)
        write_audio_manifest(output_dir, self.name, real_duration, {"source": str(source_path)})
        return ProviderResult(wav, real_duration, self.name, metadata={"source": str(source_path)})
