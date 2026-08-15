from __future__ import annotations

from pathlib import Path

import pytest

from src.providers.local.chatterbox import ChatterboxSpeechGenerator
from src.providers.local.musetalk import MuseTalkLipSyncGenerator


def test_chatterbox_voice_registry_rejects_unsafe_identifiers(tmp_path: Path) -> None:
    provider = ChatterboxSpeechGenerator(voice_root=tmp_path)
    with pytest.raises(ValueError, match="voice_id"):
        provider._voice_reference("../private")


def test_chatterbox_voice_registry_resolves_allow_listed_reference(tmp_path: Path) -> None:
    reference = tmp_path / "narrator.wav"
    reference.write_bytes(b"RIFF")
    provider = ChatterboxSpeechGenerator(voice_root=tmp_path)
    assert provider._voice_reference("narrator") == reference


def test_musetalk_requires_official_source_tree_and_checkpoints(tmp_path: Path) -> None:
    provider = MuseTalkLipSyncGenerator(
        source_root=tmp_path / "MuseTalk", models_root=tmp_path / "models"
    )
    with pytest.raises(RuntimeError, match="official inference code"):
        provider._validate_installation()

    (tmp_path / "MuseTalk" / "scripts").mkdir(parents=True)
    (tmp_path / "MuseTalk" / "scripts" / "inference.py").write_text("", encoding="utf-8")
    with pytest.raises(RuntimeError, match="checkpoint is missing"):
        provider._validate_installation()
