import os, platform, shutil, socket, subprocess
from pathlib import Path

def _version(cmd: list[str]) -> str | None:
    if not shutil.which(cmd[0]): return None
    try:
        p=subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=5)
        return p.stdout.splitlines()[0][:240]
    except Exception:
        return None

def diagnostics() -> dict:
    disk=shutil.disk_usage(Path.cwd())
    ffmpeg=_version(["ffmpeg","-version"])
    docker=_version(["docker","--version"])
    rust=_version(["rustc","--version"])
    node=_version(["node","--version"])
    python=_version(["python3","--version"])
    cuda=_version(["nvidia-smi","--query-gpu=name,memory.total","--format=csv,noheader"])
    return {
        "os": platform.platform(), "machine": platform.machine(), "cpu": platform.processor() or platform.machine(),
        "ram_bytes": _ram_bytes(), "gpu_cuda": cuda, "ffmpeg": ffmpeg, "docker": docker,
        "python": python, "rust": rust, "node": node, "disk_free_bytes": disk.free,
        "network_dns": _dns_ok(),
        "features": {"desktop_ui": True, "local_api": True, "sqlite": True, "ffmpeg_render": bool(ffmpeg), "mock_mode": bool(ffmpeg), "local_cuda_inference": bool(cuda), "remote_gpu_supported": True},
    }

def _ram_bytes() -> int | None:
    try:
        if hasattr(os, "sysconf"):
            return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    except Exception: pass
    return None

def _dns_ok() -> bool:
    try:
        socket.getaddrinfo("example.com", 443); return True
    except OSError: return False
