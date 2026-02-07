# arXiv Explorer - Quick Start Guide

## Installation

```bash
git clone https://github.com/Axect/arXiv_explorer.git
cd arXiv_explorer
uv sync
```

## First Time Setup

```bash
# Add your favorite arXiv categories
axp prefs add-category hep-ph --priority 2
axp prefs add-category cs.AI --priority 1
axp prefs add-category quant-ph

# Add keywords you're interested in
axp prefs add-keyword "quantum" --weight 1.5
axp prefs add-keyword "machine learning" --weight 2.0

# View your settings
axp prefs
```

> **How priority and weight affect recommendations**
>
> - **Category priority** (default: 1) — Priorities are normalized relative to each other. If you set hep-ph=2 and cs.AI=1, hep-ph papers receive twice the category matching bonus. The category score contributes 20% of the total recommendation score.
> - **Keyword weight** (default: 1.0) — Weights are applied directly as a multiplier. A keyword with weight 2.0 contributes twice as much as one with weight 1.0 when found in a paper. The keyword score contributes 10% of the total recommendation score.
> - Categories with no explicit `--priority` default to 1; keywords with no `--weight` default to 1.0.

### Configure AI Provider (Optional)

AI summaries and translations require an external CLI tool. The default is Gemini CLI.

```bash
# View current AI settings
axp config show

# Switch provider (gemini, claude, openai, ollama, opencode, custom)
axp config set-provider claude

# Change display language
axp config set-language ko

# Test that the provider works
axp config test
```

## Daily Workflow

### 1. Fetch Personalized Papers

```bash
# Get papers from the last day (default)
axp daily

# Get papers from the last 7 days, limit to 10
axp daily --days 7 --limit 10

# Include AI-generated summaries
axp daily --days 3 --limit 5 --summarize

# Include detailed summaries (longer analysis)
axp daily --days 3 --limit 5 --summarize --detailed
```

### 2. Search for Topics

```bash
# Search papers
axp search "quantum computing" --limit 5

# Search directly from arXiv API
axp search "neural networks" --arxiv --limit 10
```

### 3. Interact with Papers

```bash
# View a specific paper's details
axp show 2602.04878v1

# View with AI summary
axp show 2602.04878v1 --summary

# View with detailed summary
axp show 2602.04878v1 --summary --detailed

# View with translation
axp show 2602.04878v1 --translate

# View recently liked papers (no ID = list mode)
axp show

# Mark a paper as interesting (with optional note)
axp like 2602.04878v1 --note "Great approach to thermal states"

# Mark a paper as not interesting
axp dislike 2602.04878v1

# Translate a paper
axp translate 2602.04878v1
```

### 4. View Top Recommendations

```bash
# View top 10 recommended papers (scored from your like history)
axp top --limit 10

# With summaries
axp top --limit 5 --summarize
```

### 5. Organize with Reading Lists

```bash
# Create a reading list
axp list create "Weekly Papers" --desc "Papers to read this week"

# Add papers to the list
axp list add "Weekly Papers" 2602.04878v1
axp list add "Weekly Papers" 2602.04800v1

# View all reading lists
axp list

# View papers in a specific list
axp list show "Weekly Papers"

# Update reading status (unread → reading → completed)
axp list status 2602.04878v1 reading
axp list status 2602.04878v1 completed

# Remove a paper from a list
axp list remove "Weekly Papers" 2602.04878v1

# Delete a reading list
axp list delete "Weekly Papers"
```

### 6. Take Notes

```bash
# Add a note to a paper (types: general, question, insight, todo)
axp note add 2602.04878v1 "Need to check implementation details" --type todo
axp note add 2602.04878v1 "Interesting use of Pauli operators" --type insight

# View notes for a specific paper
axp note show 2602.04878v1

# View all notes
axp note

# Filter notes by type
axp note list --type todo
```

### 7. Export

```bash
# Export interesting papers
axp export interesting --format md -o interesting_papers.md
axp export interesting --format json -o interesting_papers.json
axp export interesting --format csv -o interesting_papers.csv

# Export a reading list
axp export list "Weekly Papers" --format md -o weekly.md

# Convert paper to full Markdown documentation (requires arxiv-doc-builder)
axp export markdown 2602.04878v1
```

## TUI Mode

Launch the interactive terminal UI with `axp tui`.

**Tabs** (switch with keys `1`-`5`):
1. **Daily** — Browse personalized papers
2. **Search** — Search arXiv
3. **Lists** — Manage reading lists
4. **Notes** — Browse paper notes
5. **Prefs** — Manage categories, keywords, and AI settings

**Keyboard Shortcuts**:
- `Enter` — Open paper detail modal
- `l` — Like paper
- `d` — Dislike paper
- `s` — Generate AI summary
- `t` — Translate paper
- `n` — Add note
- `a` — Add to reading list
- `r` — Refresh current tab
- `?` — Show all shortcuts
- `q` — Quit

## Helpful Defaults

All subcommand groups have smart defaults when invoked without a subcommand:

```bash
axp prefs      # → axp prefs show
axp list       # → axp list ls
axp note       # → axp note list
axp show       # → shows recently liked papers
```

## Configuration

- **Database**: `~/.config/arxiv-explorer/explorer.db`
- **All data is local** — stored in SQLite, no cloud sync
- **Paper cache** — fetched papers are cached in the DB to avoid redundant API calls

## Recommendation Algorithm

Papers are scored using a weighted combination:
- **Content similarity** (50%): TF-IDF cosine similarity to your liked papers
- **Category matching** (20%): Priority of matched categories
- **Keyword matching** (10%): Weighted keyword presence
- **Recency** (5%): Bonus for papers published in the last 30 days

The more papers you `like`, the better the recommendations become.

## Integration

Works alongside:
- **[arxivterminal](https://github.com/Axect/arxivterminal)**: Reads from `~/.local/share/arxivterminal/papers.db` (read-only)
- **[arxiv-doc-builder](https://github.com/Axect/arxiv-doc-builder)**: Converts papers to Markdown via `axp export markdown`
- **AI Providers**: Gemini CLI, Claude, OpenAI, Ollama, or custom command templates

---

**Need help?** Run any command with `--help`:

```bash
axp --help
axp daily --help
axp config --help
```
