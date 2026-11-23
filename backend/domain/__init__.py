"""Shared values and rules for the ViNote 2.0 data layer."""
from enum import Enum


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL_SUCCESS = "partial_success"
    FAILED = "failed"
    CANCEL_REQUESTED = "cancel_requested"
    CANCELLED = "cancelled"


class ReviewState(str, Enum):
    NEW = "new"
    REMEMBERED = "remembered"
    UNSURE = "unsure"
    FORGOTTEN = "forgotten"


_JOB_TRANSITIONS = {
    JobStatus.QUEUED: {JobStatus.RUNNING, JobStatus.CANCELLED},
    JobStatus.RUNNING: {
        JobStatus.COMPLETED, JobStatus.PARTIAL_SUCCESS,
        JobStatus.FAILED, JobStatus.CANCEL_REQUESTED,
    },
    JobStatus.CANCEL_REQUESTED: {JobStatus.CANCELLED, JobStatus.FAILED},
    JobStatus.PARTIAL_SUCCESS: {JobStatus.QUEUED},
    JobStatus.FAILED: {JobStatus.QUEUED},
}


def validate_job_transition(expected: JobStatus, target: JobStatus) -> None:
    if expected == target == JobStatus.RUNNING:
        return
    if target not in _JOB_TRANSITIONS.get(expected, ()):
        raise ValueError(f"Invalid job transition: {expected.value} → {target.value}")
