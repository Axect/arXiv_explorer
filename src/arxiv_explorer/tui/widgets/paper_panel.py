"""Paper detail panel (right side)."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Static

from ...core.models import PaperSummary, PaperTranslation, RecommendedPaper


class PaperPanel(VerticalScroll):
    """Right-side detail panel — shows paper metadata + abstract + summary."""

    DEFAULT_CSS = """
    PaperPanel {
        width: 1fr;
        min-width: 40;
        border-left: tall $surface-lighten-2;
        padding: 1 2;
    }
    PaperPanel #pp-placeholder {
        color: $text-muted;
        content-align: center middle;
        height: 1fr;
    }
    PaperPanel #pp-content {
        height: auto;
    }
    PaperPanel .pp-label {
        color: $accent;
        text-style: bold;
        margin-top: 1;
    }
    PaperPanel .pp-value {
        margin-bottom: 0;
    }
    PaperPanel #pp-summary-section {
        margin-top: 1;
        border-top: heavy $surface-lighten-2;
        padding-top: 1;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._current_text: str = ""

    def compose(self) -> ComposeResult:
        yield Static("Select a paper", id="pp-placeholder")
        yield Static(id="pp-content", classes="hidden")

    def show_paper(self, rec: RecommendedPaper) -> None:
        p = rec.paper
        placeholder = self.query_one("#pp-placeholder")
        content = self.query_one("#pp-content")

        authors = ", ".join(p.authors[:5])
        if len(p.authors) > 5:
            authors += f" +{len(p.authors) - 5} more"

        categories = " | ".join(p.categories)
        published = p.published.strftime("%Y-%m-%d")

        lines = [
            f"[bold]{p.title}[/bold]\n",
            f"[dim]arXiv:[/dim] {p.arxiv_id}   [dim]Score:[/dim] {rec.score:.3f}",
            f"[dim]Authors:[/dim] {authors}",
            f"[dim]Categories:[/dim] {categories}",
            f"[dim]Published:[/dim] {published}",
            "",
            "[bold cyan]Abstract[/bold cyan]",
            p.abstract,
        ]

        if rec.summary:
            lines.extend(self._format_summary(rec.summary))

        self._current_text = "\n".join(lines)
        content.update(self._current_text)
        placeholder.add_class("hidden")
        content.remove_class("hidden")
        self.scroll_home(animate=False)

    def show_summary(self, summary: PaperSummary) -> None:
        content = self.query_one("#pp-content")

        marker = "\n━━━ Summary ━━━"
        base = self._current_text
        if marker in base:
            base = base[: base.index(marker)]

        summary_lines = self._format_summary(summary)
        self._current_text = base + "\n".join(summary_lines)
        content.update(self._current_text)

    def show_translation(self, translation: PaperTranslation) -> None:
        content = self.query_one("#pp-content")

        marker = "\n━━━ Translation ━━━"
        base = self._current_text
        if marker in base:
            base = base[: base.index(marker)]

        translation_lines = self._format_translation(translation)
        self._current_text = base + "\n".join(translation_lines)
        content.update(self._current_text)

    def _format_translation(self, translation: PaperTranslation) -> list[str]:
        return [
            "",
            "━━━ Translation ━━━",
            f"[bold magenta]Title:[/bold magenta] {translation.translated_title}",
            "",
            f"[bold magenta]Abstract:[/bold magenta] {translation.translated_abstract}",
        ]

    def _format_summary(self, summary: PaperSummary) -> list[str]:
        lines = [
            "",
            "━━━ Summary ━━━",
            f"[bold green]Summary:[/bold green] {summary.summary_short}",
        ]
        if summary.summary_detailed:
            lines.extend(["", f"[bold green]Details:[/bold green] {summary.summary_detailed}"])
        if summary.key_findings:
            lines.append("\n[bold green]Key Findings:[/bold green]")
            for i, finding in enumerate(summary.key_findings, 1):
                lines.append(f"  {i}. {finding}")
        return lines

    def clear(self) -> None:
        self._current_text = ""
        self.query_one("#pp-placeholder").remove_class("hidden")
        self.query_one("#pp-content").add_class("hidden")
