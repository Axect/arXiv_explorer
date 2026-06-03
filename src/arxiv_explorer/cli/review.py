"""Review command -- generate comprehensive AI paper review."""

from pathlib import Path
from typing import Optional

import typer
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)

from ..core.models import Language, ReviewSectionType
from ..services import figure_service
from ..services.paper_service import PaperService
from ..services.review_service import PaperReviewService
from ..services.settings_service import SettingsService
from ..utils.display import console, print_error, print_info, print_success

# Human-readable names for the journal-club review sections
_SECTION_NAMES: dict[ReviewSectionType, str] = {
    ReviewSectionType.HOOK: "TL;DR",
    ReviewSectionType.PROBLEM: "The Problem",
    ReviewSectionType.KEY_IDEA: "Key Idea",
    ReviewSectionType.METHOD: "How It Works",
    ReviewSectionType.RESULTS: "Key Results",
    ReviewSectionType.SIGNIFICANCE: "Why It Matters",
    ReviewSectionType.APPRAISAL: "Strengths & Limitations",
    ReviewSectionType.DISCUSSION: "Discussion Questions",
    ReviewSectionType.TAKEAWAYS: "Takeaways",
}


def review(
    arxiv_id: str = typer.Argument(..., help="arXiv ID (e.g., 2401.00001)"),
    output: Optional[Path] = typer.Option(
        None, "--output", "-o", help="Save review to file (default: print to console)"
    ),
    force: bool = typer.Option(
        False, "--force", "-f", help="Regenerate all sections (ignore cache)"
    ),
    translate: bool = typer.Option(
        False, "--translate", "-t", help="Translate review to configured language"
    ),
    language: Optional[str] = typer.Option(
        None, "--language", "-L", help="Target language code (e.g., 'ko')"
    ),
    no_full_text: bool = typer.Option(
        False, "--no-full-text", help="Skip full text extraction, use abstract only"
    ),
    no_images: bool = typer.Option(
        False, "--no-images", help="Skip figure generation (codex imagegen)"
    ),
    theme: Optional[str] = typer.Option(
        None, "--theme", help="Figure style theme (default: configured setting)"
    ),
    status: bool = typer.Option(
        False, "--status", "-s", help="Show cached review status without generating"
    ),
    delete: bool = typer.Option(False, "--delete", help="Delete cached review for this paper"),
):
    """Generate a comprehensive AI review of an arXiv paper.

    Fetches the full paper text when possible (via arxiv-doc-builder),
    then analyzes each section with AI to produce a detailed Markdown review.
    Reviews are cached section-by-section -- interrupted reviews resume
    automatically.

    Examples:
        axp review 2401.00001
        axp review 2401.00001 -o review.md
        axp review 2401.00001 --force --translate
        axp review 2401.00001 --status
    """
    review_service = PaperReviewService()

    # Handle --delete
    if delete:
        if review_service.delete_review(arxiv_id):
            print_success(f"Deleted cached review for {arxiv_id}")
        else:
            print_info(f"No cached review found for {arxiv_id}")
        return

    # Handle --status
    if status:
        cached = review_service.get_cached_review(arxiv_id)
        if cached is None:
            print_info(f"No cached review for {arxiv_id}")
        else:
            total = len(ReviewSectionType)
            done = len(cached.sections)
            console.print(f"[bold]Review status for {arxiv_id}[/bold]")
            console.print(f"Sections: {done}/{total}")
            for st in ReviewSectionType:
                if st in cached.sections:
                    icon = "[green]\u2714[/green]"
                else:
                    icon = "[dim]\u2022[/dim]"
                console.print(f"  {icon} {_SECTION_NAMES.get(st, st.value)}")
        return

    # Fetch paper metadata
    paper_service = PaperService()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        progress.add_task("Fetching paper metadata...", total=None)
        paper = paper_service.get_paper(arxiv_id)

    if not paper:
        print_error(f"Paper not found: {arxiv_id}")
        raise typer.Exit(1)

    console.print(f"\n[bold]{paper.title}[/bold]")
    console.print(f"[dim]{', '.join(paper.authors[:5])}[/dim]\n")

    # If --no-full-text, skip extraction
    if no_full_text:
        review_service._extract_full_text = lambda _: None  # type: ignore[assignment]

    # Generate review with progress bar
    succeeded = 0
    failed = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Generating review...", total=len(ReviewSectionType))

        def on_start(section_type: ReviewSectionType, idx: int, total: int) -> None:
            name = _SECTION_NAMES.get(section_type, section_type.value)
            progress.update(task, description=f"[cyan]{name}[/cyan]...")

        def on_complete(section_type: ReviewSectionType, success: bool) -> None:
            nonlocal succeeded, failed
            if success:
                succeeded += 1
            else:
                failed += 1
            progress.advance(task)

        paper_review = review_service.generate_review(
            paper=paper,
            force=force,
            on_section_start=on_start,
            on_section_complete=on_complete,
        )

    if not paper_review:
        print_error("Review generation failed completely.")
        raise typer.Exit(1)

    # Report results
    print_info(f"Sections: {succeeded} succeeded, {failed} failed")
    if paper_review.source_type == "abstract":
        print_info("Note: Full text was not available. Review is based on abstract only.")

    settings = SettingsService()

    # Generate figures (codex imagegen) when saving to a file. Figures live in
    # <output_dir>/figures/ and are embedded with relative paths.
    if output is not None and not no_images and settings.get_review_images_enabled():
        if figure_service.codex_imagegen_available():
            briefs: list[tuple[str, dict]] = []
            method = paper_review.sections.get(ReviewSectionType.METHOD, {})
            if method.get("figure_brief"):
                briefs.append(("method", method["figure_brief"]))
            results = paper_review.sections.get(ReviewSectionType.RESULTS, {})
            if results.get("figure_brief"):
                briefs.append(("results", results["figure_brief"]))
            if briefs:
                theme_name = theme or settings.get_review_image_theme()
                fig_dir = output.parent / "figures"
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    TimeElapsedColumn(),
                    console=console,
                ) as progress:
                    progress.add_task(
                        f"Generating {len(briefs)} figure(s) with codex (~1-2 min each)...",
                        total=None,
                    )
                    generated = figure_service.generate_figures(
                        briefs, fig_dir, theme=theme_name, force=force
                    )
                for name, path in generated.items():
                    paper_review.figure_paths[name] = f"figures/{path.name}"
                if generated:
                    print_success(f"Generated {len(generated)} figure(s) in {fig_dir}")
                missing = [n for n, _ in briefs if n not in generated]
                if missing:
                    print_info(f"Figure(s) not produced: {', '.join(missing)} (rendered text-only)")
    elif output is None and not no_images and settings.get_review_images_enabled():
        print_info("Tip: use --output to a file to also generate embedded figures.")

    # Resolve language
    target_lang = Language.EN
    if translate or language:
        if language:
            try:
                target_lang = Language(language)
            except ValueError:
                supported = ", ".join(lang.value for lang in Language)
                print_error(f"Unknown language: {language}. Supported: {supported}")
                raise typer.Exit(1) from None
        else:
            target_lang = settings.get_language()

    # Render markdown
    markdown = review_service.render_markdown(paper_review, language=target_lang)

    # Output
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(markdown, encoding="utf-8")
        print_success(f"Review saved: {output}")
    else:
        console.print()
        from rich.markdown import Markdown

        console.print(Markdown(markdown))
