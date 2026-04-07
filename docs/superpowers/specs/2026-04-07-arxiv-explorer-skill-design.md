# arXiv Explorer Skill — Design Spec

**Date:** 2026-04-07
**Status:** Draft
**Type:** Global Claude Code Skill

## Overview

A global Claude Code skill (`~/.claude/skills/arxiv-explorer/`) that orchestrates the `axp` CLI to provide a conversational interface for personalized arXiv paper discovery, review, and management. Claude handles all AI tasks (review, translation, keyword extraction) directly, while `axp` manages data persistence, arXiv API calls, and recommendation scoring.

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Skill location | `~/.claude/skills/arxiv-explorer/` (global) | Available in any project context |
| Base directory | `~/.local/share/arxiv-explorer/` | XDG standard, consolidates DB + files |
| Architecture | Single skill + progressive disclosure (Approach C) | Single entry point, on-demand reference loading |
| AI provider for review/translation | Claude directly (not axp's providers) | Already in Claude session, higher quality |
| Storage | File-based content + DB metadata | Human-readable files, TUI queryable metadata |
| Category mapping | Claude interprets natural language → arXiv taxonomy | No extra code, leverages LLM capability |
| Review mode | Full (15 sections) by default, quick on request | User override, sensible default |
| Translation language | `axp config` setting default, call-time override | Flexible without extra config |

## Features (9 total)

### F1: Paper Like + Keyword Auto-extraction

**Trigger:** User mentions arXiv IDs as interesting, wants to like papers
**Workflow:**
1. Run `uv run axp like {arxiv_id}` for each paper
2. Run `uv run axp show {arxiv_id} --json` to get title/abstract
3. Claude extracts 3-5 domain-specific keywords from title+abstract
4. Present keywords to user for confirmation
5. On approval: `uv run axp prefs add-keyword {keyword} --weight {1-5}`

**Keyword weight heuristic:**
- Paper's primary topic → weight 4-5
- Secondary/methodological terms → weight 2-3

### F2: Category Management

**Trigger:** User wants to add/remove research interest categories
**Workflow:**
1. User provides natural language (e.g., "고에너지 물리", "machine learning")
2. Claude uses its built-in knowledge of arXiv taxonomy (physics, cs, math, etc.) to map natural language to category codes
3. Presents candidate categories with codes and descriptions (e.g., `hep-ph: High Energy Physics - Phenomenology`)
4. User confirms selection
5. Run `uv run axp prefs add-category {code} --priority {1-5}`

**Edge cases:**
- Ambiguous input → present multiple candidates, ask user to choose
- Exact code provided (e.g., `cs.LG`) → verify it exists, skip confirmation if exact match
- Removal: `uv run axp prefs remove-category {code}`

### F3: Daily Fetch (Today's arXiv)

**Trigger:** User asks for today's papers, daily recommendations, "what's new"
**Workflow:**
1. Run `uv run axp daily --days {N} --limit {L} --json` (default: days=1, limit=10)
2. Parse JSON output
3. Present as formatted table:

| # | Score | Title | Authors | Category |
|---|-------|-------|---------|----------|
| 1 | 0.85 | ... | ... | hep-ph |

4. User can then like, review, or explore any paper from results

### F4: Detailed Review + Translation

**Trigger:** User asks to review a specific paper
**Workflow:**
1. `uv run axp show {arxiv_id} --json` → get metadata
2. Attempt full text: run arxiv-doc-builder skill if available → `papers/{arxiv_id}/{arxiv_id}.md`
3. Claude writes review based on abstract (or full text if available)
4. **Full mode** (default) — 15 sections per `ReviewSectionType`:
   - Executive Summary, Key Contributions, Section Summaries, Methodology, Math Formulations, Figures, Tables, Experimental Results, Reproducibility, Strengths & Weaknesses, Impact & Significance, Related Work, Glossary, Questions, Reading Guide
5. **Quick mode** (on request) — 4 sections:
   - Executive Summary, Key Contributions, Methodology, Strengths & Weaknesses
6. Save to `~/.local/share/arxiv-explorer/reviews/{arxiv_id}/review.md`
7. Translate to target language → `review_{lang}.md`
   - Default language: `uv run axp config show` → read `language` field
   - Override: user specifies at call time
8. Record metadata in DB (existence flag, file path, generation date)

**Review markdown template:**
```markdown
# Review: {title}

**arXiv:** {arxiv_id}
**Authors:** {authors}
**Categories:** {categories}
**Published:** {date}
**Source:** abstract | full_text
**Generated:** {timestamp}

---

## Executive Summary
...

## Key Contributions
...

(remaining sections)
```

### F5: Paperbanana Integration

**Trigger:** Automatically during review if paperbanana skill is available
**Workflow:**
1. During review (F4), check if paperbanana skill exists
2. If available: identify key concepts that benefit from visual explanation
   - Methodology/architecture diagrams
   - Data flow / pipeline diagrams
   - Key result comparison plots
3. Invoke paperbanana to generate plots
4. Save to `~/.local/share/arxiv-explorer/reviews/{arxiv_id}/plots/`
5. Embed image references in the review markdown

**Conditional:** If paperbanana is not installed, skip silently — review still complete without plots.

### F6: Related Paper Discovery

**Trigger:** User asks for similar/related papers to a specific paper
**Workflow:**
1. `uv run axp show {arxiv_id} --json` → get categories, title, abstract
2. Claude extracts key search terms from the paper
3. `uv run axp search "{search_terms}" --limit 10 --json`
4. Optionally also: `uv run axp daily --days 30 --limit 20 --json` filtered by same categories
5. Present results sorted by recommendation score
6. User can like or review any result

### F7: Weekly/Monthly Digest

**Trigger:** User asks for a summary of recent activity ("이번 주 정리", "monthly digest")
**Workflow:**
1. `uv run axp export interesting --format json` → get all liked papers
2. Filter by date range (week: last 7 days, month: last 30 days)
3. Collect existing reviews from `~/.local/share/arxiv-explorer/reviews/`
4. Claude writes a digest report:
   - Papers liked this period (with brief descriptions)
   - Reviews completed
   - Key themes/trends across papers
   - Suggested next reads (based on gaps)
5. Save to `~/.local/share/arxiv-explorer/digests/{period}.md` (e.g., `2026-W15.md`, `2026-04.md`)
6. If `md2pdf-typora` skill available → auto-convert to PDF

### F8: Auto Keyword Extraction (bundled with F1)

Integrated into F1 workflow — not a standalone feature. See F1.

### F9: Paper Notes

**Trigger:** User makes observations, asks questions, or notes insights about a paper during conversation
**Workflow:**
1. Detect contextual paper reference (from recent review, daily fetch, etc.)
2. Classify note type: `general` | `question` | `insight` | `todo`
3. `uv run axp note add {arxiv_id} --type {type} "{content}"`
4. Confirm to user

## Base Directory Layout

```
~/.local/share/arxiv-explorer/
├── explorer.db                 # SQLite database
├── papers/                     # arxiv-doc-builder output
│   └── {arxiv_id}/
│       ├── {arxiv_id}.md
│       ├── source/
│       └── figures/
├── reviews/                    # Claude-generated reviews
│   └── {arxiv_id}/
│       ├── review.md           # Original (English)
│       ├── review_{lang}.md    # Translated version
│       └── plots/              # paperbanana output
│           └── *.png
└── digests/                    # Periodic summaries
    ├── 2026-W15.md
    └── 2026-04.md
```

## DB Migration

**Goal:** Move DB from `~/.config/arxiv-explorer/explorer.db` to `~/.local/share/arxiv-explorer/explorer.db`

**`scripts/migrate_db.py` logic:**
```
1. new_path = ~/.local/share/arxiv-explorer/explorer.db
2. old_path = ~/.config/arxiv-explorer/explorer.db
3. if new_path exists → done (already migrated)
4. if old_path exists → mkdir -p new_dir, cp old_path new_path
   → print "Migrated DB from {old_path} to {new_path}"
   → leave old_path intact as backup (do NOT delete)
5. if neither exists → skip (axp will create fresh DB)
```

**`axp` code change required:** Modify `core/config.py` `Config.default()` to use `~/.local/share/arxiv-explorer/` as DB path instead of `~/.config/arxiv-explorer/`.

## Skill File Structure

```
~/.claude/skills/arxiv-explorer/
├── SKILL.md                    # Orchestrator (< 300 lines)
├── references/
│   ├── like-papers.md          # F1 + F8: like + keyword extraction
│   ├── categories.md           # F2: category management
│   ├── daily-fetch.md          # F3: daily arxiv
│   ├── review.md               # F4 + F5: review + paperbanana
│   ├── related-papers.md       # F6: related paper discovery
│   ├── digest.md               # F7: weekly/monthly digest
│   └── notes.md                # F9: paper notes
└── scripts/
    └── migrate_db.py           # DB location migration
```

### SKILL.md Responsibilities

**Frontmatter:**
```yaml
---
name: arxiv-explorer
description: >
  Personalized arXiv paper discovery, review, and management. Use when the user
  mentions arXiv papers, wants paper recommendations, asks for daily papers,
  wants to like/review/search papers, manage research categories or keywords,
  generate paper reviews with translation, create weekly/monthly research digests,
  or take notes on papers. Orchestrates the axp CLI with Claude-powered analysis.
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, Agent, Skill
user-invocable: true
---
```

**Body structure:**
1. **Quick Reference** — one-liner per feature showing trigger → action
2. **Common Rules:**
   - Base directory: `~/.local/share/arxiv-explorer/`
   - CLI calls via `axp` (if globally installed via `uv tool install`) or `uv run --project {project_dir} axp` as fallback
   - Use `--json` flag when parsing CLI output (available on: `daily`, `search`, `show`)
   - DB migration: run `scripts/migrate_db.py` on first use
   - Review files saved to `reviews/{arxiv_id}/`
   - Digest files saved to `digests/`
3. **Intent Router** — map user intent to reference file:
   - "like", "흥미", "interesting" → `references/like-papers.md`
   - "category", "카테고리", "분야" → `references/categories.md`
   - "daily", "오늘", "today", "추천" → `references/daily-fetch.md`
   - "review", "리뷰", "분석" → `references/review.md`
   - "similar", "관련", "related" → `references/related-papers.md`
   - "digest", "정리", "요약", "이번 주" → `references/digest.md`
   - "note", "메모", "노트" → `references/notes.md`

## CLI Invocation Strategy

`axp` is not globally installed — it's a project-local command via `uv run axp`. For the global skill to work from any directory:

**Option: `uv tool install`** (recommended)
```bash
uv tool install --from /path/to/arXiv_explorer arxiv-explorer
```
This installs `axp` to `~/.local/bin/` making it available system-wide.

**SKILL.md should:**
1. First try `axp` directly (globally installed)
2. Fall back to `uv run --project {project_dir} axp` if not found
3. On first use, suggest global install if not available

## axp Code Changes Required

### 0. `axp show` — Add `--json` flag

Currently `axp show` has no `--json` output. The skill needs structured output for parsing paper metadata. Add `--json` flag to `show` command that outputs paper data as JSON (matching `axp daily --json` format).

### 1. `core/config.py` — DB path migration

Change `Config.default()`:
```python
# Before
config_dir = Path.home() / ".config" / "arxiv-explorer"
db_path = config_dir / "explorer.db"

# After
data_dir = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "arxiv-explorer"
data_dir.mkdir(parents=True, exist_ok=True)

# Auto-migrate from old location
old_db = Path.home() / ".config" / "arxiv-explorer" / "explorer.db"
new_db = data_dir / "explorer.db"
if old_db.exists() and not new_db.exists():
    import shutil
    shutil.copy2(old_db, new_db)

db_path = new_db
```

### 2. DB schema addition — review metadata table

```sql
CREATE TABLE IF NOT EXISTS skill_review_meta (
    arxiv_id TEXT PRIMARY KEY,
    review_path TEXT NOT NULL,
    translation_path TEXT,
    source_type TEXT DEFAULT 'abstract',
    has_plots INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## Out of Scope

- Custom AI provider configuration (use `axp config` directly)
- TUI modifications (Rust TUI reads DB directly, benefits automatically)
- arxivterminal integration (separate tool, orthogonal)
- Reading list management (already well-handled by `axp list`)
- Paper download/PDF management (handled by arxiv-doc-builder skill)

## Testing Strategy

- Verify each CLI command with `--help` before using in skill
- Test DB migration with both existing and fresh installs
- Test review generation and file saving for a known arXiv ID
- Verify translation triggers correctly based on language config
- Test paperbanana conditional: skill present vs absent
