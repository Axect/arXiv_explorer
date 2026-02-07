"""Notes tab."""

from __future__ import annotations

from textual import on, work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import DataTable, Label, ListItem, ListView, Static

from ...core.models import PaperNote


class NotesPane(Vertical):
    """Notes management screen.

    Left: ListView (grouped by paper)
    Right: DataTable (notes for selected paper)
    """

    DEFAULT_CSS = """
    NotesPane {
        height: 1fr;
    }
    NotesPane #notes-body {
        height: 1fr;
    }
    NotesPane #notes-left {
        width: 1fr;
        min-width: 30;
        border-right: tall $surface-lighten-1;
        padding: 0 1;
    }
    NotesPane #notes-left-title {
        text-style: bold;
        color: $accent;
        height: 1;
        margin-bottom: 1;
    }
    NotesPane #notes-list-view {
        height: 1fr;
    }
    NotesPane #notes-right {
        width: 2fr;
        padding: 0 1;
    }
    NotesPane #notes-right-title {
        text-style: bold;
        color: $accent;
        height: 1;
        margin-bottom: 1;
    }
    NotesPane #notes-detail-table {
        height: 1fr;
    }
    NotesPane #notes-right-buttons {
        dock: bottom;
        height: 3;
    }
    """

    BINDINGS = [
        ("r", "refresh", "Refresh"),
        ("delete", "delete_note", "Delete"),
    ]

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._all_notes: list[PaperNote] = []
        self._paper_groups: dict[str, list[PaperNote]] = {}
        self._current_arxiv_id: str | None = None

    def compose(self) -> ComposeResult:
        with Horizontal(id="notes-body"):
            with Vertical(id="notes-left"):
                yield Static("Notes by Paper", id="notes-left-title")
                yield ListView(id="notes-list-view")

            with Vertical(id="notes-right"):
                yield Static("Select a paper", id="notes-right-title")
                yield DataTable(id="notes-detail-table", cursor_type="row", zebra_stripes=True)

    def on_mount(self) -> None:
        table = self.query_one("#notes-detail-table", DataTable)
        table.add_column("#", key="idx", width=4)
        table.add_column("Type", key="type", width=10)
        table.add_column("Content", key="content")
        table.add_column("Date", key="date", width=12)
        self._load_notes()

    def action_refresh(self) -> None:
        self._load_notes()

    def action_delete_note(self) -> None:
        table = self.query_one("#notes-detail-table", DataTable)
        if table.cursor_row is None:
            return
        try:
            row_key, _ = table.coordinate_to_cell_key(table.cursor_coordinate)
        except Exception:
            return
        key_str = row_key.value if hasattr(row_key, "value") else str(row_key)
        note_id = int(key_str)
        self._do_delete_note(note_id)

    @on(ListView.Selected, "#notes-list-view")
    def _on_paper_selected(self, event: ListView.Selected) -> None:
        item_id = event.item.id
        if not item_id or not item_id.startswith("np-"):
            return
        arxiv_id = item_id[3:].replace("_", ".")
        self._current_arxiv_id = arxiv_id
        self._show_notes_for_paper(arxiv_id)

    # === Data ===

    @work(thread=True, exclusive=True, group="notes-load")
    def _load_notes(self) -> None:
        notes = self.app.bridge.notes.get_notes()
        self.app.call_from_thread(self._populate_notes, notes)

    def _populate_notes(self, notes: list[PaperNote]) -> None:
        self._all_notes = notes
        # Group by paper
        self._paper_groups = {}
        for n in notes:
            self._paper_groups.setdefault(n.arxiv_id, []).append(n)

        view = self.query_one("#notes-list-view", ListView)
        view.clear()

        if not self._paper_groups:
            view.append(ListItem(Label("[dim]No notes[/dim]")))
            return

        for arxiv_id, group in self._paper_groups.items():
            safe_id = arxiv_id.replace(".", "_")
            view.append(
                ListItem(
                    Label(f"{arxiv_id} ({len(group)})"),
                    id=f"np-{safe_id}",
                )
            )

    def _show_notes_for_paper(self, arxiv_id: str) -> None:
        notes = self._paper_groups.get(arxiv_id, [])
        self.query_one("#notes-right-title", Static).update(f"{arxiv_id} — {len(notes)} note(s)")
        table = self.query_one("#notes-detail-table", DataTable)
        table.clear()
        for i, n in enumerate(notes, 1):
            content = n.content[:60] + "..." if len(n.content) > 60 else n.content
            date = n.created_at.strftime("%Y-%m-%d")
            table.add_row(str(i), n.note_type.value, content, date, key=str(n.id))

    @work(thread=True, group="notes-delete")
    def _do_delete_note(self, note_id: int) -> None:
        ok = self.app.bridge.notes.delete_note(note_id)
        if ok:
            self.app.call_from_thread(self.app.notify, "Note deleted")
            self._load_notes()
        else:
            self.app.call_from_thread(self.app.notify, "Delete failed", severity="warning")
