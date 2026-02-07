"""Tests for database initialization and connection management."""

import sqlite3

import pytest

from arxiv_explorer.core.config import Config
from arxiv_explorer.core.database import get_connection, init_db

EXPECTED_TABLES = {
    "preferred_categories",
    "paper_interactions",
    "paper_summaries",
    "reading_lists",
    "reading_list_papers",
    "paper_notes",
    "keyword_interests",
    "paper_translations",
    "app_settings",
    "papers",
}


class TestInitDb:
    """Tests for init_db()."""

    def test_creates_all_tables(self, tmp_config: Config):
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
            tables = {row["name"] for row in rows}

        assert tables == EXPECTED_TABLES

    def test_idempotent(self, tmp_config: Config):
        """Running init_db twice should not raise or corrupt."""
        init_db(tmp_config.db_path)
        init_db(tmp_config.db_path)

        with get_connection() as conn:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
            tables = {row["name"] for row in rows}

        assert tables == EXPECTED_TABLES

    def test_creates_indexes(self, tmp_config: Config):
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'"
            ).fetchall()
            indexes = {row["name"] for row in rows}

        expected_indexes = {
            "idx_interactions_arxiv",
            "idx_interactions_type",
            "idx_notes_arxiv",
            "idx_list_papers_list",
            "idx_translations_arxiv",
            "idx_papers_cached_at",
        }
        assert indexes == expected_indexes


class TestGetConnection:
    """Tests for get_connection()."""

    def test_row_factory(self, tmp_config: Config):
        """Connection should use sqlite3.Row for dict-like access."""
        with get_connection() as conn:
            assert conn.row_factory is sqlite3.Row

    def test_connection_closes(self, tmp_config: Config):
        """Connection should be closed after context manager exits."""
        with get_connection() as conn:
            pass
        # Attempting to use a closed connection raises ProgrammingError
        with pytest.raises(sqlite3.ProgrammingError):
            conn.execute("SELECT 1")

    def test_data_persists(self, tmp_config: Config):
        """Data written in one connection should be readable in another."""
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO preferred_categories (category, priority) VALUES (?, ?)",
                ("cs.AI", 1),
            )
            conn.commit()

        with get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM preferred_categories WHERE category = 'cs.AI'"
            ).fetchone()
            assert row is not None
            assert row["category"] == "cs.AI"
