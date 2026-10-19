from pathlib import Path

from pipeline.production.longform import assemble_longform_proof


def test_one_minute_longform_assembly_qc(tmp_path: Path):
    manifest = assemble_longform_proof(tmp_path / "proof", 1, width=640, height=360, fps=30)
    assert manifest["qc"]["ok"] is True
    assert abs(manifest["qc"]["duration"] - 60.0) < 0.1
    assert manifest["virtual_scene_count"] == 4
