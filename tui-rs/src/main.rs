use std::io;
use std::time::Duration;

use crossterm::{
    event::{self, Event, KeyEventKind},
    execute,
    terminal::{disable_raw_mode, enable_raw_mode, EnterAlternateScreen, LeaveAlternateScreen},
};
use ratatui::{
    prelude::*,
    widgets::{Block, Borders, Cell, Paragraph, Row, Table, TableState, Wrap},
};

mod app;
mod commands;
mod db;
mod events;

use app::{App, Tab};

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
    execute!(stdout, EnterAlternateScreen)?;
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
    execute!(terminal.backend_mut(), LeaveAlternateScreen)?;

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
                    if let Ok(Event::Key(key)) = event::read() {
                        if key.kind == KeyEventKind::Press {
                            if events::handle_key(&mut app, key.code) {
                                return Ok(());
                            }
                        }
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
        Tab::Daily => " D/f Days  N/n Limit  r Fetch  l Like  d Dislike  b Bookmark  q Quit",
        Tab::Search => " ↑/k ↓/j Navigate  / Search  q Quit",
        Tab::Lists => " ↑/k ↓/j Navigate  Enter Open  q Quit",
        Tab::Notes => " ↑/k ↓/j Navigate  q Quit",
        Tab::Prefs => " ↑/k ↓/j Select  ←/h →/l Adjust  q Quit",
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
            "No papers loaded. Days={} Limit={}  Press 'r' to fetch.  D/f=Days  N/n=Limit",
            app.daily.days, app.daily.limit
        ))
            .style(Style::default().fg(TEXT_DIM).bg(BG))
            .alignment(Alignment::Center);
        f.render_widget(msg, area);
        return;
    }

    // Split: 60% table | 40% detail panel
    let chunks = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([Constraint::Percentage(60), Constraint::Percentage(40)])
        .split(area);

    render_daily_table(f, app, chunks[0]);
    render_daily_detail(f, app, chunks[1]);
}

fn render_daily_table(f: &mut Frame, app: &mut App, area: Rect) {
    // Status bar + table
    let sub = Layout::default()
        .direction(Direction::Vertical)
        .constraints([Constraint::Length(1), Constraint::Min(0)])
        .split(area);

    let total = app.daily.author_papers.len() + app.daily.scored_papers.len();
    let status = format!(
        " Days:{} Limit:{} │ {} papers │ D/f:Days N/n:Limit r:Fetch",
        app.daily.days, app.daily.limit, total
    );
    let status_p = Paragraph::new(status)
        .style(Style::default().fg(TEXT_DIM).bg(SURFACE));
    f.render_widget(status_p, sub[0]);

    let area = sub[1];

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

    let table = Table::new(rows, widths)
        .header(header)
        .block(
            Block::default()
                .title(" Papers ")
                .borders(Borders::ALL)
                .border_style(Style::default().fg(ACCENT))
                .style(Style::default().bg(BG)),
        )
        .row_highlight_style(Style::default().bg(ACCENT).fg(BG).bold())
        .column_spacing(1);

    let mut table_state = TableState::default();
    table_state.select(table_selected);

    f.render_stateful_widget(table, area, &mut table_state);
}

fn render_daily_detail(f: &mut Frame, app: &App, area: Rect) {
    let block = Block::default()
        .title(" Detail ")
        .borders(Borders::ALL)
        .border_style(Style::default().fg(TEXT_DIM))
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
        .wrap(Wrap { trim: true });

    f.render_widget(paragraph, inner);
}

// =============================================================================
// Placeholder tab renderers
// =============================================================================

fn render_search(f: &mut Frame, _app: &App, area: Rect) {
    let block = Block::default()
        .title(" Search ")
        .borders(Borders::ALL)
        .border_style(Style::default().fg(ACCENT))
        .style(Style::default().bg(BG));
    let inner = block.inner(area);
    f.render_widget(block, area);

    let msg = Paragraph::new("Press [/] to search for papers. (Search coming in Task 4)")
        .style(Style::default().fg(TEXT_DIM).bg(BG))
        .alignment(Alignment::Center);
    f.render_widget(msg, inner);
}

fn render_lists(f: &mut Frame, _app: &App, area: Rect) {
    let block = Block::default()
        .title(" Reading Lists ")
        .borders(Borders::ALL)
        .border_style(Style::default().fg(ACCENT))
        .style(Style::default().bg(BG));
    let inner = block.inner(area);
    f.render_widget(block, area);

    let msg = Paragraph::new("Press [n] to create a new list. (Lists coming in Task 4)")
        .style(Style::default().fg(TEXT_DIM).bg(BG))
        .alignment(Alignment::Center);
    f.render_widget(msg, inner);
}

fn render_notes(f: &mut Frame, _app: &App, area: Rect) {
    let block = Block::default()
        .title(" Notes ")
        .borders(Borders::ALL)
        .border_style(Style::default().fg(ACCENT))
        .style(Style::default().bg(BG));
    let inner = block.inner(area);
    f.render_widget(block, area);

    let msg = Paragraph::new("Press [n] to add a note. (Notes coming in Task 4)")
        .style(Style::default().fg(TEXT_DIM).bg(BG))
        .alignment(Alignment::Center);
    f.render_widget(msg, inner);
}

fn render_prefs(f: &mut Frame, app: &App, area: Rect) {
    let block = Block::default()
        .title(" Preferences ")
        .borders(Borders::ALL)
        .border_style(Style::default().fg(ACCENT))
        .style(Style::default().bg(BG));
    let inner = block.inner(area);
    f.render_widget(block, area);

    let labels = ["Content", "Category", "Keyword", "Recency"];
    let weights = app.prefs.weights;

    let mut lines: Vec<Line> = Vec::new();
    lines.push(Line::from(Span::styled(
        "Recommendation Weights  (←/h  →/l to adjust)",
        Style::default().fg(ACCENT).bold(),
    )));
    lines.push(Line::default());

    for (i, label) in labels.iter().enumerate() {
        let is_sel = app.prefs.selected == i;
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

    lines.push(Line::default());
    lines.push(Line::from(vec![
        Span::styled("Provider: ", Style::default().fg(ACCENT).bold()),
        Span::styled(app.prefs.provider.clone(), Style::default().fg(TEXT)),
    ]));
    lines.push(Line::from(vec![
        Span::styled("Language: ", Style::default().fg(ACCENT).bold()),
        Span::styled(app.prefs.language.clone(), Style::default().fg(TEXT)),
    ]));

    let paragraph = Paragraph::new(lines).style(Style::default().bg(BG));
    f.render_widget(paragraph, inner);
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
