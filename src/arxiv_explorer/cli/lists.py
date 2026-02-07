"""Reading list commands."""

from typing import Optional

import typer

from ..core.models import ReadingStatus
from ..services.reading_list_service import ReadingListService
from ..utils.display import console, print_error, print_success

app = typer.Typer(
    help="Reading list management",
    no_args_is_help=False,
    invoke_without_command=True,
)


@app.callback()
def list_callback(ctx: typer.Context):
    """Reading list management - shows all lists when run without a subcommand."""
    if ctx.invoked_subcommand is None:
        # No subcommand provided, list all reading lists
        ls()


@app.command("create")
def create(
    name: str = typer.Argument(..., help="List name"),
    description: Optional[str] = typer.Option(None, "--desc", "-d", help="Description"),
):
    """Create a reading list."""
    service = ReadingListService()
    try:
        service.create_list(name, description)
        print_success(f"List created: {name}")
    except Exception as e:
        print_error(f"Creation failed: {e}")


@app.command("delete")
def delete(
    name: str = typer.Argument(..., help="List name"),
):
    """Delete a reading list."""
    service = ReadingListService()
    if service.delete_list(name):
        print_success(f"List deleted: {name}")
    else:
        print_error(f"List not found: {name}")


@app.command("add")
def add(
    name: str = typer.Argument(..., help="List name"),
    arxiv_id: str = typer.Argument(..., help="arXiv ID"),
):
    """Add a paper to a list."""
    service = ReadingListService()
    if service.add_paper(name, arxiv_id):
        print_success(f"Added {arxiv_id} to '{name}'")
    else:
        print_error(f"List not found: {name}")


@app.command("remove")
def remove(
    name: str = typer.Argument(..., help="List name"),
    arxiv_id: str = typer.Argument(..., help="arXiv ID"),
):
    """Remove a paper from a list."""
    service = ReadingListService()
    if service.remove_paper(name, arxiv_id):
        print_success(f"Removed {arxiv_id} from '{name}'")
    else:
        print_error("Removal failed")


@app.command("status")
def status(
    arxiv_id: str = typer.Argument(..., help="arXiv ID"),
    new_status: str = typer.Argument(..., help="New status (unread/reading/completed)"),
):
    """Change a paper's reading status."""
    try:
        status_enum = ReadingStatus(new_status)
    except ValueError:
        print_error(f"Invalid status: {new_status}")
        raise typer.Exit(1) from None

    service = ReadingListService()
    if service.update_status(arxiv_id, status_enum):
        print_success(f"{arxiv_id} status: {new_status}")
    else:
        print_error("Status change failed")


@app.command("show")
def show(
    name: str = typer.Argument(..., help="List name"),
):
    """View papers in a list."""
    service = ReadingListService()
    reading_list = service.get_list(name)

    if not reading_list:
        print_error(f"List not found: {name}")
        raise typer.Exit(1)

    papers = service.get_papers(name)

    console.print(f"\n[bold]{reading_list.name}[/bold]")
    if reading_list.description:
        console.print(f"[dim]{reading_list.description}[/dim]")
    console.print()

    if not papers:
        console.print("[dim]No papers in this list[/dim]")
        return

    for p in papers:
        status_icon = {
            ReadingStatus.UNREAD: "○",
            ReadingStatus.READING: "◐",
            ReadingStatus.COMPLETED: "●",
        }[p.status]

        console.print(f"  {status_icon} {p.arxiv_id} [{p.status.value}]")


@app.command("ls")
def ls():
    """View all reading lists."""
    service = ReadingListService()
    lists = service.get_all_lists()

    if not lists:
        console.print("[dim]No reading lists[/dim]")
        return

    for lst in lists:
        papers = service.get_papers(lst.name)
        console.print(f"  • {lst.name} ({len(papers)} papers)")
