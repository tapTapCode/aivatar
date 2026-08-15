import pytest

from src.orchestration.state_machine import InvalidStateTransition, JobStateMachine
from src.schemas.jobs import JobRecord, JobState, WatermarkStatus


def make_job() -> JobRecord:
    return JobRecord(
        job_id="job_1",
        video_id="video_1",
        project_id="project_1",
        owner_id="owner_1",
        idempotency_key="key-12345",
        request_fingerprint="abc",
        watermark_status=WatermarkStatus.CLEAN_AUTHORIZED,
    )


def test_valid_state_transition_records_history() -> None:
    job = make_job()
    JobStateMachine().transition(job, JobState.VALIDATING, stage="schema")
    assert job.state == JobState.VALIDATING
    assert job.transitions[0].from_state == JobState.PENDING
    assert job.transitions[0].to_state == JobState.VALIDATING


def test_invalid_state_transition_fails() -> None:
    with pytest.raises(InvalidStateTransition):
        JobStateMachine().transition(make_job(), JobState.COMPLETED)


def test_preprocessing_can_return_to_queued_for_recovery() -> None:
    job = make_job()
    machine = JobStateMachine()
    machine.transition(job, JobState.VALIDATING)
    machine.transition(job, JobState.QUEUED)
    machine.transition(job, JobState.PREPROCESSING)
    machine.transition(job, JobState.QUEUED, stage="stale_recovery")
    assert job.state == JobState.QUEUED
