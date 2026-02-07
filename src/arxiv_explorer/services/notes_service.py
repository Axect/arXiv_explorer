"""Notes service."""

from datetime import datetime
from typing import Optional

from ..core.database import get_connection
from ..core.models import NoteType, PaperNote


class NotesService:
    """Paper notes management."""

    def add_note(
        self,
        arxiv_id: str,
        content: str,
        note_type: NoteType = NoteType.GENERAL,
    ) -> PaperNote:
        """Add a note."""
        with get_connection() as conn:
            cursor = conn.execute(
                """INSERT INTO paper_notes (arxiv_id, note_type, content)
                   VALUES (?, ?, ?)""",
                (arxiv_id, note_type.value, content),
            )
            conn.commit()

            return PaperNote(
                id=cursor.lastrowid,
                arxiv_id=arxiv_id,
                note_type=note_type,
                content=content,
                created_at=datetime.now(),
            )

    def delete_note(self, note_id: int) -> bool:
        """Delete a note."""
        with get_connection() as conn:
            cursor = conn.execute("DELETE FROM paper_notes WHERE id = ?", (note_id,))
            conn.commit()
            return cursor.rowcount > 0

    def get_notes(
        self,
        arxiv_id: Optional[str] = None,
        note_type: Optional[NoteType] = None,
    ) -> list[PaperNote]:
        """Get the list of notes."""
        with get_connection() as conn:
            query = "SELECT * FROM paper_notes WHERE 1=1"
            params = []

            if arxiv_id:
                query += " AND arxiv_id = ?"
                params.append(arxiv_id)

            if note_type:
                query += " AND note_type = ?"
                params.append(note_type.value)

            query += " ORDER BY created_at DESC"

            rows = conn.execute(query, params).fetchall()

            return [
                PaperNote(
                    id=row["id"],
                    arxiv_id=row["arxiv_id"],
                    note_type=NoteType(row["note_type"]),
                    content=row["content"],
                    created_at=datetime.fromisoformat(row["created_at"]),
                )
                for row in rows
            ]
