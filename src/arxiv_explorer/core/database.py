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
    name TEXT UNIQUE NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
"""


def init_db(db_path: Path | None = None) -> None:
    """Initialize database."""
    if db_path is None:
        db_path = get_config().db_path

    db_path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(db_path) as conn:
        conn.executescript(SCHEMA)
        conn.commit()


@contextmanager
def get_connection(db_path: Path | None = None) -> Iterator[sqlite3.Connection]:
    """Database connection context manager."""
    if db_path is None:
        db_path = get_config().db_path

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
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
