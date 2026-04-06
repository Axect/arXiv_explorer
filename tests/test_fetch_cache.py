"""Tests for daily fetch cache in ArxivClient."""

import hashlib
import json
from datetime import datetime
from unittest.mock import patch

import pytest

from arxiv_explorer.core.config import Config
from arxiv_explorer.core.database import get_connection
from arxiv_explorer.core.models import Paper
from arxiv_explorer.services.arxiv_client import ArxivClient


@pytest.fixture()
def client(tmp_config: Config) -> ArxivClient:
    return ArxivClient()


def _make_paper(arxiv_id: str, days_ago: int = 0) -> Paper:
    from datetime import timedelta

    return Paper(
        arxiv_id=arxiv_id,
        title=f"Paper {arxiv_id}",
        abstract="Abstract text",
        authors=["Author"],
        categories=["cs.LG"],
        published=datetime.now() - timedelta(days=days_ago),
    )


class TestCacheKey:
    def test_categories_hash_is_deterministic(self, client: ArxivClient):
        h1 = client._categories_hash(["cs.LG", "hep-ph"])
        h2 = client._categories_hash(["hep-ph", "cs.LG"])
        assert h1 == h2, "Hash should be order-independent"

    def test_categories_hash_differs_for_different_sets(self, client: ArxivClient):
        h1 = client._categories_hash(["cs.LG"])
        h2 = client._categories_hash(["cs.AI"])
        assert h1 != h2


class TestFetchCache:
    def test_cache_miss_returns_none(self, client: ArxivClient):
        result = client._get_fetch_cache("2026-04-07", 7, "somehash")
        assert result is None

    def test_cache_roundtrip(self, client: ArxivClient, tmp_config: Config):
        paper_ids = ["2401.00001", "2401.00002"]
        for pid in paper_ids:
            p = _make_paper(pid)
            client._save_cache_batch([p])

        cat_hash = client._categories_hash(["cs.LG"])
        client._save_fetch_cache("2026-04-07", 7, cat_hash, paper_ids)

        cached = client._get_fetch_cache("2026-04-07", 7, cat_hash)
        assert cached is not None
        assert len(cached) == 2
        assert {p.arxiv_id for p in cached} == set(paper_ids)

    def test_cache_miss_on_different_days(self, client: ArxivClient, tmp_config: Config):
        cat_hash = client._categories_hash(["cs.LG"])
        client._save_fetch_cache("2026-04-07", 7, cat_hash, ["2401.00001"])

        result = client._get_fetch_cache("2026-04-07", 14, cat_hash)
        assert result is None

    def test_cache_miss_on_different_date(self, client: ArxivClient, tmp_config: Config):
        cat_hash = client._categories_hash(["cs.LG"])
        client._save_fetch_cache("2026-04-07", 7, cat_hash, ["2401.00001"])

        result = client._get_fetch_cache("2026-04-08", 7, cat_hash)
        assert result is None

    def test_stale_cache_cleanup(self, client: ArxivClient, tmp_config: Config):
        cat_hash = client._categories_hash(["cs.LG"])
        with get_connection() as conn:
            conn.execute(
                """INSERT INTO daily_fetch_cache
                   (fetch_date, days, categories_hash, paper_ids, created_at)
                   VALUES (?, ?, ?, ?, datetime('now', '-10 days'))""",
                ("2026-03-28", 7, cat_hash, json.dumps(["old"])),
            )
            conn.commit()

        client._cleanup_stale_cache()

        with get_connection() as conn:
            row = conn.execute("SELECT COUNT(*) FROM daily_fetch_cache").fetchone()
            assert row[0] == 0


class TestDateRangeQuery:
    def test_builds_date_range_query(self, client: ArxivClient):
        query = client._build_date_range_query(["cs.LG", "hep-ph"], days=7)
        assert "cat:cs.LG" in query
        assert "cat:hep-ph" in query
        assert "submittedDate:" in query
