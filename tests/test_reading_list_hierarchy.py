"""Tests for reading list hierarchy (parent_id, is_folder, is_system)."""

import sqlite3
from datetime import datetime
from pathlib import Path

import pytest

from arxiv_explorer.core.database import init_db, get_connection
from arxiv_explorer.core.models import ReadingList


@pytest.fixture
def db(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    return db_path


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
            conn.execute(
                "INSERT INTO reading_lists (name, is_folder) VALUES ('parent', 1)"
            )
            parent_id = conn.execute(
                "SELECT id FROM reading_lists WHERE name='parent'"
            ).fetchone()[0]
            conn.execute(
                "INSERT INTO reading_lists (name, parent_id) VALUES ('child', ?)",
                (parent_id,),
            )
            row = conn.execute(
                "SELECT parent_id FROM reading_lists WHERE name='child'"
            ).fetchone()
            assert row[0] == parent_id

    def test_cascade_delete(self, db):
        with sqlite3.connect(db) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute(
                "INSERT INTO reading_lists (name, is_folder) VALUES ('parent', 1)"
            )
            parent_id = conn.execute(
                "SELECT id FROM reading_lists WHERE name='parent'"
            ).fetchone()[0]
            conn.execute(
                "INSERT INTO reading_lists (name, parent_id) VALUES ('child', ?)",
                (parent_id,),
            )
            conn.execute("DELETE FROM reading_lists WHERE name='parent'")
            row = conn.execute(
                "SELECT * FROM reading_lists WHERE name='child'"
            ).fetchone()
            assert row is None


class TestReadingListModel:
    def test_has_parent_id(self):
        rl = ReadingList(
            id=1, name="test", description=None,
            parent_id=None, is_folder=False, is_system=False,
            created_at=datetime.now(),
        )
        assert rl.parent_id is None

    def test_has_is_folder(self):
        rl = ReadingList(
            id=1, name="folder", description=None,
            parent_id=None, is_folder=True, is_system=False,
            created_at=datetime.now(),
        )
        assert rl.is_folder is True

    def test_has_is_system(self):
        rl = ReadingList(
            id=1, name="Like", description=None,
            parent_id=None, is_folder=False, is_system=True,
            created_at=datetime.now(),
        )
        assert rl.is_system is True
