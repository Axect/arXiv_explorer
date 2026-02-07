"""Paper list DataTable wrapper."""

from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message
from textual.widgets import DataTable, LoadingIndicator, Static

from ...core.models import RecommendedPaper


class PaperTable(Vertical):
    """DataTable wrapper for displaying paper lists.

    Manages three states:
    - loading: fetching data
    - data: showing paper list
    - empty: no results
    """

    DEFAULT_CSS = """
    PaperTable {
        height: 1fr;
    }
    PaperTable DataTable {
        height: 1fr;
    }
    PaperTable .hidden {
        display: none;
    }
    PaperTable #pt-empty {
        height: 1fr;
        content-align: center middle;
        color: $text-muted;
    }
    """

    class PaperSelected(Message):
        """Paper selected (Enter)."""

        def __init__(self, paper: RecommendedPaper) -> None:
            super().__init__()
            self.paper = paper

    class PaperHighlighted(Message):
        """Paper cursor moved (highlight)."""

        def __init__(self, paper: RecommendedPaper) -> None:
            super().__init__()
            self.paper = paper

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._papers: list[RecommendedPaper] = []

    def compose(self) -> ComposeResult:
        yield LoadingIndicator(id="pt-loading")
        yield DataTable(id="pt-table", cursor_type="row", zebra_stripes=True, classes="hidden")
        yield Static("No results.", id="pt-empty", classes="hidden")

    def on_mount(self) -> None:
        table = self.query_one("#pt-table", DataTable)
        table.add_column("#", key="idx", width=4)
        table.add_column("ID", key="arxiv_id", width=16)
        table.add_column("Title", key="title")
        table.add_column("Category", key="category", width=10)
        table.add_column("Score", key="score", width=6)

    def set_loading(self) -> None:
        self.query_one("#pt-loading").remove_class("hidden")
        self.query_one("#pt-table").add_class("hidden")
        self.query_one("#pt-empty").add_class("hidden")

    def set_papers(self, papers: list[RecommendedPaper]) -> None:
        self._papers = papers
        table = self.query_one("#pt-table", DataTable)
        table.clear()

        if not papers:
            self.query_one("#pt-loading").add_class("hidden")
            self.query_one("#pt-table").add_class("hidden")
            self.query_one("#pt-empty").remove_class("hidden")
            return

        for i, rec in enumerate(papers, 1):
            p = rec.paper
            title = p.title[:80] + "..." if len(p.title) > 80 else p.title
            table.add_row(
                str(i),
                p.arxiv_id,
                title,
                p.primary_category,
                f"{rec.score:.2f}",
                key=p.arxiv_id,
            )

        self.query_one("#pt-loading").add_class("hidden")
        self.query_one("#pt-table").remove_class("hidden")
        self.query_one("#pt-empty").add_class("hidden")

        if papers:
            self.post_message(self.PaperHighlighted(papers[0]))

    def _get_paper_by_row_key(self, row_key) -> RecommendedPaper | None:
        key_str = row_key.value if hasattr(row_key, "value") else str(row_key)
        for rec in self._papers:
            if rec.paper.arxiv_id == key_str:
                return rec
        return None

    @on(DataTable.RowSelected)
    def _on_row_selected(self, event: DataTable.RowSelected) -> None:
        rec = self._get_paper_by_row_key(event.row_key)
        if rec:
            self.post_message(self.PaperSelected(rec))

    @on(DataTable.RowHighlighted)
    def _on_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        rec = self._get_paper_by_row_key(event.row_key)
        if rec:
            self.post_message(self.PaperHighlighted(rec))

    @property
    def papers(self) -> list[RecommendedPaper]:
        return self._papers

    @property
    def current_paper(self) -> RecommendedPaper | None:
        table = self.query_one("#pt-table", DataTable)
        if table.cursor_row is not None and self._papers:
            try:
                row_key, _ = table.coordinate_to_cell_key(table.cursor_coordinate)
                return self._get_paper_by_row_key(row_key)
            except Exception:
                return None
        return None
