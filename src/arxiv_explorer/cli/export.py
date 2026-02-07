"""Export commands."""

import json
from pathlib import Path
from typing import Optional

import typer

from ..services.paper_service import PaperService
from ..services.preference_service import PreferenceService
from ..services.reading_list_service import ReadingListService
from ..utils.display import console, print_error, print_info, print_success

app = typer.Typer(help="Export")


@app.command("interesting")
def export_interesting(
    format: str = typer.Option("md", "--format", "-f", help="Format (md/json/csv)"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output file"),
):
    """Export interesting papers."""
    pref_service = PreferenceService()
    paper_service = PaperService()

    arxiv_ids = pref_service.get_interesting_papers()

    if not arxiv_ids:
        print_info("No interesting papers found.")
        return

    # Fetch paper info
    papers = []
    for arxiv_id in arxiv_ids:
        paper = paper_service.get_paper(arxiv_id)
        if paper:
            papers.append(paper)

    # Format output
    if format == "json":
        content = json.dumps(
            [
                {
                    "arxiv_id": p.arxiv_id,
                    "title": p.title,
                    "authors": p.authors,
                    "categories": p.categories,
                    "published": p.published.isoformat(),
                    "pdf_url": p.pdf_url,
                }
                for p in papers
            ],
            indent=2,
            ensure_ascii=False,
        )

    elif format == "csv":
        lines = ["arxiv_id,title,authors,categories,published,pdf_url"]
        for p in papers:
            authors = "; ".join(p.authors)
            cats = "; ".join(p.categories)
            lines.append(
                f'"{p.arxiv_id}","{p.title}","{authors}","{cats}","{p.published.date()}","{p.pdf_url}"'
            )
        content = "\n".join(lines)

    else:  # markdown
        lines = ["# Interesting Papers\n"]
        for p in papers:
            lines.append(f"## [{p.arxiv_id}]({p.pdf_url})")
            lines.append(f"**{p.title}**\n")
            lines.append(f"- Authors: {', '.join(p.authors[:3])}")
            if len(p.authors) > 3:
                lines[-1] += f" +{len(p.authors) - 3} more"
            lines.append(f"- Categories: {', '.join(p.categories)}")
            lines.append(f"- Published: {p.published.date()}\n")
        content = "\n".join(lines)

    # Output
    if output:
        output.write_text(content)
        print_success(f"Saved: {output}")
    else:
        console.print(content)


@app.command("list")
def export_list(
    name: str = typer.Argument(..., help="List name"),
    format: str = typer.Option("md", "--format", "-f", help="Format (md/json)"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output file"),
):
    """Export a reading list."""
    list_service = ReadingListService()
    paper_service = PaperService()

    reading_list = list_service.get_list(name)
    if not reading_list:
        print_error(f"List not found: {name}")
        raise typer.Exit(1)

    list_papers = list_service.get_papers(name)

    # Fetch paper info
    papers_with_status = []
    for lp in list_papers:
        paper = paper_service.get_paper(lp.arxiv_id)
        if paper:
            papers_with_status.append((paper, lp.status))

    if format == "json":
        content = json.dumps(
            {
                "name": reading_list.name,
                "description": reading_list.description,
                "papers": [
                    {
                        "arxiv_id": p.arxiv_id,
                        "title": p.title,
                        "status": s.value,
                        "pdf_url": p.pdf_url,
                    }
                    for p, s in papers_with_status
                ],
            },
            indent=2,
            ensure_ascii=False,
        )

    else:  # markdown
        lines = [f"# {reading_list.name}\n"]
        if reading_list.description:
            lines.append(f"{reading_list.description}\n")

        for p, s in papers_with_status:
            status_icon = {"unread": "○", "reading": "◐", "completed": "●"}[s.value]
            lines.append(f"- {status_icon} [{p.arxiv_id}]({p.pdf_url}): {p.title}")

        content = "\n".join(lines)

    if output:
        output.write_text(content)
        print_success(f"Saved: {output}")
    else:
        console.print(content)


@app.command("markdown")
def export_markdown(
    arxiv_id: str = typer.Argument(..., help="arXiv ID"),
):
    """Convert paper to Markdown (via arxiv-doc-builder)."""
    import subprocess

    script_path = (
        Path(__file__).parent.parent.parent.parent.parent
        / ".claude/skills/arxiv-doc-builder/scripts/convert_paper.py"
    )

    if not script_path.exists():
        print_error("arxiv-doc-builder script not found.")
        raise typer.Exit(1)

    print_info(f"Converting {arxiv_id}...")

    result = subprocess.run(
        ["uv", "run", str(script_path), arxiv_id],
        capture_output=True,
        text=True,
    )

    if result.returncode == 0:
        print_success(f"Conversion complete: papers/{arxiv_id}/{arxiv_id}.md")
    else:
        print_error(f"Conversion failed: {result.stderr}")
