"""arXiv API client."""

import hashlib
import json
import sqlite3
import time
from datetime import datetime, timedelta

import feedparser
import httpx

from ..core.database import get_connection
from ..core.models import Paper

ARXIV_API_URL = "https://export.arxiv.org/api/query"
# Lightweight per-category RSS feeds on a separate host (CDN), not subject to
# the query API's rate limiting. A combined feed (cat1+cat2+...) returns the
# latest announcement day for all categories in a single request.
ARXIV_RSS_URL = "https://rss.arxiv.org/rss/"
# OAI-PMH endpoint for date-range harvesting (export.arxiv.org/oai2 redirects
# here). Used for multi-day fetches that RSS (today only) can't cover.
ARXIV_OAI_URL = "https://oaipmh.arxiv.org/oai"
# RSS announce types worth surfacing as "new daily papers": brand-new
# submissions and new cross-listings. "replace"/"replace-cross" are revisions
# of existing papers, not new arrivals.
RSS_KEEP_ANNOUNCE = {"new", "cross"}
# OAI sets are archive-level (e.g. "cs", not "cs.AI"), so a multi-day harvest of
# a busy archive can paginate heavily. Bound it: a recommendation feed only
# needs a few hundred candidates, and the result is cached for the day.
OAI_MAX_PAGES_PER_ARCHIVE = 3
OAI_TARGET_RECORDS = 400
RATE_LIMIT_SECONDS = 3
# Keep the interactive path responsive: a healthy arXiv request returns in a
# couple of seconds, so cap a single request well below the old 60s, retry only
# a few times, and bound the total retry wall-clock. arXiv 429 blocks are
# IP-wide and last minutes, so long in-call retries can't clear them anyway:
# recover from transient blips fast, then fail fast with a clear message.
HTTP_TIMEOUT_SECONDS = 20
MAX_RETRIES = 3
MAX_BACKOFF_SECONDS = 8
RETRY_BUDGET_SECONDS = 25
# arXiv throttles with 429 and serves 503 when overloaded; both are retryable.
RETRYABLE_STATUS = {429, 503}


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

    def _get_with_retry(self, params: dict, url: str = ARXIV_API_URL) -> httpx.Response:
        """GET an arXiv endpoint with rate limiting and retry/backoff.

        arXiv frequently answers with 429 (rate limited), 503 (overloaded),
        or simply times out. Retry those cases with exponential backoff,
        honoring the Retry-After header when arXiv provides one. Retries are
        bounded by both MAX_RETRIES and a total wall-clock budget so the
        caller (e.g. an interactive TUI) never hangs for long; the last
        attempt re-raises so callers still see a real error.
        """
        backoff: float = RATE_LIMIT_SECONDS
        last_error: Exception | None = None
        deadline = time.monotonic() + RETRY_BUDGET_SECONDS

        for attempt in range(MAX_RETRIES):
            self._rate_limit()
            try:
                with httpx.Client(trust_env=False, follow_redirects=True) as client:
                    response = client.get(url, params=params, timeout=HTTP_TIMEOUT_SECONDS)
            except httpx.TransportError as exc:
                last_error = exc
            else:
                if response.status_code not in RETRYABLE_STATUS:
                    response.raise_for_status()
                    return response
                last_error = httpx.HTTPStatusError(
                    f"arXiv returned {response.status_code} (rate limited or overloaded)",
                    request=response.request,
                    response=response,
                )
                retry_after = response.headers.get("retry-after")
                if retry_after and retry_after.isdigit():
                    backoff = float(retry_after)

            # Stop if this was the last attempt or another backoff would
            # blow the total retry budget.
            sleep_for = min(backoff, MAX_BACKOFF_SECONDS)
            if attempt == MAX_RETRIES - 1 or time.monotonic() + sleep_for >= deadline:
                break
            time.sleep(sleep_for)
            backoff *= 2

        assert last_error is not None
        raise last_error

    @staticmethod
    def _build_query(query: str) -> str:
        """Convert a plain-text query to arXiv API syntax.

        If the query already contains arXiv field prefixes (e.g. cat:, all:, ti:)
        or boolean operators (AND, OR, ANDNOT), return it as-is.
        Otherwise, split into words and join with 'all:word AND all:word'.
        """
        import re

        # Already formatted: contains field prefix or boolean operator
        if re.search(r"\b(all|ti|au|abs|cat|co|jr|rn|id):", query) or re.search(
            r"\b(AND|OR|ANDNOT)\b", query
        ):
            return query

        words = query.split()
        if not words:
            return query
        return " AND ".join(f"all:{w}" for w in words)

    def search(
        self,
        query: str,
        max_results: int = 50,
        sort_by: str = "submittedDate",
        sort_order: str = "descending",
    ) -> list[Paper]:
        """Search papers by keyword (write-through cache)."""
        params = {
            "search_query": self._build_query(query),
            "max_results": max_results,
            "sortBy": sort_by,
            "sortOrder": sort_order,
        }

        response = self._get_with_retry(params)
        papers = self._parse_response(response.text)
        self._save_cache_batch(papers)
        return papers

    def fetch_by_category(
        self,
        categories: list[str],
        days: int = 1,
        max_results: int = 200,
    ) -> list[Paper]:
        """Fetch recent papers by category with smart caching.

        Source selection (all post-filtered by published date and cached):
        - days <= 1: RSS feed (today's announcements, single light request).
        - days >= 2: OAI-PMH date-range harvest.
        - On any failure: fall back to the query API.

        RSS and OAI live on separate hosts that are not subject to the query
        API's aggressive rate limiting, so they avoid the 429s that the busy
        query endpoint hands out.
        """
        today_str = datetime.now().strftime("%Y-%m-%d")
        cat_hash = self._categories_hash(categories)

        # Check cache
        cached = self._get_fetch_cache(today_str, days, cat_hash)
        if cached is not None:
            return cached

        self._cleanup_stale_cache()

        # Try sources in order, degrading gracefully. For multi-day requests
        # OAI is primary; if it is down, RSS still yields today's papers, and
        # the query API is the last resort. Each source raises on failure.
        sources = []
        if days <= 1:
            sources.append(lambda: self._fetch_rss(categories))
        else:
            sources.append(lambda: self._fetch_oai(categories, days))
            sources.append(lambda: self._fetch_rss(categories))
        sources.append(lambda: self._fetch_via_query_api(categories, days, max_results))

        papers = None
        last_error: Exception | None = None
        for source in sources:
            try:
                papers = source()
                break
            except Exception as exc:
                last_error = exc
        if papers is None:
            raise last_error if last_error else RuntimeError("No fetch source available")

        # Post-filter by published date
        start_date = datetime.now() - timedelta(days=days)
        papers = [p for p in papers if p.published >= start_date]

        # Save cache entry
        paper_ids = [p.arxiv_id for p in papers]
        self._save_fetch_cache(today_str, days, cat_hash, paper_ids)

        return papers

    def _fetch_via_query_api(
        self, categories: list[str], days: int, max_results: int
    ) -> list[Paper]:
        """Fetch recent papers through the classic query API (fallback path)."""
        cat_query = " OR ".join(f"cat:{cat}" for cat in categories)
        api_max = min(days * 50, 2000)  # scale with days, cap at 2000
        api_max = max(api_max, max_results)  # at least max_results
        return self.search(cat_query, max_results=api_max)

    def _fetch_rss(self, categories: list[str]) -> list[Paper]:
        """Fetch the latest announcement day for the given categories via RSS.

        A single combined feed (cat1+cat2+...) covers every category at once.
        """
        if not categories:
            return []
        feed_url = ARXIV_RSS_URL + "+".join(categories)
        response = self._get_with_retry({}, url=feed_url)
        papers = self._parse_rss(response.text)
        self._save_cache_batch(papers)
        return papers

    def _parse_rss(self, xml_text: str) -> list[Paper]:
        """Parse an arXiv RSS feed into Paper objects.

        Keeps only new submissions and new cross-listings; drops revisions.
        """
        import re

        feed = feedparser.parse(xml_text)
        papers = []

        for entry in feed.entries:
            if entry.get("arxiv_announce_type") not in RSS_KEEP_ANNOUNCE:
                continue

            # id looks like "oai:arXiv.org:2606.02652v1"
            arxiv_id = entry.id.split(":")[-1]

            # summary is "arXiv:<id> Announce Type: <t> Abstract: <text>"
            parts = re.split(r"Abstract:\s*", entry.get("summary", ""), maxsplit=1)
            abstract = (parts[1] if len(parts) > 1 else entry.get("summary", ""))
            abstract = abstract.replace("\n", " ").strip()

            authors = [a.strip() for a in entry.get("author", "").split(",") if a.strip()]
            categories = [tag.term for tag in entry.get("tags", []) if tag.get("term")]

            if entry.get("published_parsed"):
                published = datetime(*entry.published_parsed[:6])
            else:
                published = datetime.now()

            papers.append(
                Paper(
                    arxiv_id=arxiv_id,
                    title=entry.title.replace("\n", " ").strip(),
                    abstract=abstract,
                    authors=authors,
                    categories=categories,
                    published=published,
                    updated=None,
                    pdf_url=f"https://arxiv.org/pdf/{arxiv_id}",
                )
            )

        return papers

    def _fetch_oai(self, categories: list[str], days: int) -> list[Paper]:
        """Harvest a recent date range via OAI-PMH (multi-day path).

        OAI sets are archive-level, so we request one ListRecords per archive
        covering the requested fine-grained categories, page through with
        resumption tokens (bounded), then keep only papers that actually carry
        one of the requested categories.
        """
        if not categories:
            return []

        until = datetime.now().date()
        start = until - timedelta(days=days)
        wanted = set(categories)
        archives = sorted({c.split(".")[0] for c in categories})

        papers_by_id: dict[str, Paper] = {}
        for archive in archives:
            token: str | None = None
            for _ in range(OAI_MAX_PAGES_PER_ARCHIVE):
                if token:
                    params = {"verb": "ListRecords", "resumptionToken": token}
                else:
                    params = {
                        "verb": "ListRecords",
                        "metadataPrefix": "arXiv",
                        "set": archive,
                        "from": start.isoformat(),
                        "until": until.isoformat(),
                    }
                response = self._get_with_retry(params, url=ARXIV_OAI_URL)
                records, token = self._parse_oai(response.text)
                for paper in records:
                    if wanted.intersection(paper.categories):
                        papers_by_id[paper.arxiv_id] = paper
                if not token or len(papers_by_id) >= OAI_TARGET_RECORDS:
                    break
            if len(papers_by_id) >= OAI_TARGET_RECORDS:
                break

        papers = list(papers_by_id.values())
        self._save_cache_batch(papers)
        return papers

    @staticmethod
    def _parse_oai(xml_text: str) -> tuple[list[Paper], str | None]:
        """Parse an OAI-PMH ListRecords response (arXiv metadata format).

        Returns (papers, resumption_token). Raises on an OAI error element.
        """
        import xml.etree.ElementTree as ET

        oai = "{http://www.openarchives.org/OAI/2.0/}"
        arx = "{http://arxiv.org/OAI/arXiv/}"

        root = ET.fromstring(xml_text)

        error = root.find(f"{oai}error")
        if error is not None:
            # An empty date range is a normal, non-fatal outcome.
            if error.get("code") == "noRecordsMatch":
                return [], None
            raise RuntimeError(f"OAI error [{error.get('code')}]: {error.text}")

        list_records = root.find(f"{oai}ListRecords")
        if list_records is None:
            return [], None

        papers = []
        for record in list_records.findall(f"{oai}record"):
            header = record.find(f"{oai}header")
            if header is not None and header.get("status") == "deleted":
                continue
            meta = record.find(f"{oai}metadata")
            if meta is None:
                continue
            arxiv_el = meta.find(f"{arx}arXiv")
            if arxiv_el is None:
                continue

            arxiv_id = (arxiv_el.findtext(f"{arx}id") or "").strip()
            if not arxiv_id:
                continue

            categories = (arxiv_el.findtext(f"{arx}categories") or "").split()

            authors = []
            authors_el = arxiv_el.find(f"{arx}authors")
            if authors_el is not None:
                for author in authors_el.findall(f"{arx}author"):
                    keyname = (author.findtext(f"{arx}keyname") or "").strip()
                    forenames = (author.findtext(f"{arx}forenames") or "").strip()
                    name = f"{forenames} {keyname}".strip()
                    if name:
                        authors.append(name)

            published = ArxivClient._parse_oai_date(arxiv_el.findtext(f"{arx}created"))
            updated = ArxivClient._parse_oai_date(arxiv_el.findtext(f"{arx}updated"))

            papers.append(
                Paper(
                    arxiv_id=arxiv_id,
                    title=(arxiv_el.findtext(f"{arx}title") or "").replace("\n", " ").strip(),
                    abstract=(arxiv_el.findtext(f"{arx}abstract") or "").replace("\n", " ").strip(),
                    authors=authors,
                    categories=categories,
                    published=published or datetime.now(),
                    updated=updated,
                    pdf_url=f"https://arxiv.org/pdf/{arxiv_id}",
                )
            )

        token_el = list_records.find(f"{oai}resumptionToken")
        token = token_el.text.strip() if token_el is not None and token_el.text else None
        return papers, (token or None)

    @staticmethod
    def _parse_oai_date(value: str | None) -> datetime | None:
        """Parse an OAI 'YYYY-MM-DD' date string."""
        if not value:
            return None
        try:
            return datetime.strptime(value.strip(), "%Y-%m-%d")
        except ValueError:
            return None

    def get_paper(self, arxiv_id: str) -> Paper | None:
        """Get a specific paper (cache-first)."""
        cached = self._get_cached(arxiv_id)
        if cached:
            return cached

        params = {"id_list": arxiv_id}

        response = self._get_with_retry(params)
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
            row = conn.execute("SELECT * FROM papers WHERE arxiv_id = ?", (arxiv_id,)).fetchone()
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
    def _categories_hash(categories: list[str]) -> str:
        """Deterministic hash of sorted category names."""
        key = ",".join(sorted(categories))
        return hashlib.sha256(key.encode()).hexdigest()[:16]

    def _get_fetch_cache(self, fetch_date: str, days: int, cat_hash: str) -> list[Paper] | None:
        """Look up cached fetch result. Returns papers or None."""
        with get_connection() as conn:
            row = conn.execute(
                "SELECT paper_ids FROM daily_fetch_cache "
                "WHERE fetch_date = ? AND days = ? AND categories_hash = ?",
                (fetch_date, days, cat_hash),
            ).fetchone()
        if row is None:
            return None
        paper_ids = json.loads(row["paper_ids"])
        if not paper_ids:
            return []
        return list(self._get_cached_batch(paper_ids).values())

    def _save_fetch_cache(
        self, fetch_date: str, days: int, cat_hash: str, paper_ids: list[str]
    ) -> None:
        """Save a fetch cache entry."""
        with get_connection() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO daily_fetch_cache
                   (fetch_date, days, categories_hash, paper_ids)
                   VALUES (?, ?, ?, ?)""",
                (fetch_date, days, cat_hash, json.dumps(paper_ids)),
            )
            conn.commit()

    def _cleanup_stale_cache(self) -> None:
        """Remove cache entries older than 7 days."""
        with get_connection() as conn:
            conn.execute("DELETE FROM daily_fetch_cache WHERE fetch_date < date('now', '-7 days')")
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
