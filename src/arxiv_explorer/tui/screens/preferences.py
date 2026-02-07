"""Preferences tab."""

from __future__ import annotations

from textual import on, work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, DataTable, Input, Select, Static

from ...core.models import AIProviderType, KeywordInterest, Language, PreferredCategory
from ...services.providers import get_provider


class PreferencesPane(Vertical):
    """User preferences management screen.

    Left: Category DataTable + add/delete
    Right: Keyword DataTable + add/delete
    """

    DEFAULT_CSS = """
    PreferencesPane {
        height: 1fr;
    }
    PreferencesPane #prefs-body {
        height: 1fr;
    }
    PreferencesPane .pref-section {
        width: 1fr;
        padding: 0 1;
    }
    PreferencesPane .pref-section:first-child {
        border-right: tall $surface-lighten-1;
    }
    PreferencesPane .pref-section-title {
        text-style: bold;
        color: $accent;
        height: 1;
        margin-bottom: 1;
    }
    PreferencesPane DataTable {
        height: 1fr;
    }
    PreferencesPane .pref-input-row {
        height: 3;
        dock: bottom;
        padding: 0;
    }
    PreferencesPane .pref-input-row Input {
        width: 1fr;
        margin-right: 1;
    }
    PreferencesPane .pref-input-row Button {
        min-width: 8;
        margin-right: 1;
    }
    PreferencesPane #ai-config-section {
        height: auto;
        max-height: 8;
        dock: bottom;
        padding: 0 1;
    }
    PreferencesPane #ai-config-title {
        text-style: bold;
        color: $accent;
        height: 1;
    }
    PreferencesPane #ai-config-status {
        height: 1;
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
        margin-right: 2;
    }
    """

    BINDINGS = [
        ("r", "refresh", "Refresh"),
        ("delete", "delete_selected", "Delete"),
    ]

    def compose(self) -> ComposeResult:
        with Horizontal(id="prefs-body"):
            # Category section
            with Vertical(classes="pref-section"):
                yield Static("Categories", classes="pref-section-title")
                yield DataTable(id="cat-table", cursor_type="row", zebra_stripes=True)
                with Horizontal(classes="pref-input-row"):
                    yield Input(placeholder="Category (e.g. cs.AI)", id="cat-input")
                    yield Input(
                        placeholder="Priority", id="cat-priority", type="integer", value="1"
                    )
                    yield Button("+", id="cat-add", variant="primary")
                    yield Button("Del", id="cat-del", variant="error")

            # Keyword section
            with Vertical(classes="pref-section"):
                yield Static("Keywords", classes="pref-section-title")
                yield DataTable(id="kw-table", cursor_type="row", zebra_stripes=True)
                with Horizontal(classes="pref-input-row"):
                    yield Input(placeholder="Keyword", id="kw-input")
                    yield Input(placeholder="Weight", id="kw-weight", value="1.0")
                    yield Button("+", id="kw-add", variant="primary")
                    yield Button("Del", id="kw-del", variant="error")

        # AI Config section
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

        self._load_all()
        self._load_ai_provider()

    def action_refresh(self) -> None:
        self._load_all()
        self._load_ai_provider()

    def action_delete_selected(self) -> None:
        # Delete based on focused table
        cat_table = self.query_one("#cat-table", DataTable)
        kw_table = self.query_one("#kw-table", DataTable)
        if cat_table.has_focus:
            self._delete_category()
        elif kw_table.has_focus:
            self._delete_keyword()

    # === Categories ===

    @on(Button.Pressed, "#cat-add")
    def _on_cat_add(self) -> None:
        self._add_category()

    @on(Button.Pressed, "#cat-del")
    def _on_cat_del(self) -> None:
        self._delete_category()

    @on(Input.Submitted, "#cat-input")
    def _on_cat_submitted(self) -> None:
        self._add_category()

    def _add_category(self) -> None:
        cat = self.query_one("#cat-input", Input).value.strip()
        if not cat:
            self.app.notify("Please enter a category", severity="warning")
            return
        pri_str = self.query_one("#cat-priority", Input).value.strip()
        try:
            priority = int(pri_str) if pri_str else 1
        except ValueError:
            priority = 1
        self._do_add_category(cat, priority)

    @work(thread=True, group="pref-cat-add")
    def _do_add_category(self, category: str, priority: int) -> None:
        self.app.bridge.preferences.add_category(category, priority)
        self.app.call_from_thread(self.app.notify, f"Added: {category}")
        self.app.call_from_thread(self.query_one("#cat-input", Input).clear)
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

    @on(Button.Pressed, "#kw-add")
    def _on_kw_add(self) -> None:
        self._add_keyword()

    @on(Button.Pressed, "#kw-del")
    def _on_kw_del(self) -> None:
        self._delete_keyword()

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
            weight = float(weight_str) if weight_str else 1.0
        except ValueError:
            weight = 1.0
        self._do_add_keyword(kw, weight)

    @work(thread=True, group="pref-kw-add")
    def _do_add_keyword(self, keyword: str, weight: float) -> None:
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

    def _populate_keywords(self, keywords: list[KeywordInterest]) -> None:
        table = self.query_one("#kw-table", DataTable)
        table.clear()
        for k in keywords:
            table.add_row(k.keyword, f"{k.weight:.1f}", k.source, key=k.keyword)
