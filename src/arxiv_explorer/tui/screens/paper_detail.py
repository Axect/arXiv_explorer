"""Paper detail modal screen."""

from __future__ import annotations

from textual import on, work
from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Static, Button

from ...core.models import RecommendedPaper, PaperSummary, PaperTranslation


class PaperDetailScreen(ModalScreen):
    """Paper detail modal.

    Full paper info + action buttons (Like, Dislike, Summarize, Note, Add to List).
    """

    BINDINGS = [
        ("escape", "dismiss", "Close"),
        ("l", "like", "Like"),
        ("d", "dislike", "Dislike"),
        ("s", "summarize", "Summarize"),
        ("t", "translate", "Translate"),
        ("n", "add_note", "Note"),
        ("a", "add_to_list", "Add to List"),
    ]

    def __init__(self, rec: RecommendedPaper) -> None:
        super().__init__()
        self.rec = rec

    def compose(self) -> ComposeResult:
        p = self.rec.paper
        authors = ", ".join(p.authors[:10])
        if len(p.authors) > 10:
            authors += f" +{len(p.authors) - 10} more"
        categories = " | ".join(p.categories)
        published = p.published.strftime("%Y-%m-%d")

        with Vertical():
            yield Static(f"[bold]{p.title}[/bold]", classes="modal-title")

            with VerticalScroll(id="detail-scroll"):
                yield Static(
                    f"[dim]arXiv:[/dim] {p.arxiv_id}   [dim]Score:[/dim] {self.rec.score:.3f}\n"
                    f"[dim]Authors:[/dim] {authors}\n"
                    f"[dim]Categories:[/dim] {categories}\n"
                    f"[dim]Published:[/dim] {published}\n"
                    f"{'─' * 60}\n"
                    f"[bold cyan]Abstract[/bold cyan]\n{p.abstract}",
                    id="detail-info",
                )
                yield Static("", id="detail-summary")
                yield Static("", id="detail-translation")

            with Horizontal(classes="modal-buttons"):
                yield Button("Like [l]", id="md-like", variant="success")
                yield Button("Dislike [d]", id="md-dislike", variant="error")
                yield Button("Summarize [s]", id="md-summarize", variant="warning")
                yield Button("Translate [t]", id="md-translate")
                yield Button("Note [n]", id="md-note")
                yield Button("List [a]", id="md-list")
                yield Button("Close", id="md-close")

    def on_mount(self) -> None:
        if self.rec.summary:
            self._render_summary(self.rec.summary)
        else:
            self._check_cached_summary()

    @work(thread=True, group="detail-summary-check")
    def _check_cached_summary(self) -> None:
        cached = self.app.bridge.summarization._get_cached(self.rec.paper.arxiv_id)
        if cached:
            self.app.call_from_thread(self._render_summary, cached)

    def _render_summary(self, summary: PaperSummary) -> None:
        lines = [
            f"{'─' * 60}",
            f"[bold green]Summary:[/bold green] {summary.summary_short}",
        ]
        if summary.summary_detailed:
            lines.append(f"\n[bold green]Details:[/bold green] {summary.summary_detailed}")
        if summary.key_findings:
            lines.append("\n[bold green]Key Findings:[/bold green]")
            for i, f in enumerate(summary.key_findings, 1):
                lines.append(f"  {i}. {f}")
        self.query_one("#detail-summary", Static).update("\n".join(lines))

    # === Button events ===

    @on(Button.Pressed, "#md-close")
    def _on_close(self) -> None:
        self.dismiss()

    @on(Button.Pressed, "#md-like")
    def _on_like(self) -> None:
        self.action_like()

    @on(Button.Pressed, "#md-dislike")
    def _on_dislike(self) -> None:
        self.action_dislike()

    @on(Button.Pressed, "#md-summarize")
    def _on_summarize(self) -> None:
        self.action_summarize()

    @on(Button.Pressed, "#md-translate")
    def _on_translate(self) -> None:
        self.action_translate()

    @on(Button.Pressed, "#md-note")
    def _on_note(self) -> None:
        self.action_add_note()

    @on(Button.Pressed, "#md-list")
    def _on_list(self) -> None:
        self.action_add_to_list()

    # === Actions ===

    def action_like(self) -> None:
        self._do_like()

    @work(thread=True, group="detail-interaction")
    def _do_like(self) -> None:
        self.app.bridge.preferences.mark_interesting(self.rec.paper.arxiv_id)
        self.app.call_from_thread(
            self.app.notify, f"Liked {self.rec.paper.arxiv_id}"
        )

    def action_dislike(self) -> None:
        self._do_dislike()

    @work(thread=True, group="detail-interaction")
    def _do_dislike(self) -> None:
        self.app.bridge.preferences.mark_not_interesting(self.rec.paper.arxiv_id)
        self.app.call_from_thread(
            self.app.notify, f"Disliked {self.rec.paper.arxiv_id}"
        )

    def action_summarize(self) -> None:
        self.app.notify("Generating summary...")
        self._do_summarize()

    @work(thread=True, exclusive=True, group="detail-summarize")
    def _do_summarize(self) -> None:
        p = self.rec.paper
        summary = self.app.bridge.summarization.summarize(
            arxiv_id=p.arxiv_id, title=p.title, abstract=p.abstract, detailed=True
        )
        if summary:
            self.app.call_from_thread(self._render_summary, summary)
            self.app.call_from_thread(self.app.notify, "Summary complete")
        else:
            self.app.call_from_thread(
                self.app.notify, "Summary generation failed", severity="warning"
            )

    def action_add_note(self) -> None:
        from .note_input import NoteInputScreen
        self.app.push_screen(NoteInputScreen(self.rec.paper.arxiv_id))

    def action_translate(self) -> None:
        self.app.notify("Translating...")
        self._do_translate()

    @work(thread=True, exclusive=True, group="detail-translate")
    def _do_translate(self) -> None:
        p = self.rec.paper
        translation = self.app.bridge.translation.translate(
            arxiv_id=p.arxiv_id, title=p.title, abstract=p.abstract
        )
        if translation:
            self.app.call_from_thread(self._render_translation, translation)
            self.app.call_from_thread(self.app.notify, "Translation complete")
        else:
            self.app.call_from_thread(
                self.app.notify, "Translation failed", severity="warning"
            )

    def _render_translation(self, translation: PaperTranslation) -> None:
        lines = [
            f"{'─' * 60}",
            f"[bold magenta]Title:[/bold magenta] {translation.translated_title}",
            "",
            f"[bold magenta]Abstract:[/bold magenta] {translation.translated_abstract}",
        ]
        self.query_one("#detail-translation", Static).update("\n".join(lines))

    def action_add_to_list(self) -> None:
        from .list_picker import ListPickerScreen
        self.app.push_screen(ListPickerScreen(self.rec.paper.arxiv_id))
