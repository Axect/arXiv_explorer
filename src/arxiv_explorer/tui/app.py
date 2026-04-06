"""ArxivExplorerApp — TUI main application."""

from __future__ import annotations

from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Footer, Header, TabbedContent, TabPane

from ..core.models import Job, JobStatus
from .screens.daily import DailyPane
from .screens.notes import NotesPane
from .screens.preferences import PreferencesPane
from .screens.reading_lists import ReadingListsPane
from .screens.search import SearchPane
from .workers import ServiceBridge

CSS_PATH = Path(__file__).parent / "styles" / "app.tcss"


class ArxivExplorerApp(App):
    """arXiv Explorer TUI."""

    TITLE = "arXiv Explorer"
    SUB_TITLE = "Personalized Paper Recommendation System"

    CSS_PATH = CSS_PATH

    BINDINGS = [
        Binding("1", "tab('daily')", "Daily", show=False),
        Binding("2", "tab('search')", "Search", show=False),
        Binding("3", "tab('lists')", "Lists", show=False),
        Binding("4", "tab('notes')", "Notes", show=False),
        Binding("5", "tab('prefs')", "Prefs", show=False),
        Binding("j", "toggle_jobs", "Jobs"),
        Binding("q", "quit", "Quit"),
        Binding("question_mark", "help_keys", "Shortcuts", show=False),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.bridge = ServiceBridge()
        self.bridge.job_manager._on_status_change = self._on_job_status_change

    def compose(self) -> ComposeResult:
        yield Header()
        with TabbedContent(id="tabs"):
            with TabPane("Daily", id="daily"):
                yield DailyPane()
            with TabPane("Search", id="search"):
                yield SearchPane()
            with TabPane("Lists", id="lists"):
                yield ReadingListsPane()
            with TabPane("Notes", id="notes"):
                yield NotesPane()
            with TabPane("Prefs", id="prefs"):
                yield PreferencesPane()
        yield Footer()

    def action_tab(self, tab_id: str) -> None:
        tabs = self.query_one("#tabs", TabbedContent)
        tabs.active = tab_id

    def action_help_keys(self) -> None:
        self.notify(
            "1-5: Switch tabs | r: Refresh | l: Like | d: Dislike | "
            "s: Summary | t: Translate | Enter: Detail | /: Search | "
            "c: New list | n: Note | Delete: Delete | j: Jobs | q: Quit",
            title="Shortcuts",
            timeout=8,
        )

    def _on_job_status_change(self, job: Job) -> None:
        if job.status == JobStatus.COMPLETED:
            self.notify(
                f"\u2713 {job.job_type.value.title()} completed\n  {job.paper_id}",
                timeout=3,
            )
        elif job.status == JobStatus.FAILED and job.error != "cancelled":
            self.notify(
                f"\u2717 {job.job_type.value.title()} failed\n  {job.error}",
                severity="error",
                timeout=5,
            )
        active = len(self.bridge.job_manager.get_active_jobs())
        self.sub_title = (
            f"Jobs: {active} running" if active > 0 else "Personalized Paper Recommendation System"
        )

    def action_toggle_jobs(self) -> None:
        from .screens.jobs_panel import JobsPanel

        self.push_screen(JobsPanel())


def launch_tui() -> None:
    """Launch the TUI app."""
    app = ArxivExplorerApp()
    app.run()
