"""Reading list picker modal."""

from __future__ import annotations

from textual import on, work
from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Static, ListView, ListItem, Label, Button


class ListPickerScreen(ModalScreen):
    """Select from existing reading lists to add a paper."""

    BINDINGS = [("escape", "dismiss", "Close")]

    def __init__(self, arxiv_id: str) -> None:
        super().__init__()
        self.arxiv_id = arxiv_id
        self._lists: list = []

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(f"Add to List — {self.arxiv_id}", classes="modal-title")
            yield ListView(id="list-picker-view")
            with Horizontal(classes="modal-buttons"):
                yield Button("Cancel", id="lp-cancel")

    def on_mount(self) -> None:
        self._load_lists()

    @work(thread=True, group="lp-load")
    def _load_lists(self) -> None:
        lists = self.app.bridge.reading_lists.get_all_lists()
        self.app.call_from_thread(self._populate_lists, lists)

    def _populate_lists(self, lists) -> None:
        view = self.query_one("#list-picker-view", ListView)
        view.clear()
        if not lists:
            view.append(ListItem(Label("[dim]No reading lists[/dim]")))
            return

        self._lists = lists
        for i, rl in enumerate(lists):
            desc = f" — {rl.description}" if rl.description else ""
            view.append(
                ListItem(Label(f"{rl.name}{desc}"), id=f"lp-{i}")
            )

    @on(ListView.Selected, "#list-picker-view")
    def _on_list_selected(self, event: ListView.Selected) -> None:
        item_id = event.item.id
        if not item_id or not item_id.startswith("lp-"):
            return
        idx = int(item_id[3:])
        if 0 <= idx < len(self._lists):
            self._do_add(self._lists[idx].name)

    @on(Button.Pressed, "#lp-cancel")
    def _on_cancel(self) -> None:
        self.dismiss()

    @work(thread=True, group="lp-add")
    def _do_add(self, list_name: str) -> None:
        ok = self.app.bridge.reading_lists.add_paper(list_name, self.arxiv_id)
        if ok:
            self.app.call_from_thread(
                self.app.notify,
                f"Added {self.arxiv_id} to '{list_name}'",
            )
        else:
            self.app.call_from_thread(
                self.app.notify, "Add failed", severity="warning"
            )
        self.app.call_from_thread(self.dismiss)
