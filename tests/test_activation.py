from pipeline.activation.readiness import activation_status
from pipeline.reference.profiles import get_reference_profile, list_reference_profiles


def test_reference_profile_locks_core_editorial_contract():
    profile = get_reference_profile("reference_documentary_v1")
    assert profile["editorial"]["presenter_target"] == 0.30
    assert profile["editorial"]["core_scene_types"] == ["PRESENTER", "SPLIT", "FULL_VISUAL"]
    assert profile["visuals"]["selection_order"] == ["cache", "motion_graphic", "flux_motion", "ltx_video"]
    assert profile["audio"]["master_narration_authoritative"] is True
    assert profile["audio"]["presenter_audio_in_final"] is False
    assert profile["validation"]["requires_side_by_side_reference_review"] is True


def test_reference_profile_list_is_safe_copy():
    profiles = list_reference_profiles()
    profiles[0]["editorial"]["presenter_target"] = 1
    assert get_reference_profile("reference_documentary_v1")["editorial"]["presenter_target"] == 0.30


def test_activation_status_reports_security_gate(monkeypatch):
    from pipeline.activation import readiness
    monkeypatch.setattr(readiness.settings, "aivatar_archive_credentials_rotated", False)
    status = activation_status()
    gate = next(check for check in status["checks"] if check["id"] == "credential_rotation")
    assert gate["required"] is True
    assert gate["ready"] is False
    assert status["ready_for_real_reference_test"] is False
    assert any(blocker["id"] == "credential_rotation" for blocker in status["blockers"])
