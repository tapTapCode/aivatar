from src.orchestration.consent import missing_consents
from src.schemas.scene import ConsentRecord, OutputSpec, ProjectScript, VisualFormat
from tests.conftest import make_scene


def test_missing_consent_lists_voice_and_avatar() -> None:
    project = ProjectScript(
        project_id="consent_project",
        schema_version="1.0",
        output=OutputSpec(width=640, height=360),
        scenes=(make_scene(VisualFormat.PRESENTER),),
    )
    assert missing_consents(project) == ("avatar:avatar_1", "voice:voice_1")


def test_matching_consent_records_satisfy_policy() -> None:
    project = ProjectScript(
        project_id="consent_project",
        schema_version="1.0",
        output=OutputSpec(width=640, height=360),
        scenes=(make_scene(VisualFormat.PRESENTER),),
        consent_records=(
            ConsentRecord(
                subject_id="avatar_1",
                permission_type="avatar",
                granted_by="owner",
                granted_at="2026-07-15T00:00:00Z",
                evidence_uri="s3://private-consent/avatar_1.json",
            ),
            ConsentRecord(
                subject_id="voice_1",
                permission_type="voice",
                granted_by="owner",
                granted_at="2026-07-15T00:00:00Z",
                evidence_uri="s3://private-consent/voice_1.json",
            ),
        ),
    )
    assert missing_consents(project) == ()
