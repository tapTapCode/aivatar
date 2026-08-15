from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def resolve_packaged_file(path: str | Path) -> Path | None:
    """Resolve a packaged asset from cwd or the repository root."""

    raw = Path(path)
    candidates = [raw]
    if not raw.is_absolute():
        candidates.extend((Path.cwd() / raw, REPO_ROOT / raw))
    seen: set[Path] = set()
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        if resolved.is_file():
            return resolved
    return None
