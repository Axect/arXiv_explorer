"""Search commands."""

import typer

from ..services.paper_service import PaperService
from ..utils.display import print_info, print_paper_list


def search(
    query: str = typer.Argument(..., help="Search query"),
    limit: int = typer.Option(20, "--limit", "-l", help="Maximum number of results"),
    arxiv: bool = typer.Option(False, "--arxiv", "-a", help="Search directly from arXiv API"),
):
    """Search papers."""
    service = PaperService()

    papers = service.search_papers(query, limit=limit, from_arxiv=arxiv)

    if not papers:
        print_info("No results found.")
        return

    print_info(f"Search results for '{query}': {len(papers)} papers")
    print_paper_list(papers)
