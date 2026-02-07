# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

arXiv Explorer is a personalized paper recommendation and management system with a CLI interface. It uses TF-IDF-based content filtering combined with category priorities, keyword matching, and recency scoring to recommend papers from arXiv.

## Development Commands

### Setup and Installation
```bash
uv sync                    # Install dependencies
uv run axp --help          # Test CLI
```

### Running the Application
```bash
uv run axp daily --days 7 --limit 10        # Get daily papers
uv run axp search "quantum computing"       # Search papers
uv run axp prefs add-category hep-ph        # Add category preference
```

### Testing
```bash
uv run pytest                               # Run all tests
uv run pytest tests/test_recommendation.py  # Run specific test
uv run pytest --cov                         # Run with coverage
```

## Architecture

### Layered Structure

The codebase follows a clean 3-layer architecture:

**Core Layer** (`src/arxiv_explorer/core/`):
- `models.py`: Immutable dataclasses for all entities (Paper, PreferredCategory, ReadingList, etc.)
- `database.py`: SQLite schema and connection management with context managers
- `config.py`: Global configuration with XDG-compliant paths

**Services Layer** (`src/arxiv_explorer/services/`):
- `arxiv_client.py`: arXiv API client with rate limiting (3s delays, HTTPS required)
- `recommendation.py`: TF-IDF recommendation engine (singleton pattern via `get_recommendation_engine()`)
- `preference_service.py`: User preference CRUD operations
- `paper_service.py`: Orchestrates arxiv_client and recommendation engine
- `summarization.py`: Gemini CLI integration with SQLite caching
- `reading_list_service.py`, `notes_service.py`: Feature-specific services

**CLI Layer** (`src/arxiv_explorer/cli/`):
- `main.py`: Typer app entry point, registers all commands
- Individual command modules: `daily.py`, `search.py`, `preferences.py`, `lists.py`, `notes.py`, `export.py`
- All CLI modules use `invoke_without_command=True` pattern for smart defaults

### Key Architectural Patterns

**Recommendation Algorithm** (`services/recommendation.py`):
- Builds user profile from liked papers using TF-IDF vectorization
- Scores papers using weighted combination:
  - Content similarity: 0.5 (cosine similarity to user profile)
  - Category matching: 0.2 (normalized by priority)
  - Keyword matching: 0.1 (weighted keyword presence)
  - Recency bonus: 0.05 (papers < 30 days old)
- Configurable weights in `core/config.py`

**Smart CLI Defaults**:
- `axp prefs` → shows preferences (no subcommand needed)
- `axp list` → shows all reading lists
- `axp note` → shows all notes
- `axp show` → shows recently liked papers
- Implemented via `@app.callback()` checking `ctx.invoked_subcommand`

**Database Design**:
- Single SQLite DB at `~/.config/arxiv-explorer/explorer.db`
- Optional read-only access to arxivterminal DB at `~/.local/share/arxivterminal/papers.db`
- Tables: preferred_categories, paper_interactions, paper_summaries, reading_lists, reading_list_papers, paper_notes, keyword_interests
- Uses sqlite3.Row for dict-like access

**Caching Strategy**:
- Gemini summaries cached in `paper_summaries` table to avoid redundant API calls
- TF-IDF vectorizer fitted once per session, reused for all scoring

## Important Implementation Details

### arXiv API Integration
- **MUST use HTTPS**: `https://export.arxiv.org/api/query` (HTTP redirects)
- **Rate limiting required**: 3-second delays between requests
- **Disable proxy**: `httpx.Client(trust_env=False)` to avoid socks:// proxy errors
- **Parsing**: Uses feedparser for Atom feed parsing

### CLI UX Patterns
When adding new CLI commands:
1. Use `typer.Argument(None, ...)` for optional args with helpful defaults
2. Add `invoke_without_command=True` for command groups
3. Implement `@app.callback()` to handle no-subcommand case
4. Provide helpful error messages with example commands

### Service Layer Patterns
- Services instantiate their own dependencies (e.g., `PaperService` creates `ArxivClient`)
- Use context managers for database connections: `with get_connection() as conn:`
- Return domain models (dataclasses), not raw database rows
- Keep services stateless except for caching (recommendation engine)

### Adding New Features
**New paper interaction type**:
1. Add enum to `InteractionType` in `core/models.py`
2. Add methods to `PreferenceService`
3. Add CLI command in appropriate module

**New recommendation factor**:
1. Modify scoring weights in `Config` dataclass
2. Update `score_papers()` in `RecommendationEngine`
3. Weight should sum to ≤1.0 with existing weights

**New export format**:
1. Add elif branch in `export.py` command functions
2. Follow existing pattern: fetch data → format → output/save

## Data Storage

- **Config/DB**: `~/.config/arxiv-explorer/explorer.db`
- **Integration**: `~/.local/share/arxivterminal/papers.db` (read-only, optional)
- **No cloud sync**: All data local-only

## External Integrations

**Gemini CLI**:
- Called via subprocess: `gemini -p <prompt>`
- Expects JSON output with `summary_short` and `key_findings` fields
- Handles both plain JSON and markdown code blocks (```json)

**arxivterminal**:
- Can read from existing arxivterminal database (if present)
- Connection via `get_arxivterminal_connection()` with read-only mode

**arxiv-doc-builder**:
- Integration in `export.py` → `export_markdown` command
- Calls conversion script via `uv run` subprocess
