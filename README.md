# arXiv Explorer

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![CI](https://github.com/Axect/arXiv_explorer/actions/workflows/ci.yml/badge.svg)](https://github.com/Axect/arXiv_explorer/actions/workflows/ci.yml)
[![GitHub stars](https://img.shields.io/github/stars/Axect/arXiv_explorer)](https://github.com/Axect/arXiv_explorer/stargazers)

> Your personal research assistant for arXiv — discover, organize, and annotate papers from the terminal.

![arXiv Explorer TUI](tui.png)

## Why arXiv Explorer?

- **Learns from you** — The recommendation engine improves every time you like or dislike a paper. No manual tuning required.
- **No API keys needed** — Fetches papers directly from the public arXiv API. AI features use your locally installed CLI tools.
- **Fully local** — All data lives in a single SQLite file on your machine. No accounts, no cloud sync, no tracking.
- **Terminal-native** — A rich CLI and a full TUI, built with Typer and Textual. Works over SSH.
- **Composable** — Pipe exports to other tools, integrate with arxivterminal or arxiv-doc-builder, or build your own workflow.

## Features

- **Personalized Recommendations** — TF-IDF content similarity + category/keyword/recency scoring
- **Reading Lists** — Organize papers into named lists with reading status tracking
- **Paper Notes** — Attach typed notes (general, question, insight, todo) to any paper
- **AI Summaries** — Generate summaries via configurable AI providers (Gemini, Claude, OpenAI, Ollama, or custom)
- **Translation** — Translate paper titles and abstracts via AI
- **Export** — Markdown, JSON, CSV export for papers, lists, and notes
- **TUI** — Full terminal UI with tabs, detail panels, and keyboard shortcuts
- **Paper Cache** — SQLite-backed cache eliminates redundant arXiv API calls

## Requirements

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) package manager

## Installation

```bash
git clone https://github.com/Axect/arXiv_explorer.git
cd arXiv_explorer
uv sync
```

### Shell Completion

```bash
# fish
axp --install-completion fish

# bash
axp --install-completion bash

# zsh
axp --install-completion zsh
```

## Quick Start

```bash
# 1. Set your research interests
axp prefs add-category hep-ph --priority 2
axp prefs add-keyword "deep learning" --weight 1.5

# 2. Fetch and rank recent papers
axp daily --days 7 --limit 10

# 3. Launch the TUI for the full experience
axp tui
```

See [QUICKSTART.md](QUICKSTART.md) for a full walkthrough.

## TUI

Launch with `axp tui`. The terminal UI provides a full interactive experience with five tabs:

| Tab | Key | Description |
|-----|-----|-------------|
| **Daily** | `1` | Browse personalized papers with detail panel |
| **Search** | `2` | Search arXiv interactively |
| **Lists** | `3` | Manage reading lists and track status |
| **Notes** | `4` | Browse and filter paper notes |
| **Prefs** | `5` | Manage categories, keywords, and AI settings |

**Key bindings**: `Enter` open detail / `l` like / `d` dislike / `s` summarize / `t` translate / `n` note / `a` add to list / `r` refresh / `q` quit

## CLI Reference

### Paper Discovery

| Command | Description |
|---------|-------------|
| `axp daily [-d DAYS] [-l LIMIT] [-s]` | Fetch recent papers with personalized ranking |
| `axp top [-l LIMIT] [-s]` | View top recommended papers (from liked history) |
| `axp search QUERY [-l LIMIT] [-a]` | Search papers (add `-a` for direct arXiv API) |

### Paper Interaction

| Command | Description |
|---------|-------------|
| `axp show [ARXIV_ID] [-s] [-d] [-t]` | View paper details (or recently liked papers) |
| `axp like ARXIV_ID [-n NOTE]` | Mark a paper as interesting |
| `axp dislike ARXIV_ID` | Mark a paper as not interesting |
| `axp translate ARXIV_ID` | Translate a paper's title and abstract |

### Organization

| Command | Description |
|---------|-------------|
| `axp prefs` | View/manage preferred categories and keywords |
| `axp list` | Manage reading lists (create, add, remove, status) |
| `axp note` | Manage paper notes (add, show, list) |
| `axp export` | Export papers/lists to Markdown, JSON, or CSV |

### Configuration

| Command | Description |
|---------|-------------|
| `axp config show` | View current AI provider settings |
| `axp config set-provider PROVIDER` | Change AI provider (gemini, claude, openai, ollama, custom) |
| `axp config set-language LANG` | Change display language (en, ko) |
| `axp config test` | Test current provider connection |

## AI Providers

AI features (summarization and translation) call external CLI tools via subprocess — no API keys are stored in the application.

| Provider | CLI command | Invocation | Default model |
|----------|------------|------------|---------------|
| **Gemini** | `gemini` | `gemini -m MODEL -p PROMPT` | (provider default) |
| **Claude** | `claude` | `claude --model MODEL -p PROMPT --output-format text` | (provider default) |
| **Codex** (OpenAI) | `codex` | `codex --model MODEL --prompt PROMPT` | (provider default) |
| **Ollama** | `ollama` | `ollama run MODEL PROMPT` | `llama3.2` |
| **OpenCode** | `opencode` | `opencode run --model MODEL PROMPT` | (provider default) |
| **Custom** | user-defined | template with `{prompt}` and optional `{model}` placeholders | — |

```bash
axp config set-provider claude          # Switch provider
axp config set-model "claude-sonnet-4-5-20250929"  # Override model
axp config test                         # Verify connection
```

## Architecture

```
src/arxiv_explorer/
  core/       # Data models, database schema, configuration
  services/   # Business logic (recommendation, search, summarization, caching)
  cli/        # Typer-based CLI commands
  tui/        # Textual-based terminal UI (tabs: Daily, Search, Lists, Notes, Prefs)
  utils/      # Display helpers
```

**Recommendation** — TF-IDF cosine similarity (50%) + category priority (20%) + keyword matching (10%) + recency bonus (5%).

## Comparison

Different tools serve different workflows. [arxiv-sanity-lite](https://github.com/karpathy/arxiv-sanity-lite) pioneered TF-IDF-based paper recommendations and remains the gold standard for web-based discovery. arXiv Explorer brings a similar approach to the terminal.

| | arxiv-sanity-lite | arXiv Explorer |
|---|---|---|
| **Interface** | Web UI | CLI + TUI (works over SSH) |
| **Recommendation** | TF-IDF (web) | TF-IDF (local, learns per session) |
| **Setup** | Server deployment | `uv sync` and go |
| **Data storage** | PostgreSQL + S3 | Single SQLite file |
| **AI summaries** | No | Yes (pluggable providers) |
| **Reading lists & notes** | No | Yes |
| **Export** | No | Markdown, JSON, CSV |
| **Best for** | Browsing with a team | Solo terminal workflow |

## Integration

- **[arxivterminal](https://github.com/Axect/arxivterminal)** — Reads from its local paper database (read-only)
- **[arxiv-doc-builder](https://github.com/Axect/arxiv-doc-builder)** — Converts papers to Markdown via `axp export markdown`

## Data Storage

All data is stored locally in SQLite at `~/.config/arxiv-explorer/explorer.db`. No cloud sync.

## Contributing

Contributions are welcome! See [CONTRIBUTING.md](.github/CONTRIBUTING.md) for development setup and guidelines.

## License

[MIT](LICENSE)
