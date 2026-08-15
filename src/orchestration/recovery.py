from __future__ import annotations

from datetime import UTC, datetime

from src.orchestration.state_machine import TERMINAL_STATES, JobStateMachine
from src.schemas.jobs import JobRecord, JobState

CLAIMED_STATES = frozenset({JobState.PREPROCESSING})
RUNNING_STATES = frozenset(
    {
        JobState.VALIDATING,
        JobState.DOWNLOADING_MODELS,
        JobState.GENERATING_AUDIO,
        JobState.GENERATING_AVATAR,
        JobState.GENERATING_VISUAL,
        JobState.LIP_SYNCING,
        JobState.RENDERING_SCENE,
        JobState.ASSEMBLING_TIMELINE,
        JobState.VALIDATING_OUTPUT,
        JobState.UPLOADING,
        JobState.RETRYING,
    }
)


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def job_is_stale(
    job: JobRecord,
    *,
    now: datetime | None = None,
    claim_lease_seconds: float,
    running_lease_seconds: float,
) -> bool:
    if job.state in TERMINAL_STATES or job.state == JobState.QUEUED:
        return False
    age = (_aware(now or datetime.now(UTC)) - _aware(job.updated_at)).total_seconds()
    if job.state in CLAIMED_STATES:
        return age >= claim_lease_seconds
    if job.state in RUNNING_STATES:
        return age >= running_lease_seconds
    return False


def requeue_stranded_job(job: JobRecord, *, stage: str = "stale_recovery") -> JobRecord:
    machine = JobStateMachine()
    if job.state == JobState.QUEUED:
        return job
    job.attempt += 1
    if job.state == JobState.VALIDATING:
        return machine.transition(job, JobState.QUEUED, stage=stage)
    machine.transition(job, JobState.RETRYING, stage=stage)
    return machine.transition(job, JobState.QUEUED, stage=stage)
