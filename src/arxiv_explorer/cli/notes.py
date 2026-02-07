"""Note commands."""

from typing import Optional

import typer

from ..core.models import NoteType
from ..services.notes_service import NotesService
from ..utils.display import console, print_error, print_success

app = typer.Typer(
    help="Paper note management",
    no_args_is_help=False,
    invoke_without_command=True,
)


@app.callback()
def note_callback(ctx: typer.Context):
    """Note management - shows all notes when run without a subcommand."""
    if ctx.invoked_subcommand is None:
        # No subcommand provided, list all notes
        list_notes(None)


def _add_note(arxiv_id: str, content: str, note_type: str) -> None:
    """Internal helper for adding notes (called from other modules)."""
    try:
        type_enum = NoteType(note_type)
    except ValueError:
        type_enum = NoteType.GENERAL

    service = NotesService()
    service.add_note(arxiv_id, content, type_enum)


@app.command("add")
def add(
    arxiv_id: str = typer.Argument(..., help="arXiv ID"),
    content: str = typer.Argument(..., help="Note content"),
    note_type: str = typer.Option(
        "general", "--type", "-t", help="Type (general/question/insight/todo)"
    ),
):
    """Add a note to a paper."""
    _add_note(arxiv_id, content, note_type)
    print_success(f"Note added to {arxiv_id}")


@app.command("show")
def show(
    arxiv_id: str = typer.Argument(..., help="arXiv ID"),
):
    """View notes for a paper."""
    service = NotesService()
    notes = service.get_notes(arxiv_id=arxiv_id)

    if not notes:
        console.print(f"[dim]No notes for {arxiv_id}[/dim]")
        return

    console.print(f"\n[bold]{arxiv_id} notes[/bold]\n")

    for note in notes:
        type_color = {
            NoteType.GENERAL: "white",
            NoteType.QUESTION: "yellow",
            NoteType.INSIGHT: "green",
            NoteType.TODO: "red",
        }[note.note_type]

        console.print(f"[{type_color}][{note.note_type.value}][/{type_color}] {note.content}")
        console.print(f"  [dim]{note.created_at.strftime('%Y-%m-%d %H:%M')}[/dim]\n")


@app.command("list")
def list_notes(
    note_type: Optional[str] = typer.Option(None, "--type", "-t", help="Type filter"),
):
    """View all notes."""
    service = NotesService()

    type_enum = None
    if note_type:
        try:
            type_enum = NoteType(note_type)
        except ValueError:
            print_error(f"Invalid type: {note_type}")
            raise typer.Exit(1) from None

    notes = service.get_notes(note_type=type_enum)

    if not notes:
        console.print("[dim]No notes[/dim]")
        return

    current_paper = None
    for note in notes:
        if note.arxiv_id != current_paper:
            current_paper = note.arxiv_id
            console.print(f"\n[bold]{current_paper}[/bold]")

        console.print(f"  [{note.note_type.value}] {note.content[:50]}...")
