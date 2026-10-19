"""RunPod Serverless wrapper for MuseTalk 1.5 fallback presenter generation.

The container clones the official MuseTalk repository. Model files are downloaded into the
worker's ephemeral disk at runtime using the project's official download script rather than
being kept on a persistent RunPod volume. Inputs/outputs are exchanged through R2.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
import time
from pathlib import Path

import boto3
import runpod

REPO = Path(os.getenv("MUSETALK_REPO", "/opt/MuseTalk"))


def r2_client():
    account = os.environ["R2_ACCOUNT_ID"]
    return boto3.client(
        "s3",
        endpoint_url=f"https://{account}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )


def ensure_weights() -> None:
    required = REPO / "models" / "musetalkV15" / "unet.pth"
    if required.exists():
        return
    subprocess.run(["bash", "download_weights.sh"], cwd=REPO, check=True)
    if not required.exists():
        raise RuntimeError("MuseTalk 1.5 weights were not produced by download_weights.sh")


def run_inference(image: Path, audio: Path, output_dir: Path, output_name: str, fps: int) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    config = output_dir / "aivatar_musetalk.yaml"
    config.write_text(
        "aivatar_scene:\n"
        f"  video_path: {image}\n"
        f"  audio_path: {audio}\n"
        f"  result_name: {output_name}\n",
        encoding="utf-8",
    )
    subprocess.run(
        [
            "python3",
            "-m",
            "scripts.inference",
            "--inference_config",
            str(config),
            "--result_dir",
            str(output_dir),
            "--unet_model_path",
            "models/musetalkV15/unet.pth",
            "--unet_config",
            "models/musetalkV15/musetalk.json",
            "--version",
            "v15",
            "--fps",
            str(fps),
            "--use_float16",
        ],
        cwd=REPO,
        check=True,
    )
    matches = list(output_dir.rglob(output_name))
    if not matches:
        raise RuntimeError(f"MuseTalk did not create {output_name}")
    return matches[0]


def handler(job: dict) -> dict:
    inp = job.get("input") or {}
    bucket = os.environ["R2_BUCKET"]
    audio_key = str(inp["audio_r2_key"])
    image_key = str(inp["reference_image_r2_key"])
    output_key = str(inp["output_r2_key"])
    fps = int(inp.get("fps", 25))
    client = r2_client()
    started = time.perf_counter()
    ensure_weights()

    with tempfile.TemporaryDirectory() as temp:
        temp_dir = Path(temp)
        audio = temp_dir / "audio.wav"
        image = temp_dir / (Path(image_key).name or "reference.png")
        client.download_file(bucket, audio_key, str(audio))
        client.download_file(bucket, image_key, str(image))
        result = run_inference(image, audio, temp_dir / "results", "presenter.mp4", fps)
        # Presenter audio is deliberately preserved by MuseTalk here for inspection, but Aivatar
        # strips/ignores it during composition and uses the authoritative master narration.
        client.upload_file(str(result), bucket, output_key, ExtraArgs={"ContentType": "video/mp4"})

    runtime = time.perf_counter() - started
    return {
        "r2_key": output_key,
        "runtime_seconds": round(runtime, 4),
        "model": "MuseTalk 1.5",
        "fps": fps,
    }


if __name__ == "__main__":
    runpod.serverless.start({"handler": handler})
