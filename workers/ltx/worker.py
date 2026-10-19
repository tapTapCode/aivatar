"""RunPod Serverless worker for selective LTX-2.3 video generation.

The worker follows Lightricks' official LTX-2 monorepo DistilledPipeline CLI. Model assets are
pulled from Hugging Face into ephemeral worker storage, generated audio is removed before upload,
and the final silent clip is persisted to Cloudflare R2 for Aivatar's master-audio timeline.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
import time
from pathlib import Path

import boto3
import runpod
import torch
from huggingface_hub import hf_hub_download, snapshot_download

MODEL_REPO = os.getenv("AIVATAR_LTX_MODEL", "Lightricks/LTX-2.3")
CHECKPOINT = os.getenv("AIVATAR_LTX_CHECKPOINT", "ltx-2.3-22b-distilled-1.1.safetensors")
UPSCALER = os.getenv("AIVATAR_LTX_SPATIAL_UPSCALER", "ltx-2.3-spatial-upscaler-x2-1.1.safetensors")
GEMMA_REPO = os.getenv("AIVATAR_LTX_GEMMA_MODEL", "google/gemma-3-12b-it-qat-q4_0-unquantized")
QUANTIZATION = os.getenv("AIVATAR_LTX_QUANTIZATION", "none")
OFFLOAD = os.getenv("AIVATAR_LTX_OFFLOAD", "none")
MODEL_ROOT = Path(os.getenv("AIVATAR_MODEL_CACHE", "/tmp/aivatar-models"))


def r2_client():
    account = os.environ["R2_ACCOUNT_ID"]
    return boto3.client(
        "s3",
        endpoint_url=f"https://{account}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )


def _models() -> tuple[Path, Path, Path]:
    MODEL_ROOT.mkdir(parents=True, exist_ok=True)
    token = os.getenv("HF_TOKEN") or None
    checkpoint = Path(hf_hub_download(MODEL_REPO, CHECKPOINT, token=token, cache_dir=MODEL_ROOT / "hf"))
    upscaler = Path(hf_hub_download(MODEL_REPO, UPSCALER, token=token, cache_dir=MODEL_ROOT / "hf"))
    gemma = Path(snapshot_download(GEMMA_REPO, token=token, cache_dir=MODEL_ROOT / "hf"))
    return checkpoint, upscaler, gemma


def _snap_dimension(value: int) -> int:
    return max(256, int(round(value / 32.0)) * 32)


def _snap_frames(duration: float, fps: float) -> int:
    target = max(9, int(round(duration * fps)))
    # LTX uses the 8k+1 frame convention.
    return max(9, int(round((target - 1) / 8.0)) * 8 + 1)


def _run(command: list[str], *, cwd: str = "/opt/LTX-2") -> None:
    proc = subprocess.run(command, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode:
        raise RuntimeError((proc.stdout + "\n" + proc.stderr)[-12000:])


def handler(job: dict) -> dict:
    inp = job.get("input") or {}
    prompt = str(inp["prompt"])
    duration = float(inp.get("duration", 5.0))
    fps = float(inp.get("fps", 24.0))
    width = _snap_dimension(int(inp.get("width", 1280)))
    height = _snap_dimension(int(inp.get("height", 720)))
    frames = _snap_frames(duration, fps)
    seed = int(inp.get("seed", 0))
    bucket = str(inp.get("r2_bucket") or os.environ["R2_BUCKET"])
    key = str(inp["r2_key"])
    quantization = str(inp.get("quantization", QUANTIZATION))
    offload = str(inp.get("offload", OFFLOAD))

    checkpoint, upscaler, gemma = _models()
    torch.cuda.reset_peak_memory_stats()
    started = time.perf_counter()

    with tempfile.TemporaryDirectory() as tempdir:
        raw = Path(tempdir) / "ltx_raw.mp4"
        silent = Path(tempdir) / "ltx_silent.mp4"
        command = [
            "/opt/LTX-2/.venv/bin/python", "-m", "ltx_pipelines.distilled",
            "--distilled-checkpoint-path", str(checkpoint),
            "--spatial-upsampler-path", str(upscaler),
            "--gemma-root", str(gemma),
            "--seed", str(seed),
            "--output-path", str(raw),
            "--prompt", prompt[:4000],
            "--height", str(height),
            "--width", str(width),
            "--num-frames", str(frames),
            "--frame-rate", str(fps),
        ]
        if quantization and quantization != "none":
            command.extend(["--quantization", quantization])
        if offload and offload != "none":
            command.extend(["--offload", offload])
        _run(command)
        _run([
            "ffmpeg", "-y", "-loglevel", "error", "-i", str(raw), "-an", "-c:v", "copy", str(silent)
        ], cwd=tempdir)
        r2_client().upload_file(str(silent), bucket, key, ExtraArgs={"ContentType": "video/mp4"})

    runtime = time.perf_counter() - started
    peak_vram = int(torch.cuda.max_memory_allocated())
    return {
        "r2_key": key,
        "model": MODEL_REPO,
        "checkpoint": CHECKPOINT,
        "pipeline": "ltx_pipelines.distilled",
        "width": width,
        "height": height,
        "fps": fps,
        "frames": frames,
        "requested_duration": duration,
        "generated_duration": round(frames / fps, 4),
        "seed": seed,
        "quantization": quantization,
        "offload": offload,
        "runtime_seconds": round(runtime, 4),
        "gpu_model": torch.cuda.get_device_name(0),
        "peak_vram_bytes": peak_vram,
        "audio_removed": True,
    }


if __name__ == "__main__":
    runpod.serverless.start({"handler": handler})
