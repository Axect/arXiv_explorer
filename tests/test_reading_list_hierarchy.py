"""Tests for reading list hierarchy (parent_id, is_folder, is_system)."""

import sqlite3
from datetime import date, datetime
from unittest.mock import patch

import pytest

from arxiv_explorer.core.config import Config
from arxiv_explorer.core.database import init_db
from arxiv_explorer.core.models import ReadingList
from arxiv_explorer.services.reading_list_service import ReadingListService


@pytest.fixture
def db(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    return db_path


@pytest.fixture
def svc(db, tmp_path):
    config = Config(db_path=db, arxivterminal_db_path=tmp_path / "at.db")
    with patch("arxiv_explorer.core.database.get_config", return_value=config):
        yield ReadingListService()


class TestHierarchySchema:
    def test_reading_lists_has_parent_id_column(self, db):
        with sqlite3.connect(db) as conn:
            cursor = conn.execute("PRAGMA table_info(reading_lists)")
            columns = {row[1] for row in cursor.fetchall()}
            assert "parent_id" in columns

    def test_reading_lists_has_is_folder_column(self, db):
        with sqlite3.connect(db) as conn:
            cursor = conn.execute("PRAGMA table_info(reading_lists)")
            columns = {row[1] for row in cursor.fetchall()}
            assert "is_folder" in columns

    def test_reading_lists_has_is_system_column(self, db):
        with sqlite3.connect(db) as conn:
            cursor = conn.execute("PRAGMA table_info(reading_lists)")
            columns = {row[1] for row in cursor.fetchall()}
            assert "is_system" in columns

    def test_parent_id_foreign_key(self, db):
        with sqlite3.connect(db) as conn:
            conn.execute("INSERT INTO reading_lists (name, is_folder) VALUES ('parent', 1)")
            parent_id = conn.execute("SELECT id FROM reading_lists WHERE name='parent'").fetchone()[
                0
            ]
            conn.execute(
                "INSERT INTO reading_lists (name, parent_id) VALUES ('child', ?)",
                (parent_id,),
            )
            row = conn.execute("SELECT parent_id FROM reading_lists WHERE name='child'").fetchone()
            assert row[0] == parent_id

    def test_cascade_delete(self, db):
        with sqlite3.connect(db) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("INSERT INTO reading_lists (name, is_folder) VALUES ('parent', 1)")
            parent_id = conn.execute("SELECT id FROM reading_lists WHERE name='parent'").fetchone()[
                0
            ]
            conn.execute(
                "INSERT INTO reading_lists (name, parent_id) VALUES ('child', ?)",
                (parent_id,),
            )
            conn.execute("DELETE FROM reading_lists WHERE name='parent'")
            row = conn.execute("SELECT * FROM reading_lists WHERE name='child'").fetchone()
            assert row is None


class TestReadingListModel:
    def test_has_parent_id(self):
        rl = ReadingList(
            id=1,
            name="test",
            description=None,
            parent_id=None,
            is_folder=False,
            is_system=False,
            created_at=datetime.now(),
        )
        assert rl.parent_id is None

    def test_has_is_folder(self):
        rl = ReadingList(
            id=1,
            name="folder",
            description=None,
            parent_id=None,
            is_folder=True,
            is_system=False,
            created_at=datetime.now(),
        )
        assert rl.is_folder is True

    def test_has_is_system(self):
        rl = ReadingList(
            id=1,
            name="Like",
            description=None,
            parent_id=None,
            is_folder=False,
            is_system=True,
            created_at=datetime.now(),
        )
        assert rl.is_system is True


class TestFolderOperations:
    def test_create_folder(self, svc):
        folder = svc.create_folder("202604")
        assert folder.name == "202604"
        assert folder.is_folder is True
        assert folder.parent_id is None

    def test_create_nested_list_in_folder(self, svc):
        folder = svc.create_folder("202604")
        lst = svc.create_list("reading", description=None, parent_id=folder.id)
        assert lst.parent_id == folder.id
        assert lst.is_folder is False

    def test_get_children(self, svc):
        folder = svc.create_folder("202604")
        svc.create_list("list1", description=None, parent_id=folder.id)
        svc.create_list("list2", description=None, parent_id=folder.id)
        children = svc.get_children(folder.id)
        assert len(children) == 2
        names = {c.name for c in children}
        assert names == {"list1", "list2"}

    def test_get_top_level(self, svc):
        svc.create_folder("202604")
        svc.create_list("standalone", description=None)
        top = svc.get_top_level()
        names = {item.name for item in top}
        assert "202604" in names
        assert "standalone" in names

    def test_rename_item(self, svc):
        folder = svc.create_folder("202604")
        result = svc.rename_item(folder.id, "202605")
        assert result is True
        updated = svc.get_list_by_id(folder.id)
        assert updated.name == "202605"

    def test_rename_system_list_fails(self, svc):
        from arxiv_explorer.core.database import get_connection

        with get_connection() as conn:
            conn.execute("INSERT INTO reading_lists (name, is_system) VALUES ('Like', 1)")
        like = svc.get_list("Like")
        result = svc.rename_item(like.id, "Favorites")
        assert result is False


class TestMoveAndCopy:
    def test_move_paper(self, svc):
        folder_a = svc.create_folder("FolderA")
        folder_b = svc.create_folder("FolderB")
        svc.add_paper_to_list(folder_a.id, "2401.00001")
        result = svc.move_paper(folder_a.id, folder_b.id, "2401.00001")
        assert result is True
        papers_a = svc.get_papers_by_list_id(folder_a.id)
        papers_b = svc.get_papers_by_list_id(folder_b.id)
        assert len(papers_a) == 0
        assert len(papers_b) == 1

    def test_copy_paper(self, svc):
        folder_a = svc.create_folder("FolderA")
        folder_b = svc.create_folder("FolderB")
        svc.add_paper_to_list(folder_a.id, "2401.00001")
        result = svc.copy_paper(folder_a.id, folder_b.id, "2401.00001")
        assert result is True
        papers_a = svc.get_papers_by_list_id(folder_a.id)
        papers_b = svc.get_papers_by_list_id(folder_b.id)
        assert len(papers_a) == 1
        assert len(papers_b) == 1

    def test_move_list(self, svc):
        folder_a = svc.create_folder("FolderA")
        folder_b = svc.create_folder("FolderB")
        lst = svc.create_list("mylist", parent_id=folder_a.id)
        result = svc.move_list(lst.id, folder_b.id)
        assert result is True
        moved = svc.get_list_by_id(lst.id)
        assert moved.parent_id == folder_b.id

    def test_copy_list(self, svc):
        folder_a = svc.create_folder("FolderA")
        folder_b = svc.create_folder("FolderB")
        lst = svc.create_list("mylist", parent_id=folder_a.id)
        svc.add_paper_to_list(lst.id, "2401.00001")
        new_list = svc.copy_list(lst.id, folder_b.id)
        assert new_list is not None
        assert new_list.parent_id == folder_b.id
        papers = svc.get_papers_by_list_id(new_list.id)
        assert len(papers) == 1


class TestMonthFolderToggle:
    def test_toggle_adds_paper(self, svc):
        added = svc.toggle_paper_in_month_folder("2401.00001", date(2026, 4, 6))
        assert added is True
        folders = svc.get_top_level()
        month_folders = [f for f in folders if f.name == "202604"]
        assert len(month_folders) == 1
        papers = svc.get_papers_by_list_id(month_folders[0].id)
        assert len(papers) == 1
        assert papers[0].arxiv_id == "2401.00001"

    def test_toggle_removes_paper(self, svc):
        svc.toggle_paper_in_month_folder("2401.00001", date(2026, 4, 6))
        removed = svc.toggle_paper_in_month_folder("2401.00001", date(2026, 4, 6))
        assert removed is False
        folders = svc.get_top_level()
        month_folders = [f for f in folders if f.name == "202604"]
        papers = svc.get_papers_by_list_id(month_folders[0].id)
        assert len(papers) == 0

    def test_auto_creates_month_folder(self, svc):
        svc.toggle_paper_in_month_folder("2401.00001", date(2026, 4, 6))
        folders = svc.get_top_level()
        month_folders = [f for f in folders if f.name == "202604"]
        assert len(month_folders) == 1
        assert month_folders[0].is_folder is True

    def test_reuses_existing_month_folder(self, svc):
        svc.toggle_paper_in_month_folder("2401.00001", date(2026, 4, 6))
        svc.toggle_paper_in_month_folder("2401.00002", date(2026, 4, 7))
        folders = svc.get_top_level()
        month_folders = [f for f in folders if f.name == "202604"]
        assert len(month_folders) == 1
        papers = svc.get_papers_by_list_id(month_folders[0].id)
        assert len(papers) == 2
