from __future__ import annotations

from datetime import UTC, datetime

from src.schemas.jobs import JobRecord, JobState, StateTransition

TERMINAL_STATES = {JobState.COMPLETED, JobState.FAILED, JobState.CANCELLED}

ALLOWED_TRANSITIONS: dict[JobState, set[JobState]] = {
    JobState.PENDING: {JobState.VALIDATING, JobState.CANCELLED},
    JobState.VALIDATING: {JobState.QUEUED, JobState.FAILED, JobState.CANCELLED},
    JobState.QUEUED: {
        JobState.DOWNLOADING_MODELS,
        JobState.PREPROCESSING,
        JobState.GENERATING_AUDIO,
        JobState.CANCELLED,
        JobState.FAILED,
    },
    JobState.DOWNLOADING_MODELS: {
        JobState.PREPROCESSING,
        JobState.RETRYING,
        JobState.FAILED,
        JobState.CANCELLED,
    },
    JobState.PREPROCESSING: {
        JobState.GENERATING_AUDIO,
        JobState.QUEUED,
        JobState.RETRYING,
        JobState.FAILED,
        JobState.CANCELLED,
    },
    JobState.GENERATING_AUDIO: {
        JobState.GENERATING_AVATAR,
        JobState.GENERATING_VISUAL,
        JobState.LIP_SYNCING,
        JobState.RENDERING_SCENE,
        JobState.RETRYING,
        JobState.FAILED,
        JobState.CANCELLED,
    },
    JobState.GENERATING_AVATAR: {
        JobState.GENERATING_VISUAL,
        JobState.LIP_SYNCING,
        JobState.RETRYING,
        JobState.FAILED,
        JobState.CANCELLED,
    },
    JobState.GENERATING_VISUAL: {
        JobState.LIP_SYNCING,
        JobState.RENDERING_SCENE,
        JobState.RETRYING,
        JobState.FAILED,
        JobState.CANCELLED,
    },
    JobState.LIP_SYNCING: {
        JobState.RENDERING_SCENE,
        JobState.RETRYING,
        JobState.FAILED,
        JobState.CANCELLED,
    },
    JobState.RENDERING_SCENE: {
        JobState.GENERATING_AUDIO,
        JobState.ASSEMBLING_TIMELINE,
        JobState.RETRYING,
        JobState.FAILED,
        JobState.CANCELLED,
    },
    JobState.ASSEMBLING_TIMELINE: {
        JobState.VALIDATING_OUTPUT,
        JobState.RETRYING,
        JobState.FAILED,
        JobState.CANCELLED,
    },
    JobState.VALIDATING_OUTPUT: {
        JobState.UPLOADING,
        JobState.COMPLETED,
        JobState.RETRYING,
        JobState.FAILED,
        JobState.CANCELLED,
    },
    JobState.UPLOADING: {
        JobState.COMPLETED,
        JobState.RETRYING,
        JobState.FAILED,
        JobState.CANCELLED,
    },
    JobState.RETRYING: {JobState.QUEUED, JobState.FAILED, JobState.CANCELLED},
    JobState.COMPLETED: set(),
    JobState.FAILED: set(),
    JobState.CANCELLED: set(),
}


class InvalidStateTransition(ValueError):
    pass


class JobStateMachine:
    def transition(
        self,
        job: JobRecord,
        to_state: JobState,
        *,
        stage: str | None = None,
        error: Exception | None = None,
    ) -> JobRecord:
        if to_state not in ALLOWED_TRANSITIONS[job.state]:
            raise InvalidStateTransition(f"cannot transition {job.state} -> {to_state}")
        previous = job.state
        now = datetime.now(UTC)
        job.state = to_state
        job.updated_at = now
        job.error_class = type(error).__name__ if error else None
        job.error_message = str(error) if error else None
        job.transitions.append(
            StateTransition(
                from_state=previous,
                to_state=to_state,
                at=now,
                stage=stage,
                error_class=job.error_class,
                error_message=job.error_message,
            )
        )
        return job
