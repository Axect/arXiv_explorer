# arXiv Explorer — Ratatui TUI Port Design Spec

**Date:** 2026-04-06

---

## Overview

Port the TUI from Python Textual to Rust Ratatui. The Python service layer and CLI remain unchanged. The Rust TUI reads/writes SQLite directly for all local operations and calls the Python CLI as subprocess for complex tasks (arXiv fetch, AI summarize/translate/review, TF-IDF recommendation).

---

## Architecture

### Project Structure (Monorepo)

```
arXiv_explorer/
├── src/arxiv_explorer/       # Python (CLI, services) — unchanged
├── tui-rs/                   # NEW: Rust Ratatui TUI
│   ├── Cargo.toml
│   └── src/
│       ├── main.rs           # Entry point, terminal setup
│       ├── app.rs            # App state + event loop
│       ├── events.rs         # Keyboard/mouse event handling
│       ├── db/               # rusqlite direct access
│       │   ├── mod.rs
│       │   ├── models.rs     # DB row → Rust struct mappings
│       │   ├── papers.rs     # papers table queries
│       │   ├── preferences.rs # categories, keywords, authors
│       │   ├── lists.rs      # reading_lists + reading_list_papers
│       │   ├── interactions.rs # paper_interactions (like/dislike)
│       │   ├── notes.rs      # paper_notes
│       │   ├── settings.rs   # app_settings
│       │   └── cache.rs      # summaries, translations, review sections
│       ├── commands/          # Python subprocess calls
│       │   ├── mod.rs
│       │   ├── fetch.rs      # uv run axp daily/search --json
│       │   └── ai.rs         # summarize, translate, review
│       ├── ui/               # Tab-level rendering
│       │   ├── mod.rs
│       │   ├── daily.rs
│       │   ├── search.rs
│       │   ├── lists.rs
│       │   ├── notes.rs
│       │   ├── prefs.rs
│       │   └── jobs.rs       # Jobs overlay panel
│       └── widgets/          # Reusable custom widgets
│           ├── mod.rs
│           ├── paper_table.rs
│           ├── paper_panel.rs
│           └── tabs.rs
├── pyproject.toml
└── CLAUDE.md
```

### Data Flow

```
[Rust TUI] ──rusqlite──> [SQLite DB] <──sqlite3── [Python Services]
    │
    └──tokio::process──> [uv run axp <command> --json]
                              │
                              └──> DB write, arXiv API, AI provider
```

- **Read**: Rust queries DB directly (papers, preferences, lists, notes, settings, interactions, cached summaries/translations/reviews)
- **Simple write**: Rust INSERT/UPDATE/DELETE directly (like, dislike, bookmark, add category/keyword/author, create folder, move/copy, update settings)
- **Complex operations**: `tokio::process::Command` calls Python CLI with `--json` flag

### Dependencies

```toml
[dependencies]
ratatui = "0.29"
crossterm = "0.28"
tokio = { version = "1", features = ["full"] }
rusqlite = { version = "0.32", features = ["bundled"] }
serde = { version = "1", features = ["derive"] }
serde_json = "1"
```

---

## TUI Layout

### Overall Frame

```
┌─ arXiv Explorer ──────────────────────────────────────────┐
│ [1]Daily  [2]Search  [3]Lists  [4]Notes  [5]Prefs        │
├───────────────────────────────────────────────────────────┤
│                                                           │
│                   (Active Tab Content)                     │
│                                                           │
├───────────────────────────────────────────────────────────┤
│ [l]ike [d]islike [s]umm [t]rans [w]review [b]mark [j]obs │
└───────────────────────────────────────────────────────────┘
```

- Top: tab bar (1-5 keys, active tab highlighted)
- Center: tab content (fills remaining space)
- Bottom: context-sensitive key hints (vary per tab)

### Daily Tab

```
┌─ Days: 7 ─ Limit: 20 ─ [r]Fetch ─────────────────────────┐
│ ── From Your Authors ──────────────────────────────────── │
│ ★ 1  2604.01234  Quantum Gravity Re...  hep-th     0.82  │
│ ── Recommended ────────────────────────────────────────── │
│   2  2604.01235  Neural ODE for Ph...   cs.ML      0.75  │
│ ✓ 3  2604.01236  Dark Matter Bound...   hep-ph     0.68  │
├───────────────────────────────────────────────────────────┤
│ Title: Quantum Gravity Revisited with Modern Methods      │
│ Authors: K. Lee, J. Park | hep-th, gr-qc | 2026-04-05   │
│ Abstract: We revisit the quantum gravity problem using... │
└───────────────────────────────────────────────────────────┘
```

- Filter bar at top (Days/Limit editable, `r` to fetch)
- Paper table with author section header, color-highlighted rows
- Detail panel below for selected paper
- `Enter` opens full paper detail popup

### Search Tab

```
┌─ Search: [________________] ──────────────────────────────┐
│ #  ID             Title                   Cat     Score   │
│ 1  2604.01234     Quantum Computing...    cs.QI   0.72   │
├───────────────────────────────────────────────────────────┤
│ (Paper detail panel)                                      │
└───────────────────────────────────────────────────────────┘
```

### Lists Tab

```
┌─ Reading Lists ──────────────────┬─ Like — 3 papers ──────┐
│ 📋 Like (3)                      │ #  ID          Title    │
│ 📋 Dislike (1)                   │ 1  2604.01234  Quant... │
│ ─────────────                    │ 2  2604.01235  Neura... │
│ 📁 202604 (5)                    │ 3  2604.01236  Dark ... │
│ 📋 Quantum Papers (2)           │                         │
│ [n]ew [f]older [Del] [e]rename  │ [Del] [s]ort [m]ove     │
└──────────────────────────────────┴─────────────────────────┘
```

### Notes Tab

```
┌─ Notes ──────────────────────────┬─ Note Detail ──────────┐
│ 2604.01234 - General             │ (Note content)          │
│ 2604.01235 - Question            │                         │
└──────────────────────────────────┴─────────────────────────┘
```

### Prefs Tab

```
┌─ Categories ──────┬─ Keywords ────────┬─ Authors ─────────┐
│ hep-ph      3     │ deep learn  ★★★★★ │ K. Lee            │
│ cs.AI       2     │ quantum     ★★★☆☆ │ J. Park           │
│ [Browse] Pri:[1]  │ KW:[___] ★:[3]    │ Name:[________]   │
│ Enter:Add Del:Rm  │ Enter:Add Del:Rm  │ Enter:Add Del:Rm  │
├─ Weights ─────────────────────┬─ Config ──────────────────┤
│ Content   [████████████░░] 60%│ Provider: gemini          │
│ Category  [████░░░░░░░░░░] 20%│ Language: ko              │
│ Keyword   [███░░░░░░░░░░░] 15%│                           │
│ Recency   [█░░░░░░░░░░░░░]  5%│                           │
│ ←→:Adjust  [r]eset            │                           │
└───────────────────────────────┴───────────────────────────┘
```

### Jobs Panel (Overlay)

Toggle with `j`:

```
┌─ Background Jobs ─────────────────────────────────────────┐
│ ⟳ REVIEW    2604.01237  Quantum Gravity...        1m 23s  │
│ ✓ SUMMARY   2604.01235  Neural ODE...             Done    │
│ ✗ TRANSLATE  2604.01236  Dark Matter...    Failed: timeout │
│ [x] Cancel  [c] Clear completed  [Esc] Close             │
└───────────────────────────────────────────────────────────┘
```

---

## Color Palette (Catppuccin Mocha)

| Purpose | Color |
|---------|-------|
| Background | `#1e1e2e` |
| Surface | `#313244` |
| Text | `#cdd6f4` |
| Text (dim) | `#6c7086` |
| Accent | `#89b4fa` |
| Author highlight (full row) | `#f9e2af` |
| Bookmark highlight (full row) | `#a6e3a1` |
| Error | `#f38ba8` |
| Success | `#a6e3a1` |

---

## Python CLI Integration Protocol

### `--json` Flag

Add `--json` flag to Python CLI commands for machine-readable output:

```bash
uv run axp daily --days 7 --limit 20 --json
uv run axp search "query" --json
uv run axp show --json
```

JSON output format for daily:

```json
{
  "author_papers": [
    {"arxiv_id": "2604.01234", "title": "...", "score": 0.82, "authors": ["K. Lee"], "categories": ["hep-th"], "published": "2026-04-05", "abstract": "..."}
  ],
  "scored_papers": [...]
}
```

### Direct DB Operations (Rust)

**Reads** — all SELECT queries on: `papers`, `preferred_categories`, `keyword_interests`, `preferred_authors`, `reading_lists`, `reading_list_papers`, `paper_interactions`, `paper_notes`, `app_settings`, `paper_summaries`, `paper_translations`, `paper_review_sections`

**Writes** — INSERT/UPDATE/DELETE on: `paper_interactions` (like/dislike + Like/Dislike list sync), `reading_lists` + `reading_list_papers` (folder/list/bookmark CRUD), `preferred_categories`, `keyword_interests`, `preferred_authors`, `app_settings`, `paper_notes`

### AI Operations (Subprocess)

Summarize, translate, review run as subprocess. Results are read from DB after completion (existing cache tables):

```rust
// 1) Spawn subprocess (writes result to DB)
Command::new("uv").args(["run", "axp", "review", arxiv_id]).spawn();
// 2) On completion, read from DB
SELECT * FROM paper_review_sections WHERE arxiv_id = ?;
```

No `--json` flag needed for AI commands — the DB cache IS the output.

---

## App State and Event Loop

### App State

```rust
pub struct App {
    pub active_tab: Tab,
    pub show_jobs: bool,
    pub db_path: PathBuf,
    pub daily: DailyState,
    pub search: SearchState,
    pub lists: ListsState,
    pub notes: NotesState,
    pub prefs: PrefsState,
    pub jobs: Vec<Job>,
    pub event_rx: mpsc::UnboundedReceiver<AppEvent>,
    pub event_tx: mpsc::UnboundedSender<AppEvent>,
}
```

### Event Loop (tokio + crossterm)

```rust
loop {
    terminal.draw(|f| ui::render(f, &app))?;
    tokio::select! {
        Some(event) = crossterm_events.next() => {
            handle_input(&mut app, event);
        }
        Some(app_event) = app.event_rx.recv() => {
            handle_app_event(&mut app, app_event);
        }
    }
    if app.should_quit { break; }
}
```

### AppEvent Channel

```rust
pub enum AppEvent {
    DailyFetched { author_papers: Vec<Paper>, scored_papers: Vec<Paper> },
    SearchResults { papers: Vec<Paper> },
    JobCompleted { job_id: String },
    JobFailed { job_id: String, error: String },
    Toast { message: String, severity: Severity },
}
```

### Async Task Pattern

```rust
fn fetch_daily(tx: mpsc::UnboundedSender<AppEvent>, days: u32, limit: u32) {
    tokio::spawn(async move {
        let output = Command::new("uv")
            .args(["run", "axp", "daily", "--days", &days.to_string(),
                   "--limit", &limit.to_string(), "--json"])
            .output().await;
        match output {
            Ok(out) => {
                let result: DailyResult = serde_json::from_slice(&out.stdout).unwrap();
                let _ = tx.send(AppEvent::DailyFetched {
                    author_papers: result.author_papers,
                    scored_papers: result.scored_papers,
                });
            }
            Err(e) => {
                let _ = tx.send(AppEvent::Toast {
                    message: e.to_string(),
                    severity: Severity::Error,
                });
            }
        }
    });
}
```

---

## Build and Execution

### Running

```bash
# Direct
cd tui-rs && cargo run --release

# Via Python CLI
uv run axp tui
```

### DB Path Resolution

Rust binary resolves DB path in order:
1. `AXP_DB` environment variable
2. `~/.config/arxiv-explorer/explorer.db` (XDG default)

### Python CLI Integration

`uv run axp tui` finds and executes the Rust binary:
1. Check `axp-tui` on PATH
2. Check `tui-rs/target/release/axp-tui` relative to project
3. Fallback to existing Textual TUI if Rust binary not found

### Existing Textual TUI

Python TUI code is NOT deleted. Serves as fallback during transition. Can be removed once Ratatui TUI is stable.

### Testing

- **Rust unit tests**: DB module read/write correctness, JSON parsing
- **Integration tests**: temp DB → Python CLI populates → Rust reads/verifies
- **Existing Python tests**: unchanged (`uv run pytest`)
