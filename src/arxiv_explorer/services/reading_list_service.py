"""Reading list service."""

import sqlite3
from datetime import date, datetime
from typing import Optional

from ..core.database import get_connection
from ..core.models import ReadingList, ReadingListPaper, ReadingStatus


def _row_to_reading_list(row: sqlite3.Row) -> ReadingList:
    """Convert a database row to a ReadingList instance."""
    return ReadingList(
        id=row["id"],
        name=row["name"],
        description=row["description"],
        parent_id=row["parent_id"],
        is_folder=bool(row["is_folder"]),
        is_system=bool(row["is_system"]),
        created_at=datetime.fromisoformat(row["created_at"]),
    )


def _row_to_reading_list_paper(row: sqlite3.Row) -> ReadingListPaper:
    """Convert a database row to a ReadingListPaper instance."""
    return ReadingListPaper(
        id=row["id"],
        list_id=row["list_id"],
        arxiv_id=row["arxiv_id"],
        status=ReadingStatus(row["status"]),
        position=row["position"],
        added_at=datetime.fromisoformat(row["added_at"]),
    )


class ReadingListService:
    """Reading list management."""

    def create_list(
        self,
        name: str,
        description: Optional[str] = None,
        parent_id: Optional[int] = None,
    ) -> ReadingList:
        """Create a reading list."""
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO reading_lists (name, description, parent_id, is_folder, is_system) VALUES (?, ?, ?, 0, 0)",
                (name, description, parent_id),
            )
            conn.commit()

            row = conn.execute(
                "SELECT * FROM reading_lists WHERE name = ? AND (parent_id IS ? OR parent_id = ?)",
                (name, parent_id, parent_id),
            ).fetchone()

            return _row_to_reading_list(row)

    def create_folder(self, name: str, parent_id: Optional[int] = None) -> ReadingList:
        """Create a folder (is_folder=True)."""
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO reading_lists (name, description, parent_id, is_folder, is_system) VALUES (?, NULL, ?, 1, 0)",
                (name, parent_id),
            )
            conn.commit()

            row = conn.execute(
                "SELECT * FROM reading_lists WHERE name = ? AND is_folder = 1 AND (parent_id IS ? OR parent_id = ?)",
                (name, parent_id, parent_id),
            ).fetchone()

            return _row_to_reading_list(row)

    def delete_list(self, name: str) -> bool:
        """Delete a reading list (rejects system lists)."""
        with get_connection() as conn:
            row = conn.execute(
                "SELECT is_system FROM reading_lists WHERE name = ?", (name,)
            ).fetchone()
            if row and bool(row["is_system"]):
                return False
            cursor = conn.execute("DELETE FROM reading_lists WHERE name = ?", (name,))
            conn.commit()
            return cursor.rowcount > 0

    def get_list(self, name: str) -> Optional[ReadingList]:
        """Get a reading list by name."""
        with get_connection() as conn:
            row = conn.execute("SELECT * FROM reading_lists WHERE name = ?", (name,)).fetchone()

            if row:
                return _row_to_reading_list(row)
            return None

    def get_list_by_id(self, list_id: int) -> Optional[ReadingList]:
        """Get a reading list by ID."""
        with get_connection() as conn:
            row = conn.execute("SELECT * FROM reading_lists WHERE id = ?", (list_id,)).fetchone()

            if row:
                return _row_to_reading_list(row)
            return None

    def get_all_lists(self) -> list[ReadingList]:
        """Get all reading lists."""
        with get_connection() as conn:
            rows = conn.execute("SELECT * FROM reading_lists ORDER BY created_at DESC").fetchall()

            return [_row_to_reading_list(row) for row in rows]

    def get_children(self, parent_id: int) -> list[ReadingList]:
        """Get all direct children of a folder, ordered by name."""
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM reading_lists WHERE parent_id = ? ORDER BY name",
                (parent_id,),
            ).fetchall()
            return [_row_to_reading_list(row) for row in rows]

    def get_top_level(self) -> list[ReadingList]:
        """Get all top-level items (no parent), ordered by is_system DESC, name."""
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM reading_lists WHERE parent_id IS NULL ORDER BY is_system DESC, name"
            ).fetchall()
            return [_row_to_reading_list(row) for row in rows]

    def rename_item(self, list_id: int, new_name: str) -> bool:
        """Rename a reading list or folder. Rejects system lists."""
        with get_connection() as conn:
            row = conn.execute(
                "SELECT is_system FROM reading_lists WHERE id = ?", (list_id,)
            ).fetchone()
            if row is None:
                return False
            if bool(row["is_system"]):
                return False
            cursor = conn.execute(
                "UPDATE reading_lists SET name = ? WHERE id = ?",
                (new_name, list_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    # --- Paper operations by list_id ---

    def add_paper_to_list(self, list_id: int, arxiv_id: str) -> bool:
        """Add a paper to a list by list ID with auto-incrementing position."""
        with get_connection() as conn:
            max_pos = (
                conn.execute(
                    "SELECT MAX(position) FROM reading_list_papers WHERE list_id = ?",
                    (list_id,),
                ).fetchone()[0]
                or 0
            )
            cursor = conn.execute(
                """INSERT OR IGNORE INTO reading_list_papers
                   (list_id, arxiv_id, position) VALUES (?, ?, ?)""",
                (list_id, arxiv_id, max_pos + 1),
            )
            conn.commit()
            return cursor.rowcount > 0

    def get_papers_by_list_id(self, list_id: int) -> list[ReadingListPaper]:
        """Get all papers in a list by list ID, ordered by added_at DESC."""
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM reading_list_papers WHERE list_id = ? ORDER BY added_at DESC",
                (list_id,),
            ).fetchall()
            return [_row_to_reading_list_paper(row) for row in rows]

    def remove_paper_from_list(self, list_id: int, arxiv_id: str) -> bool:
        """Remove a paper from a list by list ID."""
        with get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM reading_list_papers WHERE list_id = ? AND arxiv_id = ?",
                (list_id, arxiv_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def move_paper(self, from_list_id: int, to_list_id: int, arxiv_id: str) -> bool:
        """Move a paper from one list to another."""
        with get_connection() as conn:
            # Check source exists
            row = conn.execute(
                "SELECT id FROM reading_list_papers WHERE list_id = ? AND arxiv_id = ?",
                (from_list_id, arxiv_id),
            ).fetchone()
            if row is None:
                return False

            # Get next position in destination
            max_pos = (
                conn.execute(
                    "SELECT MAX(position) FROM reading_list_papers WHERE list_id = ?",
                    (to_list_id,),
                ).fetchone()[0]
                or 0
            )

            # Insert into destination (ignore if already there)
            conn.execute(
                """INSERT OR IGNORE INTO reading_list_papers
                   (list_id, arxiv_id, position) VALUES (?, ?, ?)""",
                (to_list_id, arxiv_id, max_pos + 1),
            )
            # Remove from source
            conn.execute(
                "DELETE FROM reading_list_papers WHERE list_id = ? AND arxiv_id = ?",
                (from_list_id, arxiv_id),
            )
            conn.commit()
            return True

    def copy_paper(self, from_list_id: int, to_list_id: int, arxiv_id: str) -> bool:
        """Copy a paper from one list to another (keeps original)."""
        with get_connection() as conn:
            # Check source exists
            row = conn.execute(
                "SELECT id FROM reading_list_papers WHERE list_id = ? AND arxiv_id = ?",
                (from_list_id, arxiv_id),
            ).fetchone()
            if row is None:
                return False

            # Get next position in destination
            max_pos = (
                conn.execute(
                    "SELECT MAX(position) FROM reading_list_papers WHERE list_id = ?",
                    (to_list_id,),
                ).fetchone()[0]
                or 0
            )

            cursor = conn.execute(
                """INSERT OR IGNORE INTO reading_list_papers
                   (list_id, arxiv_id, position) VALUES (?, ?, ?)""",
                (to_list_id, arxiv_id, max_pos + 1),
            )
            conn.commit()
            return cursor.rowcount > 0

    def move_list(self, list_id: int, target_folder_id: int) -> bool:
        """Move a list/folder into a target folder."""
        with get_connection() as conn:
            cursor = conn.execute(
                "UPDATE reading_lists SET parent_id = ? WHERE id = ?",
                (target_folder_id, list_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def copy_list(self, list_id: int, target_folder_id: int) -> Optional[ReadingList]:
        """Copy a list (and all its papers) into a target folder."""
        source = self.get_list_by_id(list_id)
        if source is None:
            return None

        with get_connection() as conn:
            # Create new list in target folder
            conn.execute(
                """INSERT INTO reading_lists
                   (name, description, parent_id, is_folder, is_system)
                   VALUES (?, ?, ?, ?, 0)""",
                (source.name, source.description, target_folder_id, int(source.is_folder)),
            )
            conn.commit()

            # Retrieve the newly created list by lastrowid
            new_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

            # Copy all papers
            papers = conn.execute(
                "SELECT arxiv_id, status, position FROM reading_list_papers WHERE list_id = ?",
                (list_id,),
            ).fetchall()

            for p in papers:
                conn.execute(
                    """INSERT OR IGNORE INTO reading_list_papers
                       (list_id, arxiv_id, status, position) VALUES (?, ?, ?, ?)""",
                    (new_id, p["arxiv_id"], p["status"], p["position"]),
                )
            conn.commit()

            row = conn.execute("SELECT * FROM reading_lists WHERE id = ?", (new_id,)).fetchone()
            return _row_to_reading_list(row)

    def toggle_paper_in_month_folder(self, arxiv_id: str, d: date) -> bool:
        """Toggle a paper in the month folder for the given date.

        Returns True if the paper was added, False if it was removed.
        Auto-creates the month folder (YYYYMM format) if it doesn't exist.
        """
        folder_name = d.strftime("%Y%m")

        # Get or create the month folder
        folder = self.get_list(folder_name)
        if folder is None:
            folder = self.create_folder(folder_name)

        # Check if paper is already in the folder
        with get_connection() as conn:
            existing = conn.execute(
                "SELECT id FROM reading_list_papers WHERE list_id = ? AND arxiv_id = ?",
                (folder.id, arxiv_id),
            ).fetchone()

        if existing:
            self.remove_paper_from_list(folder.id, arxiv_id)
            return False
        else:
            self.add_paper_to_list(folder.id, arxiv_id)
            return True

    # --- Legacy name-based operations (kept for backward compatibility) ---

    def add_paper(self, list_name: str, arxiv_id: str) -> bool:
        """Add a paper to a list by name."""
        reading_list = self.get_list(list_name)
        if not reading_list:
            return False
        return self.add_paper_to_list(reading_list.id, arxiv_id)

    def remove_paper(self, list_name: str, arxiv_id: str) -> bool:
        """Remove a paper from a list by name."""
        reading_list = self.get_list(list_name)
        if not reading_list:
            return False
        return self.remove_paper_from_list(reading_list.id, arxiv_id)

    def update_status(self, arxiv_id: str, status: ReadingStatus) -> bool:
        """Update a paper's reading status."""
        with get_connection() as conn:
            cursor = conn.execute(
                "UPDATE reading_list_papers SET status = ? WHERE arxiv_id = ?",
                (status.value, arxiv_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def get_papers(self, list_name: str) -> list[ReadingListPaper]:
        """Get the papers in a list by name."""
        reading_list = self.get_list(list_name)
        if not reading_list:
            return []
        return self.get_papers_by_list_id(reading_list.id)
