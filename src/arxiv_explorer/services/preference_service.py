"""User preference service."""

from datetime import datetime

from ..core.database import get_connection
from ..core.models import InteractionType, KeywordInterest, PreferredCategory


class PreferenceService:
    """User preference management."""

    # === Category management ===

    def add_category(self, category: str, priority: int = 1) -> PreferredCategory:
        """Add a preferred category."""
        with get_connection() as conn:
            conn.execute(
                """INSERT INTO preferred_categories (category, priority)
                   VALUES (?, ?)
                   ON CONFLICT(category) DO UPDATE SET priority = ?""",
                (category, priority, priority),
            )
            conn.commit()

            row = conn.execute(
                "SELECT * FROM preferred_categories WHERE category = ?", (category,)
            ).fetchone()

            return PreferredCategory(
                id=row["id"],
                category=row["category"],
                priority=row["priority"],
                added_at=datetime.fromisoformat(row["added_at"]),
            )

    def remove_category(self, category: str) -> bool:
        """Remove a preferred category."""
        with get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM preferred_categories WHERE category = ?", (category,)
            )
            conn.commit()
            return cursor.rowcount > 0

    def get_categories(self) -> list[PreferredCategory]:
        """Get the list of preferred categories."""
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM preferred_categories ORDER BY priority DESC"
            ).fetchall()

            return [
                PreferredCategory(
                    id=row["id"],
                    category=row["category"],
                    priority=row["priority"],
                    added_at=datetime.fromisoformat(row["added_at"]),
                )
                for row in rows
            ]

    # === Paper interactions ===

    def mark_interesting(self, arxiv_id: str) -> None:
        """Mark a paper as interesting."""
        with get_connection() as conn:
            # Remove existing not_interesting
            conn.execute(
                """DELETE FROM paper_interactions
                   WHERE arxiv_id = ? AND interaction_type = ?""",
                (arxiv_id, InteractionType.NOT_INTERESTING.value),
            )
            # Add interesting
            conn.execute(
                """INSERT OR REPLACE INTO paper_interactions (arxiv_id, interaction_type)
                   VALUES (?, ?)""",
                (arxiv_id, InteractionType.INTERESTING.value),
            )
            conn.commit()

    def mark_not_interesting(self, arxiv_id: str) -> None:
        """Mark a paper as not interesting."""
        with get_connection() as conn:
            # Remove existing interesting
            conn.execute(
                """DELETE FROM paper_interactions
                   WHERE arxiv_id = ? AND interaction_type = ?""",
                (arxiv_id, InteractionType.INTERESTING.value),
            )
            # Add not_interesting
            conn.execute(
                """INSERT OR REPLACE INTO paper_interactions (arxiv_id, interaction_type)
                   VALUES (?, ?)""",
                (arxiv_id, InteractionType.NOT_INTERESTING.value),
            )
            conn.commit()

    def get_interesting_papers(self) -> list[str]:
        """Get the list of paper IDs marked as interesting."""
        with get_connection() as conn:
            rows = conn.execute(
                """SELECT arxiv_id FROM paper_interactions
                   WHERE interaction_type = ?
                   ORDER BY created_at DESC""",
                (InteractionType.INTERESTING.value,),
            ).fetchall()
            return [row["arxiv_id"] for row in rows]

    def get_interaction(self, arxiv_id: str) -> InteractionType | None:
        """Get the interaction status of a paper."""
        with get_connection() as conn:
            row = conn.execute(
                "SELECT interaction_type FROM paper_interactions WHERE arxiv_id = ?", (arxiv_id,)
            ).fetchone()

            if row:
                return InteractionType(row["interaction_type"])
            return None

    # === Keyword interests ===

    def add_keyword(self, keyword: str, weight: float = 1.0) -> None:
        """Add a keyword interest."""
        with get_connection() as conn:
            conn.execute(
                """INSERT INTO keyword_interests (keyword, weight, source)
                   VALUES (?, ?, 'explicit')
                   ON CONFLICT(keyword) DO UPDATE SET weight = ?""",
                (keyword.lower(), weight, weight),
            )
            conn.commit()

    def remove_keyword(self, keyword: str) -> bool:
        """Remove a keyword interest."""
        with get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM keyword_interests WHERE keyword = ?", (keyword.lower(),)
            )
            conn.commit()
            return cursor.rowcount > 0

    def get_keywords(self) -> list[KeywordInterest]:
        """Get the list of keyword interests."""
        with get_connection() as conn:
            rows = conn.execute("SELECT * FROM keyword_interests ORDER BY weight DESC").fetchall()

            return [
                KeywordInterest(
                    id=row["id"],
                    keyword=row["keyword"],
                    weight=row["weight"],
                    source=row["source"],
                )
                for row in rows
            ]
