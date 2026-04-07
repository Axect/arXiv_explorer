use std::io;
use std::time::Duration;

use crossterm::{
    event::{self, Event, EnableMouseCapture, DisableMouseCapture, KeyEventKind},
    execute,
    terminal::{disable_raw_mode, enable_raw_mode, EnterAlternateScreen, LeaveAlternateScreen},
};
use ratatui::{
    prelude::*,
    widgets::{Block, Borders, Cell, Clear, Paragraph, Row, Table, TableState, Wrap},
};

mod app;
mod commands;
mod db;
mod categories;
mod events;

use app::{App, ConfirmAction, Tab};

// =============================================================================
// Catppuccin Mocha palette
// =============================================================================
const BG: Color = Color::Rgb(30, 30, 46);
const SURFACE: Color = Color::Rgb(49, 50, 68);
const TEXT: Color = Color::Rgb(205, 214, 244);
const TEXT_DIM: Color = Color::Rgb(108, 112, 134);
const ACCENT: Color = Color::Rgb(137, 180, 250);
const AUTHOR_HL: Color = Color::Rgb(249, 226, 175);
const BOOKMARK_HL: Color = Color::Rgb(166, 227, 161);
const ERROR_COLOR: Color = Color::Rgb(243, 139, 168);
const SUCCESS_COLOR: Color = Color::Rgb(166, 227, 161);

// =============================================================================
// Entry point
// =============================================================================

#[tokio::main]
async fn main() -> io::Result<()> {
    // Setup terminal
    enable_raw_mode()?;
    let mut stdout = io::stdout();
    execute!(stdout, EnterAlternateScreen, EnableMouseCapture)?;
    let backend = CrosstermBackend::new(stdout);
    let mut terminal = Terminal::new(backend)?;

    // Build app
    let db_path = db::Database::default_path();
    let app = App::new(db_path).unwrap_or_else(|e| {
        eprintln!("Failed to open database: {e}");
        std::process::exit(1);
    });

    // Run
    let res = run_app(&mut terminal, app).await;

    // Restore terminal
    disable_raw_mode()?;
    execute!(terminal.backend_mut(), LeaveAlternateScreen, DisableMouseCapture)?;

    if let Err(e) = res {
        eprintln!("Error: {e}");
    }
    Ok(())
}

// =============================================================================
// Main event loop
// =============================================================================

async fn run_app<B: Backend>(terminal: &mut Terminal<B>, mut app: App) -> io::Result<()> {
    loop {
        // Draw frame
        terminal.draw(|f| render(f, &mut app))?;

        // Tick toasts every 200 ms
        let timeout = Duration::from_millis(200);

        tokio::select! {
            // Crossterm input events (blocking poll in a spawn_blocking)
            has_event = tokio::task::spawn_blocking(move || event::poll(timeout)) => {
                if let Ok(Ok(true)) = has_event {
                    match event::read() {
                        Ok(Event::Key(key)) => {
                            if key.kind == KeyEventKind::Press {
                                if events::handle_key(&mut app, key.code) {
                                    return Ok(());
                                }
                            }
                        }
                        Ok(Event::Mouse(mouse)) => {
                            events::handle_mouse(&mut app, mouse);
                        }
                        _ => {}
                    }
                }
            }
            // Internal app events (async task results)
            maybe_event = app.event_rx.recv() => {
                if let Some(ev) = maybe_event {
                    app.handle_app_event(ev);
                }
            }
        }

        app.tick();

        if !app.running {
            return Ok(());
        }
    }
}

// =============================================================================
// Top-level render
// =============================================================================

fn render(f: &mut Frame, app: &mut App) {
    let area = f.area();

    // Clear background
    f.render_widget(Block::default().style(Style::default().bg(BG)), area);

    // Layout: tab bar (1) | content (fill) | key hints (1)
    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(1),
            Constraint::Min(0),
            Constraint::Length(1),
        ])
        .split(area);

    render_tab_bar(f, app, chunks[0]);
    render_tab_content(f, app, chunks[1]);
    render_key_hints(f, app, chunks[2]);

    // Paper detail overlay on top of tab content
    if app.detail.is_some() {
        render_paper_detail(f, app);
    }

    // Jobs overlay on top of everything except toasts
    if app.show_jobs {
        render_jobs_panel(f, app);
    }

    // Input overlay (category picker / keyword input)
    if let Some(ref overlay) = app.overlay {
        match overlay {
            app::OverlayMode::CategoryPicker { .. } => render_category_picker(f, app),
            app::OverlayMode::KeywordInput { .. } => render_keyword_input(f, app),
            app::OverlayMode::AuthorInput { .. } => render_author_input(f, app),
            app::OverlayMode::PresetPicker { .. }
            | app::OverlayMode::ProviderNameInput { .. }
            | app::OverlayMode::CommandTemplateInput { .. } => {}
        }
    }

    // Confirmation dialog on top of everything except toasts
    if app.confirm_action.is_some() {
        render_confirm_dialog(f, app);
    }

    render_toasts(f, app, area);
}

// =============================================================================
// Tab bar
// =============================================================================

fn render_tab_bar(f: &mut Frame, app: &App, area: Rect) {
    let mut spans: Vec<Span> = Vec::new();
    for (i, tab) in Tab::all().iter().enumerate() {
        if i > 0 {
            spans.push(Span::styled("  ", Style::default().bg(SURFACE)));
        }
        let label = format!("[{}] {}", tab.key(), tab.label());
        let style = if *tab == app.active_tab {
            Style::default().fg(BG).bg(ACCENT).bold()
        } else {
            Style::default().fg(TEXT_DIM).bg(SURFACE)
        };
        spans.push(Span::styled(label, style));
    }

    // Jobs indicator on the right
    let running = app.jobs.iter().filter(|j| j.status == crate::app::JobStatus::Running).count();
    if running > 0 {
        spans.push(Span::styled(
            format!("  ⟳ {} job{}", running, if running == 1 { "" } else { "s" }),
            Style::default().fg(AUTHOR_HL).bg(SURFACE).bold(),
        ));
    } else if !app.jobs.is_empty() {
        spans.push(Span::styled(
            "  ✓ jobs done",
            Style::default().fg(SUCCESS_COLOR).bg(SURFACE),
        ));
    }

    let line = Line::from(spans);
    let paragraph = Paragraph::new(line).style(Style::default().bg(SURFACE));
    f.render_widget(paragraph, area);
}

// =============================================================================
// Tab content dispatcher
// =============================================================================

fn render_tab_content(f: &mut Frame, app: &mut App, area: Rect) {
    match app.active_tab {
        Tab::Daily => render_daily(f, app, area),
        Tab::Search => render_search(f, app, area),
        Tab::Lists => render_lists(f, app, area),
        Tab::Notes => render_notes(f, app, area),
        Tab::Prefs => render_prefs(f, app, area),
    }
}

// =============================================================================
// Key hints bar
// =============================================================================

fn render_key_hints(f: &mut Frame, app: &App, area: Rect) {
    let hints = match app.active_tab {
        Tab::Daily => " [/] Days  -/= Limit  [f]etch  [l]ike  [d]islike  [b]ookmark  [Tab] focus  [j]obs  [q]uit",
        Tab::Search => " [/] search  [l]ike  [d]islike  [↑↓] navigate  [j]obs  [q]uit",
        Tab::Lists => " [Tab] focus  [n]ew  [f]older  [e]dit  [Del]ete  [s]ort  [r]eload  [j]obs  [q]uit",
        Tab::Notes => " [↑↓] navigate  [Del]ete  [r]eload  [j]obs  [q]uit",
        Tab::Prefs => " [Tab] section  [↑↓] select  [←→] adjust  [Del]ete  [r]eload  [j]obs  [q]uit",
    };
    let p = Paragraph::new(hints)
        .style(Style::default().fg(TEXT_DIM).bg(SURFACE));
    f.render_widget(p, area);
}

// =============================================================================
// Daily tab — full implementation
// =============================================================================

fn render_daily(f: &mut Frame, app: &mut App, area: Rect) {
    if app.daily.loading {
        let msg = Paragraph::new("Fetching papers…")
            .style(Style::default().fg(TEXT).bg(BG))
            .alignment(Alignment::Center);
        f.render_widget(msg, area);
        return;
    }

    let total = app.daily.author_papers.len() + app.daily.scored_papers.len();

    if total == 0 {
        let msg = Paragraph::new(format!(
            "No papers loaded. Days={} Limit={}  Press 'f' to fetch.  [/]=Days  -/==Limit",
            app.daily.days, app.daily.limit
        ))
            .style(Style::default().fg(TEXT_DIM).bg(BG))
            .alignment(Alignment::Center);
        f.render_widget(msg, area);
        return;
    }

    // Status bar at top (spans full width)
    let main_chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([Constraint::Length(1), Constraint::Min(0)])
        .split(area);

    // Render status bar across full width
    render_daily_status(f, app, main_chunks[0]);

    // Below status: 60/40 split
    let chunks = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([Constraint::Percentage(60), Constraint::Percentage(40)])
        .split(main_chunks[1]);

    render_daily_table(f, app, chunks[0]);
    render_daily_detail(f, app, chunks[1]);
}

fn render_daily_status(f: &mut Frame, app: &App, area: Rect) {
    let total = app.daily.author_papers.len() + app.daily.scored_papers.len();
    let status = format!(
        " Days: ◀ {} ▶ ([/])  Limit: ◀ {} ▶ (-/=)  │ {} papers  │ f:Fetch",
        app.daily.days, app.daily.limit, total
    );
    let status_p = Paragraph::new(status)
        .style(Style::default().fg(TEXT_DIM).bg(SURFACE));
    f.render_widget(status_p, area);
}

fn render_daily_table(f: &mut Frame, app: &mut App, area: Rect) {
    // Build rows: author section header + papers, then scored section header + papers
    let author_len = app.daily.author_papers.len();
    let scored_len = app.daily.scored_papers.len();

    // Widths: # (5), ID (14), Title (fill), Cat (8), Score (5)
    let widths = [
        Constraint::Length(5),
        Constraint::Length(14),
        Constraint::Min(0),
        Constraint::Length(8),
        Constraint::Length(5),
    ];

    // Header row
    let header = Row::new(vec![
        Cell::from("#").style(Style::default().fg(ACCENT).bold()),
        Cell::from("ID").style(Style::default().fg(ACCENT).bold()),
        Cell::from("Title").style(Style::default().fg(ACCENT).bold()),
        Cell::from("Cat").style(Style::default().fg(ACCENT).bold()),
        Cell::from("Score").style(Style::default().fg(ACCENT).bold()),
    ])
    .style(Style::default().bg(SURFACE))
    .height(1);

    let mut rows: Vec<Row> = Vec::new();

    // Global paper index for selection highlighting
    // We need to build a flat index mapping: dividers don't count
    // Build a parallel "flat_indices" so TableState selected maps to real paper
    let mut flat_indices: Vec<Option<usize>> = Vec::new(); // None = divider row

    if author_len > 0 {
        rows.push(
            Row::new(vec![
                Cell::from(""),
                Cell::from(""),
                Cell::from("── From Your Authors ──").style(Style::default().fg(TEXT_DIM).italic()),
                Cell::from(""),
                Cell::from(""),
            ])
            .style(Style::default().bg(BG))
            .height(1),
        );
        flat_indices.push(None);

        for (local_i, paper) in app.daily.author_papers.iter().enumerate() {
            let global_i = local_i;
            let is_selected = app.daily.selected == global_i;
            let is_bookmarked = app.daily.bookmarked.contains(&paper.arxiv_id);

            let row_bg = if is_bookmarked {
                BOOKMARK_HL
            } else {
                AUTHOR_HL
            };

            let prefix = if is_bookmarked { "★" } else { "✓" };
            let num_str = format!("{}{}", prefix, global_i + 1);
            let title_trunc = truncate_str(&paper.title, 60);
            let cat = paper.primary_category();
            let cat_trunc = truncate_str(cat, 8);
            let score_str = format!("{:.2}", paper.score);

            let row_style = if is_selected {
                Style::default().fg(BG).bg(row_bg).bold()
            } else {
                Style::default().fg(BG).bg(row_bg)
            };

            let row = Row::new(vec![
                Cell::from(num_str),
                Cell::from(paper.arxiv_id.clone()),
                Cell::from(title_trunc),
                Cell::from(cat_trunc),
                Cell::from(score_str),
            ])
            .style(row_style)
            .height(1);

            rows.push(row);
            flat_indices.push(Some(global_i));
        }
    }

    if scored_len > 0 {
        rows.push(
            Row::new(vec![
                Cell::from(""),
                Cell::from(""),
                Cell::from("── Recommended ──").style(Style::default().fg(TEXT_DIM).italic()),
                Cell::from(""),
                Cell::from(""),
            ])
            .style(Style::default().bg(BG))
            .height(1),
        );
        flat_indices.push(None);

        for (local_i, paper) in app.daily.scored_papers.iter().enumerate() {
            let global_i = author_len + local_i;
            let is_selected = app.daily.selected == global_i;
            let is_bookmarked = app.daily.bookmarked.contains(&paper.arxiv_id);

            let base_fg = if is_bookmarked { BG } else { TEXT };
            let base_bg = if is_bookmarked { BOOKMARK_HL } else { BG };

            let prefix = if is_bookmarked { "★" } else { " " };
            let num_str = format!("{}{}", prefix, global_i + 1);
            let title_trunc = truncate_str(&paper.title, 60);
            let cat = paper.primary_category();
            let cat_trunc = truncate_str(cat, 8);
            let score_str = format!("{:.2}", paper.score);

            let row_style = if is_selected {
                Style::default().fg(BG).bg(ACCENT).bold()
            } else {
                Style::default().fg(base_fg).bg(base_bg)
            };

            let row = Row::new(vec![
                Cell::from(num_str),
                Cell::from(paper.arxiv_id.clone()),
                Cell::from(title_trunc),
                Cell::from(cat_trunc),
                Cell::from(score_str),
            ])
            .style(row_style)
            .height(1);

            rows.push(row);
            flat_indices.push(Some(global_i));
        }
    }

    // Find the table row index that corresponds to app.daily.selected
    let table_selected = flat_indices
        .iter()
        .position(|fi| *fi == Some(app.daily.selected));

    let papers_border_style = if app.daily.focus_detail {
        Style::default().fg(TEXT_DIM)
    } else {
        Style::default().fg(ACCENT)
    };

    let table = Table::new(rows, widths)
        .header(header)
        .block(
            Block::default()
                .title(" Papers ")
                .borders(Borders::ALL)
                .border_style(papers_border_style)
                .style(Style::default().bg(BG)),
        )
        .row_highlight_style(Style::default().bg(ACCENT).fg(BG).bold())
        .column_spacing(1);

    let mut table_state = TableState::default();
    table_state.select(table_selected);

    f.render_stateful_widget(table, area, &mut table_state);
}

fn render_daily_detail(f: &mut Frame, app: &App, area: Rect) {
    let (detail_border_style, detail_title) = if app.daily.focus_detail {
        (
            Style::default().fg(ACCENT),
            " Detail  [Tab] to papers ",
        )
    } else {
        (
            Style::default().fg(TEXT_DIM),
            " Detail  [Tab] to scroll ",
        )
    };

    let block = Block::default()
        .title(detail_title)
        .borders(Borders::ALL)
        .border_style(detail_border_style)
        .style(Style::default().bg(BG));

    let inner = block.inner(area);
    f.render_widget(block, area);

    let Some(paper) = app.selected_daily_paper() else {
        let msg = Paragraph::new("Select a paper")
            .style(Style::default().fg(TEXT_DIM).bg(BG));
        f.render_widget(msg, inner);
        return;
    };

    let authors_str = paper.authors.join(", ");
    let cats_str = paper.categories.join(", ");

    let mut lines: Vec<Line> = Vec::new();

    // Title (bold, wrapped)
    lines.push(Line::from(Span::styled(
        paper.title.clone(),
        Style::default().fg(TEXT).bold(),
    )));
    lines.push(Line::default());

    // Authors
    lines.push(Line::from(vec![
        Span::styled("Authors: ", Style::default().fg(ACCENT).bold()),
        Span::styled(authors_str, Style::default().fg(TEXT)),
    ]));

    // Categories
    lines.push(Line::from(vec![
        Span::styled("Categories: ", Style::default().fg(ACCENT).bold()),
        Span::styled(cats_str, Style::default().fg(TEXT)),
    ]));

    // Published
    lines.push(Line::from(vec![
        Span::styled("Published: ", Style::default().fg(ACCENT).bold()),
        Span::styled(paper.published.clone(), Style::default().fg(TEXT)),
    ]));

    // Score
    lines.push(Line::from(vec![
        Span::styled("Score: ", Style::default().fg(ACCENT).bold()),
        Span::styled(format!("{:.4}", paper.score), Style::default().fg(TEXT)),
    ]));

    lines.push(Line::default());

    // Abstract header
    lines.push(Line::from(Span::styled(
        "Abstract:",
        Style::default().fg(ACCENT).bold(),
    )));
    lines.push(Line::default());

    // Abstract text — add the raw text; Wrap will handle it
    lines.push(Line::from(Span::styled(
        paper.abstract_text.clone(),
        Style::default().fg(TEXT),
    )));

    let paragraph = Paragraph::new(lines)
        .style(Style::default().bg(BG))
        .wrap(Wrap { trim: true })
        .scroll((app.daily.detail_scroll, 0));

    f.render_widget(paragraph, inner);
}

// =============================================================================
// Search tab
// =============================================================================

fn render_search(f: &mut Frame, app: &App, area: Rect) {
    // Layout: search bar (1 line) + content below
    let outer = Layout::default()
        .direction(Direction::Vertical)
        .constraints([Constraint::Length(1), Constraint::Min(0)])
        .split(area);

    // Search bar
    let cursor = if app.search.editing { "█" } else { "" };
    let bar_text = format!(" / Search: {}{}", app.search.query, cursor);
    let bar_style = if app.search.editing {
        Style::default().fg(ACCENT).bg(SURFACE).bold()
    } else {
        Style::default().fg(TEXT_DIM).bg(SURFACE)
    };
    f.render_widget(Paragraph::new(bar_text).style(bar_style), outer[0]);

    // Content area: 60% results table | 40% detail panel
    let chunks = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([Constraint::Percentage(60), Constraint::Percentage(40)])
        .split(outer[1]);

    // Results table
    if app.search.loading {
        let msg = Paragraph::new("Searching…")
            .style(Style::default().fg(TEXT_DIM).bg(BG))
            .alignment(Alignment::Center);
        let block = Block::default()
            .title(" Results ")
            .borders(Borders::ALL)
            .border_style(Style::default().fg(ACCENT))
            .style(Style::default().bg(BG));
        let inner = block.inner(chunks[0]);
        f.render_widget(block, chunks[0]);
        f.render_widget(msg, inner);
    } else if app.search.results.is_empty() {
        let msg = Paragraph::new("Press / to search")
            .style(Style::default().fg(TEXT_DIM).bg(BG))
            .alignment(Alignment::Center);
        let block = Block::default()
            .title(" Results ")
            .borders(Borders::ALL)
            .border_style(Style::default().fg(ACCENT))
            .style(Style::default().bg(BG));
        let inner = block.inner(chunks[0]);
        f.render_widget(block, chunks[0]);
        f.render_widget(msg, inner);
    } else {
        let widths = [
            Constraint::Length(5),
            Constraint::Length(14),
            Constraint::Min(0),
            Constraint::Length(8),
            Constraint::Length(5),
        ];
        let header = Row::new(vec![
            Cell::from("#").style(Style::default().fg(ACCENT).bold()),
            Cell::from("ID").style(Style::default().fg(ACCENT).bold()),
            Cell::from("Title").style(Style::default().fg(ACCENT).bold()),
            Cell::from("Cat").style(Style::default().fg(ACCENT).bold()),
            Cell::from("Score").style(Style::default().fg(ACCENT).bold()),
        ])
        .style(Style::default().bg(SURFACE))
        .height(1);

        let rows: Vec<Row> = app
            .search
            .results
            .iter()
            .enumerate()
            .map(|(i, paper)| {
                let is_sel = app.search.selected == i;
                let title_trunc = truncate_str(&paper.title, 60);
                let cat = paper.primary_category();
                let cat_trunc = truncate_str(cat, 8);
                let score_str = format!("{:.2}", paper.score);
                let row_style = if is_sel {
                    Style::default().fg(BG).bg(ACCENT).bold()
                } else {
                    Style::default().fg(TEXT).bg(BG)
                };
                Row::new(vec![
                    Cell::from(format!("{}", i + 1)),
                    Cell::from(paper.arxiv_id.clone()),
                    Cell::from(title_trunc),
                    Cell::from(cat_trunc),
                    Cell::from(score_str),
                ])
                .style(row_style)
                .height(1)
            })
            .collect();

        let table = Table::new(rows, widths)
            .header(header)
            .block(
                Block::default()
                    .title(" Results ")
                    .borders(Borders::ALL)
                    .border_style(Style::default().fg(ACCENT))
                    .style(Style::default().bg(BG)),
            )
            .row_highlight_style(Style::default().bg(ACCENT).fg(BG).bold())
            .column_spacing(1);

        let mut table_state = TableState::default();
        table_state.select(Some(app.search.selected));
        f.render_stateful_widget(table, chunks[0], &mut table_state);
    }

    // Detail panel
    let detail_block = Block::default()
        .title(" Detail ")
        .borders(Borders::ALL)
        .border_style(Style::default().fg(TEXT_DIM))
        .style(Style::default().bg(BG));
    let detail_inner = detail_block.inner(chunks[1]);
    f.render_widget(detail_block, chunks[1]);

    if let Some(paper) = app.search.results.get(app.search.selected) {
        let authors_str = paper.authors.join(", ");
        let cats_str = paper.categories.join(", ");
        let mut lines: Vec<Line> = Vec::new();
        lines.push(Line::from(Span::styled(
            paper.title.clone(),
            Style::default().fg(TEXT).bold(),
        )));
        lines.push(Line::default());
        lines.push(Line::from(vec![
            Span::styled("Authors: ", Style::default().fg(ACCENT).bold()),
            Span::styled(authors_str, Style::default().fg(TEXT)),
        ]));
        lines.push(Line::from(vec![
            Span::styled("Categories: ", Style::default().fg(ACCENT).bold()),
            Span::styled(cats_str, Style::default().fg(TEXT)),
        ]));
        lines.push(Line::from(vec![
            Span::styled("Published: ", Style::default().fg(ACCENT).bold()),
            Span::styled(paper.published.clone(), Style::default().fg(TEXT)),
        ]));
        lines.push(Line::from(vec![
            Span::styled("Score: ", Style::default().fg(ACCENT).bold()),
            Span::styled(format!("{:.4}", paper.score), Style::default().fg(TEXT)),
        ]));
        lines.push(Line::default());
        lines.push(Line::from(Span::styled(
            "Abstract:",
            Style::default().fg(ACCENT).bold(),
        )));
        lines.push(Line::default());
        lines.push(Line::from(Span::styled(
            paper.abstract_text.clone(),
            Style::default().fg(TEXT),
        )));
        let paragraph = Paragraph::new(lines)
            .style(Style::default().bg(BG))
            .wrap(Wrap { trim: true });
        f.render_widget(paragraph, detail_inner);
    } else if !app.search.results.is_empty() {
        // no selection yet
    }
}

// =============================================================================
// Lists tab
// =============================================================================

fn render_lists(f: &mut Frame, app: &App, area: Rect) {
    // Split 35% list panel | 65% paper panel
    let chunks = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([Constraint::Percentage(35), Constraint::Percentage(65)])
        .split(area);

    // Left panel — list of reading lists
    let left_border_style = if app.lists.focus_left {
        Style::default().fg(ACCENT)
    } else {
        Style::default().fg(TEXT_DIM)
    };
    let left_block = Block::default()
        .title(" Reading Lists ")
        .borders(Borders::ALL)
        .border_style(left_border_style)
        .style(Style::default().bg(BG));
    let left_inner = left_block.inner(chunks[0]);
    f.render_widget(left_block, chunks[0]);

    if app.lists.items.is_empty() {
        let msg = Paragraph::new("No lists found.\n[n] new  [f] folder")
            .style(Style::default().fg(TEXT_DIM).bg(BG));
        f.render_widget(msg, left_inner);
    } else {
        let mut lines: Vec<Line> = Vec::new();
        for (i, (list, count)) in app.lists.items.iter().enumerate() {
            let is_sel = app.lists.focus_left && app.lists.selected_list == i;
            let icon = if list.is_folder { "📁" } else { "📋" };
            let label = format!("{} {} ({})", icon, list.name, count);
            let style = if is_sel {
                Style::default().fg(BG).bg(ACCENT).bold()
            } else if list.is_system {
                Style::default().fg(AUTHOR_HL).bg(BG)
            } else {
                Style::default().fg(TEXT).bg(BG)
            };
            lines.push(Line::from(Span::styled(label, style)));
        }
        lines.push(Line::default());
        lines.push(Line::from(Span::styled(
            " [n]ew [f]old [Del]delete  Tab→",
            Style::default().fg(TEXT_DIM),
        )));
        let paragraph = Paragraph::new(lines).style(Style::default().bg(BG));
        f.render_widget(paragraph, left_inner);
    }

    // Right panel — papers in the selected list
    let selected_list_name = app
        .lists
        .items
        .get(app.lists.selected_list)
        .map(|(l, _)| l.name.as_str())
        .unwrap_or("—");
    let right_title = format!(" {} — {} papers ", selected_list_name, app.lists.papers.len());
    let right_border_style = if !app.lists.focus_left {
        Style::default().fg(ACCENT)
    } else {
        Style::default().fg(TEXT_DIM)
    };
    let right_block = Block::default()
        .title(right_title)
        .borders(Borders::ALL)
        .border_style(right_border_style)
        .style(Style::default().bg(BG));
    let right_inner = right_block.inner(chunks[1]);
    f.render_widget(right_block, chunks[1]);

    if app.lists.papers.is_empty() {
        let msg = Paragraph::new("No papers in this list.")
            .style(Style::default().fg(TEXT_DIM).bg(BG));
        f.render_widget(msg, right_inner);
    } else {
        let widths = [
            Constraint::Length(4),
            Constraint::Length(14),
            Constraint::Min(0),
            Constraint::Length(8),
            Constraint::Length(8),
        ];
        let header = Row::new(vec![
            Cell::from("#").style(Style::default().fg(ACCENT).bold()),
            Cell::from("ID").style(Style::default().fg(ACCENT).bold()),
            Cell::from("Title").style(Style::default().fg(ACCENT).bold()),
            Cell::from("Cat").style(Style::default().fg(ACCENT).bold()),
            Cell::from("Added").style(Style::default().fg(ACCENT).bold()),
        ])
        .style(Style::default().bg(SURFACE))
        .height(1);

        let rows: Vec<Row> = app
            .lists
            .papers
            .iter()
            .enumerate()
            .map(|(i, p)| {
                let is_sel = !app.lists.focus_left && app.lists.selected_paper == i;
                let title = app
                    .lists
                    .paper_details
                    .get(&p.arxiv_id)
                    .map(|d| d.title.as_str())
                    .unwrap_or("—");
                let cat = app
                    .lists
                    .paper_details
                    .get(&p.arxiv_id)
                    .and_then(|d| d.categories.first())
                    .map(|s| s.as_str())
                    .unwrap_or("—");
                let added_short = p.added_at.get(..10).unwrap_or(&p.added_at);
                let row_style = if is_sel {
                    Style::default().fg(BG).bg(ACCENT).bold()
                } else {
                    Style::default().fg(TEXT).bg(BG)
                };
                Row::new(vec![
                    Cell::from(format!("{}", i + 1)),
                    Cell::from(truncate_str(&p.arxiv_id, 14)),
                    Cell::from(truncate_str(title, 40)),
                    Cell::from(truncate_str(cat, 8)),
                    Cell::from(added_short.to_string()),
                ])
                .style(row_style)
                .height(1)
            })
            .collect();

        let table = Table::new(rows, widths)
            .header(header)
            .block(Block::default().style(Style::default().bg(BG)))
            .row_highlight_style(Style::default().bg(ACCENT).fg(BG).bold())
            .column_spacing(1);

        let mut table_state = TableState::default();
        if !app.lists.focus_left {
            table_state.select(Some(app.lists.selected_paper));
        }
        f.render_stateful_widget(table, right_inner, &mut table_state);
    }
}

// =============================================================================
// Notes tab
// =============================================================================

fn render_notes(f: &mut Frame, app: &App, area: Rect) {
    // Split 35% note list | 65% note content
    let chunks = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([Constraint::Percentage(35), Constraint::Percentage(65)])
        .split(area);

    // Left panel — note list
    let left_block = Block::default()
        .title(" Notes ")
        .borders(Borders::ALL)
        .border_style(Style::default().fg(ACCENT))
        .style(Style::default().bg(BG));
    let left_inner = left_block.inner(chunks[0]);
    f.render_widget(left_block, chunks[0]);

    if app.notes.notes.is_empty() {
        let msg = Paragraph::new("No notes yet.")
            .style(Style::default().fg(TEXT_DIM).bg(BG));
        f.render_widget(msg, left_inner);
    } else {
        let mut lines: Vec<Line> = Vec::new();
        for (i, note) in app.notes.notes.iter().enumerate() {
            let is_sel = app.notes.selected == i;
            let label = format!("{} [{}]", truncate_str(&note.arxiv_id, 14), note.note_type);
            let style = if is_sel {
                Style::default().fg(BG).bg(ACCENT).bold()
            } else {
                Style::default().fg(TEXT).bg(BG)
            };
            lines.push(Line::from(Span::styled(label, style)));
        }
        let paragraph = Paragraph::new(lines).style(Style::default().bg(BG));
        f.render_widget(paragraph, left_inner);
    }

    // Right panel — note content
    let right_block = Block::default()
        .title(" Note Content ")
        .borders(Borders::ALL)
        .border_style(Style::default().fg(TEXT_DIM))
        .style(Style::default().bg(BG));
    let right_inner = right_block.inner(chunks[1]);
    f.render_widget(right_block, chunks[1]);

    if let Some(note) = app.notes.notes.get(app.notes.selected) {
        let mut lines: Vec<Line> = Vec::new();
        lines.push(Line::from(vec![
            Span::styled("Paper: ", Style::default().fg(ACCENT).bold()),
            Span::styled(note.arxiv_id.clone(), Style::default().fg(TEXT)),
        ]));
        lines.push(Line::from(vec![
            Span::styled("Type: ", Style::default().fg(ACCENT).bold()),
            Span::styled(note.note_type.clone(), Style::default().fg(TEXT)),
        ]));
        lines.push(Line::from(vec![
            Span::styled("Created: ", Style::default().fg(ACCENT).bold()),
            Span::styled(
                note.created_at.get(..10).unwrap_or(&note.created_at).to_string(),
                Style::default().fg(TEXT_DIM),
            ),
        ]));
        lines.push(Line::default());
        lines.push(Line::from(Span::styled(
            note.content.clone(),
            Style::default().fg(TEXT),
        )));
        let paragraph = Paragraph::new(lines)
            .style(Style::default().bg(BG))
            .wrap(Wrap { trim: true });
        f.render_widget(paragraph, right_inner);
    }
}

// =============================================================================
// Prefs tab
// =============================================================================

fn render_prefs(f: &mut Frame, app: &App, area: Rect) {
    // Split top (60%) | bottom (40%)
    let vert = Layout::default()
        .direction(Direction::Vertical)
        .constraints([Constraint::Percentage(60), Constraint::Percentage(40)])
        .split(area);

    // Top: 3-column split — categories | keywords | authors
    let top_cols = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([
            Constraint::Percentage(33),
            Constraint::Percentage(34),
            Constraint::Percentage(33),
        ])
        .split(vert[0]);

    // Helper: border style for a section
    let sec_border = |sec: usize| {
        if app.prefs.focus_section == sec {
            Style::default().fg(ACCENT)
        } else {
            Style::default().fg(TEXT_DIM)
        }
    };

    // Categories
    {
        let block = Block::default()
            .title(" Categories [a:Add ←→:Pri Del:Rm] ")
            .borders(Borders::ALL)
            .border_style(sec_border(0))
            .style(Style::default().bg(BG));
        let inner = block.inner(top_cols[0]);
        f.render_widget(block, top_cols[0]);

        if app.prefs.categories.is_empty() {
            f.render_widget(
                Paragraph::new("None").style(Style::default().fg(TEXT_DIM).bg(BG)),
                inner,
            );
        } else {
            let mut lines: Vec<Line> = Vec::new();
            for (i, cat) in app.prefs.categories.iter().enumerate() {
                let is_sel = app.prefs.focus_section == 0 && app.prefs.section_selected[0] == i;
                let stars = stars_display(cat.priority);
                let label = format!("{:<12} {}", truncate_str(&cat.category, 12), stars);
                let style = if is_sel {
                    Style::default().fg(BG).bg(ACCENT).bold()
                } else {
                    Style::default().fg(TEXT).bg(BG)
                };
                lines.push(Line::from(Span::styled(label, style)));
            }
            f.render_widget(Paragraph::new(lines).style(Style::default().bg(BG)), inner);
        }
    }

    // Keywords
    {
        let block = Block::default()
            .title(" Keywords [a:Add ←→:Wt Del:Rm] ")
            .borders(Borders::ALL)
            .border_style(sec_border(1))
            .style(Style::default().bg(BG));
        let inner = block.inner(top_cols[1]);
        f.render_widget(block, top_cols[1]);

        if app.prefs.keywords.is_empty() {
            f.render_widget(
                Paragraph::new("None").style(Style::default().fg(TEXT_DIM).bg(BG)),
                inner,
            );
        } else {
            let mut lines: Vec<Line> = Vec::new();
            for (i, kw) in app.prefs.keywords.iter().enumerate() {
                let is_sel = app.prefs.focus_section == 1 && app.prefs.section_selected[1] == i;
                let stars = stars_display(kw.weight);
                let label = format!("{:<12} {}", truncate_str(&kw.keyword, 12), stars);
                let style = if is_sel {
                    Style::default().fg(BG).bg(ACCENT).bold()
                } else {
                    Style::default().fg(TEXT).bg(BG)
                };
                lines.push(Line::from(Span::styled(label, style)));
            }
            f.render_widget(Paragraph::new(lines).style(Style::default().bg(BG)), inner);
        }
    }

    // Authors
    {
        let block = Block::default()
            .title(" Authors [a:Add Del:Rm] ")
            .borders(Borders::ALL)
            .border_style(sec_border(2))
            .style(Style::default().bg(BG));
        let inner = block.inner(top_cols[2]);
        f.render_widget(block, top_cols[2]);

        if app.prefs.authors.is_empty() {
            f.render_widget(
                Paragraph::new("None").style(Style::default().fg(TEXT_DIM).bg(BG)),
                inner,
            );
        } else {
            let mut lines: Vec<Line> = Vec::new();
            for (i, auth) in app.prefs.authors.iter().enumerate() {
                let is_sel = app.prefs.focus_section == 2 && app.prefs.section_selected[2] == i;
                let style = if is_sel {
                    Style::default().fg(BG).bg(ACCENT).bold()
                } else {
                    Style::default().fg(TEXT).bg(BG)
                };
                lines.push(Line::from(Span::styled(
                    truncate_str(&auth.name, 22),
                    style,
                )));
            }
            f.render_widget(Paragraph::new(lines).style(Style::default().bg(BG)), inner);
        }
    }

    // Bottom: 2-column split — weights | config
    let bot_cols = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([Constraint::Percentage(60), Constraint::Percentage(40)])
        .split(vert[1]);

    // Weights
    {
        let block = Block::default()
            .title(" Weights ")
            .borders(Borders::ALL)
            .border_style(sec_border(3))
            .style(Style::default().bg(BG));
        let inner = block.inner(bot_cols[0]);
        f.render_widget(block, bot_cols[0]);

        let labels = ["Content", "Category", "Keyword", "Recency"];
        let weights = app.prefs.weights;
        let total: i64 = weights.iter().sum();
        let mut lines: Vec<Line> = Vec::new();
        for (i, label) in labels.iter().enumerate() {
            let is_sel = app.prefs.focus_section == 3 && app.prefs.section_selected[3] == i;
            let bar = build_bar(weights[i], 100, 20);
            let style = if is_sel {
                Style::default().fg(ACCENT).bold()
            } else {
                Style::default().fg(TEXT)
            };
            let prefix = if is_sel { "► " } else { "  " };
            lines.push(Line::from(vec![
                Span::styled(prefix, style),
                Span::styled(format!("{:<10}", label), style),
                Span::styled(format!("{:>3}%  ", weights[i]), style),
                Span::styled(bar, style),
            ]));
        }
        // Total line with color indicator
        let total_color = if total == 100 { SUCCESS_COLOR } else { ERROR_COLOR };
        let total_hint = if total == 100 {
            String::new()
        } else {
            " (Tab to normalize)".to_string()
        };
        lines.push(Line::from(vec![
            Span::styled("  ", Style::default()),
            Span::styled(format!("Total: {total}%{total_hint}"), Style::default().fg(total_color)),
            Span::styled("  ←→:±1  D:Default", Style::default().fg(TEXT_DIM)),
        ]));
        f.render_widget(Paragraph::new(lines).style(Style::default().bg(BG)), inner);
    }

    // Config
    {
        let block = Block::default()
            .title(" Config ")
            .borders(Borders::ALL)
            .border_style(sec_border(4))
            .style(Style::default().bg(BG));
        let inner = block.inner(bot_cols[1]);
        f.render_widget(block, bot_cols[1]);

        let focused = app.prefs.focus_section == 4;
        let sel = app.prefs.section_selected[4];

        let provider_style = if focused && sel == 0 {
            Style::default().fg(ACCENT).bold()
        } else {
            Style::default().fg(TEXT)
        };
        let language_style = if focused && sel == 1 {
            Style::default().fg(ACCENT).bold()
        } else {
            Style::default().fg(TEXT)
        };
        let provider_prefix = if focused && sel == 0 { "► " } else { "  " };
        let language_prefix = if focused && sel == 1 { "► " } else { "  " };

        let lines = vec![
            Line::from(vec![
                Span::styled(provider_prefix, provider_style),
                Span::styled("Provider: ", Style::default().fg(ACCENT).bold()),
                Span::styled(app.prefs.provider.clone(), provider_style),
            ]),
            Line::from(vec![
                Span::styled(language_prefix, language_style),
                Span::styled("Language: ", Style::default().fg(ACCENT).bold()),
                Span::styled(app.prefs.language.clone(), language_style),
            ]),
        ];
        f.render_widget(Paragraph::new(lines).style(Style::default().bg(BG)), inner);
    }
}

// =============================================================================
// Paper Detail Overlay
// =============================================================================

fn render_paper_detail(f: &mut Frame, app: &App) {
    let detail = app.detail.as_ref().unwrap();
    let paper = &detail.paper;

    // Centered overlay: 80% width, 90% height
    let area = f.area();
    let w = (area.width * 80 / 100).max(60);
    let h = (area.height * 90 / 100).max(20);
    let x = (area.width.saturating_sub(w)) / 2;
    let y = (area.height.saturating_sub(h)) / 2;
    let overlay = Rect::new(x, y, w, h);

    // Clear background
    f.render_widget(Clear, overlay);

    let block = Block::default()
        .title(" Paper Detail ")
        .borders(Borders::ALL)
        .border_style(Style::default().fg(ACCENT))
        .style(Style::default().bg(BG));
    let inner = block.inner(overlay);
    f.render_widget(block, overlay);

    // Split inner into content area + key hints bar
    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([Constraint::Min(0), Constraint::Length(1)])
        .split(inner);

    let content_width = chunks[0].width as usize;
    let wrap_width = content_width.saturating_sub(2);

    let mut lines: Vec<Line> = Vec::new();

    // Title
    lines.push(Line::from(vec![
        Span::styled("Title: ", Style::default().fg(ACCENT).bold()),
        Span::styled(paper.title.clone(), Style::default().fg(TEXT)),
    ]));

    // Authors
    lines.push(Line::from(vec![
        Span::styled("Authors: ", Style::default().fg(ACCENT).bold()),
        Span::styled(paper.authors.join(", "), Style::default().fg(TEXT)),
    ]));

    // Categories + Published
    lines.push(Line::from(vec![
        Span::styled("Categories: ", Style::default().fg(ACCENT).bold()),
        Span::styled(paper.categories.join(", "), Style::default().fg(TEXT)),
        Span::raw("  │  "),
        Span::styled("Published: ", Style::default().fg(ACCENT).bold()),
        Span::styled(paper.published.clone(), Style::default().fg(TEXT)),
    ]));

    // ID + Score
    lines.push(Line::from(vec![
        Span::styled("arXiv: ", Style::default().fg(ACCENT).bold()),
        Span::styled(paper.arxiv_id.clone(), Style::default().fg(TEXT)),
        Span::raw("  │  "),
        Span::styled("Score: ", Style::default().fg(ACCENT).bold()),
        Span::styled(format!("{:.2}", paper.score), Style::default().fg(TEXT)),
    ]));

    // Separator
    lines.push(Line::from(Span::styled(
        "─".repeat(content_width),
        Style::default().fg(SURFACE),
    )));
    lines.push(Line::default());

    // Abstract
    lines.push(Line::from(Span::styled(
        "Abstract:",
        Style::default().fg(ACCENT).bold(),
    )));
    for line in word_wrap(&paper.abstract_text, wrap_width) {
        lines.push(Line::from(Span::styled(line, Style::default().fg(TEXT))));
    }
    lines.push(Line::default());

    // Summary section
    let sep = "─".repeat(content_width.saturating_sub(2));
    lines.push(Line::from(Span::styled(
        format!("── Summary {sep}"),
        Style::default().fg(ACCENT).bold(),
    )));
    match &detail.summary {
        Some(s) => {
            // Show summary_short first (bold)
            if let Some(short) = &s.summary_short {
                lines.push(Line::default());
                for line in word_wrap(short, wrap_width.saturating_sub(2)) {
                    lines.push(Line::from(vec![
                        Span::raw("  "),
                        Span::styled(line, Style::default().fg(TEXT).bold()),
                    ]));
                }
            }
            // Show summary_detailed with ## section headers parsed
            if let Some(detailed_text) = &s.summary_detailed {
                lines.push(Line::default());
                for raw_line in detailed_text.split('\n') {
                    if let Some(heading) = raw_line.strip_prefix("## ") {
                        lines.push(Line::default());
                        lines.push(Line::from(vec![
                            Span::raw("  "),
                            Span::styled(heading, Style::default().fg(ACCENT).bold()),
                            Span::raw(":"),
                        ]));
                    } else if raw_line.is_empty() {
                        // skip raw blank lines inside detailed text (we handle spacing above)
                    } else {
                        for wrapped in word_wrap(raw_line, wrap_width.saturating_sub(4)) {
                            lines.push(Line::from(vec![
                                Span::raw("    "),
                                Span::styled(wrapped, Style::default().fg(TEXT)),
                            ]));
                        }
                    }
                }
            }
            // Key findings
            let findings = s.key_findings.as_deref().map(parse_key_findings).unwrap_or_default();
            if !findings.is_empty() {
                lines.push(Line::default());
                lines.push(Line::from(vec![
                    Span::raw("  "),
                    Span::styled("Key Findings:", Style::default().fg(ACCENT).bold()),
                ]));
                for finding in &findings {
                    for (idx, wrapped) in word_wrap(finding, wrap_width.saturating_sub(6)).iter().enumerate() {
                        if idx == 0 {
                            lines.push(Line::from(vec![
                                Span::raw("    "),
                                Span::styled("• ", Style::default().fg(ACCENT)),
                                Span::styled(wrapped.clone(), Style::default().fg(TEXT)),
                            ]));
                        } else {
                            lines.push(Line::from(vec![
                                Span::raw("      "),
                                Span::styled(wrapped.clone(), Style::default().fg(TEXT)),
                            ]));
                        }
                    }
                }
            }
        }
        None => {
            lines.push(Line::from(vec![
                Span::raw("  "),
                Span::styled(
                    "Press [s] to generate summary",
                    Style::default().fg(TEXT_DIM),
                ),
            ]));
        }
    }
    lines.push(Line::default());

    // Translation section
    lines.push(Line::from(Span::styled(
        format!("── Translation {sep}"),
        Style::default().fg(ACCENT).bold(),
    )));
    match &detail.translation {
        Some((title, abstract_text)) => {
            lines.push(Line::default());
            lines.push(Line::from(vec![
                Span::raw("  "),
                Span::styled("Title: ", Style::default().fg(ACCENT)),
                Span::styled(title.clone(), Style::default().fg(TEXT)),
            ]));
            lines.push(Line::default());
            for line in word_wrap(abstract_text, wrap_width.saturating_sub(2)) {
                lines.push(Line::from(vec![
                    Span::raw("  "),
                    Span::styled(line, Style::default().fg(TEXT)),
                ]));
            }
        }
        None => {
            lines.push(Line::from(vec![
                Span::raw("  "),
                Span::styled(
                    "Press [t] to translate",
                    Style::default().fg(TEXT_DIM),
                ),
            ]));
        }
    }
    lines.push(Line::default());

    // Review section
    lines.push(Line::from(Span::styled(
        format!("── Review {sep}"),
        Style::default().fg(ACCENT).bold(),
    )));
    lines.push(Line::default());
    if detail.review_sections > 0 {
        lines.push(Line::from(vec![
            Span::raw("  "),
            Span::styled("✓ ", Style::default().fg(SUCCESS_COLOR).bold()),
            Span::styled(
                format!("Review generated ({} sections cached)", detail.review_sections),
                Style::default().fg(TEXT),
            ),
        ]));
        lines.push(Line::from(vec![
            Span::raw("  "),
            Span::styled("Location: ", Style::default().fg(ACCENT)),
            Span::styled("paper_review_sections table", Style::default().fg(TEXT_DIM)),
        ]));
        lines.push(Line::from(vec![
            Span::raw("  "),
            Span::styled("Use CLI: ", Style::default().fg(ACCENT)),
            Span::styled(
                format!("uv run axp review {} --output review.md", paper.arxiv_id),
                Style::default().fg(TEXT_DIM),
            ),
        ]));
    } else {
        lines.push(Line::from(vec![
            Span::raw("  "),
            Span::styled(
                "Press [r] to generate review",
                Style::default().fg(TEXT_DIM),
            ),
        ]));
    }

    // Render content with scroll
    let content = Paragraph::new(lines)
        .scroll((detail.scroll, 0))
        .style(Style::default().bg(BG));
    f.render_widget(content, chunks[0]);

    // Key hints at bottom
    let hints = Paragraph::new(
        " [s]ummarize  [t]ranslate  [r]eview  [l]ike  [d]islike  [b]ookmark  [Esc] close",
    )
    .style(Style::default().fg(TEXT_DIM).bg(SURFACE));
    f.render_widget(hints, chunks[1]);
}

// =============================================================================
// Confirmation Dialog Overlay
// =============================================================================

fn render_confirm_dialog(f: &mut Frame, app: &App) {
    let area = f.area();
    let w: u16 = 36;
    let h: u16 = 5;
    let x = (area.width.saturating_sub(w)) / 2;
    let y = (area.height.saturating_sub(h)) / 2;
    let overlay = Rect::new(x, y, w, h);

    f.render_widget(Clear, overlay);

    let (title, body) = match &app.confirm_action {
        Some(ConfirmAction::RegenerateSummary) => (
            " Regenerate? ",
            "Summary already exists.\nRegenerate? [y]es / [n]o",
        ),
        Some(ConfirmAction::RegenerateTranslation) => (
            " Regenerate? ",
            "Translation already exists.\nRegenerate? [y]es / [n]o",
        ),
        Some(ConfirmAction::RemoveCustomProvider(_)) => (
            " Remove Provider? ",
            "Remove this custom provider?\n[y]es / [n]o",
        ),
        None => return,
    };

    let block = Block::default()
        .title(title)
        .borders(Borders::ALL)
        .border_style(Style::default().fg(ACCENT))
        .style(Style::default().bg(SURFACE));
    let inner = block.inner(overlay);
    f.render_widget(block, overlay);

    let p = Paragraph::new(body)
        .style(Style::default().fg(TEXT).bg(SURFACE))
        .wrap(Wrap { trim: true });
    f.render_widget(p, inner);
}

// =============================================================================
// Jobs Panel Overlay
// =============================================================================

fn render_jobs_panel(f: &mut Frame, app: &App) {
    use crate::app::{JobStatus};

    let area = f.area();
    let w = (area.width * 70 / 100).max(60).min(area.width);
    let h = (app.jobs.len() as u16 + 6).max(8).min(area.height);
    let x = (area.width.saturating_sub(w)) / 2;
    let y = (area.height.saturating_sub(h)) / 2;
    let overlay = Rect::new(x, y, w, h);

    f.render_widget(Clear, overlay);

    let block = Block::default()
        .title(" Background Jobs ")
        .borders(Borders::ALL)
        .border_style(Style::default().fg(ACCENT))
        .style(Style::default().bg(BG));
    let inner = block.inner(overlay);
    f.render_widget(block, overlay);

    // Split inner: job list | hints bar
    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([Constraint::Min(0), Constraint::Length(1)])
        .split(inner);

    if app.jobs.is_empty() {
        let msg = Paragraph::new("No background jobs.")
            .style(Style::default().fg(TEXT_DIM).bg(BG))
            .alignment(Alignment::Center);
        f.render_widget(msg, chunks[0]);
    } else {
        let mut lines: Vec<Line> = Vec::new();
        for (i, job) in app.jobs.iter().enumerate() {
            let is_sel = app.selected_job == i;
            let (status_icon, status_str, status_color) = match &job.status {
                JobStatus::Running => ("⟳", "Running".to_string(), AUTHOR_HL),
                JobStatus::Done    => ("✓", "Done".to_string(), SUCCESS_COLOR),
                JobStatus::Failed(e) => {
                    let short = if e.len() > 20 { format!("{}…", &e[..19]) } else { e.clone() };
                    ("✗", format!("Failed: {short}"), ERROR_COLOR)
                }
            };
            let elapsed = job.elapsed_secs.unwrap_or_else(|| job.started_at.elapsed().as_secs());
            let elapsed_str = if elapsed < 60 {
                format!("{:>3}s", elapsed)
            } else {
                format!("{:>2}m{:02}s", elapsed / 60, elapsed % 60)
            };
            let title_short = truncate_str(&job.paper_title, 30);
            let label = format!(
                " {} {:<9}  {:<12}  {:<30}  {:>6}  {}",
                status_icon,
                job.job_type.label(),
                truncate_str(&job.paper_id, 12),
                title_short,
                elapsed_str,
                status_str,
            );
            let style = if is_sel {
                Style::default().fg(BG).bg(ACCENT).bold()
            } else {
                Style::default().fg(status_color).bg(BG)
            };
            lines.push(Line::from(Span::styled(label, style)));
        }
        let paragraph = Paragraph::new(lines).style(Style::default().bg(BG));
        f.render_widget(paragraph, chunks[0]);
    }

    // Key hints
    let hints = Paragraph::new(" [↑↓] navigate  [c] clear done  [j/Esc] close")
        .style(Style::default().fg(TEXT_DIM).bg(SURFACE));
    f.render_widget(hints, chunks[1]);
}

// =============================================================================
// Category picker overlay
// =============================================================================

fn render_category_picker(f: &mut Frame, app: &App) {
    let area = f.area();
    let w = (area.width * 60 / 100).max(50).min(area.width);
    let h = (area.height * 70 / 100).max(12).min(area.height);
    let x = (area.width.saturating_sub(w)) / 2;
    let y = (area.height.saturating_sub(h)) / 2;
    let overlay = Rect::new(x, y, w, h);

    f.render_widget(Clear, overlay);

    let block = Block::default()
        .title(" Add Category ")
        .borders(Borders::ALL)
        .border_style(Style::default().fg(ACCENT))
        .style(Style::default().bg(BG));
    let inner = block.inner(overlay);
    f.render_widget(block, overlay);

    if let Some(crate::app::OverlayMode::CategoryPicker { search, filtered, selected }) = &app.overlay {
        let chunks = Layout::default()
            .direction(Direction::Vertical)
            .constraints([
                Constraint::Length(1), // search
                Constraint::Length(1), // separator
                Constraint::Min(0),   // list
                Constraint::Length(1), // hints
            ])
            .split(inner);

        // Search line
        let search_line = Line::from(vec![
            Span::styled(" Search: ", Style::default().fg(ACCENT).bold()),
            Span::styled(format!("{}_", search), Style::default().fg(TEXT)),
        ]);
        f.render_widget(Paragraph::new(search_line).style(Style::default().bg(BG)), chunks[0]);

        // Separator
        f.render_widget(
            Paragraph::new("─".repeat(chunks[1].width as usize))
                .style(Style::default().fg(TEXT_DIM).bg(BG)),
            chunks[1],
        );

        // Category list
        let visible_height = chunks[2].height as usize;
        let scroll_offset = if *selected >= visible_height {
            selected - visible_height + 1
        } else {
            0
        };

        let mut lines: Vec<Line> = Vec::new();
        for (i, &idx) in filtered.iter().enumerate().skip(scroll_offset).take(visible_height) {
            let (code, desc) = categories::ARXIV_CATEGORIES[idx];
            let is_sel = i == *selected;
            let prefix = if is_sel { "► " } else { "  " };
            let style = if is_sel {
                Style::default().fg(BG).bg(ACCENT).bold()
            } else {
                Style::default().fg(TEXT).bg(BG)
            };
            lines.push(Line::from(Span::styled(
                format!("{prefix}{:<16} {desc}", code),
                style,
            )));
        }
        f.render_widget(Paragraph::new(lines).style(Style::default().bg(BG)), chunks[2]);

        // Hints
        let count = filtered.len();
        let hints = format!(" {count} matches  [↑↓] navigate  [Enter] add  [Esc] close");
        f.render_widget(
            Paragraph::new(hints).style(Style::default().fg(TEXT_DIM).bg(SURFACE)),
            chunks[3],
        );
    }
}

// =============================================================================
// Keyword input overlay
// =============================================================================

fn render_keyword_input(f: &mut Frame, app: &App) {
    let area = f.area();
    let w: u16 = 44;
    let h: u16 = 6;
    let x = (area.width.saturating_sub(w)) / 2;
    let y = (area.height.saturating_sub(h)) / 2;
    let overlay = Rect::new(x, y, w, h);

    f.render_widget(Clear, overlay);

    let block = Block::default()
        .title(" Add Keyword ")
        .borders(Borders::ALL)
        .border_style(Style::default().fg(ACCENT))
        .style(Style::default().bg(BG));
    let inner = block.inner(overlay);
    f.render_widget(block, overlay);

    if let Some(crate::app::OverlayMode::KeywordInput { text, weight }) = &app.overlay {
        let chunks = Layout::default()
            .direction(Direction::Vertical)
            .constraints([
                Constraint::Length(1), // keyword
                Constraint::Length(1), // weight
                Constraint::Length(1), // separator
                Constraint::Length(1), // hints
            ])
            .split(inner);

        // Keyword line
        let kw_line = Line::from(vec![
            Span::styled(" Keyword: ", Style::default().fg(ACCENT).bold()),
            Span::styled(format!("{text}_"), Style::default().fg(TEXT)),
        ]);
        f.render_widget(Paragraph::new(kw_line).style(Style::default().bg(BG)), chunks[0]);

        // Weight line
        let filled = *weight as usize;
        let stars = "★".repeat(filled) + &"☆".repeat(5 - filled);
        let wt_line = Line::from(vec![
            Span::styled(" Weight:  ", Style::default().fg(ACCENT).bold()),
            Span::styled(format!("{stars} ({weight})"), Style::default().fg(AUTHOR_HL)),
        ]);
        f.render_widget(Paragraph::new(wt_line).style(Style::default().bg(BG)), chunks[1]);

        // Separator
        f.render_widget(
            Paragraph::new("─".repeat(chunks[2].width as usize))
                .style(Style::default().fg(TEXT_DIM).bg(BG)),
            chunks[2],
        );

        // Hints
        f.render_widget(
            Paragraph::new(" [←→] weight  [Enter] add  [Esc] close")
                .style(Style::default().fg(TEXT_DIM).bg(SURFACE)),
            chunks[3],
        );
    }
}

fn render_author_input(f: &mut Frame, app: &App) {
    let area = f.area();
    let w: u16 = 44;
    let h: u16 = 5;
    let x = (area.width.saturating_sub(w)) / 2;
    let y = (area.height.saturating_sub(h)) / 2;
    let overlay = Rect::new(x, y, w, h);

    f.render_widget(Clear, overlay);

    let block = Block::default()
        .title(" Add Author ")
        .borders(Borders::ALL)
        .border_style(Style::default().fg(ACCENT))
        .style(Style::default().bg(BG));
    let inner = block.inner(overlay);
    f.render_widget(block, overlay);

    if let Some(crate::app::OverlayMode::AuthorInput { text }) = &app.overlay {
        let chunks = Layout::default()
            .direction(Direction::Vertical)
            .constraints([
                Constraint::Length(1), // name
                Constraint::Length(1), // separator
                Constraint::Length(1), // hints
            ])
            .split(inner);

        let name_line = Line::from(vec![
            Span::styled(" Name: ", Style::default().fg(ACCENT).bold()),
            Span::styled(format!("{text}_"), Style::default().fg(TEXT)),
        ]);
        f.render_widget(Paragraph::new(name_line).style(Style::default().bg(BG)), chunks[0]);

        f.render_widget(
            Paragraph::new("─".repeat(chunks[1].width as usize))
                .style(Style::default().fg(TEXT_DIM).bg(BG)),
            chunks[1],
        );

        f.render_widget(
            Paragraph::new(" [Enter] add  [Esc] close")
                .style(Style::default().fg(TEXT_DIM).bg(SURFACE)),
            chunks[2],
        );
    }
}

// =============================================================================
// Stars display helper
// =============================================================================

fn stars_display(n: i64) -> String {
    let filled = n.min(5).max(0) as usize;
    "★".repeat(filled) + &"☆".repeat(5 - filled)
}

// =============================================================================
// Toast overlay
// =============================================================================

fn render_toasts(f: &mut Frame, app: &App, area: Rect) {
    if app.toasts.is_empty() {
        return;
    }

    // Show toasts stacked in the bottom-right corner
    let max_width: u16 = 50;
    let toast_height: u16 = 1;
    let padding_right: u16 = 2;
    let padding_bottom: u16 = 2;

    let visible: Vec<&app::Toast> = app.toasts.iter().rev().take(4).collect();

    for (i, toast) in visible.iter().enumerate() {
        let msg = &toast.message;
        let w = (msg.len() as u16 + 4).min(max_width);
        let x = area.width.saturating_sub(w + padding_right);
        let y = area.height.saturating_sub(
            padding_bottom + (visible.len() as u16 - i as u16) * (toast_height + 1),
        );
        let rect = Rect::new(x, y, w, toast_height + 2);

        let color = if toast.is_error { ERROR_COLOR } else { SUCCESS_COLOR };
        let block = Block::default()
            .borders(Borders::ALL)
            .border_style(Style::default().fg(color))
            .style(Style::default().bg(SURFACE));
        let inner = block.inner(rect);
        f.render_widget(block, rect);

        let text = Paragraph::new(msg.as_str())
            .style(Style::default().fg(color).bg(SURFACE));
        f.render_widget(text, inner);
    }
}

// =============================================================================
// Helpers
// =============================================================================

fn truncate_str(s: &str, max_len: usize) -> String {
    if s.len() <= max_len {
        s.to_string()
    } else {
        format!("{}…", &s[..max_len.saturating_sub(1)])
    }
}

fn build_bar(value: i64, max: i64, width: usize) -> String {
    let filled = if max == 0 {
        0
    } else {
        (value as usize * width / max as usize).min(width)
    };
    let empty = width - filled;
    format!("[{}{}]", "█".repeat(filled), "░".repeat(empty))
}

fn parse_key_findings(json_str: &str) -> Vec<String> {
    serde_json::from_str(json_str).unwrap_or_default()
}

fn word_wrap(text: &str, width: usize) -> Vec<String> {
    if width == 0 {
        return vec![text.to_string()];
    }
    let mut lines = Vec::new();
    for paragraph in text.split('\n') {
        if paragraph.is_empty() {
            lines.push(String::new());
            continue;
        }
        let mut current = String::new();
        for word in paragraph.split_whitespace() {
            if current.is_empty() {
                current = word.to_string();
            } else if current.len() + 1 + word.len() <= width {
                current.push(' ');
                current.push_str(word);
            } else {
                lines.push(current);
                current = word.to_string();
            }
        }
        if !current.is_empty() {
            lines.push(current);
        }
    }
    lines
}
