from __future__ import annotations

from src.schemas.scene import ProjectScript


def missing_consents(
    project: ProjectScript,
    *,
    require_voice: bool = True,
    require_avatar: bool = True,
) -> tuple[str, ...]:
    granted = {(record.permission_type, record.subject_id) for record in project.consent_records}
    missing: set[str] = set()
    for scene in project.scenes:
        if require_voice and ("voice", scene.voice_id) not in granted:
            missing.add(f"voice:{scene.voice_id}")
        if require_avatar and scene.avatar_id and ("avatar", scene.avatar_id) not in granted:
            missing.add(f"avatar:{scene.avatar_id}")
    return tuple(sorted(missing))
