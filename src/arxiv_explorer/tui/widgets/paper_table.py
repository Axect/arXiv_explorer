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
        self._bookmarked: set[str] = set()
        self._author_matched: set[str] = set()

    def compose(self) -> ComposeResult:
        yield LoadingIndicator(id="pt-loading")
        yield DataTable(id="pt-table", cursor_type="row", zebra_stripes=True, classes="hidden")
        yield Static("No results.", id="pt-empty", classes="hidden")

    def on_mount(self) -> None:
        table = self.query_one("#pt-table", DataTable)
        table.add_column("#", key="idx", width=3)
        table.add_column("ID", key="arxiv_id", width=14)
        table.add_column("Title", key="title")
        table.add_column("Category", key="category", width=8)
        table.add_column("Score", key="score", width=5)

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

    def set_bookmarked(self, arxiv_ids: set[str]) -> None:
        """Set which papers are bookmarked and refresh the index column."""
        self._bookmarked = arxiv_ids
        self._refresh_row_labels()

    def toggle_bookmark(self, arxiv_id: str) -> bool:
        """Toggle bookmark for a paper.  Returns True if now bookmarked."""
        if arxiv_id in self._bookmarked:
            self._bookmarked.discard(arxiv_id)
            result = False
        else:
            self._bookmarked.add(arxiv_id)
            result = True
        self._refresh_row_labels()
        return result

    def set_author_matched(self, arxiv_ids: set[str]) -> None:
        """Mark papers by preferred authors with a star label."""
        self._author_matched = arxiv_ids
        self._refresh_row_labels()

    def _refresh_row_labels(self) -> None:
        """Update row cells with colored indicators for bookmarked/author-matched papers.

        Author rows get warm yellow (#f9e2af), bookmarked rows get soft green (#a6e3a1).
        The style is applied to ALL cells so the entire row appears highlighted.
        """
        from rich.text import Text

        table = self.query_one("#pt-table", DataTable)
        for i, rec in enumerate(self._papers):
            arxiv_id = rec.paper.arxiv_id
            is_author = arxiv_id in self._author_matched
            is_bookmarked = arxiv_id in self._bookmarked

            # Determine row highlight style
            if is_author:
                style = "#f9e2af"
            elif is_bookmarked:
                style = "#a6e3a1"
            else:
                style = ""

            # Build # cell with indicator prefix
            num = str(i + 1)
            if is_author or is_bookmarked:
                idx_cell = Text()
                if is_author:
                    idx_cell.append("★", style="bold #f9e2af")
                if is_bookmarked:
                    idx_cell.append("✓", style="bold #a6e3a1")
                idx_cell.append(num)
            else:
                idx_cell = Text(num)

            # Build remaining cells — apply row style when highlighted
            p = rec.paper
            title = p.title[:80] + "..." if len(p.title) > 80 else p.title

            try:
                table.update_cell(arxiv_id, "idx", idx_cell)
                if style:
                    table.update_cell(arxiv_id, "arxiv_id", Text(p.arxiv_id, style=style))
                    table.update_cell(arxiv_id, "title", Text(title, style=style))
                    table.update_cell(arxiv_id, "category", Text(p.primary_category, style=style))
                    table.update_cell(arxiv_id, "score", Text(f"{rec.score:.2f}", style=style))
                else:
                    table.update_cell(arxiv_id, "arxiv_id", p.arxiv_id)
                    table.update_cell(arxiv_id, "title", title)
                    table.update_cell(arxiv_id, "category", p.primary_category)
                    table.update_cell(arxiv_id, "score", f"{rec.score:.2f}")
            except Exception:
                pass

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
