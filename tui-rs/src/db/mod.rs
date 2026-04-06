pub mod models;

use std::path::PathBuf;

use rusqlite::{Connection, Result, params};

use models::*;

pub struct Database {
    conn: Connection,
}

impl Database {
    /// Open database at the given path, enabling WAL mode and foreign keys.
    pub fn open(path: &PathBuf) -> Result<Self> {
        let conn = Connection::open(path)?;
        conn.execute_batch("PRAGMA foreign_keys = ON; PRAGMA journal_mode = WAL;")?;
        Ok(Self { conn })
    }

    /// Return the default database path.
    /// Checks AXP_DB env var first, then ~/.config/arxiv-explorer/explorer.db
    pub fn default_path() -> PathBuf {
        if let Ok(p) = std::env::var("AXP_DB") {
            return PathBuf::from(p);
        }
        dirs::config_dir()
            .unwrap_or_else(|| PathBuf::from("."))
            .join("arxiv-explorer")
            .join("explorer.db")
    }

    // =========================================================================
    // Papers
    // =========================================================================

    /// Fetch a single paper by arxiv_id. Returns None if not found.
    /// The `authors` and `categories` columns are JSON arrays in the DB.
    pub fn get_paper(&self, arxiv_id: &str) -> Result<Option<Paper>> {
        let mut stmt = self.conn.prepare(
            "SELECT arxiv_id, title, abstract, authors, categories, published, updated, pdf_url \
             FROM papers WHERE arxiv_id = ?1",
        )?;
        let mut rows = stmt.query(params![arxiv_id])?;
        if let Some(row) = rows.next()? {
            let authors_json: String = row.get(3)?;
            let categories_json: String = row.get(4)?;
            let authors: Vec<String> =
                serde_json::from_str(&authors_json).unwrap_or_default();
            let categories: Vec<String> =
                serde_json::from_str(&categories_json).unwrap_or_default();
            Ok(Some(Paper {
                arxiv_id: row.get(0)?,
                title: row.get(1)?,
                abstract_text: row.get(2)?,
                authors,
                categories,
                published: row.get(5)?,
                updated: row.get(6)?,
                pdf_url: row.get(7)?,
            }))
        } else {
            Ok(None)
        }
    }

    // =========================================================================
    // Preferred Categories
    // =========================================================================

    pub fn get_categories(&self) -> Result<Vec<PreferredCategory>> {
        let mut stmt = self.conn.prepare(
            "SELECT id, category, priority, added_at FROM preferred_categories ORDER BY priority DESC",
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
            "INSERT OR REPLACE INTO preferred_categories (category, priority) VALUES (?1, ?2)",
            params![category, priority],
        )?;
        Ok(())
    }

    pub fn set_category_priority(&self, category: &str, priority: i64) -> Result<()> {
        self.conn.execute(
            "UPDATE preferred_categories SET priority = ?1 WHERE category = ?2",
            params![priority, category],
        )?;
        Ok(())
    }

    pub fn remove_category(&self, category: &str) -> Result<bool> {
        let n = self.conn.execute(
            "DELETE FROM preferred_categories WHERE category = ?1",
            params![category],
        )?;
        Ok(n > 0)
    }

    // =========================================================================
    // Keyword Interests
    // =========================================================================

    pub fn get_keywords(&self) -> Result<Vec<KeywordInterest>> {
        let mut stmt = self.conn.prepare(
            "SELECT id, keyword, weight, source FROM keyword_interests ORDER BY weight DESC",
        )?;
        let rows = stmt.query_map([], |row| {
            // Weight is stored as REAL in DB but the API uses i64 (1-5 stars)
            let weight_f: f64 = row.get(2)?;
            Ok(KeywordInterest {
                id: row.get(0)?,
                keyword: row.get(1)?,
                weight: weight_f.round() as i64,
                source: row.get(3)?,
            })
        })?;
        rows.collect()
    }

    pub fn add_keyword(&self, keyword: &str, weight: i64) -> Result<()> {
        let w = weight.max(1).min(5);
        self.conn.execute(
            "INSERT INTO keyword_interests (keyword, weight, source) VALUES (?1, ?2, 'explicit') \
             ON CONFLICT(keyword) DO UPDATE SET weight = ?2",
            params![keyword.to_lowercase(), w],
        )?;
        Ok(())
    }

    pub fn set_keyword_weight(&self, keyword: &str, weight: i64) -> Result<()> {
        let w = weight.max(1).min(5);
        self.conn.execute(
            "UPDATE keyword_interests SET weight = ?1 WHERE keyword = ?2",
            params![w, keyword.to_lowercase()],
        )?;
        Ok(())
    }

    pub fn remove_keyword(&self, keyword: &str) -> Result<bool> {
        let n = self.conn.execute(
            "DELETE FROM keyword_interests WHERE keyword = ?1",
            params![keyword.to_lowercase()],
        )?;
        Ok(n > 0)
    }

    // =========================================================================
    // Preferred Authors
    // =========================================================================

    pub fn get_authors(&self) -> Result<Vec<PreferredAuthor>> {
        let mut stmt = self.conn.prepare(
            "SELECT id, name, added_at FROM preferred_authors ORDER BY name",
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
            "INSERT OR IGNORE INTO preferred_authors (name) VALUES (?1)",
            params![name],
        )?;
        Ok(())
    }

    pub fn remove_author(&self, name: &str) -> Result<bool> {
        let n = self.conn.execute(
            "DELETE FROM preferred_authors WHERE name = ?1",
            params![name],
        )?;
        Ok(n > 0)
    }

    // =========================================================================
    // Paper Interactions
    // =========================================================================

    /// Get the latest interaction_type string for a paper, or None.
    #[allow(dead_code)]
    pub fn get_interaction(&self, arxiv_id: &str) -> Result<Option<String>> {
        let mut stmt = self.conn.prepare(
            "SELECT interaction_type FROM paper_interactions \
             WHERE arxiv_id = ?1 ORDER BY created_at DESC LIMIT 1",
        )?;
        let mut rows = stmt.query(params![arxiv_id])?;
        if let Some(row) = rows.next()? {
            Ok(Some(row.get(0)?))
        } else {
            Ok(None)
        }
    }

    pub fn mark_interesting(&self, arxiv_id: &str) -> Result<()> {
        self.conn.execute(
            "DELETE FROM paper_interactions WHERE arxiv_id = ?1 AND interaction_type = 'not_interesting'",
            params![arxiv_id],
        )?;
        self.conn.execute(
            "INSERT OR REPLACE INTO paper_interactions (arxiv_id, interaction_type) VALUES (?1, 'interesting')",
            params![arxiv_id],
        )?;
        self.sync_to_like_list(arxiv_id, true)?;
        Ok(())
    }

    pub fn mark_not_interesting(&self, arxiv_id: &str) -> Result<()> {
        self.conn.execute(
            "DELETE FROM paper_interactions WHERE arxiv_id = ?1 AND interaction_type = 'interesting'",
            params![arxiv_id],
        )?;
        self.conn.execute(
            "INSERT OR REPLACE INTO paper_interactions (arxiv_id, interaction_type) VALUES (?1, 'not_interesting')",
            params![arxiv_id],
        )?;
        self.sync_to_like_list(arxiv_id, false)?;
        Ok(())
    }

    // =========================================================================
    // Reading Lists
    // =========================================================================

    pub fn get_top_level_lists(&self) -> Result<Vec<ReadingList>> {
        let mut stmt = self.conn.prepare(
            "SELECT id, name, description, parent_id, is_folder, is_system, created_at \
             FROM reading_lists WHERE parent_id IS NULL ORDER BY is_system DESC, name",
        )?;
        let rows = stmt.query_map([], |row| {
            Ok(ReadingList {
                id: row.get(0)?,
                name: row.get(1)?,
                description: row.get(2)?,
                parent_id: row.get(3)?,
                is_folder: row.get::<_, i64>(4)? != 0,
                is_system: row.get::<_, i64>(5)? != 0,
                created_at: row.get(6)?,
            })
        })?;
        rows.collect()
    }

    pub fn get_list_papers(&self, list_id: i64) -> Result<Vec<ReadingListPaper>> {
        let mut stmt = self.conn.prepare(
            "SELECT id, list_id, arxiv_id, status, position, added_at \
             FROM reading_list_papers WHERE list_id = ?1 ORDER BY added_at DESC",
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
            "SELECT COUNT(*) FROM reading_list_papers WHERE list_id = ?1",
            params![list_id],
            |row| row.get(0),
        )
    }

    #[allow(dead_code)]
    pub fn create_list(&self, name: &str, parent_id: Option<i64>) -> Result<()> {
        self.conn.execute(
            "INSERT INTO reading_lists (name, parent_id, is_folder, is_system) VALUES (?1, ?2, 0, 0)",
            params![name, parent_id],
        )?;
        Ok(())
    }

    #[allow(dead_code)]
    pub fn create_folder(&self, name: &str) -> Result<()> {
        self.conn.execute(
            "INSERT INTO reading_lists (name, is_folder, is_system) VALUES (?1, 1, 0)",
            params![name],
        )?;
        Ok(())
    }

    /// Delete a list by ID. Rejects system lists. Returns true if deleted.
    pub fn delete_list(&self, list_id: i64) -> Result<bool> {
        let is_system: i64 = self.conn.query_row(
            "SELECT is_system FROM reading_lists WHERE id = ?1",
            params![list_id],
            |row| row.get(0),
        ).unwrap_or(0);
        if is_system != 0 {
            return Ok(false);
        }
        let n = self.conn.execute(
            "DELETE FROM reading_lists WHERE id = ?1",
            params![list_id],
        )?;
        Ok(n > 0)
    }

    /// Rename a list by ID. Rejects system lists. Returns true if renamed.
    #[allow(dead_code)]
    pub fn rename_list(&self, list_id: i64, new_name: &str) -> Result<bool> {
        let is_system: Option<i64> = self.conn.query_row(
            "SELECT is_system FROM reading_lists WHERE id = ?1",
            params![list_id],
            |row| row.get(0),
        ).ok();
        match is_system {
            None => return Ok(false),
            Some(v) if v != 0 => return Ok(false),
            _ => {}
        }
        let n = self.conn.execute(
            "UPDATE reading_lists SET name = ?1 WHERE id = ?2",
            params![new_name, list_id],
        )?;
        Ok(n > 0)
    }

    /// Toggle a paper's bookmark in the month folder (YYYYMM).
    /// Creates the folder if needed. Returns true if added, false if removed.
    pub fn toggle_bookmark(&self, arxiv_id: &str, month: &str) -> Result<bool> {
        // Find or create month folder
        let folder_id = self.get_or_create_month_folder(month)?;

        // Check if paper already in folder
        let existing: Option<i64> = self.conn.query_row(
            "SELECT id FROM reading_list_papers WHERE list_id = ?1 AND arxiv_id = ?2",
            params![folder_id, arxiv_id],
            |row| row.get(0),
        ).ok();

        if existing.is_some() {
            self.conn.execute(
                "DELETE FROM reading_list_papers WHERE list_id = ?1 AND arxiv_id = ?2",
                params![folder_id, arxiv_id],
            )?;
            Ok(false)
        } else {
            let max_pos: i64 = self.conn.query_row(
                "SELECT COALESCE(MAX(position), 0) FROM reading_list_papers WHERE list_id = ?1",
                params![folder_id],
                |row| row.get(0),
            ).unwrap_or(0);
            self.conn.execute(
                "INSERT OR IGNORE INTO reading_list_papers (list_id, arxiv_id, position) VALUES (?1, ?2, ?3)",
                params![folder_id, arxiv_id, max_pos + 1],
            )?;
            Ok(true)
        }
    }

    /// Get all arxiv_ids bookmarked in the given month folder.
    pub fn get_bookmarked_ids(&self, month: &str) -> Result<Vec<String>> {
        let folder_id = match self.get_month_folder_id(month)? {
            Some(id) => id,
            None => return Ok(vec![]),
        };
        let mut stmt = self.conn.prepare(
            "SELECT arxiv_id FROM reading_list_papers WHERE list_id = ?1",
        )?;
        let rows = stmt.query_map(params![folder_id], |row| row.get(0))?;
        rows.collect()
    }

    // =========================================================================
    // Paper Notes
    // =========================================================================

    pub fn get_notes(&self) -> Result<Vec<PaperNote>> {
        let mut stmt = self.conn.prepare(
            "SELECT id, arxiv_id, note_type, content, created_at FROM paper_notes ORDER BY created_at DESC",
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

    #[allow(dead_code)]
    pub fn add_note(&self, arxiv_id: &str, note_type: &str, content: &str) -> Result<()> {
        self.conn.execute(
            "INSERT INTO paper_notes (arxiv_id, note_type, content) VALUES (?1, ?2, ?3)",
            params![arxiv_id, note_type, content],
        )?;
        Ok(())
    }

    pub fn delete_note(&self, note_id: i64) -> Result<bool> {
        let n = self.conn.execute(
            "DELETE FROM paper_notes WHERE id = ?1",
            params![note_id],
        )?;
        Ok(n > 0)
    }

    // =========================================================================
    // App Settings
    // =========================================================================

    pub fn get_setting(&self, key: &str, default: &str) -> Result<String> {
        let result = self.conn.query_row(
            "SELECT value FROM app_settings WHERE key = ?1",
            params![key],
            |row| row.get::<_, String>(0),
        );
        match result {
            Ok(v) => Ok(v),
            Err(rusqlite::Error::QueryReturnedNoRows) => Ok(default.to_string()),
            Err(e) => Err(e),
        }
    }

    pub fn set_setting(&self, key: &str, value: &str) -> Result<()> {
        self.conn.execute(
            "INSERT OR REPLACE INTO app_settings (key, value, updated_at) VALUES (?1, ?2, datetime('now'))",
            params![key, value],
        )?;
        Ok(())
    }

    /// Returns [weight_content, weight_category, weight_keyword, weight_recency].
    /// Defaults: [60, 20, 15, 5]
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

    // =========================================================================
    // Summaries & Translations
    // =========================================================================

    pub fn get_summary(&self, arxiv_id: &str) -> Result<Option<PaperSummary>> {
        let mut stmt = self.conn.prepare(
            "SELECT arxiv_id, summary_short, summary_detailed, key_findings \
             FROM paper_summaries WHERE arxiv_id = ?1",
        )?;
        let mut rows = stmt.query(params![arxiv_id])?;
        if let Some(row) = rows.next()? {
            Ok(Some(PaperSummary {
                arxiv_id: row.get(0)?,
                summary_short: row.get(1)?,
                summary_detailed: row.get(2)?,
                key_findings: row.get(3)?,
            }))
        } else {
            Ok(None)
        }
    }

    pub fn get_review_section_count(&self, arxiv_id: &str) -> Result<i64> {
        self.conn.query_row(
            "SELECT COUNT(*) FROM paper_review_sections WHERE arxiv_id = ?",
            params![arxiv_id],
            |row| row.get(0),
        )
    }

    pub fn get_translation(&self, arxiv_id: &str) -> Result<Option<PaperTranslation>> {
        let mut stmt = self.conn.prepare(
            "SELECT arxiv_id, target_language, translated_title, translated_abstract \
             FROM paper_translations WHERE arxiv_id = ?1 ORDER BY generated_at DESC LIMIT 1",
        )?;
        let mut rows = stmt.query(params![arxiv_id])?;
        if let Some(row) = rows.next()? {
            Ok(Some(PaperTranslation {
                arxiv_id: row.get(0)?,
                target_language: row.get(1)?,
                translated_title: row.get(2)?,
                translated_abstract: row.get(3)?,
            }))
        } else {
            Ok(None)
        }
    }

    // =========================================================================
    // Private helpers
    // =========================================================================

    fn get_system_list_id(&self, name: &str) -> Result<Option<i64>> {
        let result = self.conn.query_row(
            "SELECT id FROM reading_lists WHERE name = ?1 AND is_system = 1",
            params![name],
            |row| row.get(0),
        );
        match result {
            Ok(id) => Ok(Some(id)),
            Err(rusqlite::Error::QueryReturnedNoRows) => Ok(None),
            Err(e) => Err(e),
        }
    }

    fn sync_to_like_list(&self, arxiv_id: &str, like: bool) -> Result<()> {
        let like_id = self.get_system_list_id("Like")?;
        let dislike_id = self.get_system_list_id("Dislike")?;

        if like {
            // Remove from Dislike, add to Like
            if let Some(did) = dislike_id {
                self.conn.execute(
                    "DELETE FROM reading_list_papers WHERE list_id = ?1 AND arxiv_id = ?2",
                    params![did, arxiv_id],
                )?;
            }
            if let Some(lid) = like_id {
                let max_pos: i64 = self.conn.query_row(
                    "SELECT COALESCE(MAX(position), 0) FROM reading_list_papers WHERE list_id = ?1",
                    params![lid],
                    |row| row.get(0),
                ).unwrap_or(0);
                self.conn.execute(
                    "INSERT OR IGNORE INTO reading_list_papers (list_id, arxiv_id, position) VALUES (?1, ?2, ?3)",
                    params![lid, arxiv_id, max_pos + 1],
                )?;
            }
        } else {
            // Remove from Like, add to Dislike
            if let Some(lid) = like_id {
                self.conn.execute(
                    "DELETE FROM reading_list_papers WHERE list_id = ?1 AND arxiv_id = ?2",
                    params![lid, arxiv_id],
                )?;
            }
            if let Some(did) = dislike_id {
                let max_pos: i64 = self.conn.query_row(
                    "SELECT COALESCE(MAX(position), 0) FROM reading_list_papers WHERE list_id = ?1",
                    params![did],
                    |row| row.get(0),
                ).unwrap_or(0);
                self.conn.execute(
                    "INSERT OR IGNORE INTO reading_list_papers (list_id, arxiv_id, position) VALUES (?1, ?2, ?3)",
                    params![did, arxiv_id, max_pos + 1],
                )?;
            }
        }
        Ok(())
    }

    fn get_month_folder_id(&self, month: &str) -> Result<Option<i64>> {
        let result = self.conn.query_row(
            "SELECT id FROM reading_lists WHERE name = ?1 AND is_folder = 1",
            params![month],
            |row| row.get(0),
        );
        match result {
            Ok(id) => Ok(Some(id)),
            Err(rusqlite::Error::QueryReturnedNoRows) => Ok(None),
            Err(e) => Err(e),
        }
    }

    fn get_or_create_month_folder(&self, month: &str) -> Result<i64> {
        if let Some(id) = self.get_month_folder_id(month)? {
            return Ok(id);
        }
        self.conn.execute(
            "INSERT INTO reading_lists (name, is_folder, is_system) VALUES (?1, 1, 0)",
            params![month],
        )?;
        Ok(self.conn.last_insert_rowid())
    }
}

// =============================================================================
// Tests
// =============================================================================

#[cfg(test)]
mod tests {
    use super::*;
    use rusqlite::Connection;

    static SCHEMA: &str = include_str!("../../tests/schema.sql");

    fn setup_test_db() -> Database {
        let conn = Connection::open_in_memory().expect("in-memory DB");
        conn.execute_batch("PRAGMA foreign_keys = ON;").unwrap();
        conn.execute_batch(SCHEMA).expect("schema applied");
        // Create system lists
        conn.execute(
            "INSERT INTO reading_lists (name, is_folder, is_system) VALUES ('Like', 0, 1)",
            [],
        ).unwrap();
        conn.execute(
            "INSERT INTO reading_lists (name, is_folder, is_system) VALUES ('Dislike', 0, 1)",
            [],
        ).unwrap();
        Database { conn }
    }

    #[test]
    fn test_categories_crud() {
        let db = setup_test_db();

        // Start empty
        let cats = db.get_categories().unwrap();
        assert!(cats.is_empty());

        // Add a category
        db.add_category("hep-ph", 5).unwrap();
        db.add_category("cs.LG", 3).unwrap();

        let cats = db.get_categories().unwrap();
        assert_eq!(cats.len(), 2);
        // Ordered by priority DESC
        assert_eq!(cats[0].category, "hep-ph");
        assert_eq!(cats[0].priority, 5);
        assert_eq!(cats[1].category, "cs.LG");

        // Update priority via add (INSERT OR REPLACE)
        db.add_category("hep-ph", 2).unwrap();
        let cats = db.get_categories().unwrap();
        // Now cs.LG should be first
        assert_eq!(cats[0].category, "cs.LG");

        // Remove
        let removed = db.remove_category("cs.LG").unwrap();
        assert!(removed);
        let removed_again = db.remove_category("cs.LG").unwrap();
        assert!(!removed_again);

        let cats = db.get_categories().unwrap();
        assert_eq!(cats.len(), 1);
        assert_eq!(cats[0].category, "hep-ph");
    }

    #[test]
    fn test_keywords_crud() {
        let db = setup_test_db();

        let kws = db.get_keywords().unwrap();
        assert!(kws.is_empty());

        db.add_keyword("neural network", 4).unwrap();
        db.add_keyword("diffusion", 2).unwrap();

        let kws = db.get_keywords().unwrap();
        assert_eq!(kws.len(), 2);
        // Ordered by weight DESC
        assert_eq!(kws[0].keyword, "neural network");
        assert_eq!(kws[0].weight, 4);

        // Weight clamping — exceeds 5
        db.add_keyword("test", 10).unwrap();
        let kws = db.get_keywords().unwrap();
        let test_kw = kws.iter().find(|k| k.keyword == "test").unwrap();
        assert_eq!(test_kw.weight, 5);

        // Remove
        let removed = db.remove_keyword("diffusion").unwrap();
        assert!(removed);
        let removed_again = db.remove_keyword("diffusion").unwrap();
        assert!(!removed_again);

        let kws = db.get_keywords().unwrap();
        assert_eq!(kws.len(), 2);
    }

    #[test]
    fn test_settings() {
        let db = setup_test_db();

        // Default value when not set
        let val = db.get_setting("my_key", "default_val").unwrap();
        assert_eq!(val, "default_val");

        // Set and retrieve
        db.set_setting("my_key", "hello").unwrap();
        let val = db.get_setting("my_key", "default_val").unwrap();
        assert_eq!(val, "hello");

        // Overwrite
        db.set_setting("my_key", "world").unwrap();
        let val = db.get_setting("my_key", "default_val").unwrap();
        assert_eq!(val, "world");
    }

    #[test]
    fn test_weights() {
        let db = setup_test_db();

        // Defaults when not set
        let w = db.get_weights().unwrap();
        assert_eq!(w, [60, 20, 15, 5]);

        // Set and verify
        db.set_weights([50, 25, 20, 5]).unwrap();
        let w = db.get_weights().unwrap();
        assert_eq!(w, [50, 25, 20, 5]);

        // Partial check
        assert_eq!(w[0], 50);
        assert_eq!(w[1], 25);
        assert_eq!(w[2], 20);
        assert_eq!(w[3], 5);
    }
}
