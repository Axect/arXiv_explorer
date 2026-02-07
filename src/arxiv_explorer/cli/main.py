"""CLI main entry point."""
import typer
from rich.console import Console

from ..core.database import init_db

app = typer.Typer(
    name="axp",
    help="arXiv Explorer - Personalized paper recommendation system",
    no_args_is_help=True,
)

console = Console()


def version_callback(value: bool):
    if value:
        from .. import __version__
        console.print(f"arXiv Explorer v{__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        None, "--version", "-v",
        callback=version_callback,
        is_eager=True,
        help="Show version",
    ),
):
    """arXiv Explorer - Personalized paper recommendation system."""
    # Initialize DB
    init_db()


# Import and register subcommands
from . import daily, search, preferences, lists, notes, export, config

app.add_typer(preferences.app, name="prefs", help="Preference management")
app.add_typer(lists.app, name="list", help="Reading list management")
app.add_typer(notes.app, name="note", help="Note management")
app.add_typer(export.app, name="export", help="Export")
app.add_typer(config.app, name="config", help="AI settings")

# Single commands
app.command()(daily.daily)
app.command()(daily.top)
app.command()(search.search)
app.command(name="like")(daily.like)
app.command(name="dislike")(daily.dislike)
app.command(name="show")(daily.show)
app.command(name="translate")(daily.translate)


@app.command()
def tui():
    """Launch TUI mode."""
    from ..tui.app import launch_tui
    launch_tui()


if __name__ == "__main__":
    app()
