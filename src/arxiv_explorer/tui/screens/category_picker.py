"""Category picker modal with fuzzy search and hierarchical browser modes."""

from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import DataTable, Input, Label, ListItem, ListView, Static

from ...core.arxiv_categories import ARXIV_CATEGORIES, fuzzy_search


class CategoryPickerScreen(ModalScreen[str | None]):
    """Modal to pick an arXiv category.

    Tab toggles between:
    - Fuzzy Search Mode (default): Input + DataTable of filtered results
    - Hierarchical Browser Mode: ListView of groups that expand to show categories
    """

    BINDINGS = [
        Binding("escape", "dismiss_none", "Close"),
        Binding("tab", "toggle_mode", "Toggle Mode"),
    ]

    DEFAULT_CSS = """
    CategoryPickerScreen {
        align: center middle;
    }
    CategoryPickerScreen > Vertical {
        width: 80;
        height: 30;
        background: $surface;
        border: tall $accent;
        padding: 1 2;
    }
    CategoryPickerScreen #cp-title {
        text-style: bold;
        color: $accent;
        height: 1;
        margin-bottom: 1;
    }
    CategoryPickerScreen #cp-mode-hint {
        color: $text-muted;
        height: 1;
        margin-bottom: 1;
    }
    CategoryPickerScreen #cp-search-input {
        height: 3;
        margin-bottom: 1;
    }
    CategoryPickerScreen #cp-results-table {
        height: 1fr;
    }
    CategoryPickerScreen #cp-hierarchy-view {
        height: 1fr;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._mode = "search"  # "search" or "hierarchy"
        self._all_results: list[tuple[str, str, str]] = []
        # For hierarchy mode: track which groups are expanded
        self._expanded_groups: set[str] = set()

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("Select Category", id="cp-title")
            yield Static(
                "[dim]Tab: toggle mode  ·  Enter: select  ·  Esc: cancel[/dim]", id="cp-mode-hint"
            )
            yield Input(
                placeholder="Type to search (e.g. hep-ph, machine learning)...",
                id="cp-search-input",
            )
            yield DataTable(id="cp-results-table", cursor_type="row", zebra_stripes=True)
            yield ListView(id="cp-hierarchy-view")

    def on_mount(self) -> None:
        # Set up table columns
        table = self.query_one("#cp-results-table", DataTable)
        table.add_column("Code", key="code", width=20)
        table.add_column("Name", key="name", width=42)
        table.add_column("Group", key="group", width=14)

        # Hide hierarchy view initially
        self.query_one("#cp-hierarchy-view", ListView).display = False

        # Load all results into search view
        self._update_search_results("")

        # Focus the search input
        self.query_one("#cp-search-input", Input).focus()

    def _update_search_results(self, query: str) -> None:
        results = fuzzy_search(query)
        self._all_results = results
        table = self.query_one("#cp-results-table", DataTable)
        table.clear()
        for code, name, group in results:
            table.add_row(code, name, group, key=code)

    def _build_hierarchy_view(self) -> None:
        view = self.query_one("#cp-hierarchy-view", ListView)
        view.clear()
        for group, cats in ARXIV_CATEGORIES.items():
            expanded = group in self._expanded_groups
            arrow = "v" if expanded else ">"
            view.append(ListItem(Label(f"[bold]{arrow} {group}[/bold]"), id=f"grp-{group}"))
            if expanded:
                for code, name in cats.items():
                    view.append(ListItem(Label(f"    {code}  [dim]{name}[/dim]"), id=f"cat-{code}"))

    @on(Input.Changed, "#cp-search-input")
    def _on_search_changed(self, event: Input.Changed) -> None:
        self._update_search_results(event.value)

    @on(Input.Submitted, "#cp-search-input")
    def _on_search_submitted(self) -> None:
        table = self.query_one("#cp-results-table", DataTable)
        if table.row_count == 0:
            return
        # Move focus to table so user can navigate, or directly pick first
        try:
            row_key, _ = table.coordinate_to_cell_key(table.cursor_coordinate)
            code = row_key.value if hasattr(row_key, "value") else str(row_key)
            self.dismiss(code)
        except Exception:
            pass

    @on(DataTable.RowSelected, "#cp-results-table")
    def _on_row_selected(self, event: DataTable.RowSelected) -> None:
        row_key = event.row_key
        code = row_key.value if hasattr(row_key, "value") else str(row_key)
        self.dismiss(code)

    @on(ListView.Selected, "#cp-hierarchy-view")
    def _on_list_selected(self, event: ListView.Selected) -> None:
        item_id = event.item.id
        if not item_id:
            return
        if item_id.startswith("grp-"):
            group = item_id[4:]
            if group in self._expanded_groups:
                self._expanded_groups.discard(group)
            else:
                self._expanded_groups.add(group)
            self._build_hierarchy_view()
        elif item_id.startswith("cat-"):
            code = item_id[4:]
            self.dismiss(code)

    def action_dismiss_none(self) -> None:
        self.dismiss(None)

    def action_toggle_mode(self) -> None:
        if self._mode == "search":
            self._mode = "hierarchy"
            self.query_one("#cp-search-input", Input).display = False
            self.query_one("#cp-results-table", DataTable).display = False
            self.query_one("#cp-hierarchy-view", ListView).display = True
            self._build_hierarchy_view()
            self.query_one("#cp-hierarchy-view", ListView).focus()
            self.query_one("#cp-mode-hint", Static).update(
                "[dim]Tab: toggle mode  ·  Enter: expand/select  ·  Esc: cancel[/dim]"
            )
        else:
            self._mode = "search"
            self.query_one("#cp-search-input", Input).display = True
            self.query_one("#cp-results-table", DataTable).display = True
            self.query_one("#cp-hierarchy-view", ListView).display = False
            self.query_one("#cp-search-input", Input).focus()
            self.query_one("#cp-mode-hint", Static).update(
                "[dim]Tab: toggle mode  ·  Enter: select  ·  Esc: cancel[/dim]"
            )
