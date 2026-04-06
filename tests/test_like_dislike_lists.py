"""Tests for Like/Dislike system lists and dual-storage behaviour."""

import sqlite3
from unittest.mock import patch

import pytest

from arxiv_explorer.core.config import Config
from arxiv_explorer.core.database import init_db
from arxiv_explorer.services.preference_service import PreferenceService
from arxiv_explorer.services.reading_list_service import ReadingListService


@pytest.fixture
def db(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    return db_path


@pytest.fixture
def config(db, tmp_path):
    return Config(db_path=db, arxivterminal_db_path=tmp_path / "at.db")


@pytest.fixture
def pref_svc(config):
    with patch("arxiv_explorer.core.database.get_config", return_value=config):
        yield PreferenceService()


@pytest.fixture
def list_svc(config):
    with patch("arxiv_explorer.core.database.get_config", return_value=config):
        yield ReadingListService()


class TestSystemListsCreation:
    def test_like_list_created(self, db):
        with sqlite3.connect(db) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM reading_lists WHERE name = 'Like' AND is_system = 1"
            ).fetchone()
            assert row is not None
            assert row["is_folder"] == 0

    def test_dislike_list_created(self, db):
        with sqlite3.connect(db) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM reading_lists WHERE name = 'Dislike' AND is_system = 1"
            ).fetchone()
            assert row is not None
            assert row["is_folder"] == 0

    def test_idempotent(self, db):
        init_db(db)  # Run again
        with sqlite3.connect(db) as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM reading_lists WHERE is_system = 1"
            ).fetchone()[0]
            assert count == 2


class TestDualStorage:
    def test_mark_interesting_adds_to_like_list(self, pref_svc, list_svc):
        pref_svc.mark_interesting("2401.00001")
        interaction = pref_svc.get_interaction("2401.00001")
        assert interaction is not None
        like_list = list_svc.get_list("Like")
        papers = list_svc.get_papers_by_list_id(like_list.id)
        arxiv_ids = {p.arxiv_id for p in papers}
        assert "2401.00001" in arxiv_ids

    def test_mark_not_interesting_adds_to_dislike_list(self, pref_svc, list_svc):
        pref_svc.mark_not_interesting("2401.00001")
        dislike_list = list_svc.get_list("Dislike")
        papers = list_svc.get_papers_by_list_id(dislike_list.id)
        arxiv_ids = {p.arxiv_id for p in papers}
        assert "2401.00001" in arxiv_ids

    def test_switch_like_to_dislike(self, pref_svc, list_svc):
        pref_svc.mark_interesting("2401.00001")
        pref_svc.mark_not_interesting("2401.00001")
        like_list = list_svc.get_list("Like")
        like_papers = list_svc.get_papers_by_list_id(like_list.id)
        assert all(p.arxiv_id != "2401.00001" for p in like_papers)
        dislike_list = list_svc.get_list("Dislike")
        dislike_papers = list_svc.get_papers_by_list_id(dislike_list.id)
        assert any(p.arxiv_id == "2401.00001" for p in dislike_papers)

    def test_switch_dislike_to_like(self, pref_svc, list_svc):
        pref_svc.mark_not_interesting("2401.00001")
        pref_svc.mark_interesting("2401.00001")
        dislike_list = list_svc.get_list("Dislike")
        dislike_papers = list_svc.get_papers_by_list_id(dislike_list.id)
        assert all(p.arxiv_id != "2401.00001" for p in dislike_papers)
        like_list = list_svc.get_list("Like")
        like_papers = list_svc.get_papers_by_list_id(like_list.id)
        assert any(p.arxiv_id == "2401.00001" for p in like_papers)
