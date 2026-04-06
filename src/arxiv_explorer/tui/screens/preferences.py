"""Preferences tab."""

from __future__ import annotations

from textual import on, work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, DataTable, Input, Select, Static

from ...core.models import (
    AIProviderType,
    KeywordInterest,
    Language,
    PreferredAuthor,
    PreferredCategory,
)
from ...services.providers import get_provider
from ...services.settings_service import WEIGHT_KEYS, adjust_weights
from .category_picker import CategoryPickerScreen

_WEIGHT_LABELS = {
    "content": "Content Similarity",
    "category": "Category Match",
    "keyword": "Keyword Match",
    "recency": "Recency Bonus",
}


class PreferencesPane(Vertical):
    """User preferences management screen.

    Left: Category DataTable + add/delete
    Right: Keyword DataTable + add/delete
    """

    DEFAULT_CSS = """
    PreferencesPane {
        height: 1fr;
    }

    /* Top: 3-column sections */
    PreferencesPane #prefs-body {
        height: 1fr;
    }
    PreferencesPane .pref-section {
        width: 1fr;
        padding: 0 1;
        border-right: tall $surface-lighten-1;
    }
    PreferencesPane .pref-section.last-section {
        border-right: none;
    }
    PreferencesPane .pref-section-title {
        text-style: bold;
        color: $accent;
        height: 1;
        margin-bottom: 1;
    }
    PreferencesPane .pref-section DataTable {
        height: 1fr;
    }
    PreferencesPane .pref-input-row {
        height: 3;
        padding: 0;
    }
    PreferencesPane .pref-input-row Input {
        width: 1fr;
        margin-right: 1;
    }
    PreferencesPane .pref-input-row Button {
        min-width: 10;
    }
    PreferencesPane .pref-hint {
        height: 1;
        color: $text-muted;
    }

    /* Bottom panels: weights + config */
    PreferencesPane #prefs-bottom {
        height: auto;
        max-height: 14;
    }
    PreferencesPane #weights-section {
        width: 2fr;
        padding: 0 1;
        border-right: tall $surface-lighten-1;
    }
    PreferencesPane #weights-title {
        text-style: bold;
        color: $accent;
        height: 1;
    }
    PreferencesPane #weights-table {
        height: auto;
    }
    PreferencesPane #weights-footer {
        height: 1;
        color: $text-muted;
    }
    PreferencesPane #weights-controls {
        height: 3;
    }
    PreferencesPane #ai-config-section {
        width: 1fr;
        padding: 0 1;
    }
    PreferencesPane #ai-config-title {
        text-style: bold;
        color: $accent;
        height: 1;
    }
    PreferencesPane #ai-config-status {
        height: auto;
        color: $text;
        margin-bottom: 1;
    }
    PreferencesPane #ai-config-controls {
        height: 3;
    }
    PreferencesPane .config-label {
        width: auto;
        height: 1;
        margin-top: 1;
        margin-right: 1;
        color: $text-muted;
    }
    PreferencesPane #ai-provider-select {
        width: 24;
        margin-right: 2;
    }
    PreferencesPane #language-select {
        width: 16;
    }
    """

    BINDINGS = [
        ("r", "refresh", "Refresh"),
        ("delete", "delete_selected", "Delete"),
        ("left", "weight_decrease", "Weight -1"),
        ("right", "weight_increase", "Weight +1"),
    ]

    def compose(self) -> ComposeResult:
        # Top: 3-column data sections
        with Horizontal(id="prefs-body"):
            with Vertical(classes="pref-section"):
                yield Static("Categories", classes="pref-section-title")
                yield DataTable(id="cat-table", cursor_type="row", zebra_stripes=True)
                with Horizontal(classes="pref-input-row"):
                    yield Button("Browse", id="cat-browse", variant="default")
                    yield Input(placeholder="Pri", id="cat-priority", type="integer", value="1")
                yield Static("[dim]Enter:Add  Del:Remove[/dim]", classes="pref-hint")

            with Vertical(classes="pref-section"):
                yield Static("Keywords", classes="pref-section-title")
                yield DataTable(id="kw-table", cursor_type="row", zebra_stripes=True)
                with Horizontal(classes="pref-input-row"):
                    yield Input(placeholder="Keyword", id="kw-input")
                    yield Input(placeholder="★1-5", id="kw-weight", value="3")
                yield Static("[dim]Enter:Add  Del:Remove[/dim]", classes="pref-hint")

            with Vertical(classes="pref-section last-section"):
                yield Static("Authors", classes="pref-section-title")
                yield DataTable(id="author-table", cursor_type="row", zebra_stripes=True)
                with Horizontal(classes="pref-input-row"):
                    yield Input(placeholder="Author name", id="author-input")
                yield Static("[dim]Enter:Add  Del:Remove[/dim]", classes="pref-hint")

        # Bottom: weights + config side by side
        with Horizontal(id="prefs-bottom"):
            with Vertical(id="weights-section"):
                yield Static("Recommendation Weights", id="weights-title")
                yield DataTable(id="weights-table", cursor_type="row", zebra_stripes=True)
                yield Static("", id="weights-footer")
                with Horizontal(id="weights-controls"):
                    yield Button("Reset", id="weights-reset", variant="warning")

            with Vertical(id="ai-config-section"):
                yield Static("Configuration", id="ai-config-title")
                yield Static("[dim]Loading...[/dim]", id="ai-config-status")
                with Horizontal(id="ai-config-controls"):
                    yield Static("Provider:", classes="config-label")
                    yield Select(
                        [(p.value, p.value) for p in AIProviderType],
                        id="ai-provider-select",
                        prompt="Provider",
                    )
                    yield Static("Lang:", classes="config-label")
                    yield Select(
                        [(lang.value, lang.value) for lang in Language],
                        id="language-select",
                        prompt="Language",
                    )

    def on_mount(self) -> None:
        self._pending_cat: str | None = None

        # Initialize category table
        cat_table = self.query_one("#cat-table", DataTable)
        cat_table.add_column("Category", key="category", width=16)
        cat_table.add_column("Priority", key="priority", width=10)
        cat_table.add_column("Added", key="added", width=12)

        # Initialize keyword table
        kw_table = self.query_one("#kw-table", DataTable)
        kw_table.add_column("Keyword", key="keyword", width=20)
        kw_table.add_column("Weight", key="weight", width=10)
        kw_table.add_column("Source", key="source", width=10)

        # Initialize author table
        author_table = self.query_one("#author-table", DataTable)
        author_table.add_column("Author", key="author", width=24)
        author_table.add_column("Added", key="added", width=12)

        # Initialize weights table
        wt = self.query_one("#weights-table", DataTable)
        wt.add_column("Weight", key="name", width=22)
        wt.add_column("Value", key="value", width=6)
        wt.add_column("Bar", key="bar", width=34)

        self._load_all()
        self._load_ai_provider()
        self._load_weights()

    def action_refresh(self) -> None:
        self._load_all()
        self._load_ai_provider()
        self._load_weights()

    def action_delete_selected(self) -> None:
        # Delete based on focused table
        cat_table = self.query_one("#cat-table", DataTable)
        kw_table = self.query_one("#kw-table", DataTable)
        author_table = self.query_one("#author-table", DataTable)
        if cat_table.has_focus:
            self._delete_category()
        elif kw_table.has_focus:
            self._delete_keyword()
        elif author_table.has_focus:
            self._delete_author()

    # === Categories ===

    @on(Button.Pressed, "#cat-browse")
    def _on_cat_browse(self) -> None:
        self.app.push_screen(CategoryPickerScreen(), self._on_category_picked)

    def _on_category_picked(self, code: str | None) -> None:
        if code:
            self._pending_cat = code
            self.app.notify(f"Selected: {code} — press Enter to add", severity="information")

    @on(Input.Submitted, "#cat-priority")
    def _on_cat_priority_submitted(self) -> None:
        self._add_category()

    def _add_category(self) -> None:
        cat = self._pending_cat
        if not cat:
            self.app.notify("Browse and select a category first", severity="warning")
            return
        pri_str = self.query_one("#cat-priority", Input).value.strip()
        try:
            priority = int(pri_str) if pri_str else 1
        except ValueError:
            priority = 1
        self._pending_cat = None
        self._do_add_category(cat, priority)

    @work(thread=True, group="pref-cat-add")
    def _do_add_category(self, category: str, priority: int) -> None:
        self.app.bridge.preferences.add_category(category, priority)
        self.app.call_from_thread(self.app.notify, f"Added: {category}")
        self._load_categories()

    def _delete_category(self) -> None:
        table = self.query_one("#cat-table", DataTable)
        if table.cursor_row is None:
            return
        try:
            row_key, _ = table.coordinate_to_cell_key(table.cursor_coordinate)
        except Exception:
            return
        cat = row_key.value if hasattr(row_key, "value") else str(row_key)
        self._do_delete_category(cat)

    @work(thread=True, group="pref-cat-del")
    def _do_delete_category(self, category: str) -> None:
        self.app.bridge.preferences.remove_category(category)
        self.app.call_from_thread(self.app.notify, f"Deleted: {category}")
        self._load_categories()

    # === Keywords ===

    @on(Input.Submitted, "#kw-input")
    def _on_kw_submitted(self) -> None:
        self._add_keyword()

    def _add_keyword(self) -> None:
        kw = self.query_one("#kw-input", Input).value.strip()
        if not kw:
            self.app.notify("Please enter a keyword", severity="warning")
            return
        weight_str = self.query_one("#kw-weight", Input).value.strip()
        try:
            weight = int(weight_str) if weight_str else 3
            weight = max(1, min(5, weight))
        except ValueError:
            weight = 3
        self._do_add_keyword(kw, weight)

    @work(thread=True, group="pref-kw-add")
    def _do_add_keyword(self, keyword: str, weight: int) -> None:
        self.app.bridge.preferences.add_keyword(keyword, weight)
        self.app.call_from_thread(self.app.notify, f"Added: {keyword}")
        self.app.call_from_thread(self.query_one("#kw-input", Input).clear)
        self._load_keywords()

    def _delete_keyword(self) -> None:
        table = self.query_one("#kw-table", DataTable)
        if table.cursor_row is None:
            return
        try:
            row_key, _ = table.coordinate_to_cell_key(table.cursor_coordinate)
        except Exception:
            return
        kw = row_key.value if hasattr(row_key, "value") else str(row_key)
        self._do_delete_keyword(kw)

    @work(thread=True, group="pref-kw-del")
    def _do_delete_keyword(self, keyword: str) -> None:
        self.app.bridge.preferences.remove_keyword(keyword)
        self.app.call_from_thread(self.app.notify, f"Deleted: {keyword}")
        self._load_keywords()

    # === Authors ===

    @on(Input.Submitted, "#author-input")
    def _on_author_submitted(self) -> None:
        self._add_author()

    def _add_author(self) -> None:
        name = self.query_one("#author-input", Input).value.strip()
        if not name:
            self.app.notify("Please enter an author name", severity="warning")
            return
        self._do_add_author(name)

    @work(thread=True, group="pref-author-add")
    def _do_add_author(self, name: str) -> None:
        self.app.bridge.authors.add_author(name)
        self.app.call_from_thread(self.app.notify, f"Added: {name}")
        self.app.call_from_thread(self.query_one("#author-input", Input).clear)
        self._load_authors()

    def _delete_author(self) -> None:
        table = self.query_one("#author-table", DataTable)
        if table.cursor_row is None:
            return
        try:
            row_key, _ = table.coordinate_to_cell_key(table.cursor_coordinate)
        except Exception:
            return
        name = row_key.value if hasattr(row_key, "value") else str(row_key)
        self._do_delete_author(name)

    @work(thread=True, group="pref-author-del")
    def _do_delete_author(self, name: str) -> None:
        self.app.bridge.authors.remove_author(name)
        self.app.call_from_thread(self.app.notify, f"Deleted: {name}")
        self._load_authors()

    # === AI Provider ===

    @on(Select.Changed, "#ai-provider-select")
    def _on_provider_changed(self, event: Select.Changed) -> None:
        if event.value != Select.BLANK:
            self._save_provider(str(event.value))

    @on(Select.Changed, "#language-select")
    def _on_language_changed(self, event: Select.Changed) -> None:
        if event.value != Select.BLANK:
            self._save_language(str(event.value))

    @work(thread=True, group="pref-lang-save")
    def _save_language(self, value: str) -> None:
        self.app.bridge.settings.set("language", value)
        self.app.call_from_thread(self.app.notify, f"Language: {value}")
        self._refresh_status()

    @work(thread=True, group="pref-ai-save")
    def _save_provider(self, value: str) -> None:
        self.app.bridge.settings.set("ai_provider", value)
        self.app.call_from_thread(self.app.notify, f"Provider: {value}")
        self._refresh_status()

    @work(thread=True, group="pref-ai-load")
    def _load_ai_provider(self) -> None:
        current = self.app.bridge.settings.get_provider()
        current_lang = self.app.bridge.settings.get_language()
        status_text = self._build_status_text()
        self.app.call_from_thread(
            self._apply_loaded_settings, current.value, current_lang.value, status_text
        )

    def _apply_loaded_settings(self, provider_val: str, lang_val: str, status_text: str) -> None:
        with self.prevent(Select.Changed):
            self.query_one("#ai-provider-select", Select).value = provider_val
            self.query_one("#language-select", Select).value = lang_val
        self.query_one("#ai-config-status", Static).update(status_text)

    def _build_status_text(self) -> str:
        settings = self.app.bridge.settings
        current = settings.get_provider()
        provider = get_provider(current)
        available = provider.is_available()
        avail_str = "[green]available[/green]" if available else "[red]not found[/red]"
        model = settings.get_model() or "(default)"
        lang = settings.get_language()
        return (
            f"[bold]{current.value}[/bold] ({provider.cli_command}) {avail_str}"
            f"  ·  Model: {model}"
            f"  ·  Language: [bold]{lang.value}[/bold]"
        )

    def _refresh_status(self) -> None:
        """Rebuild status text from current DB values (called from worker threads)."""
        text = self._build_status_text()
        self.app.call_from_thread(self.query_one("#ai-config-status", Static).update, text)

    # === Data loading ===

    def _load_all(self) -> None:
        self._load_categories()
        self._load_keywords()
        self._load_authors()

    @work(thread=True, exclusive=True, group="pref-load-cat")
    def _load_categories(self) -> None:
        cats = self.app.bridge.preferences.get_categories()
        self.app.call_from_thread(self._populate_categories, cats)

    def _populate_categories(self, cats: list[PreferredCategory]) -> None:
        table = self.query_one("#cat-table", DataTable)
        table.clear()
        for c in cats:
            added = c.added_at.strftime("%Y-%m-%d")
            table.add_row(c.category, str(c.priority), added, key=c.category)

    @work(thread=True, exclusive=True, group="pref-load-kw")
    def _load_keywords(self) -> None:
        keywords = self.app.bridge.preferences.get_keywords()
        self.app.call_from_thread(self._populate_keywords, keywords)

    @staticmethod
    def _stars_display(n: int) -> str:
        """Convert 1-5 rating to star display."""
        return "\u2605" * n + "\u2606" * (5 - n)

    def _populate_keywords(self, keywords: list[KeywordInterest]) -> None:
        table = self.query_one("#kw-table", DataTable)
        table.clear()
        for k in keywords:
            table.add_row(k.keyword, self._stars_display(k.weight), k.source, key=k.keyword)

    @work(thread=True, exclusive=True, group="pref-load-author")
    def _load_authors(self) -> None:
        authors = self.app.bridge.authors.get_authors()
        self.app.call_from_thread(self._populate_authors, authors)

    def _populate_authors(self, authors: list[PreferredAuthor]) -> None:
        table = self.query_one("#author-table", DataTable)
        table.clear()
        for a in authors:
            added = a.added_at.strftime("%Y-%m-%d")
            table.add_row(a.name, added, key=a.name)

    # === Recommendation Weights ===

    @staticmethod
    def _make_bar(value: int, width: int = 30) -> str:
        filled = round(value * width / 100)
        return "[green]" + "\u2588" * filled + "[/green]" + "\u2591" * (width - filled)

    @work(thread=True, exclusive=True, group="pref-load-weights")
    def _load_weights(self) -> None:
        weights = self.app.bridge.settings.get_weights()
        self.app.call_from_thread(self._populate_weights, weights)

    def _populate_weights(self, weights: dict[str, int]) -> None:
        table = self.query_one("#weights-table", DataTable)
        table.clear()
        for key in WEIGHT_KEYS:
            label = _WEIGHT_LABELS[key]
            value = weights[key]
            bar = self._make_bar(value)
            table.add_row(label, f"{value:3d}%", bar, key=key)
        total = sum(weights.values())
        self.query_one("#weights-footer", Static).update(
            f"Total: [bold]{total}%[/bold]  [dim]← → to adjust · Reset button to restore defaults[/dim]"
        )

    def action_weight_decrease(self) -> None:
        """Decrease the currently focused weight by 1."""
        wt = self.query_one("#weights-table", DataTable)
        if not wt.has_focus:
            return
        self._adjust_focused_weight(-1)

    def action_weight_increase(self) -> None:
        """Increase the currently focused weight by 1."""
        wt = self.query_one("#weights-table", DataTable)
        if not wt.has_focus:
            return
        self._adjust_focused_weight(1)

    def _adjust_focused_weight(self, delta: int) -> None:
        wt = self.query_one("#weights-table", DataTable)
        if wt.cursor_row is None:
            return
        try:
            row_key, _ = wt.coordinate_to_cell_key(wt.cursor_coordinate)
        except Exception:
            return
        key = row_key.value if hasattr(row_key, "value") else str(row_key)
        if key not in WEIGHT_KEYS:
            return
        self._do_adjust_weight(key, delta)

    @work(thread=True, group="pref-weight-adjust")
    def _do_adjust_weight(self, key: str, delta: int) -> None:
        weights = self.app.bridge.settings.get_weights()
        new_value = max(0, min(100, weights[key] + delta))
        if new_value == weights[key]:
            return
        new_weights = adjust_weights(key, new_value, weights)
        self.app.bridge.settings.set_weights(new_weights)
        self.app.call_from_thread(self._populate_weights, new_weights)

    @on(Button.Pressed, "#weights-reset")
    def _on_weights_reset(self) -> None:
        self._do_reset_weights()

    @work(thread=True, group="pref-weight-reset")
    def _do_reset_weights(self) -> None:
        self.app.bridge.settings.reset_weights()
        weights = self.app.bridge.settings.get_weights()
        self.app.call_from_thread(self.app.notify, "Weights reset to defaults")
        self.app.call_from_thread(self._populate_weights, weights)
