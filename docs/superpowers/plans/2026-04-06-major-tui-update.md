# arXiv Explorer Major TUI Update — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 6 features to arXiv Explorer: reading list hierarchy with month folder toggle, Like/Dislike system lists, preferred authors with dedicated Daily section, background job management, weight percentage system, and category fuzzy search with hierarchical browser.

**Architecture:** Each feature is a separate Gitflow branch off `dev`, touching 3 layers: DB schema (core/database.py), services, and TUI (Textual). Features 1→2 have a dependency; all others are independent.

**Tech Stack:** Python 3.11+, Textual 0.85+, SQLite, scikit-learn, Typer, Rich

**Design Spec:** `docs/superpowers/specs/2026-04-06-major-tui-update-design.md`

---

## File Structure Overview

### New Files
- `src/arxiv_explorer/core/arxiv_categories.py` — Static arXiv category taxonomy (~150 categories)
- `src/arxiv_explorer/services/author_service.py` — Author matching + preferred author CRUD
- `src/arxiv_explorer/services/job_manager.py` — In-memory background job tracking
- `src/arxiv_explorer/tui/screens/jobs_panel.py` — Jobs panel overlay
- `src/arxiv_explorer/tui/screens/category_picker.py` — Fuzzy search + hierarchical category browser
- `src/arxiv_explorer/tui/screens/folder_picker.py` — Folder/list picker for move/copy
- `tests/test_reading_list_hierarchy.py`
- `tests/test_like_dislike_lists.py`
- `tests/test_author_service.py`
- `tests/test_job_manager.py`
- `tests/test_weight_percentage.py`
- `tests/test_category_fuzzy.py`

### Modified Files
- `src/arxiv_explorer/core/models.py` — Add PreferredAuthor, Job, JobType, JobStatus; update ReadingList
- `src/arxiv_explorer/core/database.py` — Schema migrations for new columns + tables
- `src/arxiv_explorer/services/reading_list_service.py` — Hierarchy, move, copy, rename, toggle
- `src/arxiv_explorer/services/preference_service.py` — Dual storage for like/dislike
- `src/arxiv_explorer/services/paper_service.py` — Author section in daily papers
- `src/arxiv_explorer/services/recommendation.py` — Read weights from settings
- `src/arxiv_explorer/services/settings_service.py` — Weight percentage defaults
- `src/arxiv_explorer/tui/app.py` — Global `j` binding, Jobs status bar, JobManager
- `src/arxiv_explorer/tui/workers.py` — Add JobManager to ServiceBridge
- `src/arxiv_explorer/tui/screens/daily.py` — Author section, bookmark toggle, highlight styles
- `src/arxiv_explorer/tui/screens/reading_lists.py` — Tree view, folder ops, system lists
- `src/arxiv_explorer/tui/screens/preferences.py` — Authors section, weight bars, category picker
- `src/arxiv_explorer/tui/screens/paper_detail.py` — Use JobManager for async ops
- `src/arxiv_explorer/tui/widgets/paper_table.py` — Left border color coding
- `src/arxiv_explorer/tui/styles/app.tcss` — New styles for borders, jobs, weights

---

## Branch 1: `feature/reading-list-hierarchy`

### Task 1.1: DB Schema Migration

**Files:**
- Modify: `src/arxiv_explorer/core/database.py:10-124`
- Test: `tests/test_reading_list_hierarchy.py`

- [ ] **Step 1: Write failing test for new columns**

```python
# tests/test_reading_list_hierarchy.py
import sqlite3
from pathlib import Path
import pytest
from arxiv_explorer.core.database import init_db, get_connection


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/axect/Documents/Project/AI_Project/arXiv_explorer && uv run pytest tests/test_reading_list_hierarchy.py::TestHierarchySchema -v`
Expected: FAIL — columns not found

- [ ] **Step 3: Update schema in database.py**

In `src/arxiv_explorer/core/database.py`, replace the `reading_lists` table creation (lines 39-44) within the SCHEMA string:

```python
# Old:
CREATE TABLE IF NOT EXISTS reading_lists (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

# New:
CREATE TABLE IF NOT EXISTS reading_lists (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT,
    parent_id INTEGER REFERENCES reading_lists(id) ON DELETE CASCADE,
    is_folder BOOLEAN DEFAULT 0,
    is_system BOOLEAN DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(name, parent_id)
);
```

Note: The UNIQUE constraint changes from `name` alone to `(name, parent_id)` — folders can have same-named children under different parents.

Also add migration logic after `conn.executescript(SCHEMA)` in `init_db()` for existing databases:

```python
def init_db(db_path: Path | None = None) -> None:
    if db_path is None:
        db_path = get_config().db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.executescript(SCHEMA)
        # Migration: add new columns if missing (for existing DBs)
        existing_cols = {
            row[1] for row in conn.execute("PRAGMA table_info(reading_lists)").fetchall()
        }
        if "parent_id" not in existing_cols:
            conn.execute(
                "ALTER TABLE reading_lists ADD COLUMN parent_id INTEGER"
                " REFERENCES reading_lists(id) ON DELETE CASCADE"
            )
        if "is_folder" not in existing_cols:
            conn.execute(
                "ALTER TABLE reading_lists ADD COLUMN is_folder BOOLEAN DEFAULT 0"
            )
        if "is_system" not in existing_cols:
            conn.execute(
                "ALTER TABLE reading_lists ADD COLUMN is_system BOOLEAN DEFAULT 0"
            )
        conn.commit()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/axect/Documents/Project/AI_Project/arXiv_explorer && uv run pytest tests/test_reading_list_hierarchy.py::TestHierarchySchema -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /home/axect/Documents/Project/AI_Project/arXiv_explorer
git add src/arxiv_explorer/core/database.py tests/test_reading_list_hierarchy.py
git commit -m "feat: add hierarchy columns to reading_lists schema"
```

---

### Task 1.2: Update ReadingList Data Model

**Files:**
- Modify: `src/arxiv_explorer/core/models.py:118-125`
- Test: `tests/test_reading_list_hierarchy.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_reading_list_hierarchy.py`:

```python
from arxiv_explorer.core.models import ReadingList
from datetime import datetime


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_reading_list_hierarchy.py::TestReadingListModel -v`
Expected: FAIL — TypeError on unexpected keyword arguments

- [ ] **Step 3: Update ReadingList dataclass**

In `src/arxiv_explorer/core/models.py`, replace lines 118-125:

```python
# Old:
@dataclass
class ReadingList:
    id: int
    name: str
    description: str | None
    created_at: datetime

# New:
@dataclass
class ReadingList:
    id: int
    name: str
    description: str | None
    parent_id: int | None
    is_folder: bool
    is_system: bool
    created_at: datetime
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_reading_list_hierarchy.py::TestReadingListModel -v`
Expected: PASS

- [ ] **Step 5: Fix all existing code that constructs ReadingList**

The `ReadingListService` methods that create `ReadingList` from DB rows need updating. In `src/arxiv_explorer/services/reading_list_service.py`, update every place that constructs `ReadingList`:

In `create_list` (around line 22-27):
```python
# Old:
return ReadingList(
    id=row["id"], name=row["name"],
    description=row["description"], created_at=row["created_at"],
)

# New:
return ReadingList(
    id=row["id"], name=row["name"],
    description=row["description"],
    parent_id=row["parent_id"],
    is_folder=bool(row["is_folder"]),
    is_system=bool(row["is_system"]),
    created_at=row["created_at"],
)
```

Apply the same pattern to `get_list` (around line 44-48) and `get_all_lists` (around line 57-62). Every `ReadingList(...)` constructor must include the three new fields.

Also update the `create_list` INSERT statement to include the new columns:
```python
# Old:
conn.execute(
    "INSERT INTO reading_lists (name, description) VALUES (?, ?)",
    (name, description),
)

# New:
conn.execute(
    "INSERT INTO reading_lists (name, description, parent_id, is_folder, is_system)"
    " VALUES (?, ?, NULL, 0, 0)",
    (name, description),
)
```

- [ ] **Step 6: Run full test suite**

Run: `uv run pytest -v`
Expected: All existing tests pass (some may need fixture updates for the new fields)

- [ ] **Step 7: Fix any broken tests**

Update `tests/conftest.py` and any test that constructs ReadingList to include the new fields. Typical fix:

```python
# Wherever ReadingList is constructed in tests, add:
parent_id=None, is_folder=False, is_system=False,
```

- [ ] **Step 8: Commit**

```bash
git add src/arxiv_explorer/core/models.py src/arxiv_explorer/services/reading_list_service.py tests/
git commit -m "feat: add parent_id, is_folder, is_system to ReadingList model"
```

---

### Task 1.3: Hierarchy Service Methods

**Files:**
- Modify: `src/arxiv_explorer/services/reading_list_service.py`
- Test: `tests/test_reading_list_hierarchy.py`

- [ ] **Step 1: Write failing tests for folder operations**

Append to `tests/test_reading_list_hierarchy.py`:

```python
from unittest.mock import patch
from arxiv_explorer.core.config import Config
from arxiv_explorer.services.reading_list_service import ReadingListService


@pytest.fixture
def svc(db, tmp_path):
    config = Config(db_path=db, arxivterminal_db_path=tmp_path / "at.db")
    with patch("arxiv_explorer.services.reading_list_service.get_config", return_value=config):
        yield ReadingListService()


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
        # System lists cannot be renamed
        from arxiv_explorer.core.database import get_connection
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO reading_lists (name, is_system) VALUES ('Like', 1)"
            )
        like = svc.get_list("Like")
        result = svc.rename_item(like.id, "Favorites")
        assert result is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_reading_list_hierarchy.py::TestFolderOperations -v`
Expected: FAIL — methods not found

- [ ] **Step 3: Implement folder operations**

Add to `src/arxiv_explorer/services/reading_list_service.py`:

```python
def create_folder(self, name: str, parent_id: int | None = None) -> ReadingList:
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO reading_lists (name, parent_id, is_folder, is_system)"
            " VALUES (?, ?, 1, 0)",
            (name, parent_id),
        )
        row = conn.execute(
            "SELECT * FROM reading_lists WHERE id = last_insert_rowid()"
        ).fetchone()
        return self._row_to_reading_list(row)

def create_list(
    self, name: str, description: str | None = None, parent_id: int | None = None
) -> ReadingList:
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO reading_lists (name, description, parent_id, is_folder, is_system)"
            " VALUES (?, ?, ?, 0, 0)",
            (name, description, parent_id),
        )
        row = conn.execute(
            "SELECT * FROM reading_lists WHERE id = last_insert_rowid()"
        ).fetchone()
        return self._row_to_reading_list(row)

def get_children(self, parent_id: int) -> list[ReadingList]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM reading_lists WHERE parent_id = ? ORDER BY name",
            (parent_id,),
        ).fetchall()
        return [self._row_to_reading_list(r) for r in rows]

def get_top_level(self) -> list[ReadingList]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM reading_lists WHERE parent_id IS NULL ORDER BY is_system DESC, name"
        ).fetchall()
        return [self._row_to_reading_list(r) for r in rows]

def get_list_by_id(self, list_id: int) -> ReadingList | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM reading_lists WHERE id = ?", (list_id,)
        ).fetchone()
        return self._row_to_reading_list(row) if row else None

def rename_item(self, list_id: int, new_name: str) -> bool:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT is_system FROM reading_lists WHERE id = ?", (list_id,)
        ).fetchone()
        if not row or bool(row["is_system"]):
            return False
        conn.execute(
            "UPDATE reading_lists SET name = ? WHERE id = ?",
            (new_name, list_id),
        )
        return True

def _row_to_reading_list(self, row) -> ReadingList:
    return ReadingList(
        id=row["id"],
        name=row["name"],
        description=row["description"],
        parent_id=row["parent_id"],
        is_folder=bool(row["is_folder"]),
        is_system=bool(row["is_system"]),
        created_at=row["created_at"],
    )
```

Update all existing methods (`get_list`, `get_all_lists`, `delete_list`) to use `_row_to_reading_list()`. Also update `delete_list` to reject system lists:

```python
def delete_list(self, name: str) -> bool:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT is_system FROM reading_lists WHERE name = ? AND parent_id IS NULL",
            (name,),
        ).fetchone()
        if not row or bool(row["is_system"]):
            return False
        conn.execute(
            "DELETE FROM reading_lists WHERE name = ? AND parent_id IS NULL",
            (name,),
        )
        return conn.total_changes > 0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_reading_list_hierarchy.py::TestFolderOperations -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/arxiv_explorer/services/reading_list_service.py tests/test_reading_list_hierarchy.py
git commit -m "feat: add folder hierarchy operations to ReadingListService"
```

---

### Task 1.4: Move, Copy, and Month Folder Toggle

**Files:**
- Modify: `src/arxiv_explorer/services/reading_list_service.py`
- Test: `tests/test_reading_list_hierarchy.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_reading_list_hierarchy.py`:

```python
from datetime import date


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_reading_list_hierarchy.py::TestMoveAndCopy -v && uv run pytest tests/test_reading_list_hierarchy.py::TestMonthFolderToggle -v`
Expected: FAIL

- [ ] **Step 3: Implement move, copy, and toggle methods**

Add to `src/arxiv_explorer/services/reading_list_service.py`:

```python
from datetime import date

def add_paper_to_list(self, list_id: int, arxiv_id: str) -> bool:
    with get_connection() as conn:
        try:
            max_pos = conn.execute(
                "SELECT COALESCE(MAX(position), 0) FROM reading_list_papers WHERE list_id = ?",
                (list_id,),
            ).fetchone()[0]
            conn.execute(
                "INSERT INTO reading_list_papers (list_id, arxiv_id, status, position)"
                " VALUES (?, ?, 'unread', ?)",
                (list_id, arxiv_id, max_pos + 1),
            )
            return True
        except Exception:
            return False

def get_papers_by_list_id(self, list_id: int) -> list[ReadingListPaper]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM reading_list_papers WHERE list_id = ? ORDER BY added_at DESC",
            (list_id,),
        ).fetchall()
        return [
            ReadingListPaper(
                id=r["id"], list_id=r["list_id"], arxiv_id=r["arxiv_id"],
                status=ReadingStatus(r["status"]), position=r["position"],
                added_at=r["added_at"],
            )
            for r in rows
        ]

def move_paper(self, from_list_id: int, to_list_id: int, arxiv_id: str) -> bool:
    with get_connection() as conn:
        conn.execute(
            "DELETE FROM reading_list_papers WHERE list_id = ? AND arxiv_id = ?",
            (from_list_id, arxiv_id),
        )
        if conn.total_changes == 0:
            return False
        max_pos = conn.execute(
            "SELECT COALESCE(MAX(position), 0) FROM reading_list_papers WHERE list_id = ?",
            (to_list_id,),
        ).fetchone()[0]
        conn.execute(
            "INSERT OR IGNORE INTO reading_list_papers (list_id, arxiv_id, status, position)"
            " VALUES (?, ?, 'unread', ?)",
            (to_list_id, arxiv_id, max_pos + 1),
        )
        return True

def copy_paper(self, from_list_id: int, to_list_id: int, arxiv_id: str) -> bool:
    with get_connection() as conn:
        exists = conn.execute(
            "SELECT 1 FROM reading_list_papers WHERE list_id = ? AND arxiv_id = ?",
            (from_list_id, arxiv_id),
        ).fetchone()
        if not exists:
            return False
        max_pos = conn.execute(
            "SELECT COALESCE(MAX(position), 0) FROM reading_list_papers WHERE list_id = ?",
            (to_list_id,),
        ).fetchone()[0]
        conn.execute(
            "INSERT OR IGNORE INTO reading_list_papers (list_id, arxiv_id, status, position)"
            " VALUES (?, ?, 'unread', ?)",
            (to_list_id, arxiv_id, max_pos + 1),
        )
        return True

def move_list(self, list_id: int, target_folder_id: int | None) -> bool:
    with get_connection() as conn:
        conn.execute(
            "UPDATE reading_lists SET parent_id = ? WHERE id = ?",
            (target_folder_id, list_id),
        )
        return conn.total_changes > 0

def copy_list(self, list_id: int, target_folder_id: int | None) -> ReadingList | None:
    with get_connection() as conn:
        source = conn.execute(
            "SELECT * FROM reading_lists WHERE id = ?", (list_id,)
        ).fetchone()
        if not source:
            return None
        conn.execute(
            "INSERT INTO reading_lists (name, description, parent_id, is_folder, is_system)"
            " VALUES (?, ?, ?, ?, 0)",
            (source["name"], source["description"], target_folder_id, source["is_folder"]),
        )
        new_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        # Copy all papers
        papers = conn.execute(
            "SELECT arxiv_id, status, position FROM reading_list_papers WHERE list_id = ?",
            (list_id,),
        ).fetchall()
        for p in papers:
            conn.execute(
                "INSERT INTO reading_list_papers (list_id, arxiv_id, status, position)"
                " VALUES (?, ?, ?, ?)",
                (new_id, p["arxiv_id"], p["status"], p["position"]),
            )
        row = conn.execute(
            "SELECT * FROM reading_lists WHERE id = ?", (new_id,)
        ).fetchone()
        return self._row_to_reading_list(row)

def remove_paper_from_list(self, list_id: int, arxiv_id: str) -> bool:
    with get_connection() as conn:
        conn.execute(
            "DELETE FROM reading_list_papers WHERE list_id = ? AND arxiv_id = ?",
            (list_id, arxiv_id),
        )
        return conn.total_changes > 0

def toggle_paper_in_month_folder(self, arxiv_id: str, d: date) -> bool:
    """Toggle paper in month folder. Returns True if added, False if removed."""
    month_name = d.strftime("%Y%m")
    with get_connection() as conn:
        # Find or create month folder
        folder = conn.execute(
            "SELECT id FROM reading_lists WHERE name = ? AND is_folder = 1 AND parent_id IS NULL",
            (month_name,),
        ).fetchone()
        if not folder:
            conn.execute(
                "INSERT INTO reading_lists (name, is_folder, is_system) VALUES (?, 1, 0)",
                (month_name,),
            )
            folder_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        else:
            folder_id = folder["id"]

        # Check if paper already in folder
        existing = conn.execute(
            "SELECT id FROM reading_list_papers WHERE list_id = ? AND arxiv_id = ?",
            (folder_id, arxiv_id),
        ).fetchone()
        if existing:
            conn.execute(
                "DELETE FROM reading_list_papers WHERE id = ?", (existing["id"],)
            )
            return False
        else:
            max_pos = conn.execute(
                "SELECT COALESCE(MAX(position), 0) FROM reading_list_papers WHERE list_id = ?",
                (folder_id,),
            ).fetchone()[0]
            conn.execute(
                "INSERT INTO reading_list_papers (list_id, arxiv_id, status, position)"
                " VALUES (?, ?, 'unread', ?)",
                (folder_id, arxiv_id, max_pos + 1),
            )
            return True
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_reading_list_hierarchy.py -v`
Expected: All PASS

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/arxiv_explorer/services/reading_list_service.py tests/test_reading_list_hierarchy.py
git commit -m "feat: add move, copy, and month folder toggle to ReadingListService"
```

---

### Task 1.5: TUI — Lists Tab Tree View with Folder Operations

**Files:**
- Modify: `src/arxiv_explorer/tui/screens/reading_lists.py`
- Create: `src/arxiv_explorer/tui/screens/folder_picker.py`
- Modify: `src/arxiv_explorer/tui/styles/app.tcss`

- [ ] **Step 1: Create FolderPickerScreen**

```python
# src/arxiv_explorer/tui/screens/folder_picker.py
"""Modal for picking a target folder for move/copy operations."""

from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, Label, ListView, ListItem, Static

from arxiv_explorer.core.models import ReadingList


class FolderPickerScreen(ModalScreen[int | None]):
    """Shows a list of folders/lists to pick a target."""

    BINDINGS = [("escape", "dismiss(None)", "Cancel")]

    def __init__(self, folders: list[ReadingList], title: str = "Select target") -> None:
        super().__init__()
        self.folders = folders
        self.picker_title = title

    def compose(self) -> ComposeResult:
        with Vertical(id="folder-picker"):
            yield Label(self.picker_title, id="picker-title")
            yield ListView(
                *[
                    ListItem(
                        Label(f"{'📁' if f.is_folder else '📋'} {f.name}"),
                        id=f"folder-{f.id}",
                    )
                    for f in self.folders
                ],
                id="folder-list",
            )
            with Horizontal(id="picker-buttons"):
                yield Button("Select", variant="primary", id="btn-select")
                yield Button("Cancel", id="btn-cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-cancel":
            self.dismiss(None)
        elif event.button.id == "btn-select":
            lv = self.query_one("#folder-list", ListView)
            if lv.highlighted_child:
                folder_id = int(lv.highlighted_child.id.replace("folder-", ""))
                self.dismiss(folder_id)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        folder_id = int(event.item.id.replace("folder-", ""))
        self.dismiss(folder_id)
```

- [ ] **Step 2: Rewrite ReadingListsPane for tree structure**

Rewrite `src/arxiv_explorer/tui/screens/reading_lists.py` to use a tree-based ListView on the left (showing folders with indentation and system lists pinned at top), and DataTable on the right showing papers with an Added column. Add key bindings for `f`, `m`, `c`, `r`, `s` (sort toggle).

Key changes to the BINDINGS:
```python
BINDINGS = [
    Binding("r", "refresh", "Refresh"),
    Binding("f", "create_folder", "New Folder"),
    Binding("c", "copy_item", "Copy"),
    Binding("m", "move_item", "Move"),
    Binding("delete", "delete_item", "Delete"),
    Binding("n", "create_list", "New List"),
    Binding("s", "toggle_sort", "Sort"),
]
```

The rename (`r`) is handled by inline input — when the user presses `r` on the left panel, replace the label with an Input widget, and on submit, call `svc.rename_item()`.

The left panel should display:
```
📋 Like (12)          ← is_system, always first
📋 Dislike (5)
───────────────────
📁 202604 (10)        ← is_folder
📁 202603 (23)
📋 Quantum Papers (4) ← regular list
```

The right panel DataTable columns become: `#`, `ID`, `Title`, `Added`, `Status`.

Sorting toggle (`s`) flips between newest-first and oldest-first by `added_at`.

This is a substantial rewrite. The full implementation should:
1. Load top-level items via `svc.get_top_level()`
2. When a folder is selected, load children via `svc.get_children()`
3. When a list/folder is selected, load papers via `svc.get_papers_by_list_id()`
4. For move/copy, open `FolderPickerScreen` to select target

- [ ] **Step 3: Add CSS for the updated Lists tab**

Append to `src/arxiv_explorer/tui/styles/app.tcss`:

```css
/* Folder picker modal */
#folder-picker {
    width: 50;
    height: 60%;
    background: $surface;
    border: round $primary;
    padding: 1 2;
}

#picker-title {
    text-style: bold;
    margin-bottom: 1;
}

#picker-buttons {
    height: 3;
    align: center middle;
}

/* System list separator */
.system-separator {
    height: 1;
    margin: 0 1;
    color: $text-muted;
}
```

- [ ] **Step 4: Manual TUI test**

Run: `uv run axp tui`
Verify:
- Lists tab shows tree structure with system lists at top
- `f` creates a new folder
- `r` triggers inline rename
- `m` opens folder picker and moves item
- `c` opens folder picker and copies item
- `s` toggles sort order on paper list
- Added column shows date/time

- [ ] **Step 5: Commit**

```bash
git add src/arxiv_explorer/tui/screens/reading_lists.py src/arxiv_explorer/tui/screens/folder_picker.py src/arxiv_explorer/tui/styles/app.tcss
git commit -m "feat: rewrite Lists tab with folder hierarchy tree view"
```

---

### Task 1.6: TUI — Daily Bookmark Toggle with Green Border

**Files:**
- Modify: `src/arxiv_explorer/tui/screens/daily.py`
- Modify: `src/arxiv_explorer/tui/widgets/paper_table.py`
- Modify: `src/arxiv_explorer/tui/styles/app.tcss`

- [ ] **Step 1: Add bookmark state tracking to PaperTable**

In `src/arxiv_explorer/tui/widgets/paper_table.py`, add a set to track bookmarked arxiv_ids and a method to toggle/check:

```python
class PaperTable(DataTable):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._papers: list = []
        self._bookmarked: set[str] = set()

    def set_bookmarked(self, arxiv_ids: set[str]) -> None:
        self._bookmarked = arxiv_ids
        self._refresh_styles()

    def toggle_bookmark(self, arxiv_id: str) -> bool:
        """Toggle bookmark. Returns True if now bookmarked, False if removed."""
        if arxiv_id in self._bookmarked:
            self._bookmarked.discard(arxiv_id)
            added = False
        else:
            self._bookmarked.add(arxiv_id)
            added = True
        self._refresh_styles()
        return added

    def is_bookmarked(self, arxiv_id: str) -> bool:
        return arxiv_id in self._bookmarked

    def _refresh_styles(self) -> None:
        """Update row styles based on bookmark state."""
        for idx, paper in enumerate(self._papers):
            arxiv_id = paper.paper.arxiv_id if hasattr(paper, "paper") else paper.arxiv_id
            row_key = self.get_row_at(idx)
            if arxiv_id in self._bookmarked:
                self.update_cell(row_key, "#", f"✓ {idx + 1}")
            else:
                self.update_cell(row_key, "#", str(idx + 1))
```

- [ ] **Step 2: Add bookmark action to DailyPane**

In `src/arxiv_explorer/tui/screens/daily.py`, add binding and action:

Add to BINDINGS (around line 65-72):
```python
Binding("b", "bookmark", "Bookmark"),
```

Add action method:
```python
def action_bookmark(self) -> None:
    table = self.query_one(PaperTable)
    paper = table.current_paper
    if paper is None:
        return
    arxiv_id = paper.paper.arxiv_id if hasattr(paper, "paper") else paper.arxiv_id
    self._do_bookmark(arxiv_id)

@work(thread=True)
def _do_bookmark(self, arxiv_id: str) -> None:
    from datetime import date
    svc = self.app.service_bridge.reading_lists
    added = svc.toggle_paper_in_month_folder(arxiv_id, date.today())
    table = self.query_one(PaperTable)
    table.toggle_bookmark(arxiv_id)
    if added:
        self.notify(f"Saved to {date.today().strftime('%Y%m')}", severity="information")
    else:
        self.notify(f"Removed from {date.today().strftime('%Y%m')}", severity="information")
```

- [ ] **Step 3: Add green border CSS for bookmarked rows**

In `src/arxiv_explorer/tui/styles/app.tcss`, add:

```css
/* Bookmark highlight - green left border */
.paper-bookmarked {
    border-left: thick $success;
    background: rgba(166, 227, 161, 0.05);
}
```

Note: Textual DataTable row styling is limited. The `✓` prefix in the `#` column serves as the primary visual indicator. For richer styling, the `_refresh_styles` method in PaperTable may need to use Textual's `Rich` renderables for cell content with color.

- [ ] **Step 4: Load existing bookmarks on fetch**

In `DailyPane._do_fetch()` (around line 149-163), after fetching papers, check which are bookmarked in the current month folder:

```python
@work(thread=True)
def _do_fetch(self) -> None:
    # ... existing fetch logic ...
    papers = self.app.service_bridge.papers.get_daily_papers(days=days, limit=limit)
    
    # Load current month bookmarks
    from datetime import date
    svc = self.app.service_bridge.reading_lists
    month_name = date.today().strftime("%Y%m")
    bookmarked = set()
    top_level = svc.get_top_level()
    for item in top_level:
        if item.name == month_name and item.is_folder:
            month_papers = svc.get_papers_by_list_id(item.id)
            bookmarked = {p.arxiv_id for p in month_papers}
            break
    
    self.call_from_thread(self._update_papers, papers, bookmarked)

def _update_papers(self, papers, bookmarked: set[str] | None = None) -> None:
    table = self.query_one(PaperTable)
    table.set_papers(papers)
    if bookmarked:
        table.set_bookmarked(bookmarked)
```

- [ ] **Step 5: Manual TUI test**

Run: `uv run axp tui`
Verify:
- In Daily tab, press `b` on a paper → shows `✓` prefix, notification shows month folder name
- Press `b` again → removes `✓`, notification confirms removal
- Switch to Lists tab → month folder appears with the paper

- [ ] **Step 6: Commit**

```bash
git add src/arxiv_explorer/tui/screens/daily.py src/arxiv_explorer/tui/widgets/paper_table.py src/arxiv_explorer/tui/styles/app.tcss
git commit -m "feat: add bookmark toggle with green indicator in Daily view"
```

---

## Branch 2: `feature/like-dislike-lists`

**Depends on:** Branch 1 merged into `dev`

### Task 2.1: Auto-Create System Lists on Init

**Files:**
- Modify: `src/arxiv_explorer/core/database.py`
- Test: `tests/test_like_dislike_lists.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_like_dislike_lists.py
import sqlite3
from pathlib import Path
import pytest
from arxiv_explorer.core.database import init_db


@pytest.fixture
def db(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    return db_path


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_like_dislike_lists.py::TestSystemListsCreation -v`
Expected: FAIL

- [ ] **Step 3: Add system list creation to init_db**

In `src/arxiv_explorer/core/database.py`, at the end of `init_db()` after migrations:

```python
# Create system lists if they don't exist
conn.execute(
    "INSERT OR IGNORE INTO reading_lists (name, is_folder, is_system)"
    " VALUES ('Like', 0, 1)"
)
conn.execute(
    "INSERT OR IGNORE INTO reading_lists (name, is_folder, is_system)"
    " VALUES ('Dislike', 0, 1)"
)
conn.commit()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_like_dislike_lists.py::TestSystemListsCreation -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/arxiv_explorer/core/database.py tests/test_like_dislike_lists.py
git commit -m "feat: auto-create Like/Dislike system lists on init"
```

---

### Task 2.2: Dual Storage — Like/Dislike Writes to Both Systems

**Files:**
- Modify: `src/arxiv_explorer/services/preference_service.py`
- Test: `tests/test_like_dislike_lists.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_like_dislike_lists.py`:

```python
from unittest.mock import patch
from arxiv_explorer.core.config import Config
from arxiv_explorer.core.database import get_connection
from arxiv_explorer.services.preference_service import PreferenceService
from arxiv_explorer.services.reading_list_service import ReadingListService


@pytest.fixture
def config(db, tmp_path):
    return Config(db_path=db, arxivterminal_db_path=tmp_path / "at.db")


@pytest.fixture
def pref_svc(config):
    with patch("arxiv_explorer.services.preference_service.get_config", return_value=config):
        with patch("arxiv_explorer.services.reading_list_service.get_config", return_value=config):
            yield PreferenceService()


@pytest.fixture
def list_svc(config):
    with patch("arxiv_explorer.services.reading_list_service.get_config", return_value=config):
        yield ReadingListService()


class TestDualStorage:
    def test_mark_interesting_adds_to_like_list(self, pref_svc, list_svc, config):
        with patch("arxiv_explorer.core.database.get_config", return_value=config):
            pref_svc.mark_interesting("2401.00001")
            # Check paper_interactions
            interaction = pref_svc.get_interaction("2401.00001")
            assert interaction is not None
            # Check Like reading list
            like_list = list_svc.get_list("Like")
            papers = list_svc.get_papers_by_list_id(like_list.id)
            arxiv_ids = {p.arxiv_id for p in papers}
            assert "2401.00001" in arxiv_ids

    def test_mark_not_interesting_adds_to_dislike_list(self, pref_svc, list_svc, config):
        with patch("arxiv_explorer.core.database.get_config", return_value=config):
            pref_svc.mark_not_interesting("2401.00001")
            dislike_list = list_svc.get_list("Dislike")
            papers = list_svc.get_papers_by_list_id(dislike_list.id)
            arxiv_ids = {p.arxiv_id for p in papers}
            assert "2401.00001" in arxiv_ids

    def test_switch_like_to_dislike(self, pref_svc, list_svc, config):
        with patch("arxiv_explorer.core.database.get_config", return_value=config):
            pref_svc.mark_interesting("2401.00001")
            pref_svc.mark_not_interesting("2401.00001")
            like_list = list_svc.get_list("Like")
            like_papers = list_svc.get_papers_by_list_id(like_list.id)
            assert all(p.arxiv_id != "2401.00001" for p in like_papers)
            dislike_list = list_svc.get_list("Dislike")
            dislike_papers = list_svc.get_papers_by_list_id(dislike_list.id)
            assert any(p.arxiv_id == "2401.00001" for p in dislike_papers)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_like_dislike_lists.py::TestDualStorage -v`
Expected: FAIL

- [ ] **Step 3: Update PreferenceService to write to both systems**

In `src/arxiv_explorer/services/preference_service.py`, modify `mark_interesting` and `mark_not_interesting`:

```python
from arxiv_explorer.services.reading_list_service import ReadingListService

class PreferenceService:
    def __init__(self) -> None:
        self._reading_lists = ReadingListService()

    def mark_interesting(self, arxiv_id: str) -> None:
        with get_connection() as conn:
            conn.execute(
                "DELETE FROM paper_interactions WHERE arxiv_id = ?", (arxiv_id,)
            )
            conn.execute(
                "INSERT INTO paper_interactions (arxiv_id, interaction_type) VALUES (?, ?)",
                (arxiv_id, InteractionType.INTERESTING.value),
            )
        # Dual storage: add to Like list, remove from Dislike list
        self._sync_to_lists(arxiv_id, like=True)

    def mark_not_interesting(self, arxiv_id: str) -> None:
        with get_connection() as conn:
            conn.execute(
                "DELETE FROM paper_interactions WHERE arxiv_id = ?", (arxiv_id,)
            )
            conn.execute(
                "INSERT INTO paper_interactions (arxiv_id, interaction_type) VALUES (?, ?)",
                (arxiv_id, InteractionType.NOT_INTERESTING.value),
            )
        # Dual storage: add to Dislike list, remove from Like list
        self._sync_to_lists(arxiv_id, like=False)

    def _sync_to_lists(self, arxiv_id: str, like: bool) -> None:
        like_list = self._reading_lists.get_list("Like")
        dislike_list = self._reading_lists.get_list("Dislike")
        if not like_list or not dislike_list:
            return
        if like:
            self._reading_lists.remove_paper_from_list(dislike_list.id, arxiv_id)
            self._reading_lists.add_paper_to_list(like_list.id, arxiv_id)
        else:
            self._reading_lists.remove_paper_from_list(like_list.id, arxiv_id)
            self._reading_lists.add_paper_to_list(dislike_list.id, arxiv_id)
```

Also add `remove_paper_from_list` to `ReadingListService`:

```python
def remove_paper_from_list(self, list_id: int, arxiv_id: str) -> bool:
    with get_connection() as conn:
        conn.execute(
            "DELETE FROM reading_list_papers WHERE list_id = ? AND arxiv_id = ?",
            (list_id, arxiv_id),
        )
        return conn.total_changes > 0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_like_dislike_lists.py -v`
Expected: All PASS

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest -v`
Expected: All PASS (existing preference tests still work)

- [ ] **Step 6: Commit**

```bash
git add src/arxiv_explorer/services/preference_service.py src/arxiv_explorer/services/reading_list_service.py tests/test_like_dislike_lists.py
git commit -m "feat: dual storage for like/dislike in both interactions and reading lists"
```

---

### Task 2.3: TUI — Pin System Lists in Lists Tab

**Files:**
- Modify: `src/arxiv_explorer/tui/screens/reading_lists.py`

- [ ] **Step 1: Update list loading to sort system lists first**

The `get_top_level()` already returns `ORDER BY is_system DESC, name`. In the Lists tab, add a visual separator between system lists and user lists.

When building the left panel ListView, insert a separator after system lists:

```python
def _populate_lists(self, items: list[ReadingList]) -> None:
    lv = self.query_one("#lists-view", ListView)
    lv.clear()
    system_lists = [i for i in items if i.is_system]
    user_lists = [i for i in items if not i.is_system]
    
    for item in system_lists:
        count = len(self.app.service_bridge.reading_lists.get_papers_by_list_id(item.id))
        lv.append(ListItem(
            Label(f"📋 {item.name} ({count})"),
            id=f"list-{item.id}",
        ))
    
    if system_lists and user_lists:
        lv.append(ListItem(Label("───────────────"), disabled=True))
    
    for item in user_lists:
        icon = "📁" if item.is_folder else "📋"
        count = len(self.app.service_bridge.reading_lists.get_papers_by_list_id(item.id))
        lv.append(ListItem(
            Label(f"{icon} {item.name} ({count})"),
            id=f"list-{item.id}",
        ))
```

- [ ] **Step 2: Prevent delete/rename on system lists in action handlers**

```python
def action_delete_item(self) -> None:
    selected = self._get_selected_list()
    if selected and selected.is_system:
        self.notify("System lists cannot be deleted", severity="error")
        return
    # ... existing delete logic
```

- [ ] **Step 3: Manual TUI test**

Run: `uv run axp tui`
Verify:
- Like and Dislike appear at top of Lists tab
- Separator line visible between system and user lists
- Cannot delete or rename Like/Dislike
- Like a paper in Daily → appears in Like list
- Dislike a paper → appears in Dislike list
- Switch like→dislike → paper moves between lists

- [ ] **Step 4: Commit**

```bash
git add src/arxiv_explorer/tui/screens/reading_lists.py
git commit -m "feat: pin Like/Dislike system lists at top of Lists tab"
```

---

## Branch 3: `feature/preferred-authors`

### Task 3.1: DB Schema and Model

**Files:**
- Modify: `src/arxiv_explorer/core/database.py`
- Modify: `src/arxiv_explorer/core/models.py`
- Test: `tests/test_author_service.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_author_service.py
import sqlite3
from pathlib import Path
import pytest
from arxiv_explorer.core.database import init_db
from arxiv_explorer.core.models import PreferredAuthor


@pytest.fixture
def db(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    return db_path


class TestAuthorSchema:
    def test_preferred_authors_table_exists(self, db):
        with sqlite3.connect(db) as conn:
            tables = {
                r[0] for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            assert "preferred_authors" in tables

    def test_preferred_author_model(self):
        from datetime import datetime
        author = PreferredAuthor(id=1, name="Dong Woo Kang", added_at=datetime.now())
        assert author.name == "Dong Woo Kang"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_author_service.py::TestAuthorSchema -v`
Expected: FAIL

- [ ] **Step 3: Add table and model**

In `src/arxiv_explorer/core/database.py`, add to SCHEMA string:

```sql
CREATE TABLE IF NOT EXISTS preferred_authors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

In `src/arxiv_explorer/core/models.py`, add after KeywordInterest:

```python
@dataclass
class PreferredAuthor:
    id: int
    name: str
    added_at: datetime
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_author_service.py::TestAuthorSchema -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/arxiv_explorer/core/database.py src/arxiv_explorer/core/models.py tests/test_author_service.py
git commit -m "feat: add preferred_authors table and model"
```

---

### Task 3.2: Author Matching Algorithm

**Files:**
- Create: `src/arxiv_explorer/services/author_service.py`
- Test: `tests/test_author_service.py`

- [ ] **Step 1: Write failing tests for matching**

Append to `tests/test_author_service.py`:

```python
from arxiv_explorer.services.author_service import matches_author


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

    def test_reversed_order_no_match(self):
        # We don't support reversed name order
        assert matches_author("Dong Woo Kang", "Kang Dong Woo") is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_author_service.py::TestAuthorMatching -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement matching algorithm**

```python
# src/arxiv_explorer/services/author_service.py
"""Preferred author management and name matching."""

import re
from datetime import datetime

from arxiv_explorer.core.database import get_connection
from arxiv_explorer.core.models import PreferredAuthor


def _normalize(name: str) -> str:
    """Lowercase, strip, collapse whitespace, remove dots."""
    return re.sub(r"\s+", " ", name.lower().strip().replace(".", ""))


def _tokenize(name: str) -> list[str]:
    """Split normalized name into tokens."""
    return _normalize(name).split()


def _is_initial_of(initial: str, full: str) -> bool:
    """Check if 'initial' is the first letter of 'full'."""
    return len(initial) == 1 and full.startswith(initial)


def _merge_matches(tokens_a: list[str], tokens_b: list[str]) -> bool:
    """Check if tokens_a can match tokens_b by merging adjacent tokens.
    
    Example: ["dong", "woo"] matches ["dongwoo"] by merging.
    """
    merged_a = "".join(tokens_a)
    merged_b = "".join(tokens_b)
    return merged_a == merged_b


def matches_author(registered: str, paper_author: str) -> bool:
    """Structural name comparison.
    
    Rules:
    1. Last name (last token) must match exactly
    2. All first/middle name tokens from registered must be accounted for
    3. Accepts: exact match, initial match, whitespace merge
    """
    reg_tokens = _tokenize(registered)
    paper_tokens = _tokenize(paper_author)

    if len(reg_tokens) < 2 or len(paper_tokens) < 2:
        return False

    # Last name must match
    if reg_tokens[-1] != paper_tokens[-1]:
        return False

    reg_first = reg_tokens[:-1]  # first/middle names
    paper_first = paper_tokens[:-1]

    # Try direct token matching (exact or initial)
    if _match_first_names(reg_first, paper_first):
        return True

    # Try merge matching: "Dong Woo" vs "Dongwoo"
    if _merge_matches(reg_first, paper_first):
        return True
    if _merge_matches(paper_first, reg_first):
        return True

    return False


def _match_first_names(reg: list[str], paper: list[str]) -> bool:
    """Match first name tokens 1:1. Each registered token must match a paper token."""
    if len(reg) != len(paper):
        return False
    for r, p in zip(reg, paper):
        if r == p:
            continue
        if _is_initial_of(r, p) or _is_initial_of(p, r):
            continue
        return False
    return True


class AuthorService:
    def add_author(self, name: str) -> PreferredAuthor:
        with get_connection() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO preferred_authors (name) VALUES (?)",
                (name.strip(),),
            )
            row = conn.execute(
                "SELECT * FROM preferred_authors WHERE name = ?",
                (name.strip(),),
            ).fetchone()
            return PreferredAuthor(
                id=row["id"], name=row["name"], added_at=row["added_at"]
            )

    def remove_author(self, name: str) -> bool:
        with get_connection() as conn:
            conn.execute(
                "DELETE FROM preferred_authors WHERE name = ?", (name.strip(),)
            )
            return conn.total_changes > 0

    def get_authors(self) -> list[PreferredAuthor]:
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM preferred_authors ORDER BY name"
            ).fetchall()
            return [
                PreferredAuthor(id=r["id"], name=r["name"], added_at=r["added_at"])
                for r in rows
            ]

    def filter_author_papers(self, papers: list) -> tuple[list, list]:
        """Split papers into (author_matched, remaining)."""
        authors = self.get_authors()
        if not authors:
            return [], papers

        author_papers = []
        remaining = []
        for paper in papers:
            paper_obj = paper.paper if hasattr(paper, "paper") else paper
            if any(
                any(matches_author(a.name, pa) for pa in paper_obj.authors)
                for a in authors
            ):
                author_papers.append(paper)
            else:
                remaining.append(paper)
        return author_papers, remaining
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_author_service.py::TestAuthorMatching -v`
Expected: PASS

- [ ] **Step 5: Write tests for AuthorService CRUD**

Append to `tests/test_author_service.py`:

```python
from unittest.mock import patch
from arxiv_explorer.core.config import Config
from arxiv_explorer.services.author_service import AuthorService


@pytest.fixture
def author_svc(db, tmp_path):
    config = Config(db_path=db, arxivterminal_db_path=tmp_path / "at.db")
    with patch("arxiv_explorer.services.author_service.get_config", return_value=config):
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
```

- [ ] **Step 6: Run all author tests**

Run: `uv run pytest tests/test_author_service.py -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add src/arxiv_explorer/services/author_service.py tests/test_author_service.py
git commit -m "feat: add author matching algorithm and AuthorService"
```

---

### Task 3.3: Integrate Authors into Daily Recommendation

**Files:**
- Modify: `src/arxiv_explorer/services/paper_service.py`
- Modify: `src/arxiv_explorer/tui/workers.py`

- [ ] **Step 1: Update PaperService.get_daily_papers**

In `src/arxiv_explorer/services/paper_service.py`, modify `get_daily_papers` (around line 16-65) to return two lists:

```python
from arxiv_explorer.services.author_service import AuthorService

class PaperService:
    def __init__(self) -> None:
        self.client = ArxivClient()
        self.preferences = PreferenceService()
        self.authors = AuthorService()

    def get_daily_papers(
        self, days: int = 1, limit: int = 50
    ) -> tuple[list[RecommendedPaper], list[RecommendedPaper]]:
        """Returns (author_papers, scored_papers)."""
        # ... existing fetch and scoring logic ...
        categories = self.preferences.get_categories()
        # ... fetch papers ...
        # ... build user profile, score papers ...
        scored = engine.score_papers(papers, user_profile, categories, keywords)
        
        # Split by author match
        author_papers, remaining = self.authors.filter_author_papers(scored)
        
        return author_papers, remaining[:limit]
```

Note: This changes the return type from `list[RecommendedPaper]` to `tuple[list[RecommendedPaper], list[RecommendedPaper]]`. All callers must be updated.

- [ ] **Step 2: Update ServiceBridge**

In `src/arxiv_explorer/tui/workers.py`, add AuthorService:

```python
from arxiv_explorer.services.author_service import AuthorService

class ServiceBridge:
    def __init__(self) -> None:
        self.papers = PaperService()
        self.preferences = PreferenceService()
        self.reading_lists = ReadingListService()
        self.notes = NotesService()
        self.summarization = SummarizationService()
        self.translation = TranslationService()
        self.settings = SettingsService()
        self.review = PaperReviewService()
        self.authors = AuthorService()  # NEW
```

- [ ] **Step 3: Update CLI callers of get_daily_papers**

In `src/arxiv_explorer/cli/daily.py`, update every call to `get_daily_papers()` to unpack the tuple. Display author papers first with a header:

```python
author_papers, scored_papers = service.get_daily_papers(days=days, limit=limit)
if author_papers:
    console.print("[bold yellow]── From Your Authors ──[/bold yellow]")
    print_paper_list(author_papers)
if scored_papers:
    console.print("[bold]── Recommended ──[/bold]")
    print_paper_list(scored_papers)
```

- [ ] **Step 4: Run full test suite and fix breakages**

Run: `uv run pytest -v`
Fix any tests that call `get_daily_papers()` and expect a flat list.

- [ ] **Step 5: Commit**

```bash
git add src/arxiv_explorer/services/paper_service.py src/arxiv_explorer/tui/workers.py src/arxiv_explorer/cli/daily.py
git commit -m "feat: split daily papers into author-matched and scored sections"
```

---

### Task 3.4: TUI — Daily View Author Section with Yellow Border

**Files:**
- Modify: `src/arxiv_explorer/tui/screens/daily.py`
- Modify: `src/arxiv_explorer/tui/widgets/paper_table.py`
- Modify: `src/arxiv_explorer/tui/styles/app.tcss`

- [ ] **Step 1: Add author highlight tracking to PaperTable**

In `src/arxiv_explorer/tui/widgets/paper_table.py`, add `_author_matched` set alongside `_bookmarked`:

```python
def __init__(self, **kwargs):
    super().__init__(**kwargs)
    self._papers: list = []
    self._bookmarked: set[str] = set()
    self._author_matched: set[str] = set()

def set_author_matched(self, arxiv_ids: set[str]) -> None:
    self._author_matched = arxiv_ids
    self._refresh_styles()

def _refresh_styles(self) -> None:
    for idx, paper in enumerate(self._papers):
        arxiv_id = paper.paper.arxiv_id if hasattr(paper, "paper") else paper.arxiv_id
        row_key = self.get_row_at(idx)
        prefix = ""
        if arxiv_id in self._author_matched:
            prefix += "★ "
        if arxiv_id in self._bookmarked:
            prefix += "✓ "
        self.update_cell(row_key, "#", f"{prefix}{idx + 1}")
```

- [ ] **Step 2: Update DailyPane to show two sections**

In `src/arxiv_explorer/tui/screens/daily.py`, update `_do_fetch` and `_update_papers` to handle the tuple return from `get_daily_papers`:

```python
@work(thread=True)
def _do_fetch(self) -> None:
    author_papers, scored_papers = self.app.service_bridge.papers.get_daily_papers(
        days=days, limit=limit
    )
    # Combine for display, with author papers first
    all_papers = author_papers + scored_papers
    author_ids = {
        (p.paper.arxiv_id if hasattr(p, "paper") else p.arxiv_id)
        for p in author_papers
    }
    # ... load bookmarks as before ...
    self.call_from_thread(self._update_papers, all_papers, bookmarked, author_ids)

def _update_papers(
    self, papers, bookmarked: set[str] | None = None, author_ids: set[str] | None = None
) -> None:
    table = self.query_one(PaperTable)
    table.set_papers(papers)
    if bookmarked:
        table.set_bookmarked(bookmarked)
    if author_ids:
        table.set_author_matched(author_ids)
```

- [ ] **Step 3: Add yellow border CSS**

Append to `src/arxiv_explorer/tui/styles/app.tcss`:

```css
/* Author highlight - yellow left border */
.paper-author {
    border-left: thick #f9e2af;
    background: rgba(249, 226, 175, 0.05);
}
```

- [ ] **Step 4: Add Authors section to PreferencesPane**

In `src/arxiv_explorer/tui/screens/preferences.py`, add a third section for Authors management:

Add to compose():
```python
with Vertical(id="authors-section", classes="pref-section"):
    yield Static("Preferred Authors", classes="section-title")
    yield DataTable(id="authors-table")
    with Horizontal(id="author-input-row"):
        yield Input(placeholder="Author name...", id="author-input")
        yield Button("Add", id="btn-add-author")
```

Add key bindings and handlers for author add (`a` context) and delete (`x`).

- [ ] **Step 5: Manual TUI test**

Run: `uv run axp tui`
- Add an author in Prefs tab
- Fetch daily papers → author-matched papers show with ★ prefix
- Author papers appear before scored papers in the list

- [ ] **Step 6: Commit**

```bash
git add src/arxiv_explorer/tui/screens/daily.py src/arxiv_explorer/tui/widgets/paper_table.py src/arxiv_explorer/tui/screens/preferences.py src/arxiv_explorer/tui/styles/app.tcss
git commit -m "feat: add preferred author section with yellow highlight in Daily view"
```

---

## Branch 4: `feature/background-jobs`

### Task 4.1: Job Models and JobManager

**Files:**
- Modify: `src/arxiv_explorer/core/models.py`
- Create: `src/arxiv_explorer/services/job_manager.py`
- Test: `tests/test_job_manager.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_job_manager.py
import pytest
from datetime import datetime
from arxiv_explorer.core.models import JobType, JobStatus, Job
from arxiv_explorer.services.job_manager import JobManager


class TestJobModels:
    def test_job_type_enum(self):
        assert JobType.SUMMARIZE.value == "summarize"
        assert JobType.TRANSLATE.value == "translate"
        assert JobType.REVIEW.value == "review"

    def test_job_status_enum(self):
        assert JobStatus.PENDING.value == "pending"
        assert JobStatus.RUNNING.value == "running"
        assert JobStatus.COMPLETED.value == "completed"
        assert JobStatus.FAILED.value == "failed"


class TestJobManager:
    def test_submit_creates_job(self):
        mgr = JobManager()
        job = mgr.submit(JobType.SUMMARIZE, "2401.00001", "Test Paper")
        assert job.status == JobStatus.PENDING
        assert job.paper_id == "2401.00001"
        assert job.job_type == JobType.SUMMARIZE

    def test_get_active_jobs(self):
        mgr = JobManager()
        mgr.submit(JobType.SUMMARIZE, "2401.00001", "Paper 1")
        mgr.submit(JobType.TRANSLATE, "2401.00002", "Paper 2")
        active = mgr.get_active_jobs()
        assert len(active) == 2

    def test_cancel_job(self):
        mgr = JobManager()
        job = mgr.submit(JobType.SUMMARIZE, "2401.00001", "Paper 1")
        result = mgr.cancel(job.id)
        assert result is True
        assert mgr.jobs[job.id].status == JobStatus.FAILED

    def test_complete_job(self):
        mgr = JobManager()
        job = mgr.submit(JobType.SUMMARIZE, "2401.00001", "Paper 1")
        mgr.mark_running(job.id)
        mgr.mark_completed(job.id)
        assert mgr.jobs[job.id].status == JobStatus.COMPLETED
        assert mgr.jobs[job.id].completed_at is not None

    def test_fail_job(self):
        mgr = JobManager()
        job = mgr.submit(JobType.SUMMARIZE, "2401.00001", "Paper 1")
        mgr.mark_running(job.id)
        mgr.mark_failed(job.id, "timeout")
        assert mgr.jobs[job.id].status == JobStatus.FAILED
        assert mgr.jobs[job.id].error == "timeout"

    def test_clear_completed(self):
        mgr = JobManager()
        job = mgr.submit(JobType.SUMMARIZE, "2401.00001", "Paper 1")
        mgr.mark_running(job.id)
        mgr.mark_completed(job.id)
        mgr.clear_completed()
        assert len(mgr.get_all_jobs()) == 0

    def test_on_status_change_callback(self):
        events = []
        mgr = JobManager(on_status_change=lambda job: events.append(job))
        job = mgr.submit(JobType.SUMMARIZE, "2401.00001", "Paper 1")
        mgr.mark_running(job.id)
        mgr.mark_completed(job.id)
        assert len(events) == 3  # submit, running, completed
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_job_manager.py -v`
Expected: FAIL

- [ ] **Step 3: Add models and implement JobManager**

In `src/arxiv_explorer/core/models.py`, add after existing enums:

```python
class JobType(Enum):
    SUMMARIZE = "summarize"
    TRANSLATE = "translate"
    REVIEW = "review"

class JobStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
```

Add after existing dataclasses:

```python
@dataclass
class Job:
    id: str
    paper_id: str
    paper_title: str
    job_type: JobType
    status: JobStatus
    started_at: datetime
    completed_at: datetime | None = None
    error: str | None = None
```

Create `src/arxiv_explorer/services/job_manager.py`:

```python
"""In-memory background job tracking."""

import uuid
from collections.abc import Callable
from datetime import datetime

from arxiv_explorer.core.models import Job, JobStatus, JobType


class JobManager:
    def __init__(self, on_status_change: Callable[[Job], None] | None = None) -> None:
        self.jobs: dict[str, Job] = {}
        self._on_status_change = on_status_change

    def submit(self, job_type: JobType, paper_id: str, paper_title: str) -> Job:
        job = Job(
            id=str(uuid.uuid4()),
            paper_id=paper_id,
            paper_title=paper_title,
            job_type=job_type,
            status=JobStatus.PENDING,
            started_at=datetime.now(),
        )
        self.jobs[job.id] = job
        self._notify(job)
        return job

    def mark_running(self, job_id: str) -> None:
        job = self.jobs[job_id]
        job.status = JobStatus.RUNNING
        self._notify(job)

    def mark_completed(self, job_id: str) -> None:
        job = self.jobs[job_id]
        job.status = JobStatus.COMPLETED
        job.completed_at = datetime.now()
        self._notify(job)

    def mark_failed(self, job_id: str, error: str) -> None:
        job = self.jobs[job_id]
        job.status = JobStatus.FAILED
        job.error = error
        job.completed_at = datetime.now()
        self._notify(job)

    def cancel(self, job_id: str) -> bool:
        job = self.jobs.get(job_id)
        if not job or job.status in (JobStatus.COMPLETED, JobStatus.FAILED):
            return False
        job.status = JobStatus.FAILED
        job.error = "cancelled"
        job.completed_at = datetime.now()
        self._notify(job)
        return True

    def get_active_jobs(self) -> list[Job]:
        return [
            j for j in self.jobs.values()
            if j.status in (JobStatus.PENDING, JobStatus.RUNNING)
        ]

    def get_all_jobs(self) -> list[Job]:
        return list(self.jobs.values())

    def clear_completed(self) -> None:
        self.jobs = {
            k: v for k, v in self.jobs.items()
            if v.status in (JobStatus.PENDING, JobStatus.RUNNING)
        }

    def _notify(self, job: Job) -> None:
        if self._on_status_change:
            self._on_status_change(job)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_job_manager.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/arxiv_explorer/core/models.py src/arxiv_explorer/services/job_manager.py tests/test_job_manager.py
git commit -m "feat: add Job models and in-memory JobManager"
```

---

### Task 4.2: TUI — Integrate JobManager with App

**Files:**
- Modify: `src/arxiv_explorer/tui/app.py`
- Modify: `src/arxiv_explorer/tui/workers.py`
- Modify: `src/arxiv_explorer/tui/screens/daily.py`
- Modify: `src/arxiv_explorer/tui/screens/paper_detail.py`

- [ ] **Step 1: Add JobManager to ServiceBridge and App**

In `src/arxiv_explorer/tui/workers.py`:
```python
from arxiv_explorer.services.job_manager import JobManager

class ServiceBridge:
    def __init__(self) -> None:
        # ... existing services ...
        self.job_manager = JobManager()
```

In `src/arxiv_explorer/tui/app.py`, add global `j` binding and status bar:

```python
BINDINGS = [
    # ... existing bindings ...
    Binding("j", "toggle_jobs", "Jobs"),
]
```

Add footer widget override to show active job count:

```python
def _on_job_status_change(self, job: Job) -> None:
    """Called by JobManager when any job status changes."""
    if job.status == JobStatus.COMPLETED:
        self.notify(
            f"✓ {job.job_type.value.title()} completed\n  {job.paper_id}",
            severity="information",
            timeout=3,
        )
    elif job.status == JobStatus.FAILED and job.error != "cancelled":
        self.notify(
            f"✗ {job.job_type.value.title()} failed\n  {job.error}",
            severity="error",
            timeout=5,
        )
    # Update status bar
    active = len(self.service_bridge.job_manager.get_active_jobs())
    self.sub_title = f"Jobs: {active} running" if active > 0 else "Personalized Paper Recommendation System"
```

Wire the callback in `__init__`:
```python
def __init__(self) -> None:
    super().__init__()
    self.service_bridge = ServiceBridge()
    self.service_bridge.job_manager._on_status_change = self._on_job_status_change
```

- [ ] **Step 2: Convert summarize/translate/review to use JobManager**

In `src/arxiv_explorer/tui/screens/daily.py`, change `action_summarize`:

```python
def action_summarize(self) -> None:
    table = self.query_one(PaperTable)
    paper = table.current_paper
    if paper is None:
        return
    paper_obj = paper.paper if hasattr(paper, "paper") else paper
    mgr = self.app.service_bridge.job_manager
    job = mgr.submit(JobType.SUMMARIZE, paper_obj.arxiv_id, paper_obj.title)
    self._run_job(job, paper_obj)

@work(thread=True)
def _run_job(self, job: Job, paper) -> None:
    mgr = self.app.service_bridge.job_manager
    mgr.mark_running(job.id)
    try:
        if job.job_type == JobType.SUMMARIZE:
            self.app.service_bridge.summarization.summarize(
                paper.arxiv_id, paper.title, paper.abstract, detailed=True
            )
        elif job.job_type == JobType.TRANSLATE:
            self.app.service_bridge.translation.translate(
                paper.arxiv_id, paper.title, paper.abstract
            )
        mgr.mark_completed(job.id)
    except Exception as e:
        mgr.mark_failed(job.id, str(e))
```

Apply same pattern to `action_translate` and `action_review`. The key difference from current code: the user does NOT need to wait — the job runs in background and they can navigate away.

Do the same for `src/arxiv_explorer/tui/screens/paper_detail.py`.

- [ ] **Step 3: Commit**

```bash
git add src/arxiv_explorer/tui/app.py src/arxiv_explorer/tui/workers.py src/arxiv_explorer/tui/screens/daily.py src/arxiv_explorer/tui/screens/paper_detail.py
git commit -m "feat: integrate JobManager with TUI for background task execution"
```

---

### Task 4.3: TUI — Jobs Panel

**Files:**
- Create: `src/arxiv_explorer/tui/screens/jobs_panel.py`
- Modify: `src/arxiv_explorer/tui/app.py`
- Modify: `src/arxiv_explorer/tui/styles/app.tcss`

- [ ] **Step 1: Create JobsPanel screen**

```python
# src/arxiv_explorer/tui/screens/jobs_panel.py
"""Overlay panel showing background job status."""

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import DataTable, Static, Button
from textual.binding import Binding

from arxiv_explorer.core.models import JobStatus


class JobsPanel(ModalScreen):
    BINDINGS = [
        Binding("escape", "dismiss", "Close"),
        Binding("j", "dismiss", "Close"),
        Binding("x", "cancel_job", "Cancel"),
        Binding("c", "clear_completed", "Clear"),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="jobs-panel"):
            yield Static("Background Jobs", id="jobs-title")
            yield DataTable(id="jobs-table")

    def on_mount(self) -> None:
        table = self.query_one("#jobs-table", DataTable)
        table.add_columns("Status", "Type", "Paper ID", "Title", "Time")
        self._refresh_jobs()

    def _refresh_jobs(self) -> None:
        table = self.query_one("#jobs-table", DataTable)
        table.clear()
        mgr = self.app.service_bridge.job_manager
        for job in mgr.get_all_jobs():
            status_icon = {
                JobStatus.PENDING: "◌",
                JobStatus.RUNNING: "⟳",
                JobStatus.COMPLETED: "✓",
                JobStatus.FAILED: "✗",
            }[job.status]
            elapsed = ""
            if job.completed_at:
                elapsed = "Done" if job.status == JobStatus.COMPLETED else f"Failed: {job.error}"
            elif job.status == JobStatus.RUNNING:
                from datetime import datetime
                delta = datetime.now() - job.started_at
                elapsed = f"{int(delta.total_seconds())}s"
            table.add_row(
                status_icon,
                job.job_type.value.upper(),
                job.paper_id,
                job.paper_title[:40] + "..." if len(job.paper_title) > 40 else job.paper_title,
                elapsed,
                key=job.id,
            )

    def action_cancel_job(self) -> None:
        table = self.query_one("#jobs-table", DataTable)
        if table.cursor_row is not None:
            row_key = table.get_row_at(table.cursor_row)
            job_id = str(row_key)
            self.app.service_bridge.job_manager.cancel(job_id)
            self._refresh_jobs()

    def action_clear_completed(self) -> None:
        self.app.service_bridge.job_manager.clear_completed()
        self._refresh_jobs()
```

- [ ] **Step 2: Wire to app**

In `src/arxiv_explorer/tui/app.py`:

```python
from arxiv_explorer.tui.screens.jobs_panel import JobsPanel

def action_toggle_jobs(self) -> None:
    self.push_screen(JobsPanel())
```

- [ ] **Step 3: Add CSS**

Append to `src/arxiv_explorer/tui/styles/app.tcss`:

```css
/* Jobs panel */
#jobs-panel {
    width: 80;
    height: 60%;
    background: $surface;
    border: round $primary;
    padding: 1 2;
}

#jobs-title {
    text-style: bold;
    margin-bottom: 1;
}
```

- [ ] **Step 4: Manual TUI test**

Run: `uv run axp tui`
- Trigger summarize on a paper → notification appears
- Press `j` → Jobs panel opens showing running job
- Wait for completion → toast notification appears
- Press `c` to clear completed jobs

- [ ] **Step 5: Commit**

```bash
git add src/arxiv_explorer/tui/screens/jobs_panel.py src/arxiv_explorer/tui/app.py src/arxiv_explorer/tui/styles/app.tcss
git commit -m "feat: add Jobs panel with status tracking and toast notifications"
```

---

## Branch 5: `feature/weight-percentage`

### Task 5.1: Weight Settings and Adjustment Algorithm

**Files:**
- Modify: `src/arxiv_explorer/services/settings_service.py`
- Test: `tests/test_weight_percentage.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_weight_percentage.py
import pytest
from unittest.mock import patch
from pathlib import Path
from arxiv_explorer.core.config import Config
from arxiv_explorer.core.database import init_db
from arxiv_explorer.services.settings_service import SettingsService, adjust_weights


@pytest.fixture
def db(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    return db_path


@pytest.fixture
def svc(db, tmp_path):
    config = Config(db_path=db, arxivterminal_db_path=tmp_path / "at.db")
    with patch("arxiv_explorer.services.settings_service.get_config", return_value=config):
        yield SettingsService()


class TestWeightDefaults:
    def test_default_weights(self, svc):
        weights = svc.get_weights()
        assert weights == {
            "content": 60,
            "category": 20,
            "keyword": 15,
            "recency": 5,
        }

    def test_weights_sum_to_100(self, svc):
        weights = svc.get_weights()
        assert sum(weights.values()) == 100


class TestAdjustWeights:
    def test_increase_one_decreases_others(self):
        weights = {"content": 60, "category": 20, "keyword": 15, "recency": 5}
        result = adjust_weights("content", 80, weights)
        assert result["content"] == 80
        assert sum(result.values()) == 100

    def test_proportional_adjustment(self):
        weights = {"content": 60, "category": 20, "keyword": 15, "recency": 5}
        result = adjust_weights("content", 80, weights)
        # category:keyword:recency ratio was 20:15:5 = 4:3:1
        # remaining = 20, distributed as 10:7.5:2.5 → 10:8:2
        assert result["category"] == 10
        assert result["keyword"] + result["recency"] == 10

    def test_set_to_zero(self):
        weights = {"content": 60, "category": 20, "keyword": 15, "recency": 5}
        result = adjust_weights("content", 0, weights)
        assert result["content"] == 0
        assert sum(result.values()) == 100

    def test_set_to_100(self):
        weights = {"content": 60, "category": 20, "keyword": 15, "recency": 5}
        result = adjust_weights("content", 100, weights)
        assert result["content"] == 100
        assert result["category"] == 0
        assert result["keyword"] == 0
        assert result["recency"] == 0

    def test_all_others_zero_distributes_equally(self):
        weights = {"content": 100, "category": 0, "keyword": 0, "recency": 0}
        result = adjust_weights("content", 70, weights)
        assert result["content"] == 70
        assert sum(result.values()) == 100
        # 30 distributed among 3 others = 10 each
        assert result["category"] == 10
        assert result["keyword"] == 10
        assert result["recency"] == 10


class TestWeightPersistence:
    def test_save_and_load(self, svc):
        svc.set_weights({"content": 50, "category": 25, "keyword": 20, "recency": 5})
        weights = svc.get_weights()
        assert weights == {"content": 50, "category": 25, "keyword": 20, "recency": 5}

    def test_reset_to_defaults(self, svc):
        svc.set_weights({"content": 50, "category": 25, "keyword": 20, "recency": 5})
        svc.reset_weights()
        weights = svc.get_weights()
        assert weights == {"content": 60, "category": 20, "keyword": 15, "recency": 5}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_weight_percentage.py -v`
Expected: FAIL

- [ ] **Step 3: Implement weight methods**

In `src/arxiv_explorer/services/settings_service.py`, add to DEFAULTS:

```python
DEFAULTS: dict[str, str] = {
    # ... existing ...
    "weight_content": "60",
    "weight_category": "20",
    "weight_keyword": "15",
    "weight_recency": "5",
}
```

Add methods and standalone function:

```python
WEIGHT_KEYS = ["content", "category", "keyword", "recency"]
DEFAULT_WEIGHTS = {"content": 60, "category": 20, "keyword": 15, "recency": 5}


def adjust_weights(changed_key: str, new_value: int, weights: dict[str, int]) -> dict[str, int]:
    result = dict(weights)
    result[changed_key] = new_value
    remaining = 100 - new_value
    others = {k: v for k, v in result.items() if k != changed_key}
    others_sum = sum(others.values())

    if others_sum == 0:
        equal = remaining // len(others)
        for k in others:
            result[k] = equal
    else:
        for k in others:
            result[k] = round(remaining * others[k] / others_sum)

    # Rounding error correction
    diff = 100 - sum(result.values())
    if diff != 0:
        largest = max(others, key=lambda k: result[k])
        result[largest] += diff

    return result


class SettingsService:
    # ... existing methods ...

    def get_weights(self) -> dict[str, int]:
        return {
            key: int(self.get(f"weight_{key}"))
            for key in WEIGHT_KEYS
        }

    def set_weights(self, weights: dict[str, int]) -> None:
        for key in WEIGHT_KEYS:
            self.set(f"weight_{key}", str(weights[key]))

    def reset_weights(self) -> None:
        self.set_weights(DEFAULT_WEIGHTS)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_weight_percentage.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/arxiv_explorer/services/settings_service.py tests/test_weight_percentage.py
git commit -m "feat: add weight percentage system with auto-adjustment"
```

---

### Task 5.2: Wire Weights into Recommendation Engine

**Files:**
- Modify: `src/arxiv_explorer/services/recommendation.py`

- [ ] **Step 1: Update score_papers to read from settings**

In `src/arxiv_explorer/services/recommendation.py`, modify `score_papers` (around line 49-100) to read weights from SettingsService instead of Config:

```python
from arxiv_explorer.services.settings_service import SettingsService

class RecommendationEngine:
    def __init__(self) -> None:
        # ... existing init ...
        self._settings = SettingsService()

    def score_papers(self, papers, user_profile, preferred_categories, keywords):
        weights = self._settings.get_weights()
        content_weight = weights["content"] / 100.0
        category_weight = weights["category"] / 100.0
        keyword_weight = weights["keyword"] / 100.0
        recency_weight = weights["recency"] / 100.0
        
        # ... rest uses these local variables instead of config.content_weight etc ...
```

Replace all references to `config.content_weight`, `config.category_weight`, `config.keyword_weight`, `config.recency_weight` with the local variables.

- [ ] **Step 2: Run existing recommendation tests**

Run: `uv run pytest tests/test_recommendation.py -v`
Expected: PASS (weights should be close enough to previous values)

- [ ] **Step 3: Commit**

```bash
git add src/arxiv_explorer/services/recommendation.py
git commit -m "feat: recommendation engine reads weights from settings"
```

---

### Task 5.3: TUI — Weight Bars in Preferences

**Files:**
- Modify: `src/arxiv_explorer/tui/screens/preferences.py`
- Modify: `src/arxiv_explorer/tui/styles/app.tcss`

- [ ] **Step 1: Add weights section to PreferencesPane**

In `compose()`, add a new section:

```python
with Vertical(id="weights-section", classes="pref-section"):
    yield Static("Recommendation Weights", classes="section-title")
    for key in ["content", "category", "keyword", "recency"]:
        label = {
            "content": "Content Similarity",
            "category": "Category Match",
            "keyword": "Keyword Match",
            "recency": "Recency Bonus",
        }[key]
        with Horizontal(classes="weight-row", id=f"weight-row-{key}"):
            yield Static(f"{label:20s}", classes="weight-label")
            yield Static("", id=f"weight-bar-{key}", classes="weight-bar")
            yield Static("", id=f"weight-pct-{key}", classes="weight-pct")
    yield Static("Total: 100%", id="weight-total")
    yield Static("[←→] Adjust  [r] Reset defaults", classes="weight-hint")
```

- [ ] **Step 2: Implement weight bar rendering and key handling**

```python
def _load_weights(self) -> None:
    weights = self.app.service_bridge.settings.get_weights()
    self._current_weights = weights
    for key, value in weights.items():
        bar_len = value * 30 // 100  # 30 chars wide bar
        bar = "█" * bar_len + "░" * (30 - bar_len)
        self.query_one(f"#weight-bar-{key}", Static).update(f"[{bar}]")
        self.query_one(f"#weight-pct-{key}", Static).update(f" {value:3d}%")

def _on_key_weight_adjust(self, key: str, delta: int) -> None:
    from arxiv_explorer.services.settings_service import adjust_weights
    current = self._current_weights[key]
    new_val = max(0, min(100, current + delta))
    self._current_weights = adjust_weights(key, new_val, self._current_weights)
    self.app.service_bridge.settings.set_weights(self._current_weights)
    self._load_weights()
```

Handle left/right arrows when focus is on a weight row, and `r` to reset.

- [ ] **Step 3: Add CSS for weight bars**

```css
.weight-row {
    height: 1;
    margin: 0 1;
}

.weight-label {
    width: 22;
}

.weight-bar {
    width: 32;
    color: $accent;
}

.weight-pct {
    width: 6;
    text-align: right;
}
```

- [ ] **Step 4: Manual TUI test**

Run: `uv run axp tui`
- Navigate to Prefs → Weights section
- Use left/right arrows to adjust a weight
- Verify others auto-adjust to maintain 100%
- Press `r` to reset defaults

- [ ] **Step 5: Commit**

```bash
git add src/arxiv_explorer/tui/screens/preferences.py src/arxiv_explorer/tui/styles/app.tcss
git commit -m "feat: add weight percentage bars with interactive adjustment in Prefs"
```

---

## Branch 6: `feature/category-fuzzy-search`

### Task 6.1: arXiv Category Data

**Files:**
- Create: `src/arxiv_explorer/core/arxiv_categories.py`
- Test: `tests/test_category_fuzzy.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_category_fuzzy.py
import pytest
from arxiv_explorer.core.arxiv_categories import ARXIV_CATEGORIES, get_all_categories


class TestCategoryData:
    def test_has_physics(self):
        assert "Physics" in ARXIV_CATEGORIES

    def test_has_cs(self):
        assert "Computer Science" in ARXIV_CATEGORIES

    def test_has_math(self):
        assert "Mathematics" in ARXIV_CATEGORIES

    def test_hep_ph_exists(self):
        assert "hep-ph" in ARXIV_CATEGORIES["Physics"]

    def test_cs_ai_exists(self):
        assert "cs.AI" in ARXIV_CATEGORIES["Computer Science"]

    def test_get_all_categories_flat(self):
        cats = get_all_categories()
        # Returns list of (code, full_name, group)
        assert len(cats) > 100
        codes = {c[0] for c in cats}
        assert "hep-ph" in codes
        assert "cs.AI" in codes
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_category_fuzzy.py::TestCategoryData -v`
Expected: FAIL

- [ ] **Step 3: Create category data file**

Create `src/arxiv_explorer/core/arxiv_categories.py` with the complete arXiv taxonomy. This is a large static dictionary. Key groups and representative categories:

```python
"""Static arXiv category taxonomy."""

ARXIV_CATEGORIES: dict[str, dict[str, str]] = {
    "Physics": {
        "astro-ph": "Astrophysics",
        "astro-ph.CO": "Cosmology and Nongalactic Astrophysics",
        "astro-ph.EP": "Earth and Planetary Astrophysics",
        "astro-ph.GA": "Astrophysics of Galaxies",
        "astro-ph.HE": "High Energy Astrophysical Phenomena",
        "astro-ph.IM": "Instrumentation and Methods for Astrophysics",
        "astro-ph.SR": "Solar and Stellar Astrophysics",
        "cond-mat": "Condensed Matter",
        "cond-mat.dis-nn": "Disordered Systems and Neural Networks",
        "cond-mat.mes-hall": "Mesoscale and Nanoscale Physics",
        "cond-mat.mtrl-sci": "Materials Science",
        "cond-mat.other": "Other Condensed Matter",
        "cond-mat.quant-gas": "Quantum Gases",
        "cond-mat.soft": "Soft Condensed Matter",
        "cond-mat.stat-mech": "Statistical Mechanics",
        "cond-mat.str-el": "Strongly Correlated Electrons",
        "cond-mat.supr-con": "Superconductivity",
        "gr-qc": "General Relativity and Quantum Cosmology",
        "hep-ex": "High Energy Physics - Experiment",
        "hep-lat": "High Energy Physics - Lattice",
        "hep-ph": "High Energy Physics - Phenomenology",
        "hep-th": "High Energy Physics - Theory",
        "math-ph": "Mathematical Physics",
        "nlin.AO": "Adaptation and Self-Organizing Systems",
        "nlin.CD": "Chaotic Dynamics",
        "nlin.CG": "Cellular Automata and Lattice Gases",
        "nlin.PS": "Pattern Formation and Solitons",
        "nlin.SI": "Exactly Solvable and Integrable Systems",
        "nucl-ex": "Nuclear Experiment",
        "nucl-th": "Nuclear Theory",
        "physics.acc-ph": "Accelerator Physics",
        "physics.ao-ph": "Atmospheric and Oceanic Physics",
        "physics.app-ph": "Applied Physics",
        "physics.atm-clus": "Atomic and Molecular Clusters",
        "physics.atom-ph": "Atomic Physics",
        "physics.bio-ph": "Biological Physics",
        "physics.chem-ph": "Chemical Physics",
        "physics.class-ph": "Classical Physics",
        "physics.comp-ph": "Computational Physics",
        "physics.data-an": "Data Analysis, Statistics and Probability",
        "physics.ed-ph": "Physics Education",
        "physics.flu-dyn": "Fluid Dynamics",
        "physics.gen-ph": "General Physics",
        "physics.geo-ph": "Geophysics",
        "physics.hist-ph": "History and Philosophy of Physics",
        "physics.ins-det": "Instrumentation and Detectors",
        "physics.med-ph": "Medical Physics",
        "physics.optics": "Optics",
        "physics.plasm-ph": "Plasma Physics",
        "physics.pop-ph": "Popular Physics",
        "physics.soc-ph": "Physics and Society",
        "physics.space-ph": "Space Physics",
        "quant-ph": "Quantum Physics",
    },
    "Computer Science": {
        "cs.AI": "Artificial Intelligence",
        "cs.AR": "Hardware Architecture",
        "cs.CC": "Computational Complexity",
        "cs.CE": "Computational Engineering, Finance, and Science",
        "cs.CG": "Computational Geometry",
        "cs.CL": "Computation and Language",
        "cs.CR": "Cryptography and Security",
        "cs.CV": "Computer Vision and Pattern Recognition",
        "cs.CY": "Computers and Society",
        "cs.DB": "Databases",
        "cs.DC": "Distributed, Parallel, and Cluster Computing",
        "cs.DL": "Digital Libraries",
        "cs.DM": "Discrete Mathematics",
        "cs.DS": "Data Structures and Algorithms",
        "cs.ET": "Emerging Technologies",
        "cs.FL": "Formal Languages and Automata Theory",
        "cs.GL": "General Literature",
        "cs.GR": "Graphics",
        "cs.GT": "Computer Science and Game Theory",
        "cs.HC": "Human-Computer Interaction",
        "cs.IR": "Information Retrieval",
        "cs.IT": "Information Theory",
        "cs.LG": "Machine Learning",
        "cs.LO": "Logic in Computer Science",
        "cs.MA": "Multiagent Systems",
        "cs.MM": "Multimedia",
        "cs.MS": "Mathematical Software",
        "cs.NA": "Numerical Analysis",
        "cs.NE": "Neural and Evolutionary Computing",
        "cs.NI": "Networking and Internet Architecture",
        "cs.OH": "Other Computer Science",
        "cs.OS": "Operating Systems",
        "cs.PF": "Performance",
        "cs.PL": "Programming Languages",
        "cs.RO": "Robotics",
        "cs.SC": "Symbolic Computation",
        "cs.SD": "Sound",
        "cs.SE": "Software Engineering",
        "cs.SI": "Social and Information Networks",
        "cs.SY": "Systems and Control",
    },
    "Mathematics": {
        "math.AC": "Commutative Algebra",
        "math.AG": "Algebraic Geometry",
        "math.AP": "Analysis of PDEs",
        "math.AT": "Algebraic Topology",
        "math.CA": "Classical Analysis and ODEs",
        "math.CO": "Combinatorics",
        "math.CT": "Category Theory",
        "math.CV": "Complex Variables",
        "math.DG": "Differential Geometry",
        "math.DS": "Dynamical Systems",
        "math.FA": "Functional Analysis",
        "math.GM": "General Mathematics",
        "math.GN": "General Topology",
        "math.GR": "Group Theory",
        "math.GT": "Geometric Topology",
        "math.HO": "History and Overview",
        "math.IT": "Information Theory",
        "math.KT": "K-Theory and Homology",
        "math.LO": "Logic",
        "math.MG": "Metric Geometry",
        "math.MP": "Mathematical Physics",
        "math.NA": "Numerical Analysis",
        "math.NT": "Number Theory",
        "math.OA": "Operator Algebras",
        "math.OC": "Optimization and Control",
        "math.PR": "Probability",
        "math.QA": "Quantum Algebra",
        "math.RA": "Rings and Algebras",
        "math.RT": "Representation Theory",
        "math.SG": "Symplectic Geometry",
        "math.SP": "Spectral Theory",
        "math.ST": "Statistics Theory",
    },
    "Statistics": {
        "stat.AP": "Applications",
        "stat.CO": "Computation",
        "stat.ME": "Methodology",
        "stat.ML": "Machine Learning",
        "stat.OT": "Other Statistics",
        "stat.TH": "Statistics Theory",
    },
    "Quantitative Biology": {
        "q-bio.BM": "Biomolecules",
        "q-bio.CB": "Cell Behavior",
        "q-bio.GN": "Genomics",
        "q-bio.MN": "Molecular Networks",
        "q-bio.NC": "Neurons and Cognition",
        "q-bio.OT": "Other Quantitative Biology",
        "q-bio.PE": "Populations and Evolution",
        "q-bio.QM": "Quantitative Methods",
        "q-bio.SC": "Subcellular Processes",
        "q-bio.TO": "Tissues and Organs",
    },
    "Quantitative Finance": {
        "q-fin.CP": "Computational Finance",
        "q-fin.EC": "Economics",
        "q-fin.GN": "General Finance",
        "q-fin.MF": "Mathematical Finance",
        "q-fin.PM": "Portfolio Management",
        "q-fin.PR": "Pricing of Securities",
        "q-fin.RM": "Risk Management",
        "q-fin.ST": "Statistical Finance",
        "q-fin.TR": "Trading and Market Microstructure",
    },
    "Electrical Engineering and Systems Science": {
        "eess.AS": "Audio and Speech Processing",
        "eess.IV": "Image and Video Processing",
        "eess.SP": "Signal Processing",
        "eess.SY": "Systems and Control",
    },
    "Economics": {
        "econ.EM": "Econometrics",
        "econ.GN": "General Economics",
        "econ.TH": "Theoretical Economics",
    },
}


def get_all_categories() -> list[tuple[str, str, str]]:
    """Return flat list of (code, full_name, group) for all categories."""
    result = []
    for group, cats in ARXIV_CATEGORIES.items():
        for code, name in cats.items():
            result.append((code, name, group))
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_category_fuzzy.py::TestCategoryData -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/arxiv_explorer/core/arxiv_categories.py tests/test_category_fuzzy.py
git commit -m "feat: add static arXiv category taxonomy"
```

---

### Task 6.2: Fuzzy Matching Algorithm

**Files:**
- Modify: `src/arxiv_explorer/core/arxiv_categories.py`
- Test: `tests/test_category_fuzzy.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_category_fuzzy.py`:

```python
from arxiv_explorer.core.arxiv_categories import fuzzy_search


class TestFuzzySearch:
    def test_exact_code_match(self):
        results = fuzzy_search("hep-ph")
        assert results[0][0] == "hep-ph"

    def test_prefix_match(self):
        results = fuzzy_search("hep")
        codes = [r[0] for r in results]
        assert "hep-ph" in codes
        assert "hep-th" in codes

    def test_full_name_match(self):
        results = fuzzy_search("quantum")
        codes = [r[0] for r in results]
        assert "quant-ph" in codes

    def test_partial_name_match(self):
        results = fuzzy_search("mach learn")
        codes = [r[0] for r in results]
        assert "cs.LG" in codes or "stat.ML" in codes

    def test_case_insensitive(self):
        results = fuzzy_search("CS.AI")
        assert results[0][0] == "cs.AI"

    def test_empty_query_returns_all(self):
        results = fuzzy_search("")
        assert len(results) > 100

    def test_no_match(self):
        results = fuzzy_search("xyznonexistent")
        assert len(results) == 0

    def test_returns_code_name_group(self):
        results = fuzzy_search("hep-ph")
        code, name, group = results[0]
        assert code == "hep-ph"
        assert "Phenomenology" in name
        assert group == "Physics"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_category_fuzzy.py::TestFuzzySearch -v`
Expected: FAIL

- [ ] **Step 3: Implement fuzzy_search**

Add to `src/arxiv_explorer/core/arxiv_categories.py`:

```python
def fuzzy_search(query: str) -> list[tuple[str, str, str]]:
    """Fuzzy search categories. Returns list of (code, name, group) sorted by relevance."""
    if not query:
        return get_all_categories()

    query_lower = query.lower().strip()
    scored: list[tuple[float, str, str, str]] = []

    for code, name, group in get_all_categories():
        score = _fuzzy_score(query_lower, code.lower(), name.lower())
        if score > 0:
            scored.append((score, code, name, group))

    scored.sort(key=lambda x: -x[0])
    return [(code, name, group) for _, code, name, group in scored]


def _fuzzy_score(query: str, code: str, name: str) -> float:
    """Score a category against a query. Higher = better match."""
    best = 0.0

    # Exact match on code
    if query == code:
        return 100.0

    # Prefix match on code
    if code.startswith(query):
        best = max(best, 80.0 + len(query))

    # Exact match on name
    if query == name:
        return 95.0

    # Prefix match on name
    if name.startswith(query):
        best = max(best, 70.0 + len(query))

    # Substring match on code
    if query in code:
        best = max(best, 60.0 + len(query))

    # Substring match on name
    if query in name:
        best = max(best, 50.0 + len(query))

    # Token match: all query tokens appear in name
    query_tokens = query.split()
    if query_tokens and all(t in name for t in query_tokens):
        best = max(best, 40.0 + len(query))

    # Character sequence match (fuzzy)
    seq_score = _char_sequence_score(query, code + " " + name)
    if seq_score > 0.5:
        best = max(best, 20.0 * seq_score)

    return best


def _char_sequence_score(query: str, target: str) -> float:
    """Score based on characters appearing in order. Returns 0-1."""
    if not query:
        return 0.0
    target_idx = 0
    matched = 0
    for ch in query:
        while target_idx < len(target):
            if target[target_idx] == ch:
                matched += 1
                target_idx += 1
                break
            target_idx += 1
    return matched / len(query) if query else 0.0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_category_fuzzy.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/arxiv_explorer/core/arxiv_categories.py tests/test_category_fuzzy.py
git commit -m "feat: add fuzzy search algorithm for arXiv categories"
```

---

### Task 6.3: TUI — Category Picker Modal

**Files:**
- Create: `src/arxiv_explorer/tui/screens/category_picker.py`
- Modify: `src/arxiv_explorer/tui/screens/preferences.py`
- Modify: `src/arxiv_explorer/tui/styles/app.tcss`

- [ ] **Step 1: Create CategoryPickerScreen**

```python
# src/arxiv_explorer/tui/screens/category_picker.py
"""Modal for searching and selecting arXiv categories."""

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, DataTable, Static, ListView, ListItem, Label

from arxiv_explorer.core.arxiv_categories import (
    ARXIV_CATEGORIES,
    fuzzy_search,
    get_all_categories,
)


class CategoryPickerScreen(ModalScreen[str | None]):
    """Two-mode category picker: fuzzy search (default) and hierarchical browser."""

    BINDINGS = [
        Binding("escape", "dismiss(None)", "Cancel"),
        Binding("tab", "toggle_mode", "Toggle Mode"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._search_mode = True  # True = fuzzy search, False = browser

    def compose(self) -> ComposeResult:
        with Vertical(id="category-picker"):
            yield Static("Add Category", id="picker-header")
            yield Input(placeholder="Search categories...", id="cat-search")
            yield DataTable(id="cat-results")
            yield ListView(id="cat-browser")
            yield Static("[↑↓] Navigate  [Enter] Select  [Tab] Toggle mode", id="cat-hint")

    def on_mount(self) -> None:
        table = self.query_one("#cat-results", DataTable)
        table.add_columns("Code", "Name", "Group")
        table.cursor_type = "row"
        browser = self.query_one("#cat-browser", ListView)
        browser.display = False
        self._update_search_results("")

    def action_toggle_mode(self) -> None:
        self._search_mode = not self._search_mode
        search_input = self.query_one("#cat-search", Input)
        table = self.query_one("#cat-results", DataTable)
        browser = self.query_one("#cat-browser", ListView)

        if self._search_mode:
            search_input.display = True
            table.display = True
            browser.display = False
            search_input.focus()
        else:
            search_input.display = False
            table.display = False
            browser.display = True
            self._populate_browser()
            browser.focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "cat-search":
            self._update_search_results(event.value)

    def _update_search_results(self, query: str) -> None:
        table = self.query_one("#cat-results", DataTable)
        table.clear()
        results = fuzzy_search(query)[:20]  # Limit displayed results
        for code, name, group in results:
            table.add_row(code, name, group, key=code)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.data_table.id == "cat-results":
            code = str(event.row_key.value)
            self.dismiss(code)

    def _populate_browser(self) -> None:
        browser = self.query_one("#cat-browser", ListView)
        browser.clear()
        for group, cats in ARXIV_CATEGORIES.items():
            browser.append(
                ListItem(
                    Label(f"▸ {group} ({len(cats)})"),
                    id=f"group-{group.replace(' ', '_')}",
                )
            )

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        item_id = event.item.id or ""
        if item_id.startswith("group-"):
            group_name = item_id.replace("group-", "").replace("_", " ")
            self._expand_group(group_name)
        elif item_id.startswith("cat-"):
            code = item_id.replace("cat-", "").replace("_", ".")
            self.dismiss(code)

    def _expand_group(self, group_name: str) -> None:
        browser = self.query_one("#cat-browser", ListView)
        browser.clear()
        for group, cats in ARXIV_CATEGORIES.items():
            if group == group_name:
                browser.append(
                    ListItem(
                        Label(f"▾ {group} ({len(cats)})"),
                        id=f"group-{group.replace(' ', '_')}",
                    )
                )
                for code, name in cats.items():
                    browser.append(
                        ListItem(
                            Label(f"    {code:16s} {name}"),
                            id=f"cat-{code.replace('.', '_')}",
                        )
                    )
            else:
                browser.append(
                    ListItem(
                        Label(f"▸ {group} ({len(cats)})"),
                        id=f"group-{group.replace(' ', '_')}",
                    )
                )
```

- [ ] **Step 2: Wire into PreferencesPane**

In `src/arxiv_explorer/tui/screens/preferences.py`, replace the text-input category addition with the picker:

```python
from arxiv_explorer.tui.screens.category_picker import CategoryPickerScreen

def _add_category(self) -> None:
    def on_result(code: str | None) -> None:
        if code:
            self._do_add_category(code, priority=1)
    self.app.push_screen(CategoryPickerScreen(), callback=on_result)
```

- [ ] **Step 3: Add CSS for category picker**

Append to `src/arxiv_explorer/tui/styles/app.tcss`:

```css
/* Category picker */
#category-picker {
    width: 70;
    height: 80%;
    background: $surface;
    border: round $primary;
    padding: 1 2;
}

#picker-header {
    text-style: bold;
    margin-bottom: 1;
}

#cat-hint {
    dock: bottom;
    height: 1;
    color: $text-muted;
}
```

- [ ] **Step 4: Manual TUI test**

Run: `uv run axp tui`
- Navigate to Prefs → press `a` to add category
- Type "quan" → see filtered results
- Press Tab → switch to browser mode
- Expand Physics group → see categories
- Select one → verify it's added to preferences

- [ ] **Step 5: Commit**

```bash
git add src/arxiv_explorer/tui/screens/category_picker.py src/arxiv_explorer/tui/screens/preferences.py src/arxiv_explorer/tui/styles/app.tcss
git commit -m "feat: add category fuzzy search and hierarchical browser picker"
```

---

## Final Integration

### Task F.1: Run Full Test Suite and Fix

After all feature branches are merged to `dev`:

- [ ] **Step 1: Run all tests**

```bash
cd /home/axect/Documents/Project/AI_Project/arXiv_explorer
uv run pytest -v --tb=short
```

- [ ] **Step 2: Run linter**

```bash
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
```

- [ ] **Step 3: Fix any issues**

- [ ] **Step 4: Manual full TUI walkthrough**

Test each feature end-to-end:
1. Daily fetch → author section visible → bookmark toggle works
2. Lists tab → tree view → folders, move, copy, rename
3. Like/Dislike lists pinned, dual storage working
4. Background jobs → summarize → navigate away → toast on complete → Jobs panel
5. Prefs → weight bars adjust correctly → reset works
6. Prefs → category add via fuzzy search and browser

- [ ] **Step 5: Final commit and PR**

```bash
git checkout main
git merge dev
```
