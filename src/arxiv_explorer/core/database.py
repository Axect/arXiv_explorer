"""Database management."""

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .config import get_config

SCHEMA = """
-- Preferred categories
CREATE TABLE IF NOT EXISTS preferred_categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT UNIQUE NOT NULL,
    priority INTEGER DEFAULT 1,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Paper interactions
CREATE TABLE IF NOT EXISTS paper_interactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    arxiv_id TEXT NOT NULL,
    interaction_type TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(arxiv_id, interaction_type)
);

-- Paper summary cache
CREATE TABLE IF NOT EXISTS paper_summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    arxiv_id TEXT UNIQUE NOT NULL,
    summary_short TEXT,
    summary_detailed TEXT,
    key_findings TEXT,
    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Reading Lists
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

-- Reading List Papers
CREATE TABLE IF NOT EXISTS reading_list_papers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    list_id INTEGER NOT NULL REFERENCES reading_lists(id) ON DELETE CASCADE,
    arxiv_id TEXT NOT NULL,
    status TEXT DEFAULT 'unread',
    position INTEGER DEFAULT 0,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(list_id, arxiv_id)
);

-- Paper Notes
CREATE TABLE IF NOT EXISTS paper_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    arxiv_id TEXT NOT NULL,
    note_type TEXT DEFAULT 'general',
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Keyword Interests
CREATE TABLE IF NOT EXISTS keyword_interests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword TEXT UNIQUE NOT NULL,
    weight REAL DEFAULT 1.0,
    source TEXT DEFAULT 'explicit'
);

-- Preferred Authors
CREATE TABLE IF NOT EXISTS preferred_authors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Paper Translations
CREATE TABLE IF NOT EXISTS paper_translations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    arxiv_id TEXT NOT NULL,
    target_language TEXT NOT NULL,
    translated_title TEXT NOT NULL,
    translated_abstract TEXT NOT NULL,
    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(arxiv_id, target_language)
);

-- App Settings
CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY NOT NULL,
    value TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Paper review sections (incremental cache)
CREATE TABLE IF NOT EXISTS paper_review_sections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    arxiv_id TEXT NOT NULL,
    section_type TEXT NOT NULL,
    content_json TEXT NOT NULL,
    source_type TEXT NOT NULL DEFAULT 'abstract',
    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(arxiv_id, section_type)
);

-- Paper cache
CREATE TABLE IF NOT EXISTS papers (
    arxiv_id TEXT PRIMARY KEY NOT NULL,
    title TEXT NOT NULL,
    abstract TEXT NOT NULL,
    authors TEXT NOT NULL,
    categories TEXT NOT NULL,
    published TIMESTAMP NOT NULL,
    updated TIMESTAMP,
    pdf_url TEXT,
    cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_interactions_arxiv ON paper_interactions(arxiv_id);
CREATE INDEX IF NOT EXISTS idx_interactions_type ON paper_interactions(interaction_type);
CREATE INDEX IF NOT EXISTS idx_notes_arxiv ON paper_notes(arxiv_id);
CREATE INDEX IF NOT EXISTS idx_list_papers_list ON reading_list_papers(list_id);
CREATE INDEX IF NOT EXISTS idx_translations_arxiv ON paper_translations(arxiv_id);
CREATE INDEX IF NOT EXISTS idx_papers_cached_at ON papers(cached_at);
CREATE INDEX IF NOT EXISTS idx_review_sections_arxiv ON paper_review_sections(arxiv_id);
"""


def init_db(db_path: Path | None = None) -> None:
    """Initialize database."""
    if db_path is None:
        db_path = get_config().db_path

    db_path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(db_path) as conn:
        conn.executescript(SCHEMA)

        # Migration: add new columns to reading_lists if they don't exist
        existing_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(reading_lists)").fetchall()
        }
        migrations = [
            (
                "parent_id",
                "ALTER TABLE reading_lists ADD COLUMN parent_id INTEGER REFERENCES reading_lists(id) ON DELETE CASCADE",
            ),
            (
                "is_folder",
                "ALTER TABLE reading_lists ADD COLUMN is_folder BOOLEAN DEFAULT 0",
            ),
            (
                "is_system",
                "ALTER TABLE reading_lists ADD COLUMN is_system BOOLEAN DEFAULT 0",
            ),
        ]
        for column, sql in migrations:
            if column not in existing_columns:
                conn.execute(sql)

        # Migration: convert old float keyword weights (e.g. 1.0, 1.5) to integer percentages
        # Old format: float like 1.0 or 1.5; new format: int 0-100 (50 = 50%)
        conn.execute(
            """UPDATE keyword_interests
               SET weight = CAST(ROUND(weight * 100) AS INTEGER)
               WHERE weight < 1.1"""
        )

        # Create system lists if they don't exist
        for system_name in ("Like", "Dislike"):
            exists = conn.execute(
                "SELECT 1 FROM reading_lists WHERE name = ? AND is_system = 1",
                (system_name,),
            ).fetchone()
            if not exists:
                conn.execute(
                    "INSERT INTO reading_lists (name, is_folder, is_system) VALUES (?, 0, 1)",
                    (system_name,),
                )
        conn.commit()


@contextmanager
def get_connection(db_path: Path | None = None) -> Iterator[sqlite3.Connection]:
    """Database connection context manager. Auto-commits on clean exit."""
    if db_path is None:
        db_path = get_config().db_path

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@contextmanager
def get_arxivterminal_connection() -> Iterator[sqlite3.Connection]:
    """arxivterminal database connection (read-only)."""
    db_path = get_config().arxivterminal_db_path
    if not db_path.exists():
        raise FileNotFoundError(f"arxivterminal DB not found: {db_path}")

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()
