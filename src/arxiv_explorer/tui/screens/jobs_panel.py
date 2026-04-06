"""Overlay panel showing background job status."""

from datetime import datetime

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import DataTable, Static

from ...core.models import JobStatus


class JobsPanel(ModalScreen):
    BINDINGS = [
        Binding("escape", "dismiss", "Close"),
        Binding("j", "dismiss", "Close"),
        Binding("x", "cancel_job", "Cancel"),
        Binding("c", "clear_completed", "Clear"),
    ]

    DEFAULT_CSS = """
    JobsPanel {
        align: center middle;
    }
    JobsPanel #jobs-panel {
        width: 80;
        height: 60%;
        background: $surface;
        border: round $primary;
        padding: 1 2;
    }
    JobsPanel #jobs-title {
        text-style: bold;
        margin-bottom: 1;
    }
    JobsPanel #jobs-hint {
        dock: bottom;
        height: 1;
        color: $text-muted;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="jobs-panel"):
            yield Static("Background Jobs", id="jobs-title")
            yield DataTable(id="jobs-table", cursor_type="row", zebra_stripes=True)
            yield Static("[x] Cancel  [c] Clear completed  [Esc/j] Close", id="jobs-hint")

    def on_mount(self) -> None:
        table = self.query_one("#jobs-table", DataTable)
        table.add_columns("Status", "Type", "Paper ID", "Title", "Time")
        self._refresh_jobs()

    def _refresh_jobs(self) -> None:
        table = self.query_one("#jobs-table", DataTable)
        table.clear()
        mgr = self.app.bridge.job_manager
        for job in mgr.get_all_jobs():
            status_icon = {
                JobStatus.PENDING: "\u25cc",
                JobStatus.RUNNING: "\u27f3",
                JobStatus.COMPLETED: "\u2713",
                JobStatus.FAILED: "\u2717",
            }[job.status]
            if job.completed_at:
                elapsed = (
                    "Done"
                    if job.status == JobStatus.COMPLETED
                    else f"Failed: {job.error or 'unknown'}"
                )
            elif job.status == JobStatus.RUNNING:
                delta = datetime.now() - job.started_at
                elapsed = f"{int(delta.total_seconds())}s"
            else:
                elapsed = "Pending"
            title = job.paper_title[:40] + "..." if len(job.paper_title) > 40 else job.paper_title
            table.add_row(
                status_icon,
                job.job_type.value.upper(),
                job.paper_id,
                title,
                elapsed,
                key=job.id,
            )

    def action_cancel_job(self) -> None:
        table = self.query_one("#jobs-table", DataTable)
        if table.cursor_row is not None:
            try:
                row_key, _ = table.coordinate_to_cell_key(table.cursor_coordinate)
                job_id = row_key.value if hasattr(row_key, "value") else str(row_key)
                self.app.bridge.job_manager.cancel(job_id)
                self._refresh_jobs()
            except Exception:
                pass

    def action_clear_completed(self) -> None:
        self.app.bridge.job_manager.clear_completed()
        self._refresh_jobs()
