"""Search commands."""

import typer

from ..services.paper_service import PaperService
from ..utils.display import print_info, print_paper_list


def search(
    query: str = typer.Argument(..., help="Search query"),
    limit: int = typer.Option(20, "--limit", "-l", help="Maximum number of results"),
    arxiv: bool = typer.Option(False, "--arxiv", "-a", help="Search directly from arXiv API"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Search papers."""
    import json

    service = PaperService()

    try:
        papers = service.search_papers(query, limit=limit, from_arxiv=arxiv)
    except Exception as e:
        if json_output:
            import sys

            print(f"{type(e).__name__}: {e}", file=sys.stderr)
            raise typer.Exit(1) from e
        raise

    if json_output:

        def paper_to_dict(rec):
            p = rec.paper
            return {
                "arxiv_id": p.arxiv_id,
                "title": p.title,
                "abstract": p.abstract,
                "authors": p.authors,
                "categories": p.categories,
                "published": str(p.published),
                "score": rec.score,
            }

        result = [paper_to_dict(r) for r in papers]
        print(json.dumps(result))
        return

    if not papers:
        print_info("No results found.")
        return

    print_info(f"Search results for '{query}': {len(papers)} papers")
    print_paper_list(papers)
