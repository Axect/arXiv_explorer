"""Search tab."""

from __future__ import annotations

from textual import on, work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Input, Static

from ...core.models import RecommendedPaper
from ..widgets.paper_panel import PaperPanel
from ..widgets.paper_table import PaperTable


class SearchPane(Vertical):
    """Paper search screen.

    Top: search input
    Left: PaperTable
    Right: PaperPanel
    """

    DEFAULT_CSS = """
    SearchPane {
        height: 1fr;
    }
    SearchPane #search-toolbar {
        height: 3;
        padding: 0 1;
        dock: top;
        background: $surface;
    }
    SearchPane #search-toolbar Input {
        width: 1fr;
        margin-right: 1;
    }
    SearchPane #search-toolbar Button {
        min-width: 10;
    }
    SearchPane #search-body {
        height: 1fr;
    }
    SearchPane #search-left {
        width: 2fr;
        min-width: 50;
    }
    SearchPane #search-interaction {
        dock: bottom;
        height: 3;
        padding: 0 1;
        background: $surface;
    }
    SearchPane #search-interaction Button {
        min-width: 12;
        margin-right: 1;
    }
    SearchPane #search-status {
        dock: bottom;
        height: 1;
        padding: 0 1;
        color: $text-muted;
        background: $surface-darken-1;
    }
    """

    BINDINGS = [
        ("slash", "focus_search", "Search"),
        ("l", "like", "Like"),
        ("d", "dislike", "Dislike"),
        ("s", "summarize", "Summarize"),
        ("t", "translate", "Translate"),
        ("w", "review", "Review"),
    ]

    def compose(self) -> ComposeResult:
        with Horizontal(id="search-toolbar"):
            yield Input(
                placeholder="Enter query and press Enter...",
                id="search-input",
            )
            yield Button("Search", id="search-btn", variant="primary")

        with Horizontal(id="search-body"):
            with Vertical(id="search-left"):
                yield PaperTable(id="search-table")
                with Horizontal(id="search-interaction"):
                    yield Button("Like [l]", id="btn-s-like", variant="success")
                    yield Button("Dislike [d]", id="btn-s-dislike", variant="error")
                    yield Button("Summarize [s]", id="btn-s-summarize", variant="warning")
                    yield Button("Translate [t]", id="btn-s-translate")
                    yield Button("Review [w]", id="btn-s-review", variant="primary")
                yield Static("Enter a search query", id="search-status")
            yield PaperPanel(id="search-panel")

    def on_mount(self) -> None:
        table = self.query_one("#search-table", PaperTable)
        table.query_one("#pt-loading").add_class("hidden")
        table.query_one("#pt-empty").remove_class("hidden")
        table.query_one("#pt-empty", Static).update("Enter a search query (/)")

    @on(Input.Submitted, "#search-input")
    def _on_search_submitted(self, event: Input.Submitted) -> None:
        self._run_search(event.value)

    @on(Button.Pressed, "#search-btn")
    def _on_search_clicked(self) -> None:
        query = self.query_one("#search-input", Input).value
        self._run_search(query)

    @on(Button.Pressed, "#btn-s-like")
    def _on_like_clicked(self) -> None:
        self.action_like()

    @on(Button.Pressed, "#btn-s-dislike")
    def _on_dislike_clicked(self) -> None:
        self.action_dislike()

    @on(Button.Pressed, "#btn-s-summarize")
    def _on_summarize_clicked(self) -> None:
        self.action_summarize()

    @on(Button.Pressed, "#btn-s-translate")
    def _on_translate_clicked(self) -> None:
        self.action_translate()

    @on(Button.Pressed, "#btn-s-review")
    def _on_review_clicked(self) -> None:
        self.action_review()

    @on(PaperTable.PaperHighlighted)
    def _on_paper_highlighted(self, event: PaperTable.PaperHighlighted) -> None:
        panel = self.query_one("#search-panel", PaperPanel)
        panel.show_paper(event.paper)

    @on(PaperTable.PaperSelected)
    def _on_paper_selected(self, event: PaperTable.PaperSelected) -> None:
        from .paper_detail import PaperDetailScreen

        self.app.push_screen(PaperDetailScreen(event.paper))

    def _run_search(self, query: str) -> None:
        query = query.strip()
        if not query:
            self.app.notify("Please enter a query", severity="warning")
            return

        table = self.query_one("#search-table", PaperTable)
        table.set_loading()
        self._set_status(f'Searching "{query}"...')
        self._do_search(query)

    @work(thread=True, exclusive=True, group="search")
    def _do_search(self, query: str) -> None:
        bridge = self.app.bridge
        try:
            papers = bridge.papers.search_papers(query=query, limit=20)
        except Exception as e:
            self.app.call_from_thread(self._show_error, str(e))
            return

        self.app.call_from_thread(self._update_results, query, papers)

    def _update_results(self, query: str, papers: list[RecommendedPaper]) -> None:
        table = self.query_one("#search-table", PaperTable)
        table.set_papers(papers)
        self._set_status(f'"{query}" — {len(papers)} results')

    def _show_error(self, msg: str) -> None:
        table = self.query_one("#search-table", PaperTable)
        table.set_papers([])
        self._set_status(f"Error: {msg}")
        self.app.notify(f"Search error: {msg}", severity="error")

    def _set_status(self, text: str) -> None:
        self.query_one("#search-status", Static).update(text)

    def action_focus_search(self) -> None:
        self.query_one("#search-input", Input).focus()

    # === Interactions ===

    def _get_current(self) -> RecommendedPaper | None:
        table = self.query_one("#search-table", PaperTable)
        return table.current_paper

    def action_like(self) -> None:
        rec = self._get_current()
        if not rec:
            return
        self._do_like(rec)

    @work(thread=True, group="s-interaction")
    def _do_like(self, rec: RecommendedPaper) -> None:
        self.app.bridge.preferences.mark_interesting(rec.paper.arxiv_id)
        self.app.call_from_thread(self.app.notify, f"Liked {rec.paper.arxiv_id}")

    def action_dislike(self) -> None:
        rec = self._get_current()
        if not rec:
            return
        self._do_dislike(rec)

    @work(thread=True, group="s-interaction")
    def _do_dislike(self, rec: RecommendedPaper) -> None:
        self.app.bridge.preferences.mark_not_interesting(rec.paper.arxiv_id)
        self.app.call_from_thread(self.app.notify, f"Disliked {rec.paper.arxiv_id}")

    def action_summarize(self) -> None:
        rec = self._get_current()
        if not rec:
            return
        self._set_status(f"Summarizing {rec.paper.arxiv_id}...")
        self._do_summarize(rec)

    @work(thread=True, group="s-summarize")
    def _do_summarize(self, rec: RecommendedPaper) -> None:
        p = rec.paper
        summary = self.app.bridge.summarization.summarize(
            arxiv_id=p.arxiv_id, title=p.title, abstract=p.abstract, detailed=True
        )
        if summary:
            self.app.call_from_thread(self._show_summary, rec, summary)
        else:
            self.app.call_from_thread(self._set_status, "Summary generation failed")
            self.app.call_from_thread(
                self.app.notify, "Summary generation failed", severity="warning"
            )

    def _show_summary(self, rec, summary) -> None:
        panel = self.query_one("#search-panel", PaperPanel)
        panel.show_summary(summary)
        self._set_status(f"Summary done: {rec.paper.arxiv_id}")

    def action_translate(self) -> None:
        rec = self._get_current()
        if not rec:
            return
        self._set_status(f"Translating {rec.paper.arxiv_id}...")
        self._do_translate(rec)

    @work(thread=True, group="s-translate")
    def _do_translate(self, rec: RecommendedPaper) -> None:
        p = rec.paper
        translation = self.app.bridge.translation.translate(
            arxiv_id=p.arxiv_id, title=p.title, abstract=p.abstract
        )
        if translation:
            self.app.call_from_thread(self._show_translation, rec, translation)
        else:
            self.app.call_from_thread(self._set_status, "Translation failed")
            self.app.call_from_thread(self.app.notify, "Translation failed", severity="warning")

    def _show_translation(self, rec, translation) -> None:
        panel = self.query_one("#search-panel", PaperPanel)
        panel.show_translation(translation)
        self._set_status(f"Translation done: {rec.paper.arxiv_id}")

    def action_review(self) -> None:
        rec = self._get_current()
        if not rec:
            return
        from .review_screen import ReviewScreen

        self.app.push_screen(ReviewScreen(rec))
