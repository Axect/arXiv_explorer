"""Simple name input modal for folder/rename operations."""

from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Static


class FolderNameInputScreen(ModalScreen):
    """Single-field text input modal.

    Dismisses with the entered name string, or None if cancelled.
    """

    BINDINGS = [("escape", "dismiss", "Cancel")]

    DEFAULT_CSS = """
    FolderNameInputScreen {
        align: center middle;
    }
    FolderNameInputScreen > Vertical {
        width: 50;
        height: auto;
        background: $surface;
        border: tall $accent;
        padding: 1 2;
    }
    FolderNameInputScreen .modal-title {
        text-style: bold;
        color: $accent;
        height: 1;
        margin-bottom: 1;
    }
    FolderNameInputScreen .modal-buttons {
        height: 3;
        margin-top: 1;
    }
    FolderNameInputScreen .modal-buttons Button {
        margin-right: 1;
    }
    """

    def __init__(self, title: str = "Enter name", initial: str = "") -> None:
        super().__init__()
        self._title = title
        self._initial = initial

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(self._title, classes="modal-title")
            yield Input(value=self._initial, placeholder="Name…", id="fni-input")
            with Horizontal(classes="modal-buttons"):
                yield Button("OK", id="fni-ok", variant="primary")
                yield Button("Cancel", id="fni-cancel")

    def on_mount(self) -> None:
        inp = self.query_one("#fni-input", Input)
        inp.focus()
        # Move cursor to end of pre-filled text
        inp.cursor_position = len(self._initial)

    @on(Input.Submitted, "#fni-input")
    def _on_submitted(self) -> None:
        self._confirm()

    @on(Button.Pressed, "#fni-ok")
    def _on_ok(self) -> None:
        self._confirm()

    @on(Button.Pressed, "#fni-cancel")
    def _on_cancel(self) -> None:
        self.dismiss(None)

    def action_dismiss(self) -> None:  # type: ignore[override]
        self.dismiss(None)

    def _confirm(self) -> None:
        name = self.query_one("#fni-input", Input).value.strip()
        if not name:
            self.app.notify("Please enter a name", severity="warning")
            return
        self.dismiss(name)
