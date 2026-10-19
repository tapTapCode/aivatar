"""RunPod Serverless worker for FLUX.2 Klein still-image generation.

Model weights are pulled from Hugging Face into the worker's ephemeral cache at startup.
Outputs are uploaded directly to Cloudflare R2 so RunPod response payloads stay small.
"""
from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path

import boto3
import runpod
import torch
from diffusers import Flux2KleinPipeline

MODEL_ID = os.getenv("AIVATAR_FLUX_MODEL", "black-forest-labs/FLUX.2-klein-4B")
_PIPE = None


def r2_client():
    account = os.environ["R2_ACCOUNT_ID"]
    return boto3.client(
        "s3",
        endpoint_url=f"https://{account}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )


def pipeline():
    global _PIPE
    if _PIPE is None:
        token = os.getenv("HF_TOKEN") or None
        _PIPE = Flux2KleinPipeline.from_pretrained(MODEL_ID, torch_dtype=torch.bfloat16, token=token)
        _PIPE.to("cuda")
        _PIPE.set_progress_bar_config(disable=True)
    return _PIPE


def handler(job: dict) -> dict:
    inp = job.get("input") or {}
    prompt = str(inp["prompt"])
    width = int(inp.get("width", 1280))
    height = int(inp.get("height", 720))
    steps = int(inp.get("steps", 4))
    guidance = float(inp.get("guidance_scale", 1.0))
    seed = int(inp.get("seed", 0))
    bucket = str(inp.get("r2_bucket") or os.environ["R2_BUCKET"])
    key = str(inp["r2_key"])

    torch.cuda.reset_peak_memory_stats()
    started = time.perf_counter()
    generator = torch.Generator(device="cuda").manual_seed(seed)
    image = pipeline()(
        prompt=prompt,
        width=width,
        height=height,
        guidance_scale=guidance,
        num_inference_steps=steps,
        generator=generator,
    ).images[0]

    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp) / "image.png"
        image.save(path, format="PNG", optimize=True)
        r2_client().upload_file(str(path), bucket, key, ExtraArgs={"ContentType": "image/png"})

    runtime = time.perf_counter() - started
    peak_vram = int(torch.cuda.max_memory_allocated())
    return {
        "r2_key": key,
        "model": MODEL_ID,
        "width": width,
        "height": height,
        "steps": steps,
        "seed": seed,
        "runtime_seconds": round(runtime, 4),
        "gpu_model": torch.cuda.get_device_name(0),
        "peak_vram_bytes": peak_vram,
    }


if __name__ == "__main__":
    runpod.serverless.start({"handler": handler})
