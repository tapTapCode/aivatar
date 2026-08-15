from __future__ import annotations

import time
from collections.abc import Iterable
from contextlib import suppress
from pathlib import Path


def cleanup_expired_files(roots: Iterable[str | Path], *, retention_hours: float) -> int:
    """Remove expired regular files beneath explicitly configured storage roots."""
    if retention_hours <= 0:
        raise ValueError("retention_hours must be positive")
    cutoff = time.time() - retention_hours * 3600
    removed = 0
    for configured_root in roots:
        root = Path(configured_root).resolve()
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if (
                path.is_file()
                and not path.is_symlink()
                and path.name != ".gitkeep"
                and path.stat().st_mtime < cutoff
            ):
                path.unlink(missing_ok=True)
                removed += 1
        for directory in sorted(
            (path for path in root.rglob("*") if path.is_dir()),
            key=lambda path: len(path.parts),
            reverse=True,
        ):
            with suppress(OSError):
                directory.rmdir()
    return removed
