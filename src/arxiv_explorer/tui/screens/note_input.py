"""Note input modal."""

from __future__ import annotations

from textual import on, work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Select, Static

from ...core.models import NoteType


class NoteInputScreen(ModalScreen):
    """Note input modal — type selection + content entry."""

    BINDINGS = [("escape", "dismiss", "Close")]

    def __init__(self, arxiv_id: str) -> None:
        super().__init__()
        self.arxiv_id = arxiv_id

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(f"Add Note — {self.arxiv_id}", classes="modal-title")
            yield Select(
                [(t.value, t) for t in NoteType],
                value=NoteType.GENERAL,
                id="note-type",
                prompt="Note Type",
            )
            yield Input(placeholder="Enter note content...", id="note-content")
            with Horizontal(classes="modal-buttons"):
                yield Button("Save", id="note-save", variant="primary")
                yield Button("Cancel", id="note-cancel")

    @on(Button.Pressed, "#note-cancel")
    def _on_cancel(self) -> None:
        self.dismiss()

    @on(Button.Pressed, "#note-save")
    def _on_save(self) -> None:
        self._save_note()

    @on(Input.Submitted, "#note-content")
    def _on_submitted(self) -> None:
        self._save_note()

    def _save_note(self) -> None:
        content = self.query_one("#note-content", Input).value.strip()
        if not content:
            self.app.notify("Please enter content", severity="warning")
            return

        note_type_select = self.query_one("#note-type", Select)
        note_type = (
            note_type_select.value if note_type_select.value != Select.BLANK else NoteType.GENERAL
        )
        self._do_save(content, note_type)

    @work(thread=True, group="note-save")
    def _do_save(self, content: str, note_type: NoteType) -> None:
        self.app.bridge.notes.add_note(
            arxiv_id=self.arxiv_id,
            content=content,
            note_type=note_type,
        )
        self.app.call_from_thread(self.app.notify, f"Note saved: {self.arxiv_id}")
        self.app.call_from_thread(self.dismiss)
