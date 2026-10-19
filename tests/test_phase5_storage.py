from pathlib import Path

from pipeline.production.storage import cleanup_project_intermediates


def test_cleanup_preserves_final_and_sources(tmp_path: Path):
    base = tmp_path / "projects" / "p1"
    (base / "render").mkdir(parents=True)
    (base / "cache").mkdir()
    (base / "images").mkdir()
    (base / "render" / "scene.mp4").write_bytes(b"r" * 100)
    (base / "cache" / "temp.bin").write_bytes(b"c" * 200)
    (base / "images" / "source.png").write_bytes(b"i" * 300)
    (base / "final.mp4").write_bytes(b"f" * 400)
    report = cleanup_project_intermediates(tmp_path, "p1")
    assert report.removed_bytes == 300
    assert (base / "final.mp4").exists()
    assert (base / "images" / "source.png").exists()
    assert not (base / "render" / "scene.mp4").exists()
