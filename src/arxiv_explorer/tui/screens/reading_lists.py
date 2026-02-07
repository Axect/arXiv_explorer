"""Reading lists tab."""

from __future__ import annotations

from textual import on, work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Static, ListView, ListItem, Label, DataTable, Button, Select

from ...core.models import ReadingList, ReadingListPaper, ReadingStatus


class ReadingListsPane(Vertical):
    """Reading list management screen.

    Left: ListView (list of lists) + create/delete buttons
    Right: DataTable (papers in selected list) + status change
    """

    DEFAULT_CSS = """
    ReadingListsPane {
        height: 1fr;
    }
    ReadingListsPane #rl-body {
        height: 1fr;
    }
    ReadingListsPane #rl-left {
        width: 1fr;
        min-width: 30;
        border-right: tall $surface-lighten-1;
        padding: 0 1;
    }
    ReadingListsPane #rl-left-title {
        text-style: bold;
        color: $accent;
        height: 1;
        margin-bottom: 1;
    }
    ReadingListsPane #rl-list-view {
        height: 1fr;
    }
    ReadingListsPane #rl-left-buttons {
        dock: bottom;
        height: 3;
        padding: 0;
    }
    ReadingListsPane #rl-left-buttons Button {
        min-width: 10;
        margin-right: 1;
    }
    ReadingListsPane #rl-right {
        width: 2fr;
        padding: 0 1;
    }
    ReadingListsPane #rl-right-title {
        text-style: bold;
        color: $accent;
        height: 1;
        margin-bottom: 1;
    }
    ReadingListsPane #rl-papers-table {
        height: 1fr;
    }
    ReadingListsPane #rl-paper-actions {
        dock: bottom;
        height: 3;
        padding: 0;
    }
    ReadingListsPane #rl-paper-actions Button {
        min-width: 10;
        margin-right: 1;
    }
    ReadingListsPane #rl-paper-actions Select {
        width: 16;
        margin-right: 1;
    }
    """

    BINDINGS = [
        ("r", "refresh", "Refresh"),
        ("c", "create_list", "New List"),
        ("delete", "delete_item", "Delete"),
    ]

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._current_list: ReadingList | None = None
        self._lists: list[ReadingList] = []
        self._papers: list[ReadingListPaper] = []

    def compose(self) -> ComposeResult:
        with Horizontal(id="rl-body"):
            with Vertical(id="rl-left"):
                yield Static("Reading Lists", id="rl-left-title")
                yield ListView(id="rl-list-view")
                with Horizontal(id="rl-left-buttons"):
                    yield Button("+ Create [c]", id="rl-create", variant="primary")
                    yield Button("Delete", id="rl-delete", variant="error")

            with Vertical(id="rl-right"):
                yield Static("Select a list", id="rl-right-title")
                yield DataTable(id="rl-papers-table", cursor_type="row", zebra_stripes=True)
                with Horizontal(id="rl-paper-actions"):
                    yield Select(
                        [(s.value, s) for s in ReadingStatus],
                        value=ReadingStatus.UNREAD,
                        id="rl-status-select",
                        prompt="Status",
                    )
                    yield Button("Change Status", id="rl-status-btn")
                    yield Button("Remove Paper", id="rl-remove-paper", variant="error")

    def on_mount(self) -> None:
        table = self.query_one("#rl-papers-table", DataTable)
        table.add_column("#", key="idx", width=4)
        table.add_column("arXiv ID", key="arxiv_id", width=18)
        table.add_column("Status", key="status", width=10)
        table.add_column("Added", key="added", width=12)
        self._load_lists()

    def action_refresh(self) -> None:
        self._load_lists()

    def action_create_list(self) -> None:
        from .list_create import ListCreateScreen
        def on_dismiss(result) -> None:
            if result:
                self._load_lists()
        self.app.push_screen(ListCreateScreen(), callback=on_dismiss)

    def action_delete_item(self) -> None:
        if self._current_list:
            self._do_delete_list(self._current_list.name)

    @on(Button.Pressed, "#rl-create")
    def _on_create_clicked(self) -> None:
        self.action_create_list()

    @on(Button.Pressed, "#rl-delete")
    def _on_delete_clicked(self) -> None:
        self.action_delete_item()

    @on(Button.Pressed, "#rl-status-btn")
    def _on_status_clicked(self) -> None:
        self._change_status()

    @on(Button.Pressed, "#rl-remove-paper")
    def _on_remove_paper_clicked(self) -> None:
        self._remove_current_paper()

    @on(ListView.Selected, "#rl-list-view")
    def _on_list_selected(self, event: ListView.Selected) -> None:
        item_id = event.item.id
        if not item_id or not item_id.startswith("rll-"):
            return
        idx = int(item_id[4:])
        if 0 <= idx < len(self._lists):
            self._current_list = self._lists[idx]
            self._load_papers()

    # === Data loading ===

    @work(thread=True, exclusive=True, group="rl-load-lists")
    def _load_lists(self) -> None:
        lists = self.app.bridge.reading_lists.get_all_lists()
        self.app.call_from_thread(self._populate_lists, lists)

    def _populate_lists(self, lists: list[ReadingList]) -> None:
        self._lists = lists
        view = self.query_one("#rl-list-view", ListView)
        view.clear()
        for i, rl in enumerate(lists):
            desc = f" ({rl.description})" if rl.description else ""
            view.append(
                ListItem(Label(f"{rl.name}{desc}"), id=f"rll-{i}")
            )
        if not lists:
            self.query_one("#rl-right-title", Static).update("No lists — press [c] to create")

    @work(thread=True, exclusive=True, group="rl-load-papers")
    def _load_papers(self) -> None:
        if not self._current_list:
            return
        papers = self.app.bridge.reading_lists.get_papers(self._current_list.name)
        self.app.call_from_thread(self._populate_papers, papers)

    def _populate_papers(self, papers: list[ReadingListPaper]) -> None:
        self._papers = papers
        self.query_one("#rl-right-title", Static).update(
            f"{self._current_list.name} — {len(papers)} paper(s)"
        )
        table = self.query_one("#rl-papers-table", DataTable)
        table.clear()
        for i, p in enumerate(papers, 1):
            added = p.added_at.strftime("%Y-%m-%d")
            table.add_row(str(i), p.arxiv_id, p.status.value, added, key=str(p.id))

    # === Actions ===

    @work(thread=True, group="rl-delete")
    def _do_delete_list(self, name: str) -> None:
        ok = self.app.bridge.reading_lists.delete_list(name)
        if ok:
            self.app.call_from_thread(self.app.notify, f"Deleted: {name}")
            self._current_list = None
            self._load_lists()
        else:
            self.app.call_from_thread(
                self.app.notify, "Delete failed", severity="warning"
            )

    def _change_status(self) -> None:
        if not self._current_list or not self._papers:
            return
        table = self.query_one("#rl-papers-table", DataTable)
        if table.cursor_row is None:
            return
        try:
            row_key, _ = table.coordinate_to_cell_key(table.cursor_coordinate)
        except Exception:
            return
        key_str = row_key.value if hasattr(row_key, "value") else str(row_key)
        paper_id = int(key_str)
        paper = next((p for p in self._papers if p.id == paper_id), None)
        if not paper:
            return

        status_select = self.query_one("#rl-status-select", Select)
        status = status_select.value if status_select.value != Select.BLANK else ReadingStatus.UNREAD
        self._do_change_status(paper.arxiv_id, status)

    @work(thread=True, group="rl-status")
    def _do_change_status(self, arxiv_id: str, status: ReadingStatus) -> None:
        self.app.bridge.reading_lists.update_status(arxiv_id, status)
        self.app.call_from_thread(
            self.app.notify, f"{arxiv_id} → {status.value}"
        )
        self._load_papers()

    def _remove_current_paper(self) -> None:
        if not self._current_list or not self._papers:
            return
        table = self.query_one("#rl-papers-table", DataTable)
        if table.cursor_row is None:
            return
        try:
            row_key, _ = table.coordinate_to_cell_key(table.cursor_coordinate)
        except Exception:
            return
        key_str = row_key.value if hasattr(row_key, "value") else str(row_key)
        paper_id = int(key_str)
        paper = next((p for p in self._papers if p.id == paper_id), None)
        if paper:
            self._do_remove_paper(paper.arxiv_id)

    @work(thread=True, group="rl-remove")
    def _do_remove_paper(self, arxiv_id: str) -> None:
        self.app.bridge.reading_lists.remove_paper(self._current_list.name, arxiv_id)
        self.app.call_from_thread(self.app.notify, f"Removed: {arxiv_id}")
        self._load_papers()
