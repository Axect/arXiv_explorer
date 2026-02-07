"""Console output utilities."""

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ..core.models import Paper, PaperSummary, PaperTranslation, RecommendedPaper

console = Console()


def print_paper_list(papers: list[RecommendedPaper], show_score: bool = True) -> None:
    """Display a list of papers."""
    table = Table(
        title="Paper List",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan",
    )

    table.add_column("#", style="dim", width=3)
    table.add_column("arXiv ID", style="green", width=15)
    table.add_column("Title", width=50)
    table.add_column("Category", style="yellow", width=12)
    if show_score:
        table.add_column("Score", style="magenta", width=6)

    for i, rec in enumerate(papers, 1):
        paper = rec.paper
        title = paper.title[:47] + "..." if len(paper.title) > 50 else paper.title

        row = [
            str(i),
            paper.arxiv_id,
            title,
            paper.primary_category,
        ]
        if show_score:
            row.append(f"{rec.score:.2f}")

        table.add_row(*row)

    console.print(table)


def print_paper_detail(
    paper: Paper,
    summary: PaperSummary | None = None,
    translation: PaperTranslation | None = None,
) -> None:
    """Display paper details."""
    # Title
    console.print(
        Panel(
            f"[bold]{paper.title}[/bold]",
            title=f"[green]{paper.arxiv_id}[/green]",
            border_style="blue",
        )
    )

    # Metadata
    console.print(f"[cyan]Authors:[/cyan] {', '.join(paper.authors[:5])}")
    if len(paper.authors) > 5:
        console.print(f"       and {len(paper.authors) - 5} more")
    console.print(f"[cyan]Categories:[/cyan] {', '.join(paper.categories)}")
    console.print(f"[cyan]Published:[/cyan] {paper.published.strftime('%Y-%m-%d')}")

    # Summary
    if summary:
        console.print()
        console.print(
            Panel(
                summary.summary_short,
                title="[yellow]Summary[/yellow]",
                border_style="yellow",
            )
        )

        # Detailed summary
        if summary.summary_detailed:
            console.print()
            console.print(
                Panel(
                    summary.summary_detailed,
                    title="[cyan]Detailed Summary[/cyan]",
                    border_style="cyan",
                )
            )

        if summary.key_findings:
            console.print()
            console.print("[yellow]Key Findings:[/yellow]")
            for finding in summary.key_findings:
                console.print(f"  • {finding}")

    # Abstract
    console.print()
    console.print(
        Panel(
            paper.abstract,
            title="[dim]Abstract[/dim]",
            border_style="dim",
        )
    )

    # Translation
    if translation:
        console.print()
        console.print(
            Panel(
                translation.translated_title,
                title="[magenta]Translated Title[/magenta]",
                border_style="magenta",
            )
        )
        console.print()
        console.print(
            Panel(
                translation.translated_abstract,
                title="[magenta]Translated Abstract[/magenta]",
                border_style="magenta",
            )
        )


def print_categories(categories: list) -> None:
    """Display category list."""
    table = Table(
        title="Preferred Categories",
        box=box.SIMPLE,
    )
    table.add_column("Category", style="green")
    table.add_column("Priority", style="yellow")
    table.add_column("Added", style="dim")

    for cat in categories:
        table.add_row(
            cat.category,
            str(cat.priority),
            cat.added_at.strftime("%Y-%m-%d"),
        )

    console.print(table)


def print_success(message: str) -> None:
    """Display a success message."""
    console.print(f"[green]✓[/green] {message}")


def print_error(message: str) -> None:
    """Display an error message."""
    console.print(f"[red]✗[/red] {message}")


def print_info(message: str) -> None:
    """Display an info message."""
    console.print(f"[blue]ℹ[/blue] {message}")
