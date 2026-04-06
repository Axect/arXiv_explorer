"""In-memory background job tracking."""

import uuid
from collections.abc import Callable
from datetime import datetime

from arxiv_explorer.core.models import Job, JobStatus, JobType


class JobManager:
    def __init__(self, on_status_change: Callable[[Job], None] | None = None) -> None:
        self.jobs: dict[str, Job] = {}
        self._on_status_change = on_status_change

    def submit(self, job_type: JobType, paper_id: str, paper_title: str) -> Job:
        job = Job(
            id=str(uuid.uuid4()),
            paper_id=paper_id,
            paper_title=paper_title,
            job_type=job_type,
            status=JobStatus.PENDING,
            started_at=datetime.now(),
        )
        self.jobs[job.id] = job
        self._notify(job)
        return job

    def mark_running(self, job_id: str) -> None:
        job = self.jobs[job_id]
        job.status = JobStatus.RUNNING
        self._notify(job)

    def mark_completed(self, job_id: str) -> None:
        job = self.jobs[job_id]
        job.status = JobStatus.COMPLETED
        job.completed_at = datetime.now()
        self._notify(job)

    def mark_failed(self, job_id: str, error: str) -> None:
        job = self.jobs[job_id]
        job.status = JobStatus.FAILED
        job.error = error
        job.completed_at = datetime.now()
        self._notify(job)

    def cancel(self, job_id: str) -> bool:
        job = self.jobs.get(job_id)
        if not job or job.status in (JobStatus.COMPLETED, JobStatus.FAILED):
            return False
        job.status = JobStatus.FAILED
        job.error = "cancelled"
        job.completed_at = datetime.now()
        self._notify(job)
        return True

    def get_active_jobs(self) -> list[Job]:
        return [j for j in self.jobs.values() if j.status in (JobStatus.PENDING, JobStatus.RUNNING)]

    def get_all_jobs(self) -> list[Job]:
        return list(self.jobs.values())

    def clear_completed(self) -> None:
        self.jobs = {
            k: v for k, v in self.jobs.items() if v.status in (JobStatus.PENDING, JobStatus.RUNNING)
        }

    def _notify(self, job: Job) -> None:
        if self._on_status_change:
            self._on_status_change(job)
