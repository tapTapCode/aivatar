from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from pipeline.models.entities import AssetCacheEntry, Project


@dataclass(slots=True)
class CleanupReport:
    removed_files: int = 0
    removed_bytes: int = 0
    removed_cache_entries: int = 0
    skipped_locked: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "removed_files": self.removed_files,
            "removed_bytes": self.removed_bytes,
            "removed_cache_entries": self.removed_cache_entries,
            "skipped_locked": self.skipped_locked,
        }


def directory_size(path: Path) -> int:
    total = 0
    if not path.exists():
        return 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            file_path = Path(root) / name
            try:
                total += file_path.stat().st_size
            except FileNotFoundError:
                pass
    return total


def cleanup_project_intermediates(workspace: Path, project_id: str, *, keep_final: bool = True) -> CleanupReport:
    """Remove safe-to-regenerate render/cache intermediates while preserving source assets."""
    base = workspace / "projects" / project_id
    report = CleanupReport()
    if not base.exists():
        return report
    for name in ("render", "cache"):
        target = base / name
        if not target.exists():
            continue
        for file_path in [p for p in target.rglob("*") if p.is_file()]:
            try:
                size = file_path.stat().st_size
                file_path.unlink()
                report.removed_files += 1
                report.removed_bytes += size
            except FileNotFoundError:
                pass
        for directory in sorted([p for p in target.rglob("*") if p.is_dir()], reverse=True):
            try:
                directory.rmdir()
            except OSError:
                pass
        target.mkdir(parents=True, exist_ok=True)
    if not keep_final:
        final = base / "final.mp4"
        if final.exists():
            size = final.stat().st_size
            final.unlink()
            report.removed_files += 1
            report.removed_bytes += size
    return report


def prune_asset_cache(db: Session, *, older_than_days: int = 30, max_bytes: int | None = None, dry_run: bool = False) -> CleanupReport:
    """Prune least-recently-used generated cache entries."""
    report = CleanupReport()
    cutoff = datetime.now(timezone.utc) - timedelta(days=max(0, older_than_days))
    rows = list(db.scalars(select(AssetCacheEntry).order_by(AssetCacheEntry.last_used_at.asc())).all())
    total = sum(row.size_bytes for row in rows)
    for row in rows:
        last_used = row.last_used_at
        if last_used is not None and last_used.tzinfo is None:
            last_used = last_used.replace(tzinfo=timezone.utc)
        stale = last_used is not None and last_used < cutoff
        over_budget = max_bytes is not None and total > max_bytes
        if not stale and not over_budget:
            continue
        path = Path(row.path)
        size = row.size_bytes or (path.stat().st_size if path.exists() else 0)
        existed = path.exists()
        if not dry_run:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                continue
            db.delete(row)
        report.removed_cache_entries += 1
        report.removed_files += 1 if existed else 0
        report.removed_bytes += size
        total -= size
    if not dry_run:
        db.commit()
    return report


def workspace_usage(db: Session, workspace: Path) -> dict:
    projects = list(db.scalars(select(Project)).all())
    project_rows = []
    for project in projects:
        project_path = workspace / "projects" / project.id
        project_rows.append({"project_id": project.id, "name": project.name, "state": project.state, "bytes": directory_size(project_path)})
    return {"workspace_bytes": directory_size(workspace), "projects": sorted(project_rows, key=lambda item: item["bytes"], reverse=True)}
