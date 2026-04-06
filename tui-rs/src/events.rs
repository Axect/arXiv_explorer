use crossterm::event::KeyCode;

use crate::app::{App, Tab};

// =============================================================================
// Global key handler
// =============================================================================

/// Returns true if the app should quit.
pub fn handle_key(app: &mut App, key: KeyCode) -> bool {
    match key {
        // Quit
        KeyCode::Char('q') | KeyCode::Char('Q') => {
            app.running = false;
            return true;
        }
        // Tab switch: 1-5
        KeyCode::Char('1') => app.active_tab = Tab::Daily,
        KeyCode::Char('2') => app.active_tab = Tab::Search,
        KeyCode::Char('3') => app.active_tab = Tab::Lists,
        KeyCode::Char('4') => app.active_tab = Tab::Notes,
        KeyCode::Char('5') => app.active_tab = Tab::Prefs,
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
// Daily
// =============================================================================

pub fn handle_daily_key(app: &mut App, key: KeyCode) {
    let total = app.daily.author_papers.len() + app.daily.scored_papers.len();
    if total == 0 && !matches!(key, KeyCode::Char('r') | KeyCode::Char('R')) {
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
        // Refresh / fetch
        KeyCode::Char('r') | KeyCode::Char('R') => {
            if !app.daily.loading {
                app.daily.loading = true;
                // Placeholder — Task 4 will wire up the actual fetch command
                let _ = app.event_tx.send(crate::app::AppEvent::Toast {
                    message: "Fetching papers… (not implemented yet)".to_string(),
                    is_error: false,
                });
                app.daily.loading = false;
            }
        }
        _ => {}
    }
}

// =============================================================================
// Search (stub)
// =============================================================================

pub fn handle_search_key(app: &mut App, key: KeyCode) {
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
        _ => {}
    }
}

// =============================================================================
// Lists (stub)
// =============================================================================

pub fn handle_lists_key(app: &mut App, key: KeyCode) {
    match key {
        KeyCode::Down | KeyCode::Char('j') => {
            app.lists.selected = app.lists.selected.saturating_add(1);
        }
        KeyCode::Up | KeyCode::Char('k') => {
            app.lists.selected = app.lists.selected.saturating_sub(1);
        }
        _ => {}
    }
}

// =============================================================================
// Notes (stub)
// =============================================================================

pub fn handle_notes_key(app: &mut App, key: KeyCode) {
    match key {
        KeyCode::Down | KeyCode::Char('j') => {
            app.notes.selected = app.notes.selected.saturating_add(1);
        }
        KeyCode::Up | KeyCode::Char('k') => {
            app.notes.selected = app.notes.selected.saturating_sub(1);
        }
        _ => {}
    }
}

// =============================================================================
// Prefs (stub)
// =============================================================================

pub fn handle_prefs_key(app: &mut App, key: KeyCode) {
    match key {
        KeyCode::Down | KeyCode::Char('j') => {
            if app.prefs.selected + 1 < 4 {
                app.prefs.selected += 1;
            }
        }
        KeyCode::Up | KeyCode::Char('k') => {
            if app.prefs.selected > 0 {
                app.prefs.selected -= 1;
            }
        }
        KeyCode::Left | KeyCode::Char('h') => {
            let idx = app.prefs.selected;
            let new_weights = adjust_weights(idx, app.prefs.weights[idx] - 5, app.prefs.weights);
            app.prefs.weights = new_weights;
            let _ = app.db.set_weights(new_weights);
        }
        KeyCode::Right | KeyCode::Char('l') => {
            let idx = app.prefs.selected;
            let new_weights = adjust_weights(idx, app.prefs.weights[idx] + 5, app.prefs.weights);
            app.prefs.weights = new_weights;
            let _ = app.db.set_weights(new_weights);
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
