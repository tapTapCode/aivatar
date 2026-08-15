from __future__ import annotations

import os
import time
from pathlib import Path

from src.storage.cleanup import cleanup_expired_files


def test_cleanup_only_removes_expired_files(tmp_path: Path) -> None:
    expired = tmp_path / "old.tmp"
    current = tmp_path / "current.tmp"
    expired.write_text("old", encoding="utf-8")
    current.write_text("current", encoding="utf-8")
    old = time.time() - 48 * 3600
    os.utime(expired, (old, old))

    assert cleanup_expired_files([tmp_path], retention_hours=24) == 1
    assert not expired.exists()
    assert current.exists()
