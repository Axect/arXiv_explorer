# Ratatui TUI Port — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port arXiv Explorer's TUI from Python Textual to Rust Ratatui, with direct SQLite access for reads/writes and Python CLI subprocess calls for complex operations.

**Architecture:** Rust crate in `tui-rs/` within the existing monorepo. Uses `rusqlite` for direct DB access, `tokio` for async subprocess execution, `ratatui`+`crossterm` for terminal rendering. Python services/CLI remain unchanged; a `--json` flag is added to key CLI commands for machine-readable output.

**Tech Stack:** Rust, ratatui 0.29, crossterm 0.28, tokio 1, rusqlite 0.32, serde/serde_json 1

**Design Spec:** `docs/superpowers/specs/2026-04-06-ratatui-tui-port-design.md`

---

## Phase 1: Foundation (Tasks 1–4)

Produces a running TUI shell with tab navigation and DB connectivity.

### Task 1: Cargo Project Scaffold

**Files:**
- Create: `tui-rs/Cargo.toml`
- Create: `tui-rs/src/main.rs`

- [ ] **Step 1: Create Cargo.toml**

```toml
# tui-rs/Cargo.toml
[package]
name = "axp-tui"
version = "0.1.0"
edition = "2024"

[[bin]]
name = "axp-tui"
path = "src/main.rs"

[dependencies]
ratatui = "0.29"
crossterm = "0.28"
tokio = { version = "1", features = ["full"] }
rusqlite = { version = "0.32", features = ["bundled"] }
serde = { version = "1", features = ["derive"] }
serde_json = "1"
dirs = "6"
unicode-width = "0.2"
```

- [ ] **Step 2: Create minimal main.rs**

```rust
// tui-rs/src/main.rs
use std::io;
use crossterm::{
    event::{self, Event, KeyCode},
    execute,
    terminal::{disable_raw_mode, enable_raw_mode, EnterAlternateScreen, LeaveAlternateScreen},
};
use ratatui::{
    prelude::*,
    widgets::{Block, Borders, Paragraph},
};

fn main() -> io::Result<()> {
    // Setup terminal
    enable_raw_mode()?;
    let mut stdout = io::stdout();
    execute!(stdout, EnterAlternateScreen)?;
    let backend = CrosstermBackend::new(stdout);
    let mut terminal = Terminal::new(backend)?;

    // Main loop
    loop {
        terminal.draw(|f| {
            let area = f.area();
            let block = Block::default()
                .title(" arXiv Explorer ")
                .borders(Borders::ALL);
            let text = Paragraph::new("Press 'q' to quit")
                .block(block);
            f.render_widget(text, area);
        })?;

        if let Event::Key(key) = event::read()? {
            if key.code == KeyCode::Char('q') {
                break;
            }
        }
    }

    // Restore terminal
    disable_raw_mode()?;
    execute!(terminal.backend_mut(), LeaveAlternateScreen)?;
    Ok(())
}
```

- [ ] **Step 3: Build and verify**

```bash
cd tui-rs && cargo build 2>&1 | tail -5
```
Expected: `Compiling axp-tui v0.1.0` ... `Finished`

- [ ] **Step 4: Quick run test**

```bash
cd tui-rs && cargo run
```
Expected: TUI shows "Press 'q' to quit", press q exits cleanly.

- [ ] **Step 5: Commit**

```bash
git add tui-rs/
git commit -m "feat: scaffold Rust Ratatui TUI crate"
```

---

### Task 2: DB Models and Connection

**Files:**
- Create: `tui-rs/src/db/mod.rs`
- Create: `tui-rs/src/db/models.rs`
- Modify: `tui-rs/src/main.rs`

- [ ] **Step 1: Create db/models.rs with all Rust structs**

```rust
// tui-rs/src/db/models.rs
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Paper {
    pub arxiv_id: String,
    pub title: String,
    pub abstract_text: String,
    pub authors: Vec<String>,
    pub categories: Vec<String>,
    pub published: String,
    pub updated: Option<String>,
    pub pdf_url: Option<String>,
}

impl Paper {
    pub fn primary_category(&self) -> &str {
        self.categories.first().map(|s| s.as_str()).unwrap_or("")
    }
}

#[derive(Debug, Clone)]
pub struct PreferredCategory {
    pub id: i64,
    pub category: String,
    pub priority: i64,
    pub added_at: String,
}

#[derive(Debug, Clone)]
pub struct KeywordInterest {
    pub id: i64,
    pub keyword: String,
    pub weight: i64,
    pub source: String,
}

#[derive(Debug, Clone)]
pub struct PreferredAuthor {
    pub id: i64,
    pub name: String,
    pub added_at: String,
}

#[derive(Debug, Clone)]
pub struct ReadingList {
    pub id: i64,
    pub name: String,
    pub description: Option<String>,
    pub parent_id: Option<i64>,
    pub is_folder: bool,
    pub is_system: bool,
    pub created_at: String,
}

#[derive(Debug, Clone)]
pub struct ReadingListPaper {
    pub id: i64,
    pub list_id: i64,
    pub arxiv_id: String,
    pub status: String,
    pub position: i64,
    pub added_at: String,
}

#[derive(Debug, Clone)]
pub struct PaperInteraction {
    pub id: i64,
    pub arxiv_id: String,
    pub interaction_type: String,
    pub created_at: String,
}

#[derive(Debug, Clone)]
pub struct PaperNote {
    pub id: i64,
    pub arxiv_id: String,
    pub note_type: String,
    pub content: String,
    pub created_at: String,
}

#[derive(Debug, Clone)]
pub struct PaperSummary {
    pub arxiv_id: String,
    pub summary_short: Option<String>,
    pub summary_detailed: Option<String>,
    pub key_findings: Option<String>,
}

#[derive(Debug, Clone)]
pub struct PaperTranslation {
    pub arxiv_id: String,
    pub target_language: String,
    pub translated_title: String,
    pub translated_abstract: String,
}

#[derive(Debug, Clone)]
pub struct AppSetting {
    pub key: String,
    pub value: String,
}

/// Paper with recommendation score (from --json output)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ScoredPaper {
    pub arxiv_id: String,
    pub title: String,
    #[serde(rename = "abstract")]
    pub abstract_text: String,
    pub authors: Vec<String>,
    pub categories: Vec<String>,
    pub published: String,
    pub score: f64,
}

impl ScoredPaper {
    pub fn primary_category(&self) -> &str {
        self.categories.first().map(|s| s.as_str()).unwrap_or("")
    }
}

#[derive(Debug, Clone, PartialEq)]
pub enum JobType {
    Summarize,
    Translate,
    Review,
}

impl std::fmt::Display for JobType {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            JobType::Summarize => write!(f, "SUMMARY"),
            JobType::Translate => write!(f, "TRANSLATE"),
            JobType::Review => write!(f, "REVIEW"),
        }
    }
}

#[derive(Debug, Clone, PartialEq)]
pub enum JobStatus {
    Pending,
    Running,
    Completed,
    Failed,
}

#[derive(Debug, Clone)]
pub struct Job {
    pub id: String,
    pub paper_id: String,
    pub paper_title: String,
    pub job_type: JobType,
    pub status: JobStatus,
    pub started_at: std::time::Instant,
    pub error: Option<String>,
}
```

- [ ] **Step 2: Create db/mod.rs with connection + basic queries**

```rust
// tui-rs/src/db/mod.rs
pub mod models;

use std::path::PathBuf;
use rusqlite::{Connection, Result, params};
use models::*;

pub struct Database {
    conn: Connection,
}

impl Database {
    pub fn open(path: &PathBuf) -> Result<Self> {
        let conn = Connection::open(path)?;
        conn.execute_batch("PRAGMA foreign_keys = ON;")?;
        Ok(Database { conn })
    }

    /// Resolve DB path: AXP_DB env var → XDG default
    pub fn default_path() -> PathBuf {
        if let Ok(p) = std::env::var("AXP_DB") {
            return PathBuf::from(p);
        }
        let config_dir = dirs::config_dir()
            .unwrap_or_else(|| PathBuf::from("."));
        config_dir.join("arxiv-explorer").join("explorer.db")
    }

    // === Papers ===

    pub fn get_paper(&self, arxiv_id: &str) -> Result<Option<Paper>> {
        let mut stmt = self.conn.prepare(
            "SELECT arxiv_id, title, abstract, authors, categories, published, updated, pdf_url
             FROM papers WHERE arxiv_id = ?"
        )?;
        let mut rows = stmt.query_map(params![arxiv_id], |row| {
            let authors_json: String = row.get(3)?;
            let cats_json: String = row.get(4)?;
            Ok(Paper {
                arxiv_id: row.get(0)?,
                title: row.get(1)?,
                abstract_text: row.get(2)?,
                authors: serde_json::from_str(&authors_json).unwrap_or_default(),
                categories: serde_json::from_str(&cats_json).unwrap_or_default(),
                published: row.get(5)?,
                updated: row.get(6)?,
                pdf_url: row.get(7)?,
            })
        })?;
        match rows.next() {
            Some(Ok(p)) => Ok(Some(p)),
            _ => Ok(None),
        }
    }

    // === Preferences ===

    pub fn get_categories(&self) -> Result<Vec<PreferredCategory>> {
        let mut stmt = self.conn.prepare(
            "SELECT id, category, priority, added_at FROM preferred_categories ORDER BY priority DESC"
        )?;
        let rows = stmt.query_map([], |row| {
            Ok(PreferredCategory {
                id: row.get(0)?,
                category: row.get(1)?,
                priority: row.get(2)?,
                added_at: row.get(3)?,
            })
        })?;
        rows.collect()
    }

    pub fn add_category(&self, category: &str, priority: i64) -> Result<()> {
        self.conn.execute(
            "INSERT OR REPLACE INTO preferred_categories (category, priority) VALUES (?, ?)",
            params![category, priority],
        )?;
        Ok(())
    }

    pub fn remove_category(&self, category: &str) -> Result<bool> {
        let changed = self.conn.execute(
            "DELETE FROM preferred_categories WHERE category = ?",
            params![category],
        )?;
        Ok(changed > 0)
    }

    pub fn get_keywords(&self) -> Result<Vec<KeywordInterest>> {
        let mut stmt = self.conn.prepare(
            "SELECT id, keyword, weight, source FROM keyword_interests ORDER BY weight DESC"
        )?;
        let rows = stmt.query_map([], |row| {
            Ok(KeywordInterest {
                id: row.get(0)?,
                keyword: row.get(1)?,
                weight: row.get(2)?,
                source: row.get(3)?,
            })
        })?;
        rows.collect()
    }

    pub fn add_keyword(&self, keyword: &str, weight: i64) -> Result<()> {
        self.conn.execute(
            "INSERT OR REPLACE INTO keyword_interests (keyword, weight, source) VALUES (?, ?, 'explicit')",
            params![keyword, weight],
        )?;
        Ok(())
    }

    pub fn remove_keyword(&self, keyword: &str) -> Result<bool> {
        let changed = self.conn.execute(
            "DELETE FROM keyword_interests WHERE keyword = ?",
            params![keyword],
        )?;
        Ok(changed > 0)
    }

    pub fn get_authors(&self) -> Result<Vec<PreferredAuthor>> {
        let mut stmt = self.conn.prepare(
            "SELECT id, name, added_at FROM preferred_authors ORDER BY name"
        )?;
        let rows = stmt.query_map([], |row| {
            Ok(PreferredAuthor {
                id: row.get(0)?,
                name: row.get(1)?,
                added_at: row.get(2)?,
            })
        })?;
        rows.collect()
    }

    pub fn add_author(&self, name: &str) -> Result<()> {
        self.conn.execute(
            "INSERT OR IGNORE INTO preferred_authors (name) VALUES (?)",
            params![name],
        )?;
        Ok(())
    }

    pub fn remove_author(&self, name: &str) -> Result<bool> {
        let changed = self.conn.execute(
            "DELETE FROM preferred_authors WHERE name = ?",
            params![name],
        )?;
        Ok(changed > 0)
    }

    // === Interactions ===

    pub fn get_interaction(&self, arxiv_id: &str) -> Result<Option<String>> {
        let mut stmt = self.conn.prepare(
            "SELECT interaction_type FROM paper_interactions WHERE arxiv_id = ? ORDER BY created_at DESC LIMIT 1"
        )?;
        let mut rows = stmt.query_map(params![arxiv_id], |row| row.get::<_, String>(0))?;
        match rows.next() {
            Some(Ok(t)) => Ok(Some(t)),
            _ => Ok(None),
        }
    }

    pub fn mark_interesting(&self, arxiv_id: &str) -> Result<()> {
        self.conn.execute("DELETE FROM paper_interactions WHERE arxiv_id = ?", params![arxiv_id])?;
        self.conn.execute(
            "INSERT INTO paper_interactions (arxiv_id, interaction_type) VALUES (?, 'interesting')",
            params![arxiv_id],
        )?;
        self.sync_to_like_list(arxiv_id, true)?;
        Ok(())
    }

    pub fn mark_not_interesting(&self, arxiv_id: &str) -> Result<()> {
        self.conn.execute("DELETE FROM paper_interactions WHERE arxiv_id = ?", params![arxiv_id])?;
        self.conn.execute(
            "INSERT INTO paper_interactions (arxiv_id, interaction_type) VALUES (?, 'not_interesting')",
            params![arxiv_id],
        )?;
        self.sync_to_like_list(arxiv_id, false)?;
        Ok(())
    }

    fn sync_to_like_list(&self, arxiv_id: &str, like: bool) -> Result<()> {
        let like_id = self.get_system_list_id("Like")?;
        let dislike_id = self.get_system_list_id("Dislike")?;
        if let (Some(lid), Some(did)) = (like_id, dislike_id) {
            if like {
                self.conn.execute("DELETE FROM reading_list_papers WHERE list_id = ? AND arxiv_id = ?", params![did, arxiv_id])?;
                self.conn.execute("INSERT OR IGNORE INTO reading_list_papers (list_id, arxiv_id, status, position) VALUES (?, ?, 'unread', 0)", params![lid, arxiv_id])?;
            } else {
                self.conn.execute("DELETE FROM reading_list_papers WHERE list_id = ? AND arxiv_id = ?", params![lid, arxiv_id])?;
                self.conn.execute("INSERT OR IGNORE INTO reading_list_papers (list_id, arxiv_id, status, position) VALUES (?, ?, 'unread', 0)", params![did, arxiv_id])?;
            }
        }
        Ok(())
    }

    fn get_system_list_id(&self, name: &str) -> Result<Option<i64>> {
        let mut stmt = self.conn.prepare(
            "SELECT id FROM reading_lists WHERE name = ? AND is_system = 1"
        )?;
        let mut rows = stmt.query_map(params![name], |row| row.get::<_, i64>(0))?;
        match rows.next() {
            Some(Ok(id)) => Ok(Some(id)),
            _ => Ok(None),
        }
    }

    // === Reading Lists ===

    pub fn get_top_level_lists(&self) -> Result<Vec<ReadingList>> {
        let mut stmt = self.conn.prepare(
            "SELECT id, name, description, parent_id, is_folder, is_system, created_at
             FROM reading_lists WHERE parent_id IS NULL ORDER BY is_system DESC, name"
        )?;
        let rows = stmt.query_map([], |row| {
            Ok(ReadingList {
                id: row.get(0)?,
                name: row.get(1)?,
                description: row.get(2)?,
                parent_id: row.get(3)?,
                is_folder: row.get(4)?,
                is_system: row.get(5)?,
                created_at: row.get(6)?,
            })
        })?;
        rows.collect()
    }

    pub fn get_list_papers(&self, list_id: i64) -> Result<Vec<ReadingListPaper>> {
        let mut stmt = self.conn.prepare(
            "SELECT id, list_id, arxiv_id, status, position, added_at
             FROM reading_list_papers WHERE list_id = ? ORDER BY added_at DESC"
        )?;
        let rows = stmt.query_map(params![list_id], |row| {
            Ok(ReadingListPaper {
                id: row.get(0)?,
                list_id: row.get(1)?,
                arxiv_id: row.get(2)?,
                status: row.get(3)?,
                position: row.get(4)?,
                added_at: row.get(5)?,
            })
        })?;
        rows.collect()
    }

    pub fn get_list_paper_count(&self, list_id: i64) -> Result<i64> {
        self.conn.query_row(
            "SELECT COUNT(*) FROM reading_list_papers WHERE list_id = ?",
            params![list_id],
            |row| row.get(0),
        )
    }

    pub fn create_list(&self, name: &str, parent_id: Option<i64>) -> Result<()> {
        self.conn.execute(
            "INSERT INTO reading_lists (name, parent_id, is_folder, is_system) VALUES (?, ?, 0, 0)",
            params![name, parent_id],
        )?;
        Ok(())
    }

    pub fn create_folder(&self, name: &str) -> Result<()> {
        self.conn.execute(
            "INSERT INTO reading_lists (name, is_folder, is_system) VALUES (?, 1, 0)",
            params![name],
        )?;
        Ok(())
    }

    pub fn delete_list(&self, list_id: i64) -> Result<bool> {
        let is_system: bool = self.conn.query_row(
            "SELECT is_system FROM reading_lists WHERE id = ?",
            params![list_id],
            |row| row.get(0),
        ).unwrap_or(true);
        if is_system { return Ok(false); }
        let changed = self.conn.execute("DELETE FROM reading_lists WHERE id = ?", params![list_id])?;
        Ok(changed > 0)
    }

    pub fn rename_list(&self, list_id: i64, new_name: &str) -> Result<bool> {
        let is_system: bool = self.conn.query_row(
            "SELECT is_system FROM reading_lists WHERE id = ?",
            params![list_id],
            |row| row.get(0),
        ).unwrap_or(true);
        if is_system { return Ok(false); }
        let changed = self.conn.execute(
            "UPDATE reading_lists SET name = ? WHERE id = ?",
            params![new_name, list_id],
        )?;
        Ok(changed > 0)
    }

    pub fn toggle_bookmark(&self, arxiv_id: &str, month: &str) -> Result<bool> {
        // Find or create month folder
        let folder_id: i64 = match self.conn.query_row(
            "SELECT id FROM reading_lists WHERE name = ? AND is_folder = 1 AND parent_id IS NULL",
            params![month],
            |row| row.get(0),
        ) {
            Ok(id) => id,
            Err(_) => {
                self.conn.execute(
                    "INSERT INTO reading_lists (name, is_folder, is_system) VALUES (?, 1, 0)",
                    params![month],
                )?;
                self.conn.last_insert_rowid()
            }
        };
        // Toggle
        let exists: bool = self.conn.query_row(
            "SELECT COUNT(*) > 0 FROM reading_list_papers WHERE list_id = ? AND arxiv_id = ?",
            params![folder_id, arxiv_id],
            |row| row.get(0),
        )?;
        if exists {
            self.conn.execute(
                "DELETE FROM reading_list_papers WHERE list_id = ? AND arxiv_id = ?",
                params![folder_id, arxiv_id],
            )?;
            Ok(false) // removed
        } else {
            self.conn.execute(
                "INSERT INTO reading_list_papers (list_id, arxiv_id, status, position) VALUES (?, ?, 'unread', 0)",
                params![folder_id, arxiv_id],
            )?;
            Ok(true) // added
        }
    }

    pub fn get_bookmarked_ids(&self, month: &str) -> Result<Vec<String>> {
        let folder_id: Option<i64> = self.conn.query_row(
            "SELECT id FROM reading_lists WHERE name = ? AND is_folder = 1 AND parent_id IS NULL",
            params![month],
            |row| row.get(0),
        ).ok();
        match folder_id {
            Some(fid) => {
                let mut stmt = self.conn.prepare(
                    "SELECT arxiv_id FROM reading_list_papers WHERE list_id = ?"
                )?;
                let rows = stmt.query_map(params![fid], |row| row.get::<_, String>(0))?;
                rows.collect()
            }
            None => Ok(vec![]),
        }
    }

    // === Notes ===

    pub fn get_notes(&self) -> Result<Vec<PaperNote>> {
        let mut stmt = self.conn.prepare(
            "SELECT id, arxiv_id, note_type, content, created_at FROM paper_notes ORDER BY created_at DESC"
        )?;
        let rows = stmt.query_map([], |row| {
            Ok(PaperNote {
                id: row.get(0)?,
                arxiv_id: row.get(1)?,
                note_type: row.get(2)?,
                content: row.get(3)?,
                created_at: row.get(4)?,
            })
        })?;
        rows.collect()
    }

    pub fn add_note(&self, arxiv_id: &str, note_type: &str, content: &str) -> Result<()> {
        self.conn.execute(
            "INSERT INTO paper_notes (arxiv_id, note_type, content) VALUES (?, ?, ?)",
            params![arxiv_id, note_type, content],
        )?;
        Ok(())
    }

    pub fn delete_note(&self, note_id: i64) -> Result<bool> {
        let changed = self.conn.execute("DELETE FROM paper_notes WHERE id = ?", params![note_id])?;
        Ok(changed > 0)
    }

    // === Settings ===

    pub fn get_setting(&self, key: &str, default: &str) -> Result<String> {
        match self.conn.query_row(
            "SELECT value FROM app_settings WHERE key = ?",
            params![key],
            |row| row.get::<_, String>(0),
        ) {
            Ok(v) => Ok(v),
            Err(_) => Ok(default.to_string()),
        }
    }

    pub fn set_setting(&self, key: &str, value: &str) -> Result<()> {
        self.conn.execute(
            "INSERT OR REPLACE INTO app_settings (key, value, updated_at) VALUES (?, ?, datetime('now'))",
            params![key, value],
        )?;
        Ok(())
    }

    pub fn get_weights(&self) -> Result<[i64; 4]> {
        let content = self.get_setting("weight_content", "60")?.parse::<i64>().unwrap_or(60);
        let category = self.get_setting("weight_category", "20")?.parse::<i64>().unwrap_or(20);
        let keyword = self.get_setting("weight_keyword", "15")?.parse::<i64>().unwrap_or(15);
        let recency = self.get_setting("weight_recency", "5")?.parse::<i64>().unwrap_or(5);
        Ok([content, category, keyword, recency])
    }

    pub fn set_weights(&self, weights: [i64; 4]) -> Result<()> {
        self.set_setting("weight_content", &weights[0].to_string())?;
        self.set_setting("weight_category", &weights[1].to_string())?;
        self.set_setting("weight_keyword", &weights[2].to_string())?;
        self.set_setting("weight_recency", &weights[3].to_string())?;
        Ok(())
    }

    // === Summaries / Translations (read-only from Rust) ===

    pub fn get_summary(&self, arxiv_id: &str) -> Result<Option<PaperSummary>> {
        let mut stmt = self.conn.prepare(
            "SELECT arxiv_id, summary_short, summary_detailed, key_findings FROM paper_summaries WHERE arxiv_id = ?"
        )?;
        let mut rows = stmt.query_map(params![arxiv_id], |row| {
            Ok(PaperSummary {
                arxiv_id: row.get(0)?,
                summary_short: row.get(1)?,
                summary_detailed: row.get(2)?,
                key_findings: row.get(3)?,
            })
        })?;
        match rows.next() {
            Some(Ok(s)) => Ok(Some(s)),
            _ => Ok(None),
        }
    }

    pub fn get_translation(&self, arxiv_id: &str) -> Result<Option<PaperTranslation>> {
        let mut stmt = self.conn.prepare(
            "SELECT arxiv_id, target_language, translated_title, translated_abstract FROM paper_translations WHERE arxiv_id = ? LIMIT 1"
        )?;
        let mut rows = stmt.query_map(params![arxiv_id], |row| {
            Ok(PaperTranslation {
                arxiv_id: row.get(0)?,
                target_language: row.get(1)?,
                translated_title: row.get(2)?,
                translated_abstract: row.get(3)?,
            })
        })?;
        match rows.next() {
            Some(Ok(t)) => Ok(Some(t)),
            _ => Ok(None),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use rusqlite::Connection;

    fn setup_test_db() -> Database {
        let conn = Connection::open_in_memory().unwrap();
        // Create schema from the Python project
        conn.execute_batch(include_str!("../../tests/schema.sql")).unwrap();
        Database { conn }
    }

    #[test]
    fn test_categories_crud() {
        let db = setup_test_db();
        db.add_category("hep-ph", 3).unwrap();
        db.add_category("cs.AI", 2).unwrap();
        let cats = db.get_categories().unwrap();
        assert_eq!(cats.len(), 2);
        assert_eq!(cats[0].category, "hep-ph");
        assert_eq!(cats[0].priority, 3);
        db.remove_category("hep-ph").unwrap();
        assert_eq!(db.get_categories().unwrap().len(), 1);
    }

    #[test]
    fn test_keywords_crud() {
        let db = setup_test_db();
        db.add_keyword("quantum", 4).unwrap();
        let kws = db.get_keywords().unwrap();
        assert_eq!(kws.len(), 1);
        assert_eq!(kws[0].keyword, "quantum");
        assert_eq!(kws[0].weight, 4);
    }

    #[test]
    fn test_settings() {
        let db = setup_test_db();
        assert_eq!(db.get_setting("foo", "bar").unwrap(), "bar");
        db.set_setting("foo", "baz").unwrap();
        assert_eq!(db.get_setting("foo", "bar").unwrap(), "baz");
    }

    #[test]
    fn test_weights() {
        let db = setup_test_db();
        let w = db.get_weights().unwrap();
        assert_eq!(w, [60, 20, 15, 5]); // defaults
        db.set_weights([50, 25, 20, 5]).unwrap();
        assert_eq!(db.get_weights().unwrap(), [50, 25, 20, 5]);
    }
}
```

- [ ] **Step 3: Create test schema SQL file**

Copy the Python SCHEMA to `tui-rs/tests/schema.sql` — this is used by Rust tests to create identical tables in memory:

```bash
# Extract schema from Python source
cd /home/axect/Documents/Project/AI_Project/arXiv_explorer
grep -A 120 'SCHEMA = """' src/arxiv_explorer/core/database.py | sed '1d;$d' > tui-rs/tests/schema.sql
```

- [ ] **Step 4: Update main.rs to declare db module**

Add at top of `tui-rs/src/main.rs`:
```rust
mod db;
```

- [ ] **Step 5: Run tests**

```bash
cd tui-rs && cargo test
```
Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add tui-rs/
git commit -m "feat: add DB models and rusqlite connection layer"
```

---

### Task 3: App State + Async Event Loop

**Files:**
- Create: `tui-rs/src/app.rs`
- Create: `tui-rs/src/events.rs`
- Modify: `tui-rs/src/main.rs`

- [ ] **Step 1: Create app.rs**

```rust
// tui-rs/src/app.rs
use std::path::PathBuf;
use tokio::sync::mpsc;

use crate::db::Database;
use crate::db::models::*;

#[derive(Debug, Clone, Copy, PartialEq)]
pub enum Tab {
    Daily,
    Search,
    Lists,
    Notes,
    Prefs,
}

impl Tab {
    pub fn all() -> &'static [Tab] {
        &[Tab::Daily, Tab::Search, Tab::Lists, Tab::Notes, Tab::Prefs]
    }

    pub fn label(&self) -> &str {
        match self {
            Tab::Daily => "Daily",
            Tab::Search => "Search",
            Tab::Lists => "Lists",
            Tab::Notes => "Notes",
            Tab::Prefs => "Prefs",
        }
    }

    pub fn key(&self) -> char {
        match self {
            Tab::Daily => '1',
            Tab::Search => '2',
            Tab::Lists => '3',
            Tab::Notes => '4',
            Tab::Prefs => '5',
        }
    }
}

pub enum AppEvent {
    DailyFetched {
        author_papers: Vec<ScoredPaper>,
        scored_papers: Vec<ScoredPaper>,
    },
    SearchResults {
        papers: Vec<ScoredPaper>,
    },
    JobCompleted {
        job_id: String,
    },
    JobFailed {
        job_id: String,
        error: String,
    },
    Toast {
        message: String,
        is_error: bool,
    },
}

pub struct DailyState {
    pub days: u32,
    pub limit: u32,
    pub author_papers: Vec<ScoredPaper>,
    pub scored_papers: Vec<ScoredPaper>,
    pub selected: usize,
    pub bookmarked: std::collections::HashSet<String>,
    pub loading: bool,
}

pub struct SearchState {
    pub query: String,
    pub papers: Vec<ScoredPaper>,
    pub selected: usize,
    pub editing: bool,
    pub loading: bool,
}

pub struct ListsState {
    pub items: Vec<(ReadingList, i64)>, // (list, paper_count)
    pub selected_list: usize,
    pub papers: Vec<(ReadingListPaper, Option<Paper>)>,
    pub selected_paper: usize,
    pub focus_left: bool,
}

pub struct NotesState {
    pub notes: Vec<PaperNote>,
    pub selected: usize,
}

pub struct PrefsState {
    pub categories: Vec<PreferredCategory>,
    pub keywords: Vec<KeywordInterest>,
    pub authors: Vec<PreferredAuthor>,
    pub weights: [i64; 4],
    pub provider: String,
    pub language: String,
    pub focus_section: usize, // 0=cats, 1=kw, 2=authors, 3=weights
    pub selected: [usize; 4], // cursor per section
    pub input_buf: String,
    pub input_active: bool,
}

pub struct Toast {
    pub message: String,
    pub is_error: bool,
    pub expires_at: std::time::Instant,
}

pub struct App {
    pub active_tab: Tab,
    pub should_quit: bool,
    pub show_jobs: bool,
    pub db: Database,
    pub daily: DailyState,
    pub search: SearchState,
    pub lists: ListsState,
    pub notes: NotesState,
    pub prefs: PrefsState,
    pub jobs: Vec<Job>,
    pub toasts: Vec<Toast>,
    pub event_tx: mpsc::UnboundedSender<AppEvent>,
    pub event_rx: mpsc::UnboundedReceiver<AppEvent>,
}

impl App {
    pub fn new(db_path: PathBuf) -> Self {
        let db = Database::open(&db_path).expect("Failed to open database");
        let (event_tx, event_rx) = mpsc::unbounded_channel();

        let weights = db.get_weights().unwrap_or([60, 20, 15, 5]);
        let provider = db.get_setting("ai_provider", "gemini").unwrap_or_default();
        let language = db.get_setting("language", "en").unwrap_or_default();

        App {
            active_tab: Tab::Daily,
            should_quit: false,
            show_jobs: false,
            db,
            daily: DailyState {
                days: 7,
                limit: 20,
                author_papers: vec![],
                scored_papers: vec![],
                selected: 0,
                bookmarked: std::collections::HashSet::new(),
                loading: false,
            },
            search: SearchState {
                query: String::new(),
                papers: vec![],
                selected: 0,
                editing: false,
                loading: false,
            },
            lists: ListsState {
                items: vec![],
                selected_list: 0,
                papers: vec![],
                selected_paper: 0,
                focus_left: true,
            },
            notes: NotesState {
                notes: vec![],
                selected: 0,
            },
            prefs: PrefsState {
                categories: vec![],
                keywords: vec![],
                authors: vec![],
                weights,
                provider,
                language,
                focus_section: 0,
                selected: [0; 4],
                input_buf: String::new(),
                input_active: false,
            },
            jobs: vec![],
            toasts: vec![],
            event_tx,
            event_rx,
        }
    }

    pub fn handle_app_event(&mut self, event: AppEvent) {
        match event {
            AppEvent::DailyFetched { author_papers, scored_papers } => {
                self.daily.author_papers = author_papers;
                self.daily.scored_papers = scored_papers;
                self.daily.selected = 0;
                self.daily.loading = false;
            }
            AppEvent::SearchResults { papers } => {
                self.search.papers = papers;
                self.search.selected = 0;
                self.search.loading = false;
            }
            AppEvent::JobCompleted { job_id } => {
                if let Some(job) = self.jobs.iter_mut().find(|j| j.id == job_id) {
                    job.status = JobStatus::Completed;
                    self.add_toast(&format!("✓ {} done: {}", job.job_type, job.paper_id), false);
                }
            }
            AppEvent::JobFailed { job_id, error } => {
                if let Some(job) = self.jobs.iter_mut().find(|j| j.id == job_id) {
                    job.status = JobStatus::Failed;
                    job.error = Some(error.clone());
                    self.add_toast(&format!("✗ {} failed: {}", job.job_type, error), true);
                }
            }
            AppEvent::Toast { message, is_error } => {
                self.add_toast(&message, is_error);
            }
        }
    }

    fn add_toast(&mut self, message: &str, is_error: bool) {
        self.toasts.push(Toast {
            message: message.to_string(),
            is_error,
            expires_at: std::time::Instant::now() + std::time::Duration::from_secs(3),
        });
    }

    pub fn tick(&mut self) {
        let now = std::time::Instant::now();
        self.toasts.retain(|t| t.expires_at > now);
    }

    pub fn all_papers(&self) -> Vec<&ScoredPaper> {
        self.daily.author_papers.iter()
            .chain(self.daily.scored_papers.iter())
            .collect()
    }

    pub fn selected_daily_paper(&self) -> Option<&ScoredPaper> {
        let all = self.all_papers();
        all.get(self.daily.selected).copied()
    }
}
```

- [ ] **Step 2: Create events.rs**

```rust
// tui-rs/src/events.rs
use crossterm::event::{self, Event, KeyCode, KeyEvent, KeyModifiers};
use crate::app::{App, Tab};

pub fn handle_key(app: &mut App, key: KeyEvent) {
    // Global keys
    match key.code {
        KeyCode::Char('q') => { app.should_quit = true; return; }
        KeyCode::Char('j') => { app.show_jobs = !app.show_jobs; return; }
        KeyCode::Char('1') => { app.active_tab = Tab::Daily; return; }
        KeyCode::Char('2') => { app.active_tab = Tab::Search; return; }
        KeyCode::Char('3') => { app.active_tab = Tab::Lists; return; }
        KeyCode::Char('4') => { app.active_tab = Tab::Notes; return; }
        KeyCode::Char('5') => { app.active_tab = Tab::Prefs; return; }
        _ => {}
    }

    // Tab-specific keys
    match app.active_tab {
        Tab::Daily => handle_daily_key(app, key),
        Tab::Search => handle_search_key(app, key),
        Tab::Lists => handle_lists_key(app, key),
        Tab::Notes => handle_notes_key(app, key),
        Tab::Prefs => handle_prefs_key(app, key),
    }
}

fn handle_daily_key(app: &mut App, key: KeyEvent) {
    let paper_count = app.daily.author_papers.len() + app.daily.scored_papers.len();
    match key.code {
        KeyCode::Up | KeyCode::Char('k') => {
            if app.daily.selected > 0 { app.daily.selected -= 1; }
        }
        KeyCode::Down | KeyCode::Char('j') if !app.show_jobs => {
            if app.daily.selected + 1 < paper_count { app.daily.selected += 1; }
        }
        KeyCode::Char('r') => {
            // Fetch will be handled by command module
        }
        KeyCode::Char('l') => {
            // Like
            if let Some(paper) = app.selected_daily_paper() {
                let _ = app.db.mark_interesting(&paper.arxiv_id);
                app.add_toast(&format!("Liked {}", paper.arxiv_id), false);
            }
        }
        KeyCode::Char('d') => {
            // Dislike
            if let Some(paper) = app.selected_daily_paper() {
                let _ = app.db.mark_not_interesting(&paper.arxiv_id);
                app.add_toast(&format!("Disliked {}", paper.arxiv_id), false);
            }
        }
        KeyCode::Char('b') => {
            // Bookmark toggle
            if let Some(paper) = app.selected_daily_paper() {
                let month = chrono::Local::now().format("%Y%m").to_string();
                // We'll need chrono for this — for now use a simple approach
                let arxiv_id = paper.arxiv_id.clone();
                if let Ok(added) = app.db.toggle_bookmark(&arxiv_id, &month) {
                    if added {
                        app.daily.bookmarked.insert(arxiv_id.clone());
                        app.add_toast(&format!("Saved to {month}"), false);
                    } else {
                        app.daily.bookmarked.remove(&arxiv_id);
                        app.add_toast(&format!("Removed from {month}"), false);
                    }
                }
            }
        }
        _ => {}
    }
}

fn handle_search_key(app: &mut App, key: KeyEvent) {
    if app.search.editing {
        match key.code {
            KeyCode::Enter => { app.search.editing = false; /* trigger search */ }
            KeyCode::Esc => { app.search.editing = false; }
            KeyCode::Backspace => { app.search.query.pop(); }
            KeyCode::Char(c) => { app.search.query.push(c); }
            _ => {}
        }
        return;
    }
    match key.code {
        KeyCode::Char('/') => { app.search.editing = true; }
        KeyCode::Up | KeyCode::Char('k') => {
            if app.search.selected > 0 { app.search.selected -= 1; }
        }
        KeyCode::Down => {
            if app.search.selected + 1 < app.search.papers.len() { app.search.selected += 1; }
        }
        _ => {}
    }
}

fn handle_lists_key(app: &mut App, key: KeyEvent) {
    match key.code {
        KeyCode::Tab => { app.lists.focus_left = !app.lists.focus_left; }
        KeyCode::Up | KeyCode::Char('k') => {
            if app.lists.focus_left {
                if app.lists.selected_list > 0 { app.lists.selected_list -= 1; }
            } else if app.lists.selected_paper > 0 {
                app.lists.selected_paper -= 1;
            }
        }
        KeyCode::Down => {
            if app.lists.focus_left {
                if app.lists.selected_list + 1 < app.lists.items.len() { app.lists.selected_list += 1; }
            } else if app.lists.selected_paper + 1 < app.lists.papers.len() {
                app.lists.selected_paper += 1;
            }
        }
        _ => {}
    }
}

fn handle_notes_key(app: &mut App, key: KeyEvent) {
    match key.code {
        KeyCode::Up | KeyCode::Char('k') => {
            if app.notes.selected > 0 { app.notes.selected -= 1; }
        }
        KeyCode::Down => {
            if app.notes.selected + 1 < app.notes.notes.len() { app.notes.selected += 1; }
        }
        _ => {}
    }
}

fn handle_prefs_key(app: &mut App, key: KeyEvent) {
    match key.code {
        KeyCode::Tab => {
            app.prefs.focus_section = (app.prefs.focus_section + 1) % 4;
        }
        KeyCode::Up | KeyCode::Char('k') => {
            let s = app.prefs.focus_section;
            if app.prefs.selected[s] > 0 { app.prefs.selected[s] -= 1; }
        }
        KeyCode::Down => {
            let s = app.prefs.focus_section;
            app.prefs.selected[s] += 1; // bounds checked in render
        }
        KeyCode::Left if app.prefs.focus_section == 3 => {
            // Decrease weight
            let idx = app.prefs.selected[3];
            if idx < 4 && app.prefs.weights[idx] > 0 {
                let old = app.prefs.weights[idx];
                app.prefs.weights = adjust_weights(idx, old - 1, app.prefs.weights);
                let _ = app.db.set_weights(app.prefs.weights);
            }
        }
        KeyCode::Right if app.prefs.focus_section == 3 => {
            // Increase weight
            let idx = app.prefs.selected[3];
            if idx < 4 && app.prefs.weights[idx] < 100 {
                let old = app.prefs.weights[idx];
                app.prefs.weights = adjust_weights(idx, old + 1, app.prefs.weights);
                let _ = app.db.set_weights(app.prefs.weights);
            }
        }
        _ => {}
    }
}

fn adjust_weights(changed: usize, new_value: i64, weights: [i64; 4]) -> [i64; 4] {
    let mut result = weights;
    result[changed] = new_value;
    let remaining = 100 - new_value;
    let others_sum: i64 = result.iter().enumerate()
        .filter(|(i, _)| *i != changed)
        .map(|(_, v)| *v)
        .sum();

    if others_sum == 0 {
        let equal = remaining / 3;
        for (i, v) in result.iter_mut().enumerate() {
            if i != changed { *v = equal; }
        }
    } else {
        for (i, v) in result.iter_mut().enumerate() {
            if i != changed {
                *v = (remaining as f64 * weights[i] as f64 / others_sum as f64).round() as i64;
            }
        }
    }
    // Fix rounding
    let diff = 100 - result.iter().sum::<i64>();
    if diff != 0 {
        let largest = (0..4).filter(|i| *i != changed).max_by_key(|i| result[*i]).unwrap();
        result[largest] += diff;
    }
    result
}
```

- [ ] **Step 3: Rewrite main.rs with tokio event loop**

```rust
// tui-rs/src/main.rs
mod app;
mod db;
mod events;

use std::io;
use std::time::Duration;
use crossterm::{
    event::{self, Event, KeyCode},
    execute,
    terminal::{disable_raw_mode, enable_raw_mode, EnterAlternateScreen, LeaveAlternateScreen},
};
use ratatui::prelude::*;
use ratatui::widgets::*;

use app::App;
use db::Database;

#[tokio::main]
async fn main() -> io::Result<()> {
    let db_path = Database::default_path();
    if !db_path.exists() {
        eprintln!("Database not found at {:?}", db_path);
        eprintln!("Run 'uv run axp daily' first to initialize the database.");
        std::process::exit(1);
    }

    let mut app = App::new(db_path);

    // Setup terminal
    enable_raw_mode()?;
    let mut stdout = io::stdout();
    execute!(stdout, EnterAlternateScreen)?;
    let backend = CrosstermBackend::new(stdout);
    let mut terminal = Terminal::new(backend)?;

    // Main loop
    let result = run_app(&mut terminal, &mut app).await;

    // Restore terminal
    disable_raw_mode()?;
    execute!(terminal.backend_mut(), LeaveAlternateScreen)?;

    result
}

async fn run_app(
    terminal: &mut Terminal<CrosstermBackend<io::Stdout>>,
    app: &mut App,
) -> io::Result<()> {
    loop {
        terminal.draw(|f| render(f, app))?;

        // Poll for events with timeout for tick
        tokio::select! {
            // Check for keyboard events
            _ = tokio::time::sleep(Duration::from_millis(100)) => {
                // Check crossterm events (non-blocking)
                while event::poll(Duration::ZERO)? {
                    if let Event::Key(key) = event::read()? {
                        events::handle_key(app, key);
                    }
                }
            }
            // Check for async app events
            Some(app_event) = app.event_rx.recv() => {
                app.handle_app_event(app_event);
            }
        }

        app.tick();

        if app.should_quit {
            break;
        }
    }
    Ok(())
}

fn render(f: &mut Frame, app: &App) {
    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(1),  // Tab bar
            Constraint::Min(0),    // Content
            Constraint::Length(1),  // Key hints
        ])
        .split(f.area());

    render_tab_bar(f, app, chunks[0]);
    render_tab_content(f, app, chunks[1]);
    render_key_hints(f, app, chunks[2]);

    // Toast overlay
    if let Some(toast) = app.toasts.last() {
        let toast_area = Rect {
            x: f.area().width.saturating_sub(40),
            y: f.area().height.saturating_sub(3),
            width: 38.min(f.area().width),
            height: 2,
        };
        let style = if toast.is_error {
            Style::default().fg(Color::Rgb(243, 139, 168))
        } else {
            Style::default().fg(Color::Rgb(166, 227, 161))
        };
        let block = Block::default().borders(Borders::ALL).border_style(style);
        let text = Paragraph::new(toast.message.as_str()).block(block);
        f.render_widget(text, toast_area);
    }
}

fn render_tab_bar(f: &mut Frame, app: &App, area: Rect) {
    let mut spans = Vec::new();
    for tab in app::Tab::all() {
        let style = if *tab == app.active_tab {
            Style::default().fg(Color::Rgb(137, 180, 250)).add_modifier(Modifier::BOLD)
        } else {
            Style::default().fg(Color::Rgb(108, 112, 134))
        };
        spans.push(Span::styled(format!(" [{}]{} ", tab.key(), tab.label()), style));
    }
    let tabs = Line::from(spans);
    f.render_widget(Paragraph::new(tabs).bg(Color::Rgb(30, 30, 46)), area);
}

fn render_tab_content(f: &mut Frame, app: &App, area: Rect) {
    match app.active_tab {
        app::Tab::Daily => render_daily(f, app, area),
        app::Tab::Search => render_search(f, app, area),
        app::Tab::Lists => render_lists(f, app, area),
        app::Tab::Notes => render_notes(f, app, area),
        app::Tab::Prefs => render_prefs(f, app, area),
    }
}

fn render_key_hints(f: &mut Frame, app: &App, area: Rect) {
    let hints = match app.active_tab {
        app::Tab::Daily => "[r]fetch [l]ike [d]islike [s]umm [t]rans [w]review [b]mark [j]obs [q]uit",
        app::Tab::Search => "[/]search [l]ike [d]islike [s]umm [t]rans [w]review [j]obs [q]uit",
        app::Tab::Lists => "[n]ew [f]older [e]dit [Del]ete [s]ort [m]ove [c]opy [q]uit",
        app::Tab::Notes => "[n]ew [Del]ete [q]uit",
        app::Tab::Prefs => "[Tab]section [Enter]add [Del]ete [←→]weights [q]uit",
    };
    let style = Style::default().fg(Color::Rgb(108, 112, 134)).bg(Color::Rgb(30, 30, 46));
    f.render_widget(Paragraph::new(hints).style(style), area);
}

// === Placeholder renderers (to be filled in Phase 2-3) ===

fn render_daily(f: &mut Frame, app: &App, area: Rect) {
    if app.daily.loading {
        let text = Paragraph::new("Fetching papers...")
            .alignment(Alignment::Center)
            .block(Block::default().borders(Borders::ALL).title(" Daily "));
        f.render_widget(text, area);
        return;
    }
    if app.daily.author_papers.is_empty() && app.daily.scored_papers.is_empty() {
        let text = Paragraph::new("Press [r] to fetch papers")
            .alignment(Alignment::Center)
            .block(Block::default().borders(Borders::ALL).title(" Daily "));
        f.render_widget(text, area);
        return;
    }

    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([Constraint::Percentage(60), Constraint::Percentage(40)])
        .split(area);

    // Paper table
    let all_papers = app.all_papers();
    let header = Row::new(vec!["#", "ID", "Title", "Cat", "Score"])
        .style(Style::default().add_modifier(Modifier::BOLD));
    let rows: Vec<Row> = all_papers.iter().enumerate().map(|(i, p)| {
        let is_author = i < app.daily.author_papers.len();
        let is_bookmarked = app.daily.bookmarked.contains(&p.arxiv_id);
        let prefix = match (is_author, is_bookmarked) {
            (true, true) => "★✓",
            (true, false) => "★ ",
            (false, true) => "✓ ",
            (false, false) => "  ",
        };
        let style = if is_author {
            Style::default().fg(Color::Rgb(249, 226, 175))
        } else if is_bookmarked {
            Style::default().fg(Color::Rgb(166, 227, 161))
        } else {
            Style::default()
        };
        let title = if p.title.len() > 50 { format!("{}...", &p.title[..47]) } else { p.title.clone() };
        Row::new(vec![
            format!("{}{}", prefix, i + 1),
            p.arxiv_id.clone(),
            title,
            p.primary_category().to_string(),
            format!("{:.2}", p.score),
        ]).style(style)
    }).collect();

    let table = Table::new(rows, [
        Constraint::Length(5),
        Constraint::Length(14),
        Constraint::Min(20),
        Constraint::Length(8),
        Constraint::Length(5),
    ])
    .header(header)
    .highlight_style(Style::default().add_modifier(Modifier::REVERSED))
    .block(Block::default().borders(Borders::ALL).title(
        format!(" Daily — Days:{} Limit:{} ", app.daily.days, app.daily.limit)
    ));

    let mut table_state = ratatui::widgets::TableState::default()
        .with_selected(Some(app.daily.selected));
    f.render_stateful_widget(table, chunks[0], &mut table_state);

    // Paper detail
    if let Some(paper) = app.selected_daily_paper() {
        let detail = vec![
            Line::from(vec![
                Span::styled("Title: ", Style::default().add_modifier(Modifier::BOLD)),
                Span::raw(&paper.title),
            ]),
            Line::from(vec![
                Span::styled("Authors: ", Style::default().add_modifier(Modifier::BOLD)),
                Span::raw(paper.authors.join(", ")),
            ]),
            Line::from(vec![
                Span::styled("Categories: ", Style::default().add_modifier(Modifier::BOLD)),
                Span::raw(paper.categories.join(", ")),
                Span::raw("  "),
                Span::styled("Published: ", Style::default().add_modifier(Modifier::BOLD)),
                Span::raw(&paper.published),
            ]),
            Line::from(""),
            Line::from(paper.abstract_text.as_str()),
        ];
        let detail_widget = Paragraph::new(detail)
            .wrap(Wrap { trim: true })
            .block(Block::default().borders(Borders::ALL).title(" Detail "));
        f.render_widget(detail_widget, chunks[1]);
    }
}

fn render_search(f: &mut Frame, app: &App, area: Rect) {
    let text = Paragraph::new("Search tab — press [/] to start typing")
        .alignment(Alignment::Center)
        .block(Block::default().borders(Borders::ALL).title(" Search "));
    f.render_widget(text, area);
}

fn render_lists(f: &mut Frame, app: &App, area: Rect) {
    let text = Paragraph::new("Lists tab")
        .alignment(Alignment::Center)
        .block(Block::default().borders(Borders::ALL).title(" Lists "));
    f.render_widget(text, area);
}

fn render_notes(f: &mut Frame, app: &App, area: Rect) {
    let text = Paragraph::new("Notes tab")
        .alignment(Alignment::Center)
        .block(Block::default().borders(Borders::ALL).title(" Notes "));
    f.render_widget(text, area);
}

fn render_prefs(f: &mut Frame, app: &App, area: Rect) {
    let text = Paragraph::new("Prefs tab")
        .alignment(Alignment::Center)
        .block(Block::default().borders(Borders::ALL).title(" Prefs "));
    f.render_widget(text, area);
}
```

- [ ] **Step 4: Build and verify**

```bash
cd tui-rs && cargo build
```

- [ ] **Step 5: Commit**

```bash
git add tui-rs/
git commit -m "feat: add app state, event loop, tab navigation, and Daily table rendering"
```

---

### Task 4: Python CLI --json Flag + Fetch Command

**Files:**
- Modify: `src/arxiv_explorer/cli/daily.py`
- Modify: `src/arxiv_explorer/cli/search.py`
- Create: `tui-rs/src/commands/mod.rs`
- Create: `tui-rs/src/commands/fetch.rs`
- Create: `tui-rs/src/commands/ai.rs`

- [ ] **Step 1: Add --json to Python daily command**

In `src/arxiv_explorer/cli/daily.py`, add `json_output` parameter to `daily()`:

```python
def daily(
    days: int = typer.Option(1, "--days", "-d", help="Number of days to fetch"),
    summarize: bool = typer.Option(False, "--summarize", "-s", help="Generate summaries"),
    detailed: bool = typer.Option(False, "--detailed", help="Generate detailed summaries"),
    limit: int = typer.Option(20, "--limit", "-l", help="Maximum number of results"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Fetch today's/recent papers (personalized ranking)."""
    service = PaperService()
    pref_service = PreferenceService()

    categories = pref_service.get_categories()
    if not categories:
        if json_output:
            import json
            print(json.dumps({"error": "No preferred categories"}))
            return
        print_error("No preferred categories. Add one with 'axp prefs add-category'.")
        raise typer.Exit(1)

    author_papers, scored_papers = service.get_daily_papers(days=days, limit=limit)

    if json_output:
        import json

        def paper_to_dict(rec):
            p = rec.paper
            return {
                "arxiv_id": p.arxiv_id,
                "title": p.title,
                "abstract": p.abstract,
                "authors": p.authors,
                "categories": p.categories,
                "published": str(p.published),
                "score": rec.score,
            }

        result = {
            "author_papers": [paper_to_dict(r) for r in author_papers],
            "scored_papers": [paper_to_dict(r) for r in scored_papers],
        }
        print(json.dumps(result))
        return

    # ... rest of existing code unchanged ...
```

- [ ] **Step 2: Add --json to Python search command**

In `src/arxiv_explorer/cli/search.py`, add similar `json_output` parameter.

- [ ] **Step 3: Create Rust commands module**

```rust
// tui-rs/src/commands/mod.rs
pub mod fetch;
pub mod ai;
```

```rust
// tui-rs/src/commands/fetch.rs
use tokio::process::Command;
use tokio::sync::mpsc;
use serde::Deserialize;

use crate::app::AppEvent;
use crate::db::models::ScoredPaper;

#[derive(Deserialize)]
struct DailyResult {
    author_papers: Vec<ScoredPaper>,
    scored_papers: Vec<ScoredPaper>,
}

pub fn fetch_daily(tx: mpsc::UnboundedSender<AppEvent>, days: u32, limit: u32) {
    tokio::spawn(async move {
        let output = Command::new("uv")
            .args([
                "run", "axp", "daily",
                "--days", &days.to_string(),
                "--limit", &limit.to_string(),
                "--json",
            ])
            .output()
            .await;

        match output {
            Ok(out) if out.status.success() => {
                match serde_json::from_slice::<DailyResult>(&out.stdout) {
                    Ok(result) => {
                        let _ = tx.send(AppEvent::DailyFetched {
                            author_papers: result.author_papers,
                            scored_papers: result.scored_papers,
                        });
                    }
                    Err(e) => {
                        let _ = tx.send(AppEvent::Toast {
                            message: format!("JSON parse error: {}", e),
                            is_error: true,
                        });
                    }
                }
            }
            Ok(out) => {
                let stderr = String::from_utf8_lossy(&out.stderr);
                let _ = tx.send(AppEvent::Toast {
                    message: format!("Fetch failed: {}", stderr),
                    is_error: true,
                });
            }
            Err(e) => {
                let _ = tx.send(AppEvent::Toast {
                    message: format!("Command error: {}", e),
                    is_error: true,
                });
            }
        }
    });
}

pub fn search_papers(tx: mpsc::UnboundedSender<AppEvent>, query: &str) {
    let query = query.to_string();
    tokio::spawn(async move {
        let output = Command::new("uv")
            .args(["run", "axp", "search", &query, "--json"])
            .output()
            .await;

        match output {
            Ok(out) if out.status.success() => {
                match serde_json::from_slice::<Vec<ScoredPaper>>(&out.stdout) {
                    Ok(papers) => {
                        let _ = tx.send(AppEvent::SearchResults { papers });
                    }
                    Err(e) => {
                        let _ = tx.send(AppEvent::Toast {
                            message: format!("JSON parse error: {}", e),
                            is_error: true,
                        });
                    }
                }
            }
            _ => {
                let _ = tx.send(AppEvent::Toast {
                    message: "Search failed".to_string(),
                    is_error: true,
                });
            }
        }
    });
}
```

```rust
// tui-rs/src/commands/ai.rs
use tokio::process::Command;
use tokio::sync::mpsc;

use crate::app::AppEvent;

pub fn run_summarize(tx: mpsc::UnboundedSender<AppEvent>, job_id: String, arxiv_id: String) {
    tokio::spawn(async move {
        let output = Command::new("uv")
            .args(["run", "axp", "daily", "summarize", &arxiv_id])
            .output()
            .await;

        match output {
            Ok(out) if out.status.success() => {
                let _ = tx.send(AppEvent::JobCompleted { job_id });
            }
            Ok(out) => {
                let stderr = String::from_utf8_lossy(&out.stderr).to_string();
                let _ = tx.send(AppEvent::JobFailed { job_id, error: stderr });
            }
            Err(e) => {
                let _ = tx.send(AppEvent::JobFailed { job_id, error: e.to_string() });
            }
        }
    });
}

pub fn run_translate(tx: mpsc::UnboundedSender<AppEvent>, job_id: String, arxiv_id: String) {
    tokio::spawn(async move {
        let output = Command::new("uv")
            .args(["run", "axp", "daily", "translate", &arxiv_id])
            .output()
            .await;

        match output {
            Ok(out) if out.status.success() => {
                let _ = tx.send(AppEvent::JobCompleted { job_id });
            }
            _ => {
                let _ = tx.send(AppEvent::JobFailed { job_id, error: "Translation failed".to_string() });
            }
        }
    });
}

pub fn run_review(tx: mpsc::UnboundedSender<AppEvent>, job_id: String, arxiv_id: String) {
    tokio::spawn(async move {
        let output = Command::new("uv")
            .args(["run", "axp", "review", &arxiv_id])
            .output()
            .await;

        match output {
            Ok(out) if out.status.success() => {
                let _ = tx.send(AppEvent::JobCompleted { job_id });
            }
            _ => {
                let _ = tx.send(AppEvent::JobFailed { job_id, error: "Review failed".to_string() });
            }
        }
    });
}
```

- [ ] **Step 4: Wire fetch into Daily tab key handler**

In `events.rs`, update the `'r'` handler in `handle_daily_key`:

```rust
KeyCode::Char('r') => {
    app.daily.loading = true;
    crate::commands::fetch::fetch_daily(
        app.event_tx.clone(),
        app.daily.days,
        app.daily.limit,
    );
}
```

- [ ] **Step 5: Add commands module to main.rs**

```rust
mod commands;
```

- [ ] **Step 6: Build and test**

```bash
cd tui-rs && cargo build
```

- [ ] **Step 7: Run full Python tests to ensure --json doesn't break existing CLI**

```bash
cd /home/axect/Documents/Project/AI_Project/arXiv_explorer && uv run pytest -v
```

- [ ] **Step 8: Commit**

```bash
git add tui-rs/ src/arxiv_explorer/cli/
git commit -m "feat: add --json flag to CLI, Rust command layer for fetch/AI subprocess calls"
```

---

## Phase 2: Remaining Tabs (Tasks 5–8)

Each task fills in one of the placeholder tab renderers with full functionality.

### Task 5: Search Tab

Fill in `render_search` in main.rs with: search input at top, paper table, detail panel. Same layout as Daily but with editable search bar. Wire `/` key to enter edit mode, Enter to trigger `commands::fetch::search_papers`.

### Task 6: Lists Tab

Fill in `render_lists` with: left panel (ListView of reading lists with system/user separation), right panel (paper table with Title/Category/Added/Status columns). Load data from `app.db.get_top_level_lists()` and `app.db.get_list_papers()`. Wire `n`, `f`, `e`, `Del`, `s`, `m`, `c` keys.

### Task 7: Notes Tab

Fill in `render_notes` with: left panel (note list), right panel (note content). Load from `app.db.get_notes()`. Wire `n` (new), `Del` (delete).

### Task 8: Prefs Tab

Fill in `render_prefs` with 5 sections:
- Top row: Categories | Keywords | Authors (3-column, Tab to switch focus)
- Bottom row: Weights | Config (2-column)
- Categories: table + Browse button (launches fuzzy search popup)
- Keywords: table with star display (★★★☆☆)
- Authors: table + input
- Weights: bars with ←→ adjustment
- Config: provider + language display

---

## Phase 3: Integration (Task 9)

### Task 9: Python CLI `tui` Command + Polish

Modify `src/arxiv_explorer/cli/main.py` to detect and launch the Rust binary. Add `AXP_DB` environment variable passing. Keep Textual as fallback. Update `.gitignore` for `tui-rs/target/`.

---

## Notes

- Tasks 5-9 follow the same patterns established in Tasks 1-4. Each fills in a render function and wires key handlers.
- The plan provides complete code for Phase 1 (Tasks 1-4) which establishes all patterns. Phase 2-3 tasks follow these patterns for each tab.
- `cargo test` should pass after each task. `uv run pytest` should pass after Task 4.
