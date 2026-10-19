from pipeline.core.enums import ProjectState

_ALLOWED: dict[ProjectState, set[ProjectState]] = {
    ProjectState.CREATED: {ProjectState.SCRIPT_READY, ProjectState.CANCELLED, ProjectState.FAILED},
    ProjectState.SCRIPT_READY: {ProjectState.VOICE_GENERATING, ProjectState.CANCELLED, ProjectState.FAILED},
    ProjectState.VOICE_GENERATING: {ProjectState.VOICE_READY, ProjectState.FAILED, ProjectState.CANCELLED},
    ProjectState.VOICE_READY: {ProjectState.ALIGNING, ProjectState.PLANNING, ProjectState.FAILED},
    ProjectState.ALIGNING: {ProjectState.PLANNING, ProjectState.FAILED},
    ProjectState.PLANNING: {ProjectState.ASSETS_GENERATING, ProjectState.ASSETS_READY, ProjectState.FAILED},
    ProjectState.ASSETS_GENERATING: {ProjectState.ASSETS_READY, ProjectState.FAILED, ProjectState.CANCELLED},
    ProjectState.ASSETS_READY: {ProjectState.PRESENTER_GENERATING, ProjectState.RENDERING, ProjectState.FAILED},
    ProjectState.PRESENTER_GENERATING: {ProjectState.RENDERING, ProjectState.FAILED, ProjectState.CANCELLED},
    ProjectState.RENDERING: {ProjectState.QUALITY_CHECK, ProjectState.FAILED, ProjectState.CANCELLED},
    ProjectState.QUALITY_CHECK: {ProjectState.COMPLETED, ProjectState.FAILED},
    ProjectState.COMPLETED: {ProjectState.RENDERING},
    ProjectState.FAILED: {ProjectState.SCRIPT_READY, ProjectState.RENDERING, ProjectState.CANCELLED},
    ProjectState.CANCELLED: set(),
}

def can_transition(current: ProjectState, target: ProjectState) -> bool:
    return target == current or target in _ALLOWED[current]

def require_transition(current: ProjectState, target: ProjectState) -> None:
    if not can_transition(current, target):
        raise ValueError(f"Invalid project state transition: {current} -> {target}")
