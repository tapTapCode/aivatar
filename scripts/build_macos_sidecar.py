from __future__ import annotations

import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TAURI = ROOT / "apps" / "desktop" / "src-tauri"
BINARIES = TAURI / "binaries"


def target_triple() -> str:
    machine = platform.machine().lower()
    if machine in {"arm64", "aarch64"}:
        return "aarch64-apple-darwin"
    if machine in {"x86_64", "amd64"}:
        return "x86_64-apple-darwin"
    raise SystemExit(f"Unsupported macOS architecture: {machine}")


def main() -> None:
    if platform.system() != "Darwin":
        raise SystemExit("This sidecar build script must run on macOS")
    pyinstaller = shutil.which("pyinstaller")
    if not pyinstaller:
        raise SystemExit("PyInstaller is not installed. Run: python3 -m pip install -e '.[dev]'")
    dist = ROOT / "build" / "sidecar-dist"
    work = ROOT / "build" / "sidecar-work"
    spec = ROOT / "build" / "sidecar-spec"
    dist.mkdir(parents=True, exist_ok=True); work.mkdir(parents=True, exist_ok=True); spec.mkdir(parents=True, exist_ok=True)
    subprocess.run([
        pyinstaller,
        "--noconfirm", "--clean", "--onefile",
        "--name", "aivatar-api",
        "--distpath", str(dist), "--workpath", str(work), "--specpath", str(spec),
        "--paths", str(ROOT),
        "--collect-submodules", "uvicorn",
        "--collect-submodules", "pipeline",
        str(ROOT / "pipeline" / "sidecar.py"),
    ], check=True)
    source = dist / "aivatar-api"
    target = BINARIES / f"aivatar-api-{target_triple()}"
    BINARIES.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    target.chmod(0o755)
    print(target)


if __name__ == "__main__":
    main()
