"""Daily paper commands."""
from typing import Optional
import typer
from rich.progress import Progress, SpinnerColumn, TextColumn

from ..services.paper_service import PaperService
from ..services.preference_service import PreferenceService
from ..services.summarization import SummarizationService
from ..services.translation import TranslationService
from ..utils.display import (
    console, print_paper_list, print_paper_detail,
    print_success, print_error, print_info
)


def daily(
    days: int = typer.Option(1, "--days", "-d", help="Number of days to fetch"),
    summarize: bool = typer.Option(False, "--summarize", "-s", help="Generate summaries"),
    detailed: bool = typer.Option(False, "--detailed", help="Generate detailed summaries (use with --summarize)"),
    limit: int = typer.Option(20, "--limit", "-l", help="Maximum number of results"),
):
    """Fetch today's/recent papers (personalized ranking)."""
    service = PaperService()
    pref_service = PreferenceService()

    # Check categories
    categories = pref_service.get_categories()
    if not categories:
        print_error("No preferred categories. Add one with 'axp prefs add-category'.")
        raise typer.Exit(1)

    cat_names = ", ".join(c.category for c in categories)
    print_info(f"Categories: {cat_names}")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Fetching papers...", total=None)
        papers = service.get_daily_papers(days=days, limit=limit)

    if not papers:
        print_info("No new papers found.")
        return

    print_info(f"{len(papers)} papers found")

    # Generate summaries
    if summarize or detailed:
        summarizer = SummarizationService()
        summary_type = "detailed summary" if detailed else "summary"
        success_count = 0
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task(f"Generating {summary_type}...", total=len(papers))
            for rec in papers:
                summary = summarizer.summarize(
                    rec.paper.arxiv_id,
                    rec.paper.title,
                    rec.paper.abstract,
                    detailed=detailed,
                )
                rec.summary = summary
                if summary:
                    success_count += 1
                progress.advance(task)

        if success_count < len(papers):
            failed_count = len(papers) - success_count
            print_info(f"Summaries: {success_count} succeeded, {failed_count} failed")

    print_paper_list(papers)


def top(
    limit: int = typer.Option(10, "--limit", "-l", help="Maximum number of results"),
    summarize: bool = typer.Option(False, "--summarize", "-s", help="Generate summaries"),
    detailed: bool = typer.Option(False, "--detailed", help="Generate detailed summaries"),
):
    """View top recommended papers."""
    service = PaperService()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Fetching top papers...", total=None)
        papers = service.get_daily_papers(days=7, limit=limit)

    if not papers:
        print_info("No papers to recommend.")
        return

    print_info(f"Top {len(papers)} papers from the last 7 days")

    # Generate summaries
    if summarize or detailed:
        summarizer = SummarizationService()
        summary_type = "detailed summary" if detailed else "summary"
        success_count = 0
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task(f"Generating {summary_type}...", total=len(papers))
            for rec in papers:
                summary = summarizer.summarize(
                    rec.paper.arxiv_id,
                    rec.paper.title,
                    rec.paper.abstract,
                    detailed=detailed,
                )
                rec.summary = summary
                if summary:
                    success_count += 1
                progress.advance(task)

        if success_count < len(papers):
            failed_count = len(papers) - success_count
            print_info(f"Summaries: {success_count} succeeded, {failed_count} failed")

    print_paper_list(papers)


def like(
    arxiv_id: str = typer.Argument(..., help="arXiv ID"),
    note: Optional[str] = typer.Option(None, "--note", "-n", help="Add a note"),
):
    """Mark a paper as interesting."""
    pref_service = PreferenceService()
    pref_service.mark_interesting(arxiv_id)
    print_success(f"{arxiv_id} marked as interesting")

    if note:
        from .notes import _add_note
        _add_note(arxiv_id, note, "general")


def dislike(
    arxiv_id: str = typer.Argument(..., help="arXiv ID"),
):
    """Mark a paper as not interesting."""
    pref_service = PreferenceService()
    pref_service.mark_not_interesting(arxiv_id)
    print_success(f"{arxiv_id} marked as not interesting")


def show(
    arxiv_id: Optional[str] = typer.Argument(None, help="arXiv ID (if omitted, shows recently liked papers)"),
    summary: bool = typer.Option(False, "--summary", "-s", help="Include summary"),
    detailed: bool = typer.Option(False, "--detailed", "-d", help="Generate detailed summary (longer summary and analysis)"),
    translate: bool = typer.Option(False, "--translate", "-t", help="Include translation"),
):
    """View paper details."""
    service = PaperService()
    pref_service = PreferenceService()

    # If no arxiv_id provided, show recently liked papers
    if arxiv_id is None:
        interesting_ids = pref_service.get_interesting_papers()

        if not interesting_ids:
            print_info("No papers marked as interesting.")
            console.print("\nUsage:")
            console.print("  View a specific paper: [cyan]axp show 2602.04878v1[/cyan]")
            console.print("  With summary: [cyan]axp show 2602.04878v1 --summary[/cyan]")
            console.print("  Detailed summary: [cyan]axp show 2602.04878v1 --detailed[/cyan]")
            console.print("  Fetch recent papers: [cyan]axp daily --days 7[/cyan]")
            console.print("  Search by keyword: [cyan]axp search \"quantum computing\"[/cyan]")
            return

        console.print("[bold]Recently liked papers:[/bold]\n")
        for i, paper_id in enumerate(interesting_ids[:5], 1):
            console.print(f"{i}. [green]{paper_id}[/green]")

        console.print(f"\nView details: [cyan]axp show {interesting_ids[0]} --detailed[/cyan]")
        return

    paper = service.get_paper(arxiv_id)

    if not paper:
        print_error(f"Paper not found: {arxiv_id}")
        raise typer.Exit(1)

    paper_summary = None
    if summary or detailed:
        summarizer = SummarizationService()
        paper_summary = summarizer.summarize(arxiv_id, paper.title, paper.abstract, detailed=detailed)

    paper_translation = None
    if translate:
        translator = TranslationService()
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            progress.add_task("Translating...", total=None)
            paper_translation = translator.translate(arxiv_id, paper.title, paper.abstract)

    print_paper_detail(paper, paper_summary, paper_translation)


def translate(
    arxiv_id: str = typer.Argument(..., help="arXiv ID"),
):
    """Translate a paper."""
    service = PaperService()
    paper = service.get_paper(arxiv_id)

    if not paper:
        print_error(f"Paper not found: {arxiv_id}")
        raise typer.Exit(1)

    translator = TranslationService()
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        progress.add_task("Translating...", total=None)
        translation = translator.translate(arxiv_id, paper.title, paper.abstract)

    if not translation:
        print_error("Translation failed")
        raise typer.Exit(1)

    print_paper_detail(paper, translation=translation)
