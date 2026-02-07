"""Daily papers tab."""

from __future__ import annotations

from textual import on, work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Select, Static

from ...core.models import RecommendedPaper
from ..widgets.paper_panel import PaperPanel
from ..widgets.paper_table import PaperTable


class DailyPane(Vertical):
    """Daily paper exploration screen.

    Left: filters + PaperTable
    Right: PaperPanel
    """

    DEFAULT_CSS = """
    DailyPane {
        height: 1fr;
    }
    DailyPane #daily-toolbar {
        height: 3;
        padding: 0 1;
        dock: top;
        background: $surface;
    }
    DailyPane #daily-toolbar Select {
        width: 16;
        margin-right: 1;
    }
    DailyPane #daily-toolbar Button {
        min-width: 10;
    }
    DailyPane #daily-body {
        height: 1fr;
    }
    DailyPane #daily-left {
        width: 2fr;
        min-width: 50;
    }
    DailyPane #daily-interaction {
        dock: bottom;
        height: 3;
        padding: 0 1;
        background: $surface;
    }
    DailyPane #daily-interaction Button {
        min-width: 12;
        margin-right: 1;
    }
    DailyPane #daily-status {
        dock: bottom;
        height: 1;
        padding: 0 1;
        color: $text-muted;
        background: $surface-darken-1;
    }
    """

    BINDINGS = [
        ("r", "refresh", "Refresh"),
        ("l", "like", "Like"),
        ("d", "dislike", "Dislike"),
        ("s", "summarize", "Summarize"),
        ("t", "translate", "Translate"),
    ]

    def compose(self) -> ComposeResult:
        with Horizontal(id="daily-toolbar"):
            yield Select(
                [(f"{d}d", d) for d in [1, 3, 7, 14, 30]],
                value=7,
                id="daily-days",
                prompt="Days",
            )
            yield Select(
                [(str(n), n) for n in [10, 20, 50, 100]],
                value=20,
                id="daily-limit",
                prompt="Limit",
            )
            yield Button("Fetch", id="daily-fetch", variant="primary")

        with Horizontal(id="daily-body"):
            with Vertical(id="daily-left"):
                yield PaperTable(id="daily-table")
                with Horizontal(id="daily-interaction"):
                    yield Button("Like [l]", id="btn-like", variant="success")
                    yield Button("Dislike [d]", id="btn-dislike", variant="error")
                    yield Button("Summarize [s]", id="btn-summarize", variant="warning")
                    yield Button("Translate [t]", id="btn-translate")
                yield Static("", id="daily-status")
            yield PaperPanel(id="daily-panel")

    def on_mount(self) -> None:
        table = self.query_one("#daily-table", PaperTable)
        table.query_one("#pt-loading").add_class("hidden")
        table.query_one("#pt-empty").remove_class("hidden")
        self._set_status("Press Fetch or [r] to load papers")

    @on(Button.Pressed, "#daily-fetch")
    def _on_fetch_clicked(self) -> None:
        self._fetch_papers()

    @on(Button.Pressed, "#btn-like")
    def _on_like_clicked(self) -> None:
        self.action_like()

    @on(Button.Pressed, "#btn-dislike")
    def _on_dislike_clicked(self) -> None:
        self.action_dislike()

    @on(Button.Pressed, "#btn-summarize")
    def _on_summarize_clicked(self) -> None:
        self.action_summarize()

    @on(Button.Pressed, "#btn-translate")
    def _on_translate_clicked(self) -> None:
        self.action_translate()

    @on(PaperTable.PaperHighlighted)
    def _on_paper_highlighted(self, event: PaperTable.PaperHighlighted) -> None:
        panel = self.query_one("#daily-panel", PaperPanel)
        panel.show_paper(event.paper)

    @on(PaperTable.PaperSelected)
    def _on_paper_selected(self, event: PaperTable.PaperSelected) -> None:
        from .paper_detail import PaperDetailScreen

        self.app.push_screen(PaperDetailScreen(event.paper))

    def _fetch_papers(self) -> None:
        table = self.query_one("#daily-table", PaperTable)
        table.set_loading()
        self._set_status("Fetching papers...")
        self._do_fetch()

    @work(thread=True, exclusive=True, group="daily-fetch")
    def _do_fetch(self) -> None:
        days_select = self.query_one("#daily-days", Select)
        limit_select = self.query_one("#daily-limit", Select)
        days = days_select.value if days_select.value != Select.BLANK else 7
        limit = limit_select.value if limit_select.value != Select.BLANK else 20

        bridge = self.app.bridge
        try:
            papers = bridge.papers.get_daily_papers(days=days, limit=limit)
        except Exception as e:
            self.app.call_from_thread(self._show_error, str(e))
            return

        self.app.call_from_thread(self._update_papers, papers)

    def _update_papers(self, papers: list[RecommendedPaper]) -> None:
        table = self.query_one("#daily-table", PaperTable)
        table.set_papers(papers)
        if not papers:
            cats = self.app.bridge.preferences.get_categories()
            if not cats:
                self._set_status("No categories set — add categories in Prefs tab (5)")
                return
        self._set_status(f"{len(papers)} papers loaded")

    def _show_error(self, msg: str) -> None:
        table = self.query_one("#daily-table", PaperTable)
        table.set_papers([])
        self._set_status(f"Error: {msg}")
        self.app.notify(f"Error: {msg}", severity="error")

    def _set_status(self, text: str) -> None:
        self.query_one("#daily-status", Static).update(text)

    # === Actions ===

    def _get_current(self) -> RecommendedPaper | None:
        table = self.query_one("#daily-table", PaperTable)
        return table.current_paper

    def action_refresh(self) -> None:
        self._fetch_papers()

    def action_like(self) -> None:
        rec = self._get_current()
        if not rec:
            return
        self._do_like(rec)

    @work(thread=True, group="interaction")
    def _do_like(self, rec: RecommendedPaper) -> None:
        self.app.bridge.preferences.mark_interesting(rec.paper.arxiv_id)
        self.app.call_from_thread(
            self.app.notify,
            f"Liked {rec.paper.arxiv_id}",
        )

    def action_dislike(self) -> None:
        rec = self._get_current()
        if not rec:
            return
        self._do_dislike(rec)

    @work(thread=True, group="interaction")
    def _do_dislike(self, rec: RecommendedPaper) -> None:
        self.app.bridge.preferences.mark_not_interesting(rec.paper.arxiv_id)
        self.app.call_from_thread(
            self.app.notify,
            f"Disliked {rec.paper.arxiv_id}",
        )

    def action_summarize(self) -> None:
        rec = self._get_current()
        if not rec:
            return
        self._set_status(f"Summarizing {rec.paper.arxiv_id}...")
        self._do_summarize(rec)

    @work(thread=True, group="summarize")
    def _do_summarize(self, rec: RecommendedPaper) -> None:
        p = rec.paper
        summary = self.app.bridge.summarization.summarize(
            arxiv_id=p.arxiv_id,
            title=p.title,
            abstract=p.abstract,
            detailed=True,
        )
        if summary:
            self.app.call_from_thread(self._show_summary, rec, summary)
        else:
            self.app.call_from_thread(self._set_status, "Summary generation failed")
            self.app.call_from_thread(
                self.app.notify,
                "Could not generate summary (check Gemini CLI)",
                severity="warning",
            )

    def _show_summary(self, rec, summary) -> None:
        panel = self.query_one("#daily-panel", PaperPanel)
        panel.show_summary(summary)
        self._set_status(f"Summary done: {rec.paper.arxiv_id}")

    def action_translate(self) -> None:
        rec = self._get_current()
        if not rec:
            return
        self._set_status(f"Translating {rec.paper.arxiv_id}...")
        self._do_translate(rec)

    @work(thread=True, group="translate")
    def _do_translate(self, rec: RecommendedPaper) -> None:
        p = rec.paper
        translation = self.app.bridge.translation.translate(
            arxiv_id=p.arxiv_id,
            title=p.title,
            abstract=p.abstract,
        )
        if translation:
            self.app.call_from_thread(self._show_translation, rec, translation)
        else:
            self.app.call_from_thread(self._set_status, "Translation failed")
            self.app.call_from_thread(
                self.app.notify,
                "Could not generate translation",
                severity="warning",
            )

    def _show_translation(self, rec, translation) -> None:
        panel = self.query_one("#daily-panel", PaperPanel)
        panel.show_translation(translation)
        self._set_status(f"Translation done: {rec.paper.arxiv_id}")
