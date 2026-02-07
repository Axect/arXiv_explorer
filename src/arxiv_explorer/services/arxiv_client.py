"""arXiv API client."""
import json
import time
from datetime import datetime, timedelta
from typing import Iterator
import xml.etree.ElementTree as ET

import httpx
import feedparser

from ..core.database import get_connection
from ..core.models import Paper


ARXIV_API_URL = "https://export.arxiv.org/api/query"
RATE_LIMIT_SECONDS = 3


class ArxivClient:
    """arXiv API client."""

    def __init__(self):
        self._last_request_time: float = 0

    def _rate_limit(self) -> None:
        """Apply rate limiting."""
        elapsed = time.time() - self._last_request_time
        if elapsed < RATE_LIMIT_SECONDS:
            time.sleep(RATE_LIMIT_SECONDS - elapsed)
        self._last_request_time = time.time()

    def search(
        self,
        query: str,
        max_results: int = 50,
        sort_by: str = "submittedDate",
        sort_order: str = "descending",
    ) -> list[Paper]:
        """Search papers by keyword (write-through cache)."""
        self._rate_limit()

        params = {
            "search_query": query,
            "max_results": max_results,
            "sortBy": sort_by,
            "sortOrder": sort_order,
        }

        with httpx.Client(trust_env=False) as client:
            response = client.get(ARXIV_API_URL, params=params, timeout=60)
            response.raise_for_status()

        papers = self._parse_response(response.text)
        self._save_cache_batch(papers)
        return papers

    def fetch_by_category(
        self,
        categories: list[str],
        days: int = 1,
        max_results: int = 200,
    ) -> list[Paper]:
        """Fetch recent papers by category."""
        # Calculate date range
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

        # Build category query
        cat_query = " OR ".join(f"cat:{cat}" for cat in categories)

        # Date filtering is not natively supported by the API; post-filter
        papers = self.search(cat_query, max_results=max_results)

        # Filter by date
        return [
            p for p in papers
            if p.published >= start_date
        ]

    def get_paper(self, arxiv_id: str) -> Paper | None:
        """Get a specific paper (cache-first)."""
        cached = self._get_cached(arxiv_id)
        if cached:
            return cached

        self._rate_limit()

        params = {"id_list": arxiv_id}

        with httpx.Client(trust_env=False) as client:
            response = client.get(ARXIV_API_URL, params=params, timeout=60)
            response.raise_for_status()

        papers = self._parse_response(response.text)
        if papers:
            self._save_cache_batch(papers)
            return papers[0]
        return None

    def get_paper_cached(self, arxiv_id: str) -> Paper | None:
        """Look up a paper from cache only (no API call)."""
        return self._get_cached(arxiv_id)

    def get_papers_cached_batch(self, arxiv_ids: list[str]) -> dict[str, Paper]:
        """Batch look up multiple papers from cache."""
        return self._get_cached_batch(arxiv_ids)

    def _get_cached(self, arxiv_id: str) -> Paper | None:
        """Look up a single paper from DB."""
        with get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM papers WHERE arxiv_id = ?", (arxiv_id,)
            ).fetchone()
        if row is None:
            return None
        return self._row_to_paper(row)

    def _get_cached_batch(self, arxiv_ids: list[str]) -> dict[str, Paper]:
        """Batch look up multiple papers from DB."""
        if not arxiv_ids:
            return {}
        placeholders = ",".join("?" for _ in arxiv_ids)
        with get_connection() as conn:
            rows = conn.execute(
                f"SELECT * FROM papers WHERE arxiv_id IN ({placeholders})",
                arxiv_ids,
            ).fetchall()
        return {row["arxiv_id"]: self._row_to_paper(row) for row in rows}

    def _save_cache_batch(self, papers: list[Paper]) -> None:
        """Batch save papers to DB."""
        if not papers:
            return
        with get_connection() as conn:
            conn.executemany(
                """INSERT OR REPLACE INTO papers
                   (arxiv_id, title, abstract, authors, categories,
                    published, updated, pdf_url, cached_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
                [
                    (
                        p.arxiv_id,
                        p.title,
                        p.abstract,
                        json.dumps(p.authors),
                        json.dumps(p.categories),
                        p.published.isoformat(),
                        p.updated.isoformat() if p.updated else None,
                        p.pdf_url,
                    )
                    for p in papers
                ],
            )
            conn.commit()

    @staticmethod
    def _row_to_paper(row: "sqlite3.Row") -> Paper:
        """Convert a DB row to a Paper object."""
        published = row["published"]
        if isinstance(published, str):
            published = datetime.fromisoformat(published)

        updated = row["updated"]
        if isinstance(updated, str):
            updated = datetime.fromisoformat(updated)

        return Paper(
            arxiv_id=row["arxiv_id"],
            title=row["title"],
            abstract=row["abstract"],
            authors=json.loads(row["authors"]),
            categories=json.loads(row["categories"]),
            published=published,
            updated=updated,
            pdf_url=row["pdf_url"],
        )

    def _parse_response(self, xml_text: str) -> list[Paper]:
        """Parse API response."""
        feed = feedparser.parse(xml_text)
        papers = []

        for entry in feed.entries:
            # Extract arXiv ID from URL
            arxiv_id = entry.id.split("/abs/")[-1]

            # Extract categories
            categories = [tag.term for tag in entry.get("tags", [])]

            # Extract authors
            authors = [author.name for author in entry.get("authors", [])]

            # Parse dates
            published = datetime(*entry.published_parsed[:6])
            updated = None
            if hasattr(entry, "updated_parsed") and entry.updated_parsed:
                updated = datetime(*entry.updated_parsed[:6])

            # PDF URL
            pdf_url = None
            for link in entry.get("links", []):
                if link.get("type") == "application/pdf":
                    pdf_url = link.href
                    break

            paper = Paper(
                arxiv_id=arxiv_id,
                title=entry.title.replace("\n", " ").strip(),
                abstract=entry.summary.replace("\n", " ").strip(),
                authors=authors,
                categories=categories,
                published=published,
                updated=updated,
                pdf_url=pdf_url,
            )
            papers.append(paper)

        return papers
