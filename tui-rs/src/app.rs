use std::collections::HashSet;
use std::path::PathBuf;
use std::time::{Duration, Instant};
use tokio::sync::mpsc;

use crate::db::{Database, models::ScoredPaper};

// =============================================================================
// Tab
// =============================================================================

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
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

    pub fn label(&self) -> &'static str {
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

// =============================================================================
// AppEvent — results from async tasks
// =============================================================================

#[derive(Debug)]
pub enum AppEvent {
    DailyFetched {
        author_papers: Vec<ScoredPaper>,
        scored_papers: Vec<ScoredPaper>,
    },
    SearchResults(Vec<ScoredPaper>),
    JobCompleted {
        job_id: String,
        message: String,
    },
    JobFailed {
        job_id: String,
        message: String,
    },
    Toast {
        message: String,
        is_error: bool,
    },
}

// =============================================================================
// Toast
// =============================================================================

#[derive(Debug, Clone)]
pub struct Toast {
    pub message: String,
    pub is_error: bool,
    pub expires_at: Instant,
}

impl Toast {
    pub fn new(message: impl Into<String>, is_error: bool) -> Self {
        Toast {
            message: message.into(),
            is_error,
            expires_at: Instant::now() + Duration::from_secs(4),
        }
    }
}

// =============================================================================
// Per-tab state
// =============================================================================

pub struct DailyState {
    pub days: u32,
    pub limit: u32,
    pub author_papers: Vec<ScoredPaper>,
    pub scored_papers: Vec<ScoredPaper>,
    pub selected: usize,
    pub bookmarked: HashSet<String>,
    pub loading: bool,
}

impl Default for DailyState {
    fn default() -> Self {
        DailyState {
            days: 7,
            limit: 20,
            author_papers: vec![],
            scored_papers: vec![],
            selected: 0,
            bookmarked: HashSet::new(),
            loading: false,
        }
    }
}

pub struct SearchState {
    pub query: String,
    pub results: Vec<ScoredPaper>,
    pub selected: usize,
    pub loading: bool,
    pub editing: bool,
}

impl Default for SearchState {
    fn default() -> Self {
        SearchState {
            query: String::new(),
            results: vec![],
            selected: 0,
            loading: false,
            editing: false,
        }
    }
}

pub struct ListsState {
    pub selected: usize,
}

impl Default for ListsState {
    fn default() -> Self {
        ListsState { selected: 0 }
    }
}

pub struct NotesState {
    pub selected: usize,
}

impl Default for NotesState {
    fn default() -> Self {
        NotesState { selected: 0 }
    }
}

pub struct PrefsState {
    pub weights: [i64; 4],
    pub provider: String,
    pub language: String,
    pub selected: usize,
}

impl Default for PrefsState {
    fn default() -> Self {
        PrefsState {
            weights: [60, 20, 15, 5],
            provider: "gemini".to_string(),
            language: "en".to_string(),
            selected: 0,
        }
    }
}

// =============================================================================
// App
// =============================================================================

pub struct App {
    pub running: bool,
    pub active_tab: Tab,
    pub db: Database,
    pub daily: DailyState,
    pub search: SearchState,
    pub lists: ListsState,
    pub notes: NotesState,
    pub prefs: PrefsState,
    pub toasts: Vec<Toast>,
    pub event_tx: mpsc::UnboundedSender<AppEvent>,
    pub event_rx: mpsc::UnboundedReceiver<AppEvent>,
}

impl App {
    pub fn new(db_path: PathBuf) -> anyhow::Result<Self> {
        let db = Database::open(&db_path).map_err(|e| anyhow::anyhow!("DB error: {e}"))?;

        let weights = db.get_weights().unwrap_or([60, 20, 15, 5]);
        let provider = db.get_setting("ai_provider", "gemini").unwrap_or_else(|_| "gemini".to_string());
        let language = db.get_setting("language", "en").unwrap_or_else(|_| "en".to_string());

        // Pre-populate bookmarks for current month
        let month = chrono::Local::now().format("%Y%m").to_string();
        let bookmarked_ids = db.get_bookmarked_ids(&month).unwrap_or_default();
        let bookmarked: HashSet<String> = bookmarked_ids.into_iter().collect();

        let (event_tx, event_rx) = mpsc::unbounded_channel();

        Ok(App {
            running: true,
            active_tab: Tab::Daily,
            db,
            daily: DailyState {
                bookmarked,
                ..DailyState::default()
            },
            search: SearchState::default(),
            lists: ListsState::default(),
            notes: NotesState::default(),
            prefs: PrefsState {
                weights,
                provider,
                language,
                selected: 0,
            },
            toasts: vec![],
            event_tx,
            event_rx,
        })
    }

    /// Process an async event result.
    pub fn handle_app_event(&mut self, event: AppEvent) {
        match event {
            AppEvent::DailyFetched { author_papers, scored_papers } => {
                self.daily.author_papers = author_papers;
                self.daily.scored_papers = scored_papers;
                self.daily.selected = 0;
                self.daily.loading = false;
                let total = self.daily.author_papers.len() + self.daily.scored_papers.len();
                self.push_toast(format!("Fetched {total} papers"), false);
            }
            AppEvent::SearchResults(results) => {
                let n = results.len();
                self.search.results = results;
                self.search.selected = 0;
                self.search.loading = false;
                self.push_toast(format!("Found {n} papers"), false);
            }
            AppEvent::JobCompleted { job_id: _, message } => {
                self.push_toast(message, false);
            }
            AppEvent::JobFailed { job_id: _, message } => {
                self.push_toast(message, true);
            }
            AppEvent::Toast { message, is_error } => {
                self.push_toast(message, is_error);
            }
        }
    }

    /// Remove expired toasts.
    pub fn tick(&mut self) {
        let now = Instant::now();
        self.toasts.retain(|t| t.expires_at > now);
    }

    /// Returns all papers: author papers first, then scored papers.
    pub fn all_papers(&self) -> Vec<&ScoredPaper> {
        self.daily
            .author_papers
            .iter()
            .chain(self.daily.scored_papers.iter())
            .collect()
    }

    /// Returns the currently selected paper in the Daily tab.
    pub fn selected_daily_paper(&self) -> Option<&ScoredPaper> {
        let papers = self.all_papers();
        papers.get(self.daily.selected).copied()
    }

    fn push_toast(&mut self, message: impl Into<String>, is_error: bool) {
        self.toasts.push(Toast::new(message, is_error));
    }
}
