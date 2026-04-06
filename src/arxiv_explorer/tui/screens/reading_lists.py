"""Reading lists tab with tree-view hierarchy."""

from __future__ import annotations

from textual import on, work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import DataTable, Label, ListItem, ListView, Static

from ...core.models import ReadingList, ReadingListPaper


class ReadingListsPane(Vertical):
    """Reading list management screen.

    Left: Tree-like ListView showing system lists pinned at top,
          then a separator, then user folders/lists.
    Right: DataTable with columns: #, arXiv ID, Title, Added, Status
           Default sort: most recent added_at first; `s` toggles order.
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
    ReadingListsPane #rl-left-hints {
        dock: bottom;
        height: 1;
        padding: 0 1;
        color: $text-muted;
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
    ReadingListsPane #rl-paper-hints {
        dock: bottom;
        height: 1;
        padding: 0 1;
        color: $text-muted;
    }
    """

    BINDINGS = [
        ("r", "refresh", "Refresh"),
        ("f", "create_folder", "New Folder"),
        ("n", "create_list", "New List"),
        ("m", "move_item", "Move"),
        ("c", "copy_item", "Copy"),
        ("delete", "delete_item", "Delete"),
        ("s", "toggle_sort", "Toggle Sort"),
        ("e", "rename_item", "Rename"),
    ]

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._current_list: ReadingList | None = None
        # All lists displayed in the left panel (maps index → ReadingList)
        self._items: list[ReadingList] = []
        # Papers in the currently selected list
        self._papers: list[ReadingListPaper] = []
        # Sort newest-first by default
        self._sort_newest_first: bool = True

    # =========================================================================
    # Compose / Mount
    # =========================================================================

    def compose(self) -> ComposeResult:
        with Horizontal(id="rl-body"):
            with Vertical(id="rl-left"):
                yield Static("Reading Lists", id="rl-left-title")
                yield ListView(id="rl-list-view")
                yield Static(
                    "[dim][n] New List  [f] Folder  [Del] Delete  [e] Rename[/dim]",
                    id="rl-left-hints",
                )

            with Vertical(id="rl-right"):
                yield Static("Select a list", id="rl-right-title")
                yield DataTable(id="rl-papers-table", cursor_type="row", zebra_stripes=True)
                yield Static(
                    "[dim][Del] Remove  [s] Toggle Sort  [m] Move  [c] Copy[/dim]",
                    id="rl-paper-hints",
                )

    def on_mount(self) -> None:
        table = self.query_one("#rl-papers-table", DataTable)
        table.add_column("#", key="idx", width=4)
        table.add_column("arXiv ID", key="arxiv_id", width=18)
        table.add_column("Title", key="title")
        table.add_column("Added", key="added", width=12)
        table.add_column("Status", key="status", width=10)
        self._load_lists()

    # =========================================================================
    # Left panel population
    # =========================================================================

    @work(thread=True, exclusive=True, group="rl-load-lists")
    def _load_lists(self) -> None:
        items = self.app.bridge.reading_lists.get_top_level()
        self.app.call_from_thread(self._populate_lists, items)

    def _populate_lists(self, items: list[ReadingList]) -> None:
        """Build a flat list for the ListView:
        system lists first, then a separator label, then user items.
        """
        self._items = []
        view = self.query_one("#rl-list-view", ListView)
        view.clear()

        system_items = [it for it in items if it.is_system]
        user_items = [it for it in items if not it.is_system]

        # System lists (pinned at top)
        for it in system_items:
            icon = "📁" if it.is_folder else "📋"
            count = self._paper_count(it.id)
            label = f"{icon} {it.name} ({count})"
            idx = len(self._items)
            self._items.append(it)
            view.append(ListItem(Label(label), id=f"rll-{idx}"))

        # Separator (non-selectable)
        if system_items and user_items:
            view.append(ListItem(Label("───────────────────"), id="rll-sep"))

        # User folders and lists
        for it in user_items:
            icon = "📁" if it.is_folder else "📋"
            count = self._paper_count(it.id)
            label = f"{icon} {it.name} ({count})"
            idx = len(self._items)
            self._items.append(it)
            view.append(ListItem(Label(label), id=f"rll-{idx}"))

        if not items:
            self.query_one("#rl-right-title", Static).update(
                "No lists — press [n] to create or [f] for a folder"
            )

    def _paper_count(self, list_id: int) -> int:
        """Synchronously get paper count; safe to call from main thread (on mount only
        from worker). Called during populate which runs in the main thread after worker
        finishes — but the worker already fetched the list items, so we do a quick
        in-line count here.  Falls back to 0 on any error."""
        try:
            papers = self.app.bridge.reading_lists.get_papers_by_list_id(list_id)
            return len(papers)
        except Exception:
            return 0

    # =========================================================================
    # Right panel population
    # =========================================================================

    @work(thread=True, exclusive=True, group="rl-load-papers")
    def _load_papers(self) -> None:
        if not self._current_list:
            return
        papers = self.app.bridge.reading_lists.get_papers_by_list_id(self._current_list.id)
        self.app.call_from_thread(self._populate_papers, papers)

    def _sorted_papers(self, papers: list[ReadingListPaper]) -> list[ReadingListPaper]:
        return sorted(papers, key=lambda p: p.added_at, reverse=self._sort_newest_first)

    def _populate_papers(self, papers: list[ReadingListPaper]) -> None:
        self._papers = papers
        assert self._current_list is not None
        sort_label = "newest first" if self._sort_newest_first else "oldest first"
        self.query_one("#rl-right-title", Static).update(
            f"{self._current_list.name} — {len(papers)} paper(s) [{sort_label}] (s=toggle)"
        )
        table = self.query_one("#rl-papers-table", DataTable)
        table.clear()
        for i, p in enumerate(self._sorted_papers(papers), 1):
            added = p.added_at.strftime("%Y-%m-%d")
            table.add_row(str(i), p.arxiv_id, "", added, p.status.value, key=str(p.id))

    # =========================================================================
    # Event handlers
    # =========================================================================

    @on(ListView.Selected, "#rl-list-view")
    def _on_list_selected(self, event: ListView.Selected) -> None:
        item_id = event.item.id
        if not item_id or not item_id.startswith("rll-") or item_id == "rll-sep":
            return
        idx = int(item_id[4:])
        if 0 <= idx < len(self._items):
            selected = self._items[idx]
            # Folders are containers — don't load papers for folders
            if selected.is_folder:
                self._current_list = selected
                self.query_one("#rl-right-title", Static).update(
                    f"📁 {selected.name} — select a list inside this folder"
                )
                table = self.query_one("#rl-papers-table", DataTable)
                table.clear()
                self._papers = []
            else:
                self._current_list = selected
                self._load_papers()

    # =========================================================================
    # Actions
    # =========================================================================

    def action_refresh(self) -> None:
        self._load_lists()

    def action_create_list(self) -> None:
        from .list_create import ListCreateScreen

        def on_dismiss(result) -> None:
            if result:
                self._load_lists()

        self.app.push_screen(ListCreateScreen(), callback=on_dismiss)

    def action_create_folder(self) -> None:
        self._prompt_create_folder()

    def _prompt_create_folder(self) -> None:
        """Show inline prompt modal to get folder name."""
        from .folder_name_input import FolderNameInputScreen

        def on_dismiss(name: str | None) -> None:
            if name:
                self._do_create_folder(name)

        self.app.push_screen(FolderNameInputScreen(title="New Folder"), callback=on_dismiss)

    @work(thread=True, group="rl-folder-create")
    def _do_create_folder(self, name: str) -> None:
        try:
            self.app.bridge.reading_lists.create_folder(name)
            self.app.call_from_thread(self.app.notify, f"Folder created: {name}")
            self._load_lists()
        except Exception as e:
            self.app.call_from_thread(
                self.app.notify, f"Failed to create folder: {e}", severity="error"
            )

    def action_rename_item(self) -> None:
        if not self._current_list:
            return
        if self._current_list.is_system:
            self.app.notify("Cannot rename system lists", severity="warning")
            return
        self._prompt_rename(self._current_list)

    def _prompt_rename(self, item: ReadingList) -> None:
        from .folder_name_input import FolderNameInputScreen

        def on_dismiss(name: str | None) -> None:
            if name:
                self._do_rename(item.id, name)

        self.app.push_screen(
            FolderNameInputScreen(title=f"Rename '{item.name}'", initial=item.name),
            callback=on_dismiss,
        )

    @work(thread=True, group="rl-rename")
    def _do_rename(self, list_id: int, new_name: str) -> None:
        ok = self.app.bridge.reading_lists.rename_item(list_id, new_name)
        if ok:
            self.app.call_from_thread(self.app.notify, f"Renamed to: {new_name}")
            self._load_lists()
        else:
            self.app.call_from_thread(
                self.app.notify, "Rename failed (system list?)", severity="warning"
            )

    def action_delete_item(self) -> None:
        if not self._current_list:
            return
        if self._current_list.is_system:
            self.app.notify("Cannot delete system lists", severity="warning")
            return
        self._do_delete_list(self._current_list.name)

    @work(thread=True, group="rl-delete")
    def _do_delete_list(self, name: str) -> None:
        ok = self.app.bridge.reading_lists.delete_list(name)
        if ok:
            self.app.call_from_thread(self.app.notify, f"Deleted: {name}")
            self.app.call_from_thread(self._clear_right_panel)
            self._current_list = None
            self._load_lists()
        else:
            self.app.call_from_thread(
                self.app.notify, "Delete failed (system list?)", severity="warning"
            )

    def _clear_right_panel(self) -> None:
        self.query_one("#rl-right-title", Static).update("Select a list")
        self.query_one("#rl-papers-table", DataTable).clear()
        self._papers = []

    def action_toggle_sort(self) -> None:
        self._sort_newest_first = not self._sort_newest_first
        if self._papers:
            self._populate_papers(self._papers)

    def action_move_item(self) -> None:
        """Move the selected list/folder into another folder."""
        if not self._current_list:
            return
        self._open_folder_picker_for_move(self._current_list)

    def _open_folder_picker_for_move(self, item: ReadingList) -> None:
        from .folder_picker import FolderPickerScreen

        # Only offer non-system folders as targets (exclude self)
        targets = [
            it for it in self._items if it.is_folder and not it.is_system and it.id != item.id
        ]

        def on_dismiss(target_id: int | None) -> None:
            if target_id is not None:
                self._do_move_list(item.id, target_id)

        self.app.push_screen(
            FolderPickerScreen(targets, title=f"Move '{item.name}' to…"),
            callback=on_dismiss,
        )

    @work(thread=True, group="rl-move")
    def _do_move_list(self, list_id: int, target_folder_id: int) -> None:
        ok = self.app.bridge.reading_lists.move_list(list_id, target_folder_id)
        if ok:
            self.app.call_from_thread(self.app.notify, "Moved successfully")
            self._load_lists()
        else:
            self.app.call_from_thread(self.app.notify, "Move failed", severity="warning")

    def action_copy_item(self) -> None:
        """Copy the selected list/folder into another folder."""
        if not self._current_list:
            return
        self._open_folder_picker_for_copy(self._current_list)

    def _open_folder_picker_for_copy(self, item: ReadingList) -> None:
        from .folder_picker import FolderPickerScreen

        targets = [
            it for it in self._items if it.is_folder and not it.is_system and it.id != item.id
        ]

        def on_dismiss(target_id: int | None) -> None:
            if target_id is not None:
                self._do_copy_list(item.id, target_id)

        self.app.push_screen(
            FolderPickerScreen(targets, title=f"Copy '{item.name}' to…"),
            callback=on_dismiss,
        )

    @work(thread=True, group="rl-copy")
    def _do_copy_list(self, list_id: int, target_folder_id: int) -> None:
        result = self.app.bridge.reading_lists.copy_list(list_id, target_folder_id)
        if result:
            self.app.call_from_thread(self.app.notify, f"Copied as '{result.name}'")
            self._load_lists()
        else:
            self.app.call_from_thread(self.app.notify, "Copy failed", severity="warning")

    # =========================================================================
    # Paper removal
    # =========================================================================

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
        if not self._current_list:
            return
        self.app.bridge.reading_lists.remove_paper_from_list(self._current_list.id, arxiv_id)
        self.app.call_from_thread(self.app.notify, f"Removed: {arxiv_id}")
        self._load_papers()
