use crossterm::event::KeyCode;

use crate::app::{App, Tab};

// =============================================================================
// Global key handler
// =============================================================================

/// Returns true if the app should quit.
pub fn handle_key(app: &mut App, key: KeyCode) -> bool {
    // Paper detail overlay takes priority over all other handlers
    if app.detail.is_some() {
        handle_detail_key(app, key);
        return false;
    }

    match key {
        // Quit
        KeyCode::Char('q') | KeyCode::Char('Q') => {
            app.running = false;
            return true;
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
            load_list_papers(app);
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
        KeyCode::Down | KeyCode::Char('j') => {
            if let Some(detail) = &mut app.detail {
                detail.scroll = detail.scroll.saturating_add(1);
            }
        }
        KeyCode::Char('s') => {
            if let Some(detail) = &app.detail {
                let arxiv_id = detail.paper.arxiv_id.clone();
                let job_id = format!("sum-{}", &arxiv_id);
                let tx = app.event_tx.clone();
                app.push_toast("Summarizing...", false);
                crate::commands::ai::run_summarize(tx, job_id, arxiv_id);
            }
        }
        KeyCode::Char('t') => {
            if let Some(detail) = &app.detail {
                let arxiv_id = detail.paper.arxiv_id.clone();
                let job_id = format!("trans-{}", &arxiv_id);
                let tx = app.event_tx.clone();
                app.push_toast("Translating...", false);
                crate::commands::ai::run_translate(tx, job_id, arxiv_id);
            }
        }
        KeyCode::Char('w') => {
            if let Some(detail) = &app.detail {
                let arxiv_id = detail.paper.arxiv_id.clone();
                let job_id = format!("review-{}", &arxiv_id);
                let tx = app.event_tx.clone();
                app.push_toast("Reviewing...", false);
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
    if total == 0 && !matches!(key, KeyCode::Char('r') | KeyCode::Char('R') | KeyCode::Char('[') | KeyCode::Char(']') | KeyCode::Char('-') | KeyCode::Char('=')) {
        return;
    }

    match key {
        // Navigate down
        KeyCode::Down | KeyCode::Char('j') => {
            if total > 0 && app.daily.selected + 1 < total {
                app.daily.selected += 1;
            }
        }
        // Navigate up
        KeyCode::Up | KeyCode::Char('k') => {
            if app.daily.selected > 0 {
                app.daily.selected -= 1;
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
        // Refresh / fetch
        KeyCode::Char('r') | KeyCode::Char('R') => {
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
        KeyCode::Down | KeyCode::Char('j') => {
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
            load_list_papers(app);
        }
        KeyCode::Down | KeyCode::Char('j') => {
            if app.lists.focus_left {
                let max = app.lists.items.len().saturating_sub(1);
                if app.lists.selected_list < max {
                    app.lists.selected_list += 1;
                    load_list_papers(app);
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
                    load_list_papers(app);
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
fn load_list_papers(app: &mut App) {
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
        KeyCode::Down | KeyCode::Char('j') => {
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
            app.prefs.focus_section = (app.prefs.focus_section + 1) % 4;
        }
        KeyCode::Down | KeyCode::Char('j') => {
            let sec = app.prefs.focus_section;
            let max = match sec {
                0 => app.prefs.categories.len(),
                1 => app.prefs.keywords.len(),
                2 => app.prefs.authors.len(),
                3 => 4,
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
            if app.prefs.focus_section == 3 {
                let idx = app.prefs.selected;
                let new_weights =
                    adjust_weights(idx, app.prefs.weights[idx] - 5, app.prefs.weights);
                app.prefs.weights = new_weights;
                let _ = app.db.set_weights(new_weights);
            }
        }
        KeyCode::Right | KeyCode::Char('l') => {
            if app.prefs.focus_section == 3 {
                let idx = app.prefs.selected;
                let new_weights =
                    adjust_weights(idx, app.prefs.weights[idx] + 5, app.prefs.weights);
                app.prefs.weights = new_weights;
                let _ = app.db.set_weights(new_weights);
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

// =============================================================================
// Weight adjustment helper
// =============================================================================

/// Adjust weights so that changing `weights[changed]` to `new_value` keeps
/// the total at 100. The remaining budget is distributed proportionally among
/// the other three weights. All values are clamped to [0, 100].
pub fn adjust_weights(changed: usize, new_value: i64, weights: [i64; 4]) -> [i64; 4] {
    let clamped = new_value.max(0).min(100);
    let remaining = 100 - clamped;

    // Sum of the other weights
    let other_sum: i64 = weights
        .iter()
        .enumerate()
        .filter(|(i, _)| *i != changed)
        .map(|(_, &w)| w)
        .sum();

    let mut result = weights;
    result[changed] = clamped;

    if other_sum == 0 {
        // Distribute evenly
        let per = remaining / 3;
        let mut leftover = remaining - per * 3;
        for i in 0..4 {
            if i != changed {
                result[i] = per + if leftover > 0 { leftover -= 1; 1 } else { 0 };
            }
        }
    } else {
        // Distribute proportionally
        let mut distributed = 0i64;
        let mut last_idx = None;
        for i in 0..4 {
            if i != changed {
                let share = (weights[i] as f64 / other_sum as f64 * remaining as f64).round() as i64;
                result[i] = share;
                distributed += share;
                last_idx = Some(i);
            }
        }
        // Fix rounding error on last non-changed index
        if let Some(last) = last_idx {
            result[last] += remaining - distributed;
            result[last] = result[last].max(0);
        }
    }

    result
}
