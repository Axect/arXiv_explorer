"""Preference commands."""
import typer

from ..services.preference_service import PreferenceService
from ..utils.display import print_categories, print_success, print_error, console

app = typer.Typer(
    help="User preference management",
    no_args_is_help=False,
    invoke_without_command=True,
)


@app.callback()
def prefs_callback(ctx: typer.Context):
    """Preference management - shows current preferences when run without a subcommand."""
    if ctx.invoked_subcommand is None:
        # No subcommand provided, show current preferences
        show()


@app.command("add-category")
def add_category(
    category: str = typer.Argument(..., help="Category (e.g. cs.AI, hep-ph)"),
    priority: int = typer.Option(1, "--priority", "-p", help="Priority (higher = more important)"),
):
    """Add a preferred category."""
    service = PreferenceService()
    service.add_category(category, priority)
    print_success(f"Category added: {category} (priority: {priority})")


@app.command("remove-category")
def remove_category(
    category: str = typer.Argument(..., help="Category"),
):
    """Remove a preferred category."""
    service = PreferenceService()
    if service.remove_category(category):
        print_success(f"Category removed: {category}")
    else:
        print_error(f"Category not found: {category}")


@app.command("add-keyword")
def add_keyword(
    keyword: str = typer.Argument(..., help="Keyword"),
    weight: float = typer.Option(1.0, "--weight", "-w", help="Weight"),
):
    """Add a keyword interest."""
    service = PreferenceService()
    service.add_keyword(keyword, weight)
    print_success(f"Keyword added: {keyword} (weight: {weight})")


@app.command("remove-keyword")
def remove_keyword(
    keyword: str = typer.Argument(..., help="Keyword"),
):
    """Remove a keyword interest."""
    service = PreferenceService()
    if service.remove_keyword(keyword):
        print_success(f"Keyword removed: {keyword}")
    else:
        print_error(f"Keyword not found: {keyword}")


@app.command("show")
def show():
    """View current preferences."""
    service = PreferenceService()

    categories = service.get_categories()
    if categories:
        print_categories(categories)
    else:
        console.print("[dim]No preferred categories[/dim]")

    console.print()

    keywords = service.get_keywords()
    if keywords:
        console.print("[bold]Keyword interests:[/bold]")
        for kw in keywords:
            console.print(f"  • {kw.keyword} (weight: {kw.weight})")
    else:
        console.print("[dim]No keyword interests[/dim]")

    console.print()

    interesting = service.get_interesting_papers()
    console.print(f"[bold]Interesting papers:[/bold] {len(interesting)}")
