#![allow(dead_code)]
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

// Job types for background tasks (in-memory only)
#[derive(Debug, Clone, PartialEq)]
pub enum JobType {
    Summarize,
    Translate,
    Review,
}

impl std::fmt::Display for JobType {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            JobType::Summarize => write!(f, "Summarize"),
            JobType::Translate => write!(f, "Translate"),
            JobType::Review => write!(f, "Review"),
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
