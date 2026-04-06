"""Folder/list picker modal for move/copy operations."""

from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label, ListItem, ListView, Static

from ...core.models import ReadingList


class FolderPickerScreen(ModalScreen):
    """Select a target folder or list for move/copy operations.

    Dismisses with the selected ReadingList ID, or None if cancelled.
    """

    BINDINGS = [("escape", "dismiss", "Cancel")]

    DEFAULT_CSS = """
    FolderPickerScreen {
        align: center middle;
    }
    FolderPickerScreen > Vertical {
        width: 60;
        height: auto;
        max-height: 30;
        background: $surface;
        border: tall $accent;
        padding: 1 2;
    }
    FolderPickerScreen .modal-title {
        text-style: bold;
        color: $accent;
        height: 1;
        margin-bottom: 1;
    }
    FolderPickerScreen ListView {
        height: auto;
        max-height: 20;
        border: tall $surface-lighten-2;
    }
    FolderPickerScreen .modal-buttons {
        height: 3;
        margin-top: 1;
    }
    FolderPickerScreen .modal-buttons Button {
        margin-right: 1;
    }
    """

    def __init__(self, items: list[ReadingList], title: str = "Select destination") -> None:
        super().__init__()
        self._items = items
        self._title = title

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(self._title, classes="modal-title")
            yield ListView(id="fp-list-view")
            with Horizontal(classes="modal-buttons"):
                yield Button("Cancel", id="fp-cancel")

    def on_mount(self) -> None:
        view = self.query_one("#fp-list-view", ListView)
        if not self._items:
            view.append(ListItem(Label("[dim]No destinations available[/dim]")))
            return
        for i, item in enumerate(self._items):
            icon = "📁" if item.is_folder else "📋"
            view.append(ListItem(Label(f"{icon} {item.name}"), id=f"fp-{i}"))

    @on(ListView.Selected, "#fp-list-view")
    def _on_selected(self, event: ListView.Selected) -> None:
        item_id = event.item.id
        if not item_id or not item_id.startswith("fp-"):
            return
        idx = int(item_id[3:])
        if 0 <= idx < len(self._items):
            self.dismiss(self._items[idx].id)

    @on(Button.Pressed, "#fp-cancel")
    def _on_cancel(self) -> None:
        self.dismiss(None)
