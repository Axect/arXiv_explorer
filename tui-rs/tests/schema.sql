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
