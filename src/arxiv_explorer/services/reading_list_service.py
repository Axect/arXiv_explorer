"""Reading list service."""

from datetime import datetime
from typing import Optional

from ..core.database import get_connection
from ..core.models import ReadingList, ReadingListPaper, ReadingStatus


class ReadingListService:
    """Reading list management."""

    def create_list(self, name: str, description: Optional[str] = None) -> ReadingList:
        """Create a reading list."""
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO reading_lists (name, description) VALUES (?, ?)", (name, description)
            )
            conn.commit()

            row = conn.execute("SELECT * FROM reading_lists WHERE name = ?", (name,)).fetchone()

            return ReadingList(
                id=row["id"],
                name=row["name"],
                description=row["description"],
                created_at=datetime.fromisoformat(row["created_at"]),
            )

    def delete_list(self, name: str) -> bool:
        """Delete a reading list."""
        with get_connection() as conn:
            cursor = conn.execute("DELETE FROM reading_lists WHERE name = ?", (name,))
            conn.commit()
            return cursor.rowcount > 0

    def get_list(self, name: str) -> Optional[ReadingList]:
        """Get a reading list by name."""
        with get_connection() as conn:
            row = conn.execute("SELECT * FROM reading_lists WHERE name = ?", (name,)).fetchone()

            if row:
                return ReadingList(
                    id=row["id"],
                    name=row["name"],
                    description=row["description"],
                    created_at=datetime.fromisoformat(row["created_at"]),
                )
            return None

    def get_all_lists(self) -> list[ReadingList]:
        """Get all reading lists."""
        with get_connection() as conn:
            rows = conn.execute("SELECT * FROM reading_lists ORDER BY created_at DESC").fetchall()

            return [
                ReadingList(
                    id=row["id"],
                    name=row["name"],
                    description=row["description"],
                    created_at=datetime.fromisoformat(row["created_at"]),
                )
                for row in rows
            ]

    def add_paper(self, list_name: str, arxiv_id: str) -> bool:
        """Add a paper to a list."""
        reading_list = self.get_list(list_name)
        if not reading_list:
            return False

        with get_connection() as conn:
            # Get the maximum position
            max_pos = (
                conn.execute(
                    "SELECT MAX(position) FROM reading_list_papers WHERE list_id = ?",
                    (reading_list.id,),
                ).fetchone()[0]
                or 0
            )

            conn.execute(
                """INSERT OR IGNORE INTO reading_list_papers
                   (list_id, arxiv_id, position) VALUES (?, ?, ?)""",
                (reading_list.id, arxiv_id, max_pos + 1),
            )
            conn.commit()
            return True

    def remove_paper(self, list_name: str, arxiv_id: str) -> bool:
        """Remove a paper from a list."""
        reading_list = self.get_list(list_name)
        if not reading_list:
            return False

        with get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM reading_list_papers WHERE list_id = ? AND arxiv_id = ?",
                (reading_list.id, arxiv_id),
            )
            conn.commit()
            return cursor.rowcount > 0

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
        """Get the papers in a list."""
        reading_list = self.get_list(list_name)
        if not reading_list:
            return []

        with get_connection() as conn:
            rows = conn.execute(
                """SELECT * FROM reading_list_papers
                   WHERE list_id = ? ORDER BY position""",
                (reading_list.id,),
            ).fetchall()

            return [
                ReadingListPaper(
                    id=row["id"],
                    list_id=row["list_id"],
                    arxiv_id=row["arxiv_id"],
                    status=ReadingStatus(row["status"]),
                    position=row["position"],
                    added_at=datetime.fromisoformat(row["added_at"]),
                )
                for row in rows
            ]
