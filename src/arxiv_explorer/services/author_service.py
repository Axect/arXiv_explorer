"""Preferred author management and name matching."""

import re
from datetime import datetime

from arxiv_explorer.core.database import get_connection
from arxiv_explorer.core.models import PreferredAuthor


def _normalize(name: str) -> str:
    return re.sub(r"\s+", " ", name.lower().strip().replace(".", ""))


def _tokenize(name: str) -> list[str]:
    return _normalize(name).split()


def _is_initial_of(initial: str, full: str) -> bool:
    return len(initial) == 1 and full.startswith(initial)


def matches_author(registered: str, paper_author: str) -> bool:
    reg_tokens = _tokenize(registered)
    paper_tokens = _tokenize(paper_author)

    if len(reg_tokens) < 2 or len(paper_tokens) < 2:
        return False

    if reg_tokens[-1] != paper_tokens[-1]:
        return False

    reg_first = reg_tokens[:-1]
    paper_first = paper_tokens[:-1]

    if _match_first_names(reg_first, paper_first):
        return True

    # Try merge matching
    if "".join(reg_first) == "".join(paper_first):
        return True

    return False


def _match_first_names(reg: list[str], paper: list[str]) -> bool:
    if len(reg) != len(paper):
        return False
    for r, p in zip(reg, paper, strict=False):
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
            conn.commit()
            row = conn.execute(
                "SELECT * FROM preferred_authors WHERE name = ?", (name.strip(),)
            ).fetchone()
            return PreferredAuthor(
                id=row["id"],
                name=row["name"],
                added_at=datetime.fromisoformat(row["added_at"]),
            )

    def remove_author(self, name: str) -> bool:
        with get_connection() as conn:
            cursor = conn.execute("DELETE FROM preferred_authors WHERE name = ?", (name.strip(),))
            conn.commit()
            return cursor.rowcount > 0

    def get_authors(self) -> list[PreferredAuthor]:
        with get_connection() as conn:
            rows = conn.execute("SELECT * FROM preferred_authors ORDER BY name").fetchall()
            return [
                PreferredAuthor(
                    id=r["id"],
                    name=r["name"],
                    added_at=datetime.fromisoformat(r["added_at"]),
                )
                for r in rows
            ]

    def filter_author_papers(self, papers: list) -> tuple[list, list]:
        authors = self.get_authors()
        if not authors:
            return [], papers
        author_papers = []
        remaining = []
        for paper in papers:
            paper_obj = paper.paper if hasattr(paper, "paper") else paper
            if any(any(matches_author(a.name, pa) for pa in paper_obj.authors) for a in authors):
                author_papers.append(paper)
            else:
                remaining.append(paper)
        return author_papers, remaining
