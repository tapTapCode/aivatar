from __future__ import annotations

import contextlib
import json
import os
import platform
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _command(arguments: list[str]) -> str | None:
    if not shutil.which(arguments[0]):
        return None
    result = subprocess.run(arguments, text=True, capture_output=True, check=False)
    return result.stdout.strip() or result.stderr.strip() or None


def _package_version(name: str) -> str | None:
    try:
        from importlib.metadata import version

        return version(name)
    except Exception:
        return None


def capture_environment() -> dict[str, Any]:
    uname = platform.uname()
    nvidia_smi = _command(
        [
            "nvidia-smi",
            "--query-gpu=name,memory.total,power.limit,clocks.current.graphics,temperature.gpu,driver_version",
            "--format=csv,noheader,nounits",
        ]
    )
    background_processes = _command(
        [
            "nvidia-smi",
            "--query-compute-apps=pid,process_name,used_memory",
            "--format=csv,noheader,nounits",
        ]
    )
    git_commit = _command(["git", "rev-parse", "HEAD"])
    docker_version = _command(["docker", "version", "--format", "{{.Server.Version}}"])
    total_ram = None
    if hasattr(os, "sysconf"):
        with contextlib.suppress(ValueError, OSError):
            total_ram = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    return {
        "captured_at": datetime.now(UTC).isoformat(),
        "status": "OBSERVED",
        "gpu_query": nvidia_smi,
        "background_gpu_processes": background_processes,
        "nvidia_driver": _command(
            ["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"]
        ),
        "cuda_toolkit": _command(["nvcc", "--version"]),
        "python": sys.version,
        "pytorch": _package_version("torch"),
        "cuda_runtime_from_pytorch": _torch_cuda_version(),
        "cudnn_from_pytorch": _torch_cudnn_version(),
        "xformers": _package_version("xformers"),
        "flash_attention": _package_version("flash-attn"),
        "diffusers": _package_version("diffusers"),
        "transformers": _package_version("transformers"),
        "operating_system": platform.platform(),
        "machine": uname.machine,
        "cpu": uname.processor or platform.machine(),
        "system_ram_bytes": total_ram,
        "container_runtime": docker_version,
        "git_commit": git_commit,
        "docker_image_digest": os.environ.get("DOCKER_IMAGE_DIGEST"),
        "storage_type": os.environ.get("BENCHMARK_STORAGE_TYPE", "UNVERIFIED"),
        "thermal_state": "OBSERVED only when gpu_query includes temperature",
    }


def _torch_cuda_version() -> str | None:
    try:
        import torch

        return torch.version.cuda
    except ImportError:
        return None


def _torch_cudnn_version() -> int | None:
    try:
        import torch

        return torch.backends.cudnn.version()
    except ImportError:
        return None


def write_environment(output_dir: str | Path) -> dict[str, Any]:
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    data = capture_environment()
    (target / "environment.json").write_text(json.dumps(data, indent=2, sort_keys=True))
    return data
