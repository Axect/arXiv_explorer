from arxiv_explorer.core.models import JobStatus, JobType
from arxiv_explorer.services.job_manager import JobManager


class TestJobModels:
    def test_job_type_enum(self):
        assert JobType.SUMMARIZE.value == "summarize"
        assert JobType.TRANSLATE.value == "translate"
        assert JobType.REVIEW.value == "review"

    def test_job_status_enum(self):
        assert JobStatus.PENDING.value == "pending"
        assert JobStatus.RUNNING.value == "running"
        assert JobStatus.COMPLETED.value == "completed"
        assert JobStatus.FAILED.value == "failed"


class TestJobManager:
    def test_submit_creates_job(self):
        mgr = JobManager()
        job = mgr.submit(JobType.SUMMARIZE, "2401.00001", "Test Paper")
        assert job.status == JobStatus.PENDING
        assert job.paper_id == "2401.00001"
        assert job.job_type == JobType.SUMMARIZE

    def test_get_active_jobs(self):
        mgr = JobManager()
        mgr.submit(JobType.SUMMARIZE, "2401.00001", "Paper 1")
        mgr.submit(JobType.TRANSLATE, "2401.00002", "Paper 2")
        active = mgr.get_active_jobs()
        assert len(active) == 2

    def test_cancel_job(self):
        mgr = JobManager()
        job = mgr.submit(JobType.SUMMARIZE, "2401.00001", "Paper 1")
        result = mgr.cancel(job.id)
        assert result is True
        assert mgr.jobs[job.id].status == JobStatus.FAILED

    def test_complete_job(self):
        mgr = JobManager()
        job = mgr.submit(JobType.SUMMARIZE, "2401.00001", "Paper 1")
        mgr.mark_running(job.id)
        mgr.mark_completed(job.id)
        assert mgr.jobs[job.id].status == JobStatus.COMPLETED
        assert mgr.jobs[job.id].completed_at is not None

    def test_fail_job(self):
        mgr = JobManager()
        job = mgr.submit(JobType.SUMMARIZE, "2401.00001", "Paper 1")
        mgr.mark_running(job.id)
        mgr.mark_failed(job.id, "timeout")
        assert mgr.jobs[job.id].status == JobStatus.FAILED
        assert mgr.jobs[job.id].error == "timeout"

    def test_clear_completed(self):
        mgr = JobManager()
        job = mgr.submit(JobType.SUMMARIZE, "2401.00001", "Paper 1")
        mgr.mark_running(job.id)
        mgr.mark_completed(job.id)
        mgr.clear_completed()
        assert len(mgr.get_all_jobs()) == 0

    def test_on_status_change_callback(self):
        events = []
        mgr = JobManager(on_status_change=lambda job: events.append(job))
        job = mgr.submit(JobType.SUMMARIZE, "2401.00001", "Paper 1")
        mgr.mark_running(job.id)
        mgr.mark_completed(job.id)
        assert len(events) == 3  # submit, running, completed
