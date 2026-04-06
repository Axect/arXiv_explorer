use crossterm::event::{KeyCode, MouseEvent, MouseEventKind};

use crate::app::{App, ConfirmAction, Tab};
use crate::categories;

// =============================================================================
// Global key handler
// =============================================================================

/// Returns true if the app should quit.
pub fn handle_key(app: &mut App, key: KeyCode) -> bool {
    // Confirmation dialog takes highest priority
    if app.confirm_action.is_some() {
        handle_confirm_key(app, key);
        return false;
    }

    // Paper detail overlay takes priority over all other handlers
    if app.detail.is_some() {
        handle_detail_key(app, key);
        return false;
    }

    // Input overlay takes priority
    if app.overlay.is_some() {
        handle_overlay_key(app, key);
        return false;
    }

    // Jobs panel takes priority after detail overlay
    if app.show_jobs {
        handle_jobs_key(app, key);
        return false;
    }

    match key {
        // Quit
        KeyCode::Char('q') | KeyCode::Char('Q') => {
            app.running = false;
            return true;
        }
        // Toggle jobs panel (global — works from any tab)
        KeyCode::Char('j') => {
            app.show_jobs = true;
        }
        // Tab switch: 1-5
        KeyCode::Char('1') => app.active_tab = Tab::Daily,
        KeyCode::Char('2') => app.active_tab = Tab::Search,
        KeyCode::Char('3') => {
            app.active_tab = Tab::Lists;
            app.lists.items = app
                .db
                .get_top_level_lists()
                .unwrap_or_default()
                .into_iter()
                .map(|l| {
                    let count = app.db.get_list_paper_count(l.id).unwrap_or(0);
                    (l, count)
                })
                .collect();
            // Load papers for the currently selected list (if any)
            load_list_papers_pub(app);
        }
        KeyCode::Char('4') => {
            app.active_tab = Tab::Notes;
            app.notes.notes = app.db.get_notes().unwrap_or_default();
        }
        KeyCode::Char('5') => {
            app.active_tab = Tab::Prefs;
            app.prefs.categories = app.db.get_categories().unwrap_or_default();
            app.prefs.keywords = app.db.get_keywords().unwrap_or_default();
            app.prefs.authors = app.db.get_authors().unwrap_or_default();
            app.prefs.weights = app.db.get_weights().unwrap_or([60, 20, 15, 5]);
            app.prefs.provider = app.db.get_setting("ai_provider", "gemini").unwrap_or_else(|_| "gemini".to_string());
            app.prefs.language = app.db.get_setting("language", "en").unwrap_or_else(|_| "en".to_string());
        }
        // Delegate to per-tab handler
        _ => match app.active_tab {
            Tab::Daily => handle_daily_key(app, key),
            Tab::Search => handle_search_key(app, key),
            Tab::Lists => handle_lists_key(app, key),
            Tab::Notes => handle_notes_key(app, key),
            Tab::Prefs => handle_prefs_key(app, key),
        },
    }
    false
}

// =============================================================================
// Jobs Panel
// =============================================================================

pub fn handle_jobs_key(app: &mut App, key: KeyCode) {
    match key {
        KeyCode::Char('j') | KeyCode::Esc | KeyCode::Char('q') => {
            app.show_jobs = false;
        }
        KeyCode::Up | KeyCode::Char('k') => {
            if app.selected_job > 0 {
                app.selected_job -= 1;
            }
        }
        KeyCode::Down | KeyCode::Char('K') => {
            if app.selected_job + 1 < app.jobs.len() {
                app.selected_job += 1;
            }
        }
        KeyCode::Char('c') => {
            // Clear completed/failed jobs
            app.jobs.retain(|j| j.status == crate::app::JobStatus::Running);
            app.selected_job = app.selected_job.min(app.jobs.len().saturating_sub(1));
        }
        _ => {}
    }
}

// =============================================================================
// Confirmation Dialog
// =============================================================================

pub fn handle_confirm_key(app: &mut App, key: KeyCode) {
    let action = match app.confirm_action.take() {
        Some(a) => a,
        None => return,
    };
    match key {
        KeyCode::Char('y') | KeyCode::Char('Y') => {
            match action {
                ConfirmAction::RegenerateSummary => trigger_summarize(app),
                ConfirmAction::RegenerateTranslation => trigger_translate(app),
            }
        }
        _ => {
            // n, Esc, or any other key — cancel
        }
    }
    // confirm_action was already taken above; ensure it's None
}

// =============================================================================
// Input Overlay (Category Picker / Keyword Input)
// =============================================================================

pub fn handle_overlay_key(app: &mut App, key: KeyCode) {
    let overlay = match app.overlay.take() {
        Some(o) => o,
        None => return,
    };

    match overlay {
        crate::app::OverlayMode::CategoryPicker { mut search, mut filtered, mut selected } => {
            match key {
                KeyCode::Esc => {
                    app.overlay = None;
                }
                KeyCode::Enter => {
                    if let Some(&idx) = filtered.get(selected) {
                        let (code, _desc) = categories::ARXIV_CATEGORIES[idx];
                        let exists = app.prefs.categories.iter().any(|c| c.category == code);
                        if exists {
                            app.push_toast(format!("{code} already added"), false);
                            app.overlay = Some(crate::app::OverlayMode::CategoryPicker { search, filtered, selected });
                        } else {
                            match app.db.add_category(code, 1) {
                                Ok(_) => {
                                    app.prefs.categories = app.db.get_categories().unwrap_or_default();
                                    app.push_toast(format!("Added: {code}"), false);
                                    app.overlay = None;
                                }
                                Err(e) => {
                                    app.push_toast(format!("Error: {e}"), true);
                                    app.overlay = Some(crate::app::OverlayMode::CategoryPicker { search, filtered, selected });
                                }
                            }
                        }
                    }
                }
                KeyCode::Up => {
                    if selected > 0 {
                        selected -= 1;
                    }
                    app.overlay = Some(crate::app::OverlayMode::CategoryPicker { search, filtered, selected });
                }
                KeyCode::Down => {
                    if selected + 1 < filtered.len() {
                        selected += 1;
                    }
                    app.overlay = Some(crate::app::OverlayMode::CategoryPicker { search, filtered, selected });
                }
                KeyCode::Backspace => {
                    search.pop();
                    filtered = categories::filter_categories(&search);
                    selected = 0;
                    app.overlay = Some(crate::app::OverlayMode::CategoryPicker { search, filtered, selected });
                }
                KeyCode::Char(c) => {
                    search.push(c);
                    filtered = categories::filter_categories(&search);
                    selected = 0;
                    app.overlay = Some(crate::app::OverlayMode::CategoryPicker { search, filtered, selected });
                }
                _ => {
                    app.overlay = Some(crate::app::OverlayMode::CategoryPicker { search, filtered, selected });
                }
            }
        }
        crate::app::OverlayMode::KeywordInput { mut text, mut weight } => {
            match key {
                KeyCode::Esc => {
                    app.overlay = None;
                }
                KeyCode::Enter => {
                    let trimmed = text.trim().to_string();
                    if trimmed.is_empty() {
                        app.push_toast("Enter a keyword", false);
                        app.overlay = Some(crate::app::OverlayMode::KeywordInput { text, weight });
                    } else {
                        match app.db.add_keyword(&trimmed, weight) {
                            Ok(_) => {
                                app.prefs.keywords = app.db.get_keywords().unwrap_or_default();
                                app.push_toast(format!("Added: {trimmed}"), false);
                                app.overlay = None;
                            }
                            Err(e) => {
                                app.push_toast(format!("Error: {e}"), true);
                                app.overlay = Some(crate::app::OverlayMode::KeywordInput { text, weight });
                            }
                        }
                    }
                }
                KeyCode::Left => {
                    weight = (weight - 1).max(1);
                    app.overlay = Some(crate::app::OverlayMode::KeywordInput { text, weight });
                }
                KeyCode::Right => {
                    weight = (weight + 1).min(5);
                    app.overlay = Some(crate::app::OverlayMode::KeywordInput { text, weight });
                }
                KeyCode::Backspace => {
                    text.pop();
                    app.overlay = Some(crate::app::OverlayMode::KeywordInput { text, weight });
                }
                KeyCode::Char(c) => {
                    text.push(c);
                    app.overlay = Some(crate::app::OverlayMode::KeywordInput { text, weight });
                }
                _ => {
                    app.overlay = Some(crate::app::OverlayMode::KeywordInput { text, weight });
                }
            }
        }
        crate::app::OverlayMode::AuthorInput { mut text } => {
            match key {
                KeyCode::Esc => {
                    app.overlay = None;
                }
                KeyCode::Enter => {
                    let trimmed = text.trim().to_string();
                    if trimmed.is_empty() {
                        app.push_toast("Enter an author name", false);
                        app.overlay = Some(crate::app::OverlayMode::AuthorInput { text });
                    } else {
                        match app.db.add_author(&trimmed) {
                            Ok(_) => {
                                app.prefs.authors = app.db.get_authors().unwrap_or_default();
                                app.push_toast(format!("Added: {trimmed}"), false);
                                app.overlay = None;
                            }
                            Err(e) => {
                                app.push_toast(format!("Error: {e}"), true);
                                app.overlay = Some(crate::app::OverlayMode::AuthorInput { text });
                            }
                        }
                    }
                }
                KeyCode::Backspace => {
                    text.pop();
                    app.overlay = Some(crate::app::OverlayMode::AuthorInput { text });
                }
                KeyCode::Char(c) => {
                    text.push(c);
                    app.overlay = Some(crate::app::OverlayMode::AuthorInput { text });
                }
                _ => {
                    app.overlay = Some(crate::app::OverlayMode::AuthorInput { text });
                }
            }
        }
    }
}

// =============================================================================
// AI trigger helpers
// =============================================================================

fn trigger_summarize(app: &mut App) {
    if let Some(detail) = &app.detail {
        let arxiv_id = detail.paper.arxiv_id.clone();
        let title = detail.paper.title.clone();
        let job_id = format!("sum-{}", &arxiv_id);
        let tx = app.event_tx.clone();
        app.push_toast("Summarizing...", false);
        app.jobs.push(crate::app::JobEntry {
            id: job_id.clone(),
            paper_id: arxiv_id.clone(),
            paper_title: title,
            job_type: crate::app::JobType::Summarize,
            status: crate::app::JobStatus::Running,
            started_at: std::time::Instant::now(),
            elapsed_secs: None,
        });
        crate::commands::ai::run_summarize(tx, job_id, arxiv_id);
    }
}

fn trigger_translate(app: &mut App) {
    if let Some(detail) = &app.detail {
        let arxiv_id = detail.paper.arxiv_id.clone();
        let title = detail.paper.title.clone();
        let job_id = format!("trans-{}", &arxiv_id);
        let tx = app.event_tx.clone();
        app.push_toast("Translating...", false);
        app.jobs.push(crate::app::JobEntry {
            id: job_id.clone(),
            paper_id: arxiv_id.clone(),
            paper_title: title,
            job_type: crate::app::JobType::Translate,
            status: crate::app::JobStatus::Running,
            started_at: std::time::Instant::now(),
            elapsed_secs: None,
        });
        crate::commands::ai::run_translate(tx, job_id, arxiv_id);
    }
}

// =============================================================================
// Mouse handler
// =============================================================================

pub fn handle_mouse(app: &mut App, mouse: MouseEvent) {
    // If detail overlay is open, only scroll the overlay
    if app.detail.is_some() {
        match mouse.kind {
            MouseEventKind::ScrollUp => {
                if let Some(detail) = &mut app.detail {
                    if detail.scroll > 0 {
                        detail.scroll -= 1;
                    }
                }
            }
            MouseEventKind::ScrollDown => {
                if let Some(detail) = &mut app.detail {
                    detail.scroll += 1;
                }
            }
            _ => {}
        }
        return;
    }

    // If jobs panel is open, scroll the jobs list
    if app.show_jobs {
        match mouse.kind {
            MouseEventKind::ScrollUp => {
                if app.selected_job > 0 {
                    app.selected_job -= 1;
                }
            }
            MouseEventKind::ScrollDown => {
                if app.selected_job + 1 < app.jobs.len() {
                    app.selected_job += 1;
                }
            }
            _ => {}
        }
        return;
    }

    // Otherwise, scroll the active tab content
    match mouse.kind {
        MouseEventKind::ScrollUp => {
            match app.active_tab {
                Tab::Daily => {
                    if app.daily.focus_detail {
                        if app.daily.detail_scroll > 0 {
                            app.daily.detail_scroll -= 1;
                        }
                    } else if app.daily.selected > 0 {
                        app.daily.selected -= 1;
                    }
                }
                Tab::Search => {
                    if app.search.selected > 0 {
                        app.search.selected -= 1;
                    }
                }
                Tab::Lists => {
                    if app.lists.focus_left {
                        if app.lists.selected_list > 0 {
                            app.lists.selected_list -= 1;
                            load_list_papers_pub(app);
                        }
                    } else if app.lists.selected_paper > 0 {
                        app.lists.selected_paper -= 1;
                    }
                }
                Tab::Notes => {
                    if app.notes.selected > 0 {
                        app.notes.selected -= 1;
                    }
                }
                Tab::Prefs => {}
            }
        }
        MouseEventKind::ScrollDown => {
            match app.active_tab {
                Tab::Daily => {
                    if app.daily.focus_detail {
                        app.daily.detail_scroll += 1;
                    } else {
                        let total = app.daily.author_papers.len() + app.daily.scored_papers.len();
                        if total > 0 && app.daily.selected + 1 < total {
                            app.daily.selected += 1;
                        }
                    }
                }
                Tab::Search => {
                    if app.search.selected + 1 < app.search.results.len() {
                        app.search.selected += 1;
                    }
                }
                Tab::Lists => {
                    if app.lists.focus_left {
                        let max = app.lists.items.len().saturating_sub(1);
                        if app.lists.selected_list < max {
                            app.lists.selected_list += 1;
                            load_list_papers_pub(app);
                        }
                    } else {
                        let max = app.lists.papers.len().saturating_sub(1);
                        if app.lists.selected_paper < max {
                            app.lists.selected_paper += 1;
                        }
                    }
                }
                Tab::Notes => {
                    let max = app.notes.notes.len().saturating_sub(1);
                    if app.notes.selected < max {
                        app.notes.selected += 1;
                    }
                }
                Tab::Prefs => {}
            }
        }
        _ => {}
    }
}

// =============================================================================
// Paper Detail Overlay
// =============================================================================

pub fn handle_detail_key(app: &mut App, key: KeyCode) {
    match key {
        KeyCode::Esc | KeyCode::Char('q') => {
            app.detail = None;
        }
        KeyCode::Up | KeyCode::Char('k') => {
            if let Some(detail) = &mut app.detail {
                detail.scroll = detail.scroll.saturating_sub(1);
            }
        }
        KeyCode::Down => {
            if let Some(detail) = &mut app.detail {
                detail.scroll = detail.scroll.saturating_add(1);
            }
        }
        KeyCode::Char('s') => {
            if let Some(detail) = &app.detail {
                if detail.summary.is_some() {
                    app.confirm_action = Some(ConfirmAction::RegenerateSummary);
                } else {
                    trigger_summarize(app);
                }
            }
        }
        KeyCode::Char('t') => {
            if let Some(detail) = &app.detail {
                if detail.translation.is_some() {
                    app.confirm_action = Some(ConfirmAction::RegenerateTranslation);
                } else {
                    trigger_translate(app);
                }
            }
        }
        KeyCode::Char('r') => {
            if let Some(detail) = &app.detail {
                let arxiv_id = detail.paper.arxiv_id.clone();
                let title = detail.paper.title.clone();
                let job_id = format!("review-{}", &arxiv_id);
                let tx = app.event_tx.clone();
                app.push_toast("Reviewing...", false);
                app.jobs.push(crate::app::JobEntry {
                    id: job_id.clone(),
                    paper_id: arxiv_id.clone(),
                    paper_title: title,
                    job_type: crate::app::JobType::Review,
                    status: crate::app::JobStatus::Running,
                    started_at: std::time::Instant::now(),
                    elapsed_secs: None,
                });
                crate::commands::ai::run_review(tx, job_id, arxiv_id);
            }
        }
        KeyCode::Char('l') => {
            if let Some(detail) = &app.detail {
                let id = detail.paper.arxiv_id.clone();
                match app.db.mark_interesting(&id) {
                    Ok(_) => app.push_toast(format!("Liked: {id}"), false),
                    Err(e) => app.push_toast(format!("Error liking: {e}"), true),
                }
            }
        }
        KeyCode::Char('d') => {
            if let Some(detail) = &app.detail {
                let id = detail.paper.arxiv_id.clone();
                match app.db.mark_not_interesting(&id) {
                    Ok(_) => app.push_toast(format!("Disliked: {id}"), false),
                    Err(e) => app.push_toast(format!("Error disliking: {e}"), true),
                }
            }
        }
        KeyCode::Char('b') => {
            if let Some(detail) = &app.detail {
                let id = detail.paper.arxiv_id.clone();
                let month = chrono::Local::now().format("%Y%m").to_string();
                match app.db.toggle_bookmark(&id, &month) {
                    Ok(added) => {
                        if added {
                            app.daily.bookmarked.insert(id.clone());
                            app.push_toast(format!("Bookmarked: {id}"), false);
                        } else {
                            app.daily.bookmarked.remove(&id);
                            app.push_toast(format!("Bookmark removed: {id}"), false);
                        }
                    }
                    Err(e) => app.push_toast(format!("Error bookmarking: {e}"), true),
                }
            }
        }
        _ => {}
    }
}

// =============================================================================
// Daily
// =============================================================================

pub fn handle_daily_key(app: &mut App, key: KeyCode) {
    let total = app.daily.author_papers.len() + app.daily.scored_papers.len();
    if total == 0 && !matches!(key, KeyCode::Char('f') | KeyCode::Char('F') | KeyCode::Char('[') | KeyCode::Char(']') | KeyCode::Char('-') | KeyCode::Char('=')) {
        return;
    }

    match key {
        // Toggle focus between papers table and detail panel
        KeyCode::Tab => {
            app.daily.focus_detail = !app.daily.focus_detail;
        }
        // Navigate / scroll — behaviour depends on which panel has focus
        KeyCode::Down | KeyCode::Char('K') => {
            if app.daily.focus_detail {
                app.daily.detail_scroll = app.daily.detail_scroll.saturating_add(1);
            } else if total > 0 && app.daily.selected + 1 < total {
                app.daily.selected += 1;
                app.daily.detail_scroll = 0;
            }
        }
        KeyCode::Up | KeyCode::Char('k') => {
            if app.daily.focus_detail {
                app.daily.detail_scroll = app.daily.detail_scroll.saturating_sub(1);
            } else if app.daily.selected > 0 {
                app.daily.selected -= 1;
                app.daily.detail_scroll = 0;
            }
        }
        // Like
        KeyCode::Char('l') => {
            if let Some(paper) = app.selected_daily_paper() {
                let id = paper.arxiv_id.clone();
                match app.db.mark_interesting(&id) {
                    Ok(_) => {
                        let _ = app.event_tx.send(crate::app::AppEvent::Toast {
                            message: format!("Liked: {}", &id),
                            is_error: false,
                        });
                    }
                    Err(e) => {
                        let _ = app.event_tx.send(crate::app::AppEvent::Toast {
                            message: format!("Error liking paper: {e}"),
                            is_error: true,
                        });
                    }
                }
            }
        }
        // Dislike
        KeyCode::Char('d') => {
            if let Some(paper) = app.selected_daily_paper() {
                let id = paper.arxiv_id.clone();
                match app.db.mark_not_interesting(&id) {
                    Ok(_) => {
                        let _ = app.event_tx.send(crate::app::AppEvent::Toast {
                            message: format!("Disliked: {}", &id),
                            is_error: false,
                        });
                    }
                    Err(e) => {
                        let _ = app.event_tx.send(crate::app::AppEvent::Toast {
                            message: format!("Error disliking paper: {e}"),
                            is_error: true,
                        });
                    }
                }
            }
        }
        // Bookmark
        KeyCode::Char('b') => {
            if let Some(paper) = app.selected_daily_paper() {
                let id = paper.arxiv_id.clone();
                let month = chrono::Local::now().format("%Y%m").to_string();
                match app.db.toggle_bookmark(&id, &month) {
                    Ok(added) => {
                        if added {
                            app.daily.bookmarked.insert(id.clone());
                            let _ = app.event_tx.send(crate::app::AppEvent::Toast {
                                message: format!("Bookmarked: {}", &id),
                                is_error: false,
                            });
                        } else {
                            app.daily.bookmarked.remove(&id);
                            let _ = app.event_tx.send(crate::app::AppEvent::Toast {
                                message: format!("Bookmark removed: {}", &id),
                                is_error: false,
                            });
                        }
                    }
                    Err(e) => {
                        let _ = app.event_tx.send(crate::app::AppEvent::Toast {
                            message: format!("Error bookmarking: {e}"),
                            is_error: true,
                        });
                    }
                }
            }
        }
        // Cycle days: [ = prev, ] = next (1→3→7→14→30)
        KeyCode::Char('[') => {
            let options = [1, 3, 7, 14, 30];
            let pos = options.iter().position(|&d| d == app.daily.days).unwrap_or(2);
            app.daily.days = options[if pos == 0 { options.len() - 1 } else { pos - 1 }];
        }
        KeyCode::Char(']') => {
            let options = [1, 3, 7, 14, 30];
            let pos = options.iter().position(|&d| d == app.daily.days).unwrap_or(2);
            app.daily.days = options[(pos + 1) % options.len()];
        }
        // Cycle limit: - = prev, = = next (10→20→50→100)
        KeyCode::Char('-') => {
            let options = [10, 20, 50, 100];
            let pos = options.iter().position(|&n| n == app.daily.limit).unwrap_or(1);
            app.daily.limit = options[if pos == 0 { options.len() - 1 } else { pos - 1 }];
        }
        KeyCode::Char('=') => {
            let options = [10, 20, 50, 100];
            let pos = options.iter().position(|&n| n == app.daily.limit).unwrap_or(1);
            app.daily.limit = options[(pos + 1) % options.len()];
        }
        // Fetch papers
        KeyCode::Char('f') | KeyCode::Char('F') => {
            if !app.daily.loading {
                app.daily.loading = true;
                crate::commands::fetch::fetch_daily(
                    app.event_tx.clone(),
                    app.daily.days,
                    app.daily.limit,
                );
            }
        }
        // Open detail overlay
        KeyCode::Enter => {
            if let Some(paper) = app.selected_daily_paper().cloned() {
                app.open_paper_detail(paper);
            }
        }
        _ => {}
    }
}

// =============================================================================
// Search (stub)
// =============================================================================

pub fn handle_search_key(app: &mut App, key: KeyCode) {
    if app.search.editing {
        match key {
            KeyCode::Enter => {
                app.search.editing = false;
                app.search.loading = true;
                let query = app.search.query.clone();
                crate::commands::fetch::search_papers(app.event_tx.clone(), &query);
            }
            KeyCode::Esc => {
                app.search.editing = false;
            }
            KeyCode::Backspace => {
                app.search.query.pop();
            }
            KeyCode::Char(c) => {
                app.search.query.push(c);
            }
            _ => {}
        }
        return;
    }

    let total = app.search.results.len();
    match key {
        KeyCode::Down | KeyCode::Char('K') => {
            if total > 0 && app.search.selected + 1 < total {
                app.search.selected += 1;
            }
        }
        KeyCode::Up | KeyCode::Char('k') => {
            if app.search.selected > 0 {
                app.search.selected -= 1;
            }
        }
        KeyCode::Char('/') => {
            app.search.editing = true;
        }
        KeyCode::Char('l') => {
            if let Some(paper) = app.search.results.get(app.search.selected) {
                let id = paper.arxiv_id.clone();
                match app.db.mark_interesting(&id) {
                    Ok(_) => {
                        let _ = app.event_tx.send(crate::app::AppEvent::Toast {
                            message: format!("Liked: {id}"),
                            is_error: false,
                        });
                    }
                    Err(e) => {
                        let _ = app.event_tx.send(crate::app::AppEvent::Toast {
                            message: format!("Error liking: {e}"),
                            is_error: true,
                        });
                    }
                }
            }
        }
        KeyCode::Char('d') => {
            if let Some(paper) = app.search.results.get(app.search.selected) {
                let id = paper.arxiv_id.clone();
                match app.db.mark_not_interesting(&id) {
                    Ok(_) => {
                        let _ = app.event_tx.send(crate::app::AppEvent::Toast {
                            message: format!("Disliked: {id}"),
                            is_error: false,
                        });
                    }
                    Err(e) => {
                        let _ = app.event_tx.send(crate::app::AppEvent::Toast {
                            message: format!("Error disliking: {e}"),
                            is_error: true,
                        });
                    }
                }
            }
        }
        // Open detail overlay
        KeyCode::Enter => {
            if let Some(paper) = app.search.results.get(app.search.selected).cloned() {
                app.open_paper_detail(paper);
            }
        }
        _ => {}
    }
}

// =============================================================================
// Lists
// =============================================================================

pub fn handle_lists_key(app: &mut App, key: KeyCode) {
    match key {
        KeyCode::Tab => {
            app.lists.focus_left = !app.lists.focus_left;
        }
        KeyCode::Char('r') | KeyCode::Char('R') => {
            app.lists.items = app
                .db
                .get_top_level_lists()
                .unwrap_or_default()
                .into_iter()
                .map(|l| {
                    let count = app.db.get_list_paper_count(l.id).unwrap_or(0);
                    (l, count)
                })
                .collect();
            load_list_papers_pub(app);
        }
        KeyCode::Down | KeyCode::Char('K') => {
            if app.lists.focus_left {
                let max = app.lists.items.len().saturating_sub(1);
                if app.lists.selected_list < max {
                    app.lists.selected_list += 1;
                    load_list_papers_pub(app);
                }
            } else {
                let max = app.lists.papers.len().saturating_sub(1);
                if app.lists.selected_paper < max {
                    app.lists.selected_paper += 1;
                }
            }
        }
        KeyCode::Up | KeyCode::Char('k') => {
            if app.lists.focus_left {
                if app.lists.selected_list > 0 {
                    app.lists.selected_list -= 1;
                    load_list_papers_pub(app);
                }
            } else if app.lists.selected_paper > 0 {
                app.lists.selected_paper -= 1;
            }
        }
        KeyCode::Enter => {
            if app.lists.focus_left {
                // Already loaded on navigation; move focus to papers panel
                app.lists.focus_left = false;
            } else {
                // Open paper detail overlay
                if let Some(p) = app.lists.papers.get(app.lists.selected_paper).cloned() {
                    let detail_opt = app.lists.paper_details.get(&p.arxiv_id).cloned();
                    let scored = if let Some(d) = detail_opt {
                        crate::db::models::ScoredPaper {
                            arxiv_id: d.arxiv_id,
                            title: d.title,
                            abstract_text: d.abstract_text,
                            authors: d.authors,
                            categories: d.categories,
                            published: d.published,
                            score: 0.0,
                        }
                    } else {
                        crate::db::models::ScoredPaper {
                            arxiv_id: p.arxiv_id.clone(),
                            title: p.arxiv_id.clone(),
                            abstract_text: String::new(),
                            authors: vec![],
                            categories: vec![],
                            published: p.added_at.get(..10).unwrap_or(&p.added_at).to_string(),
                            score: 0.0,
                        }
                    };
                    app.open_paper_detail(scored);
                }
            }
        }
        KeyCode::Delete => {
            if app.lists.focus_left {
                if let Some((list, _)) = app.lists.items.get(app.lists.selected_list) {
                    let list_id = list.id;
                    let name = list.name.clone();
                    match app.db.delete_list(list_id) {
                        Ok(true) => {
                            // Reload lists
                            app.lists.items = app
                                .db
                                .get_top_level_lists()
                                .unwrap_or_default()
                                .into_iter()
                                .map(|l| {
                                    let count = app.db.get_list_paper_count(l.id).unwrap_or(0);
                                    (l, count)
                                })
                                .collect();
                            app.lists.selected_list =
                                app.lists.selected_list.min(app.lists.items.len().saturating_sub(1));
                            app.lists.papers.clear();
                            app.lists.paper_details.clear();
                            let _ = app.event_tx.send(crate::app::AppEvent::Toast {
                                message: format!("Deleted list: {name}"),
                                is_error: false,
                            });
                        }
                        Ok(false) => {
                            let _ = app.event_tx.send(crate::app::AppEvent::Toast {
                                message: "Cannot delete system list".to_string(),
                                is_error: true,
                            });
                        }
                        Err(e) => {
                            let _ = app.event_tx.send(crate::app::AppEvent::Toast {
                                message: format!("Error: {e}"),
                                is_error: true,
                            });
                        }
                    }
                }
            }
        }
        _ => {}
    }
}

/// Load papers for the currently selected list and cache their details.
pub fn load_list_papers_pub(app: &mut App) {
    if let Some((list, _)) = app.lists.items.get(app.lists.selected_list) {
        let list_id = list.id;
        let papers = app.db.get_list_papers(list_id).unwrap_or_default();
        for p in &papers {
            if !app.lists.paper_details.contains_key(&p.arxiv_id) {
                if let Ok(Some(detail)) = app.db.get_paper(&p.arxiv_id) {
                    app.lists.paper_details.insert(p.arxiv_id.clone(), detail);
                }
            }
        }
        app.lists.papers = papers;
        app.lists.selected_paper = 0;
    }
}

#[allow(dead_code)]
fn truncate_for_toast(s: &str, max: usize) -> &str {
    if s.len() <= max {
        s
    } else {
        &s[..max]
    }
}

// =============================================================================
// Notes
// =============================================================================

pub fn handle_notes_key(app: &mut App, key: KeyCode) {
    match key {
        KeyCode::Down | KeyCode::Char('K') => {
            let max = app.notes.notes.len().saturating_sub(1);
            if app.notes.selected < max {
                app.notes.selected += 1;
            }
        }
        KeyCode::Up | KeyCode::Char('k') => {
            if app.notes.selected > 0 {
                app.notes.selected -= 1;
            }
        }
        KeyCode::Delete => {
            if let Some(note) = app.notes.notes.get(app.notes.selected) {
                let note_id = note.id;
                let arxiv_id = note.arxiv_id.clone();
                match app.db.delete_note(note_id) {
                    Ok(true) => {
                        app.notes.notes = app.db.get_notes().unwrap_or_default();
                        app.notes.selected =
                            app.notes.selected.min(app.notes.notes.len().saturating_sub(1));
                        let _ = app.event_tx.send(crate::app::AppEvent::Toast {
                            message: format!("Note deleted: {arxiv_id}"),
                            is_error: false,
                        });
                    }
                    Ok(false) => {}
                    Err(e) => {
                        let _ = app.event_tx.send(crate::app::AppEvent::Toast {
                            message: format!("Error deleting note: {e}"),
                            is_error: true,
                        });
                    }
                }
            }
        }
        KeyCode::Char('r') | KeyCode::Char('R') => {
            app.notes.notes = app.db.get_notes().unwrap_or_default();
            app.notes.selected = app.notes.selected.min(app.notes.notes.len().saturating_sub(1));
        }
        _ => {}
    }
}

// =============================================================================
// Prefs
// =============================================================================

pub fn handle_prefs_key(app: &mut App, key: KeyCode) {
    match key {
        KeyCode::Tab => {
            // Auto-normalize weights when leaving the weights section
            if app.prefs.focus_section == 3 {
                let total: i64 = app.prefs.weights.iter().sum();
                if total != 100 && total > 0 {
                    let mut result = [0i64; 4];
                    let mut distributed = 0i64;
                    for i in 0..4 {
                        result[i] = (app.prefs.weights[i] * 100 + total / 2) / total;
                        distributed += result[i];
                    }
                    // Fix rounding
                    let diff = 100 - distributed;
                    if diff != 0 {
                        let max_idx = result.iter().enumerate().max_by_key(|(_, v)| **v).map(|(i, _)| i).unwrap_or(0);
                        result[max_idx] += diff;
                    }
                    app.prefs.weights = result;
                    let _ = app.db.set_weights(result);
                    app.push_toast("Weights normalized to 100%", false);
                } else if total == 0 {
                    app.prefs.weights = [60, 20, 15, 5];
                    let _ = app.db.set_weights(app.prefs.weights);
                    app.push_toast("Weights reset to defaults", false);
                }
            }
            app.prefs.focus_section = (app.prefs.focus_section + 1) % 5;
        }
        // Reset weights to default
        KeyCode::Char('D') => {
            if app.prefs.focus_section == 3 {
                app.prefs.weights = [60, 20, 15, 5];
                let _ = app.db.set_weights(app.prefs.weights);
                app.push_toast("Weights reset to defaults", false);
            }
        }
        KeyCode::Down | KeyCode::Char('K') => {
            let sec = app.prefs.focus_section;
            let max = match sec {
                0 => app.prefs.categories.len(),
                1 => app.prefs.keywords.len(),
                2 => app.prefs.authors.len(),
                3 => 4,
                4 => 2, // provider (0) and language (1)
                _ => 1,
            };
            if max > 0 && app.prefs.section_selected[sec] + 1 < max {
                app.prefs.section_selected[sec] += 1;
                if sec == 3 {
                    app.prefs.selected = app.prefs.section_selected[3];
                }
            }
        }
        KeyCode::Up | KeyCode::Char('k') => {
            let sec = app.prefs.focus_section;
            if app.prefs.section_selected[sec] > 0 {
                app.prefs.section_selected[sec] -= 1;
                if sec == 3 {
                    app.prefs.selected = app.prefs.section_selected[3];
                }
            }
        }
        KeyCode::Left | KeyCode::Char('h') => {
            match app.prefs.focus_section {
                0 => {
                    // Decrease category priority
                    let sel = app.prefs.section_selected[0];
                    if let Some(cat) = app.prefs.categories.get(sel) {
                        let new_pri = (cat.priority - 1).max(1);
                        if new_pri != cat.priority {
                            let cat_name = cat.category.clone();
                            let _ = app.db.set_category_priority(&cat_name, new_pri);
                            app.prefs.categories = app.db.get_categories().unwrap_or_default();
                        }
                    }
                }
                1 => {
                    // Decrease keyword weight (1-5 stars)
                    let sel = app.prefs.section_selected[1];
                    if let Some(kw) = app.prefs.keywords.get(sel) {
                        let new_w = (kw.weight - 1).max(1);
                        if new_w != kw.weight {
                            let kw_name = kw.keyword.clone();
                            let _ = app.db.set_keyword_weight(&kw_name, new_w);
                            app.prefs.keywords = app.db.get_keywords().unwrap_or_default();
                        }
                    }
                }
                3 => {
                    // Decrease weight by 1 (no normalize)
                    let idx = app.prefs.selected;
                    let new_val = (app.prefs.weights[idx] - 1).max(0);
                    if new_val != app.prefs.weights[idx] {
                        app.prefs.weights[idx] = new_val;
                        let _ = app.db.set_weights(app.prefs.weights);
                    }
                }
                4 => {
                    cycle_config_option(app, false);
                }
                _ => {}
            }
        }
        KeyCode::Right | KeyCode::Char('l') => {
            match app.prefs.focus_section {
                0 => {
                    // Increase category priority
                    let sel = app.prefs.section_selected[0];
                    if let Some(cat) = app.prefs.categories.get(sel) {
                        let new_pri = cat.priority + 1;
                        let cat_name = cat.category.clone();
                        let _ = app.db.set_category_priority(&cat_name, new_pri);
                        app.prefs.categories = app.db.get_categories().unwrap_or_default();
                    }
                }
                1 => {
                    // Increase keyword weight (1-5 stars)
                    let sel = app.prefs.section_selected[1];
                    if let Some(kw) = app.prefs.keywords.get(sel) {
                        let new_w = (kw.weight + 1).min(5);
                        if new_w != kw.weight {
                            let kw_name = kw.keyword.clone();
                            let _ = app.db.set_keyword_weight(&kw_name, new_w);
                            app.prefs.keywords = app.db.get_keywords().unwrap_or_default();
                        }
                    }
                }
                3 => {
                    // Increase weight by 1 (no normalize)
                    let idx = app.prefs.selected;
                    let new_val = (app.prefs.weights[idx] + 1).min(100);
                    if new_val != app.prefs.weights[idx] {
                        app.prefs.weights[idx] = new_val;
                        let _ = app.db.set_weights(app.prefs.weights);
                    }
                }
                4 => {
                    cycle_config_option(app, true);
                }
                _ => {}
            }
        }
        KeyCode::Char('a') => {
            match app.prefs.focus_section {
                0 => {
                    let filtered = categories::filter_categories("");
                    app.overlay = Some(crate::app::OverlayMode::CategoryPicker {
                        search: String::new(),
                        filtered,
                        selected: 0,
                    });
                }
                1 => {
                    app.overlay = Some(crate::app::OverlayMode::KeywordInput {
                        text: String::new(),
                        weight: 3,
                    });
                }
                2 => {
                    app.overlay = Some(crate::app::OverlayMode::AuthorInput {
                        text: String::new(),
                    });
                }
                _ => {}
            }
        }
        KeyCode::Delete => {
            let sec = app.prefs.focus_section;
            match sec {
                0 => {
                    let sel = app.prefs.section_selected[0];
                    if let Some(cat) = app.prefs.categories.get(sel) {
                        let cat_name = cat.category.clone();
                        let _ = app.db.remove_category(&cat_name);
                        app.prefs.categories = app.db.get_categories().unwrap_or_default();
                        app.prefs.section_selected[0] = sel
                            .min(app.prefs.categories.len().saturating_sub(1));
                    }
                }
                1 => {
                    let sel = app.prefs.section_selected[1];
                    if let Some(kw) = app.prefs.keywords.get(sel) {
                        let kw_name = kw.keyword.clone();
                        let _ = app.db.remove_keyword(&kw_name);
                        app.prefs.keywords = app.db.get_keywords().unwrap_or_default();
                        app.prefs.section_selected[1] = sel
                            .min(app.prefs.keywords.len().saturating_sub(1));
                    }
                }
                2 => {
                    let sel = app.prefs.section_selected[2];
                    if let Some(auth) = app.prefs.authors.get(sel) {
                        let auth_name = auth.name.clone();
                        let _ = app.db.remove_author(&auth_name);
                        app.prefs.authors = app.db.get_authors().unwrap_or_default();
                        app.prefs.section_selected[2] = sel
                            .min(app.prefs.authors.len().saturating_sub(1));
                    }
                }
                _ => {}
            }
        }
        KeyCode::Char('r') | KeyCode::Char('R') => {
            app.prefs.categories = app.db.get_categories().unwrap_or_default();
            app.prefs.keywords = app.db.get_keywords().unwrap_or_default();
            app.prefs.authors = app.db.get_authors().unwrap_or_default();
            app.prefs.weights = app.db.get_weights().unwrap_or([60, 20, 15, 5]);
            app.prefs.provider = app
                .db
                .get_setting("ai_provider", "gemini")
                .unwrap_or_else(|_| "gemini".to_string());
            app.prefs.language = app
                .db
                .get_setting("language", "en")
                .unwrap_or_else(|_| "en".to_string());
        }
        _ => {}
    }
}

/// Cycle through config options for the currently selected config item (section 4).
/// `forward=true` goes to the next option, `forward=false` goes to the previous.
fn cycle_config_option(app: &mut App, forward: bool) {
    let item = app.prefs.section_selected[4]; // 0=provider, 1=language
    match item {
        0 => {
            let providers = ["gemini", "claude", "ollama", "openai", "opencode", "custom"];
            let current = providers.iter().position(|&p| p == app.prefs.provider).unwrap_or(0);
            let next = if forward {
                (current + 1) % providers.len()
            } else {
                if current == 0 { providers.len() - 1 } else { current - 1 }
            };
            app.prefs.provider = providers[next].to_string();
            let _ = app.db.set_setting("ai_provider", providers[next]);
            app.push_toast(format!("Provider: {}", providers[next]), false);
        }
        1 => {
            let langs = ["en", "ko"];
            let current = langs.iter().position(|&l| l == app.prefs.language).unwrap_or(0);
            let next = if forward {
                (current + 1) % langs.len()
            } else {
                if current == 0 { langs.len() - 1 } else { current - 1 }
            };
            app.prefs.language = langs[next].to_string();
            let _ = app.db.set_setting("language", langs[next]);
            app.push_toast(format!("Language: {}", langs[next]), false);
        }
        _ => {}
    }
}

