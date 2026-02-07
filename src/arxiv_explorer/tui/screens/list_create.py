"""Reading list creation modal."""

from __future__ import annotations

from textual import on, work
from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Static, Input, Button


class ListCreateScreen(ModalScreen):
    """New reading list creation modal."""

    BINDINGS = [("escape", "dismiss", "Close")]

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("New Reading List", classes="modal-title")
            yield Input(placeholder="List name", id="list-name")
            yield Input(placeholder="Description (optional)", id="list-desc")
            with Horizontal(classes="modal-buttons"):
                yield Button("Create", id="list-create-btn", variant="primary")
                yield Button("Cancel", id="list-cancel-btn")

    @on(Button.Pressed, "#list-cancel-btn")
    def _on_cancel(self) -> None:
        self.dismiss()

    @on(Button.Pressed, "#list-create-btn")
    def _on_create(self) -> None:
        self._create_list()

    @on(Input.Submitted, "#list-name")
    def _on_name_submitted(self) -> None:
        self.query_one("#list-desc", Input).focus()

    @on(Input.Submitted, "#list-desc")
    def _on_desc_submitted(self) -> None:
        self._create_list()

    def _create_list(self) -> None:
        name = self.query_one("#list-name", Input).value.strip()
        if not name:
            self.app.notify("Please enter a name", severity="warning")
            return

        desc = self.query_one("#list-desc", Input).value.strip() or None
        self._do_create(name, desc)

    @work(thread=True, group="list-create")
    def _do_create(self, name: str, desc: str | None) -> None:
        try:
            self.app.bridge.reading_lists.create_list(name=name, description=desc)
            self.app.call_from_thread(self.app.notify, f"List created: {name}")
            self.app.call_from_thread(self.dismiss, True)  # True = creation success result
        except Exception as e:
            self.app.call_from_thread(
                self.app.notify, f"Creation failed: {e}", severity="error"
            )
