import sqlite3
from datetime import datetime
from unittest.mock import patch

import pytest

from arxiv_explorer.core.config import Config
from arxiv_explorer.core.database import init_db
from arxiv_explorer.core.models import PreferredAuthor
from arxiv_explorer.services.author_service import AuthorService, matches_author


@pytest.fixture
def db(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    return db_path


class TestAuthorSchema:
    def test_preferred_authors_table_exists(self, db):
        with sqlite3.connect(db) as conn:
            tables = {
                r[0]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            assert "preferred_authors" in tables

    def test_preferred_author_model(self):
        author = PreferredAuthor(id=1, name="Dong Woo Kang", added_at=datetime.now())
        assert author.name == "Dong Woo Kang"


class TestAuthorMatching:
    def test_exact_match(self):
        assert matches_author("Dong Woo Kang", "Dong Woo Kang") is True

    def test_initial_match(self):
        assert matches_author("Dong Woo Kang", "D. W. Kang") is True

    def test_initial_no_dot(self):
        assert matches_author("Dong Woo Kang", "D W Kang") is True

    def test_whitespace_merge(self):
        assert matches_author("Dong Woo Kang", "Dongwoo Kang") is True

    def test_partial_first_name_no_match(self):
        assert matches_author("Dong Woo Kang", "D. Kang") is False

    def test_last_name_only_no_match(self):
        assert matches_author("Dong Woo Kang", "Kang") is False

    def test_wrong_last_name(self):
        assert matches_author("Dong Woo Kang", "Dong Woo Kim") is False

    def test_case_insensitive(self):
        assert matches_author("dong woo kang", "DONG WOO KANG") is True

    def test_single_first_name_exact(self):
        assert matches_author("John Smith", "John Smith") is True

    def test_single_first_name_initial(self):
        assert matches_author("John Smith", "J. Smith") is True

    def test_single_first_name_wrong_initial(self):
        assert matches_author("John Smith", "K. Smith") is False

    def test_middle_name_initial(self):
        assert matches_author("John Robert Smith", "J. R. Smith") is True

    def test_middle_name_partial_missing(self):
        assert matches_author("John Robert Smith", "J. Smith") is False


@pytest.fixture
def author_svc(db, tmp_path):
    config = Config(db_path=db, arxivterminal_db_path=tmp_path / "at.db")
    with patch("arxiv_explorer.core.database.get_config", return_value=config):
        yield AuthorService()


class TestAuthorServiceCRUD:
    def test_add_author(self, author_svc):
        author = author_svc.add_author("John Smith")
        assert author.name == "John Smith"

    def test_get_authors(self, author_svc):
        author_svc.add_author("John Smith")
        author_svc.add_author("Alice Lee")
        authors = author_svc.get_authors()
        names = [a.name for a in authors]
        assert "Alice Lee" in names
        assert "John Smith" in names

    def test_remove_author(self, author_svc):
        author_svc.add_author("John Smith")
        result = author_svc.remove_author("John Smith")
        assert result is True
        assert len(author_svc.get_authors()) == 0

    def test_duplicate_add_ignored(self, author_svc):
        author_svc.add_author("John Smith")
        author_svc.add_author("John Smith")
        assert len(author_svc.get_authors()) == 1
