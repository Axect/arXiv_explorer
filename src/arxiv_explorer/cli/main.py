"""CLI main entry point."""

import typer
from rich.console import Console

from ..core.database import init_db
from ..core.update_checker import UpdateStatus, check_for_updates, pull_updates

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


def _prompt_update(status: UpdateStatus) -> None:
    """Display update info, warn about conflicts, and prompt user."""
    console.print(
        f"\n[bold yellow]Update available[/bold yellow]: "
        f"{status.behind_count} new commit{'s' if status.behind_count != 1 else ''} "
        f"on remote"
    )

    if status.ahead_count > 0:
        console.print(
            f"[dim](local is also {status.ahead_count} commit{'s' if status.ahead_count != 1 else ''} "
            f"ahead of remote)[/dim]"
        )

    # Show changed files summary
    if status.changed_files:
        n = len(status.changed_files)
        console.print(f"[dim]Changed files: {n}[/dim]")

    # Warn about conflicts
    if status.conflict_files:
        console.print(
            "\n[bold red]Warning:[/bold red] "
            "The following locally modified files also changed on remote:"
        )
        for f in status.conflict_files:
            console.print(f"  [red]- {f}[/red]")
        console.print(
            "[yellow]Pulling may cause merge conflicts. "
            "Consider committing or stashing your local changes first.[/yellow]\n"
        )

    try:
        answer = typer.prompt("Update now? [y/n]", default="n")
    except (EOFError, KeyboardInterrupt):
        console.print()
        return

    if answer.strip().lower() in ("y", "yes"):
        console.print("[dim]Pulling updates...[/dim]")
        success, message = pull_updates()
        if success:
            console.print(f"[green]Updated successfully.[/green] {message}")
            console.print(
                "[yellow]Note: if dependencies changed, run 'uv sync' to update them.[/yellow]\n"
            )
        else:
            console.print(f"[red]Update failed:[/red] {message}\n")
    else:
        console.print("[dim]Skipped.[/dim]\n")


@app.callback()
def main(
    version: bool = typer.Option(
        None,
        "--version",
        "-v",
        callback=version_callback,
        is_eager=True,
        help="Show version",
    ),
    no_update_check: bool = typer.Option(
        False,
        "--no-update-check",
        hidden=True,
        help="Skip update check",
    ),
):
    """arXiv Explorer - Personalized paper recommendation system."""
    # Initialize DB
    init_db()

    # Check for git updates (throttled, silent on failure)
    if not no_update_check:
        status = check_for_updates()
        if status and status.has_update:
            _prompt_update(status)


# Import and register subcommands
from . import config, daily, export, lists, notes, preferences, review, search  # noqa: E402

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
app.command(name="review")(review.review)


@app.command()
def tui():
    """Launch TUI mode (Rust)."""
    import shutil
    import subprocess
    from pathlib import Path

    project_root = Path(__file__).resolve().parents[3]
    tui_dir = project_root / "tui-rs"

    # Always build release binary if Cargo.toml exists (i.e. dev environment)
    if (tui_dir / "Cargo.toml").exists():
        result = subprocess.run(
            ["cargo", "build", "--release"],
            cwd=tui_dir,
        )
        if result.returncode != 0:
            typer.echo("Failed to build axp-tui.")
            raise typer.Exit(1)

    bin_path = shutil.which("axp-tui")
    if bin_path is None:
        candidate = tui_dir / "target" / "release" / "axp-tui"
        if candidate.exists():
            bin_path = str(candidate)
        else:
            typer.echo("axp-tui not found. Build it with: cd tui-rs && cargo build --release")
            raise typer.Exit(1)

    raise typer.Exit(subprocess.call([bin_path]))


if __name__ == "__main__":
    app()
