"""Paper review modal screen."""

from __future__ import annotations

from pathlib import Path

from textual import on, work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Markdown, Static

from ...core.models import Language, RecommendedPaper, ReviewSectionType

# Human-readable section names for progress display
_SECTION_NAMES: dict[ReviewSectionType, str] = {
    ReviewSectionType.EXECUTIVE_SUMMARY: "Executive Summary",
    ReviewSectionType.KEY_CONTRIBUTIONS: "Key Contributions",
    ReviewSectionType.SECTION_SUMMARIES: "Section Summaries",
    ReviewSectionType.METHODOLOGY: "Methodology",
    ReviewSectionType.MATH_FORMULATIONS: "Math Formulations",
    ReviewSectionType.FIGURES: "Figures",
    ReviewSectionType.TABLES: "Tables",
    ReviewSectionType.EXPERIMENTAL_RESULTS: "Experiments",
    ReviewSectionType.STRENGTHS_WEAKNESSES: "Strengths & Weaknesses",
    ReviewSectionType.RELATED_WORK: "Related Work",
    ReviewSectionType.GLOSSARY: "Glossary",
    ReviewSectionType.QUESTIONS: "Questions",
}


class ReviewScreen(ModalScreen):
    """Full-screen modal displaying a comprehensive paper review.

    Shows progress while generating, then renders the final markdown.
    """

    DEFAULT_CSS = """
    ReviewScreen {
        align: center middle;
    }
    ReviewScreen > Vertical {
        width: 90%;
        height: 90%;
        border: thick $accent;
        background: $surface;
    }
    ReviewScreen .review-title {
        text-align: center;
        padding: 1 2;
        text-style: bold;
        color: $accent;
    }
    ReviewScreen #review-status {
        height: 1;
        padding: 0 2;
        color: $text-muted;
        background: $surface-darken-1;
    }
    ReviewScreen #review-content {
        height: 1fr;
        padding: 1 2;
    }
    ReviewScreen .review-buttons {
        height: 3;
        padding: 0 1;
        align: center middle;
        background: $surface;
    }
    ReviewScreen .review-buttons Button {
        min-width: 14;
        margin: 0 1;
    }
    """

    BINDINGS = [
        ("escape", "dismiss", "Close"),
    ]

    def __init__(self, rec: RecommendedPaper) -> None:
        super().__init__()
        self.rec = rec
        self._review = None
        self._generating = False
        self._translated_md: str | None = None
        self._translated_lang: Language | None = None

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(
                f"Review: {self.rec.paper.title}", classes="review-title"
            )
            yield Static("Loading...", id="review-status")
            yield Markdown("", id="review-content")
            with Horizontal(classes="review-buttons"):
                yield Button(
                    "Save [s]", id="review-save", variant="primary"
                )
                yield Button(
                    "Translate [t]", id="review-translate", variant="warning"
                )
                yield Button("Close [esc]", id="review-close")

    def on_mount(self) -> None:
        self._load_or_generate()

    def _set_status(self, text: str) -> None:
        try:
            self.query_one("#review-status", Static).update(text)
        except Exception:
            pass

    # ── Generation ────────────────────────────────────────────────────

    @work(thread=True, exclusive=True, group="review-generate")
    def _load_or_generate(self) -> None:
        """Load cached review instantly, then generate missing sections."""
        self._generating = True
        bridge = self.app.bridge
        paper = self.rec.paper

        # Check for cached review (even partial)
        cached = bridge.review.get_cached_review(paper.arxiv_id)
        if cached and cached.sections:
            # Fill in paper metadata (cached review has empty metadata)
            cached.title = paper.title
            cached.authors = paper.authors
            cached.categories = paper.categories
            cached.published = paper.published
            cached.pdf_url = paper.pdf_url
            cached.abstract = paper.abstract
            self._review = cached
            md = bridge.review.render_markdown(cached)
            self.app.call_from_thread(self._show_review, md)

            if cached.is_complete:
                done = len(cached.sections)
                self.app.call_from_thread(
                    self._set_status, f"Loaded from cache — {done} sections"
                )
                self._generating = False
                return

            # Partial cache: show what we have, generate the rest
            missing = cached.missing_sections
            self.app.call_from_thread(
                self._set_status,
                f"Loaded {len(cached.sections)} sections"
                f" — generating {len(missing)} remaining...",
            )

        # Generate (all or remaining) with progress
        def on_start(
            section_type: ReviewSectionType, idx: int, total: int
        ) -> None:
            name = _SECTION_NAMES.get(section_type, section_type.value)
            self.app.call_from_thread(
                self._set_status,
                f"Generating [{idx + 1}/{total}]: {name}...",
            )

        succeeded = [0]
        failed = [0]

        def on_complete(section_type: ReviewSectionType, success: bool) -> None:
            if success:
                succeeded[0] += 1
            else:
                failed[0] += 1

        review = bridge.review.generate_review(
            paper=paper,
            on_section_start=on_start,
            on_section_complete=on_complete,
        )

        self._generating = False

        if review:
            self._review = review
            md = bridge.review.render_markdown(review)
            self.app.call_from_thread(self._show_review, md)
            self.app.call_from_thread(
                self._set_status,
                f"Done — {succeeded[0]} sections"
                + (f" ({failed[0]} failed)" if failed[0] else ""),
            )
        else:
            self.app.call_from_thread(
                self._set_status, "Review generation failed"
            )
            self.app.call_from_thread(
                self.app.notify,
                "Could not generate review",
                severity="warning",
            )

    def _show_review(self, markdown_text: str) -> None:
        self.query_one("#review-content", Markdown).update(markdown_text)

    # ── Button Events ─────────────────────────────────────────────────

    @on(Button.Pressed, "#review-close")
    def _on_close(self) -> None:
        self.dismiss()

    @on(Button.Pressed, "#review-save")
    def _on_save(self) -> None:
        self._save_review()

    @on(Button.Pressed, "#review-translate")
    def _on_translate(self) -> None:
        self._translate_review()

    def key_s(self) -> None:
        self._save_review()

    def key_t(self) -> None:
        self._translate_review()

    # ── Save ──────────────────────────────────────────────────────────

    def _save_review(self) -> None:
        if not self._review:
            self.app.notify("No review to save", severity="warning")
            return
        self._do_save()

    @work(thread=True, group="review-save")
    def _do_save(self) -> None:
        review = self._review
        md = self.app.bridge.review.render_markdown(review)
        normalized = review.arxiv_id.replace("/", "_")
        out_dir = Path.cwd() / "reviews"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{normalized}_review.md"
        out_path.write_text(md, encoding="utf-8")
        saved_files = [str(out_path)]

        # Also save translated version if available
        if self._translated_md and self._translated_lang:
            lang_code = self._translated_lang.value
            trans_path = out_dir / f"{normalized}_review_{lang_code}.md"
            trans_path.write_text(self._translated_md, encoding="utf-8")
            saved_files.append(str(trans_path))

        self.app.call_from_thread(
            self.app.notify, f"Saved: {', '.join(saved_files)}"
        )

    # ── Translate ─────────────────────────────────────────────────────

    def _translate_review(self) -> None:
        if not self._review:
            self.app.notify("No review to translate", severity="warning")
            return
        lang = self.app.bridge.settings.get_language()
        if lang == Language.EN:
            self.app.notify(
                "Language is set to English. Change in Prefs tab.",
                severity="warning",
            )
            return
        self.app.notify("Translating review...")
        self._do_translate(lang)

    @work(thread=True, exclusive=True, group="review-translate")
    def _do_translate(self, lang: Language) -> None:
        review = self._review
        md = self.app.bridge.review.render_markdown(review, language=lang)
        self._translated_md = md
        self._translated_lang = lang
        self.app.call_from_thread(self._show_review, md)
        self.app.call_from_thread(
            self._set_status, f"Translated to {lang.value}"
        )
        self.app.call_from_thread(self.app.notify, "Translation complete")
