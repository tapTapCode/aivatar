from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path
from typing import Any

from src.providers.common import asset_id, file_sha256
from src.schemas.assets import AssetKind, GeneratedAsset, Provenance
from src.schemas.requests import SpeechGenerationRequest


class ChatterboxSpeechGenerator:
    """Lazy, worker-local Chatterbox adapter with an allow-listed voice registry."""

    def __init__(self, *, voice_root: str | Path, device: str = "cuda") -> None:
        self.voice_root = Path(voice_root).resolve()
        self.device = device
        self._model: Any | None = None

    async def generate(self, request: SpeechGenerationRequest) -> GeneratedAsset:
        return await asyncio.to_thread(self._generate, request)

    def _generate(self, request: SpeechGenerationRequest) -> GeneratedAsset:
        started = time.perf_counter()
        reference = self._voice_reference(request.voice_id)
        output = Path(request.context.work_dir) / f"{request.context.scene_id}-speech.wav"
        output.parent.mkdir(parents=True, exist_ok=True)
        model = self._load_model()
        wav = model.generate(request.text, audio_prompt_path=str(reference))
        try:
            import torchaudio
        except ImportError as exc:  # pragma: no cover - exercised in the GPU image
            raise RuntimeError("torchaudio is required by the Chatterbox worker") from exc
        torchaudio.save(str(output), wav, model.sr)
        digest = file_sha256(output)
        duration = float(wav.shape[-1]) / float(model.sr)
        return GeneratedAsset(
            asset_id=asset_id("aud", digest),
            kind=AssetKind.AUDIO,
            uri=str(output.resolve()),
            content_hash=digest,
            project_id=request.context.project_id,
            scene_id=request.context.scene_id,
            duration_seconds=duration,
            sample_rate=int(model.sr),
            mime_type="audio/wav",
            provenance=Provenance(
                provider="chatterbox-local",
                model_identifier="resemble-ai/chatterbox",
                checkpoint_revision=os.environ.get("CHATTERBOX_MODEL_REVISION", "0.1.7"),
                model_configuration={"voice_id": request.voice_id, "device": self.device},
                generation_latency_seconds=time.perf_counter() - started,
            ),
        )

    def _load_model(self) -> Any:
        if self._model is None:
            try:
                from chatterbox.tts import ChatterboxTTS
            except ImportError as exc:  # pragma: no cover - exercised in the GPU image
                raise RuntimeError("install chatterbox-tts==0.1.7 in the TTS worker") from exc
            self._model = ChatterboxTTS.from_pretrained(device=self.device)
        return self._model

    def _voice_reference(self, voice_id: str) -> Path:
        if not voice_id or not voice_id.replace("_", "").replace("-", "").isalnum():
            raise ValueError("voice_id must contain only letters, numbers, hyphens, or underscores")
        for suffix in (".wav", ".mp3", ".flac", ".m4a"):
            candidate = self.voice_root / f"{voice_id}{suffix}"
            if candidate.is_file() and candidate.resolve().is_relative_to(self.voice_root):
                return candidate
        raise FileNotFoundError(f"authorized voice reference was not found for {voice_id}")


def create_chatterbox_provider() -> ChatterboxSpeechGenerator:
    return ChatterboxSpeechGenerator(
        voice_root=os.environ.get("VOICE_REGISTRY_ROOT", "/data/voices"),
        device=os.environ.get("CHATTERBOX_DEVICE", "cuda"),
    )
