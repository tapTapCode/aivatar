from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import yaml

from src.providers.common import asset_id, file_sha256
from src.schemas.assets import AssetKind, GeneratedAsset, Provenance
from src.schemas.requests import LipSyncRequest


class MuseTalkLipSyncGenerator:
    """Adapter for the official MuseTalk 1.5 inference entrypoint."""

    def __init__(self, *, source_root: str | Path, models_root: str | Path) -> None:
        self.source_root = Path(source_root).resolve()
        self.models_root = Path(models_root).resolve()

    async def generate(self, request: LipSyncRequest) -> GeneratedAsset:
        if request.audio is None:
            raise ValueError("MuseTalk requires a narration audio asset")
        return await asyncio.to_thread(self._generate, request)

    def _generate(self, request: LipSyncRequest) -> GeneratedAsset:
        started = time.perf_counter()
        self._validate_installation()
        work_dir = Path(request.context.work_dir).resolve()
        work_dir.mkdir(parents=True, exist_ok=True)
        config = work_dir / "musetalk-inference.yaml"
        config.write_text(
            yaml.safe_dump(
                {
                    "task_0": {
                        "video_path": str(Path(request.avatar.uri).resolve()),
                        "audio_path": str(Path(request.audio.uri).resolve()),
                        "bbox_shift": int(os.environ.get("MUSETALK_BBOX_SHIFT", "0")),
                    }
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        result_dir = work_dir / "musetalk-results"
        command = [
            sys.executable,
            "-m",
            "scripts.inference",
            "--inference_config",
            str(config),
            "--result_dir",
            str(result_dir),
            "--unet_model_path",
            str(self.models_root / "musetalkV15" / "unet.pth"),
            "--unet_config",
            str(self.models_root / "musetalkV15" / "musetalk.json"),
            "--version",
            "v15",
            "--ffmpeg_path",
            shutil.which("ffmpeg") or "ffmpeg",
        ]
        completed = subprocess.run(
            command,
            cwd=self.source_root,
            check=False,
            capture_output=True,
            text=True,
            timeout=float(os.environ.get("MUSETALK_TIMEOUT_SECONDS", "3600")),
        )
        if completed.returncode:
            detail = (completed.stderr or completed.stdout)[-2000:]
            raise RuntimeError(f"MuseTalk inference failed: {detail}")
        candidates = sorted(result_dir.rglob("*.mp4"), key=lambda path: path.stat().st_mtime)
        if not candidates:
            raise RuntimeError("MuseTalk completed without producing an MP4")
        output = work_dir / f"{request.context.scene_id}-lipsync.mp4"
        shutil.copy2(candidates[-1], output)
        digest = file_sha256(output)
        return GeneratedAsset(
            asset_id=asset_id("lip", digest),
            kind=AssetKind.LIPSYNC_VIDEO,
            uri=str(output),
            content_hash=digest,
            project_id=request.context.project_id,
            scene_id=request.context.scene_id,
            parent_asset_ids=(request.avatar.asset_id, request.audio.asset_id),
            duration_seconds=request.duration_seconds,
            width=request.avatar.width,
            height=request.avatar.height,
            fps=request.fps,
            mime_type="video/mp4",
            provenance=Provenance(
                provider="musetalk-local",
                model_identifier="TMElyralab/MuseTalk-1.5",
                checkpoint_revision=os.environ.get("MUSETALK_MODEL_REVISION", "PIN_REQUIRED"),
                model_configuration={"bbox_shift": int(os.environ.get("MUSETALK_BBOX_SHIFT", "0"))},
                generation_latency_seconds=time.perf_counter() - started,
            ),
        )

    def _validate_installation(self) -> None:
        if not (self.source_root / "scripts" / "inference.py").is_file():
            raise RuntimeError("MUSETALK_SOURCE_ROOT does not contain the official inference code")
        for relative in ("musetalkV15/unet.pth", "musetalkV15/musetalk.json"):
            if not (self.models_root / relative).is_file():
                raise RuntimeError(f"MuseTalk checkpoint is missing: {relative}")


def create_musetalk_provider() -> MuseTalkLipSyncGenerator:
    return MuseTalkLipSyncGenerator(
        source_root=os.environ.get("MUSETALK_SOURCE_ROOT", "/opt/MuseTalk"),
        models_root=os.environ.get("MUSETALK_MODELS_ROOT", "/models"),
    )
