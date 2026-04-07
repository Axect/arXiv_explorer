# arXiv Explorer Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a global Claude Code skill that orchestrates the `axp` CLI for conversational paper discovery, review, and management — plus the prerequisite `axp` code changes (DB path migration, `show --json`, review metadata table).

**Architecture:** The skill is a single SKILL.md orchestrator + 7 reference files at `~/.claude/skills/arxiv-explorer/`. It delegates data operations to `axp` CLI and handles AI tasks (review, translation, keyword extraction) via Claude directly. File-based content storage at `~/.local/share/arxiv-explorer/` with DB metadata.

**Tech Stack:** Python (axp CLI), Rust (TUI DB path), Claude Code skill system (Markdown)

---

## File Structure

### axp Code Changes
- Modify: `src/arxiv_explorer/core/config.py` — DB path from `~/.config/` to `~/.local/share/`
- Modify: `src/arxiv_explorer/core/database.py` — add `skill_review_meta` table to schema
- Modify: `src/arxiv_explorer/cli/daily.py` — add `--json` flag to `show` command
- Modify: `tui-rs/src/db/mod.rs` — update `default_path()` to use `~/.local/share/`
- Modify: `tests/conftest.py` — no changes needed (uses tmp_path, unaffected)
- Create: `tests/test_config_migration.py` — test DB auto-migration
- Create: `tests/test_show_json.py` — test show --json output

### Skill Files
- Create: `~/.claude/skills/arxiv-explorer/SKILL.md`
- Create: `~/.claude/skills/arxiv-explorer/references/like-papers.md`
- Create: `~/.claude/skills/arxiv-explorer/references/categories.md`
- Create: `~/.claude/skills/arxiv-explorer/references/daily-fetch.md`
- Create: `~/.claude/skills/arxiv-explorer/references/review.md`
- Create: `~/.claude/skills/arxiv-explorer/references/related-papers.md`
- Create: `~/.claude/skills/arxiv-explorer/references/digest.md`
- Create: `~/.claude/skills/arxiv-explorer/references/notes.md`
- Create: `~/.claude/skills/arxiv-explorer/scripts/migrate_db.py`

---

### Task 1: Migrate DB path in Python config

**Files:**
- Modify: `src/arxiv_explorer/core/config.py`
- Create: `tests/test_config_migration.py`

- [ ] **Step 1: Write failing test for new default path**

```python
# tests/test_config_migration.py
"""Tests for DB path migration from ~/.config to ~/.local/share."""

from pathlib import Path

from arxiv_explorer.core.config import Config


class TestConfigDefaultPath:
    def test_default_uses_xdg_data_home(self, monkeypatch, tmp_path):
        """DB should be at XDG_DATA_HOME/arxiv-explorer/explorer.db."""
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
        # Clear old config path so migration doesn't trigger
        monkeypatch.setattr("arxiv_explorer.core.config._config", None)
        config = Config.default()
        assert config.db_path == tmp_path / "data" / "arxiv-explorer" / "explorer.db"

    def test_default_without_xdg_uses_local_share(self, monkeypatch, tmp_path):
        """Without XDG_DATA_HOME, use ~/.local/share."""
        monkeypatch.delenv("XDG_DATA_HOME", raising=False)
        monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
        monkeypatch.setattr("arxiv_explorer.core.config._config", None)
        config = Config.default()
        assert config.db_path == tmp_path / ".local" / "share" / "arxiv-explorer" / "explorer.db"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_config_migration.py -v`
Expected: FAIL — current config uses `~/.config/arxiv-explorer/`

- [ ] **Step 3: Update Config.default() to use XDG data path**

Replace the `Config.default()` method in `src/arxiv_explorer/core/config.py`:

```python
@classmethod
def default(cls) -> "Config":
    """Load default configuration."""
    # Data directory (DB + files)
    data_dir = (
        Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
        / "arxiv-explorer"
    )
    data_dir.mkdir(parents=True, exist_ok=True)

    # Auto-migrate DB from old location (~/.config/arxiv-explorer/)
    old_db = Path.home() / ".config" / "arxiv-explorer" / "explorer.db"
    new_db = data_dir / "explorer.db"
    if old_db.exists() and not new_db.exists():
        import shutil

        shutil.copy2(old_db, new_db)

    # Find arxivterminal DB path
    xdg_data = os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")
    arxivterminal_paths = [
        Path(xdg_data) / "arxivterminal" / "papers.db",
        Path.home() / ".local" / "share" / "arxivterminal" / "papers.db",
        Path.home() / "Library" / "Application Support" / "arxivterminal" / "papers.db",
    ]

    arxivterminal_db = None
    for p in arxivterminal_paths:
        if p.exists():
            arxivterminal_db = p
            break

    return cls(
        db_path=new_db,
        arxivterminal_db_path=arxivterminal_db or arxivterminal_paths[0],
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_config_migration.py -v`
Expected: PASS

- [ ] **Step 5: Write test for DB auto-migration**

Add to `tests/test_config_migration.py`:

```python
class TestDBAutoMigration:
    def test_copies_old_db_to_new_location(self, monkeypatch, tmp_path):
        """If old DB exists and new doesn't, copy it over."""
        old_config_dir = tmp_path / ".config" / "arxiv-explorer"
        old_config_dir.mkdir(parents=True)
        old_db = old_config_dir / "explorer.db"
        old_db.write_text("fake-db-content")

        new_data_dir = tmp_path / ".local" / "share"

        monkeypatch.delenv("XDG_DATA_HOME", raising=False)
        monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
        monkeypatch.setattr("arxiv_explorer.core.config._config", None)

        config = Config.default()
        assert config.db_path.exists()
        assert config.db_path.read_text() == "fake-db-content"
        # Old DB should still exist (backup)
        assert old_db.exists()

    def test_does_not_overwrite_existing_new_db(self, monkeypatch, tmp_path):
        """If new DB already exists, don't overwrite with old one."""
        old_config_dir = tmp_path / ".config" / "arxiv-explorer"
        old_config_dir.mkdir(parents=True)
        (old_config_dir / "explorer.db").write_text("old-content")

        new_data_dir = tmp_path / ".local" / "share" / "arxiv-explorer"
        new_data_dir.mkdir(parents=True)
        (new_data_dir / "explorer.db").write_text("new-content")

        monkeypatch.delenv("XDG_DATA_HOME", raising=False)
        monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
        monkeypatch.setattr("arxiv_explorer.core.config._config", None)

        config = Config.default()
        assert config.db_path.read_text() == "new-content"
```

- [ ] **Step 6: Run migration tests**

Run: `uv run pytest tests/test_config_migration.py -v`
Expected: All PASS

- [ ] **Step 7: Run full test suite to check for regressions**

Run: `uv run pytest -v`
Expected: All PASS (existing tests use `tmp_config` fixture, unaffected by path change)

- [ ] **Step 8: Commit**

```bash
git add src/arxiv_explorer/core/config.py tests/test_config_migration.py
git commit -m "feat: migrate DB path from ~/.config to ~/.local/share (XDG data)"
```

---

### Task 2: Update Rust TUI DB path

**Files:**
- Modify: `tui-rs/src/db/mod.rs:36-44`

- [ ] **Step 1: Update default_path() in Rust TUI**

In `tui-rs/src/db/mod.rs`, change `default_path()`:

```rust
pub fn default_path() -> PathBuf {
    if let Ok(p) = std::env::var("AXP_DB") {
        return PathBuf::from(p);
    }
    // XDG_DATA_HOME or fallback to ~/.local/share
    if let Ok(data_home) = std::env::var("XDG_DATA_HOME") {
        return PathBuf::from(data_home)
            .join("arxiv-explorer")
            .join("explorer.db");
    }
    let home = dirs::home_dir().unwrap_or_else(|| PathBuf::from("."));
    home.join(".local")
        .join("share")
        .join("arxiv-explorer")
        .join("explorer.db")
}
```

- [ ] **Step 2: Verify TUI builds**

Run: `cd tui-rs && cargo build --release 2>&1 | tail -5`
Expected: Build succeeds

- [ ] **Step 3: Commit**

```bash
git add tui-rs/src/db/mod.rs
git commit -m "feat(tui): update DB path to ~/.local/share/arxiv-explorer"
```

---

### Task 3: Add skill_review_meta table to DB schema

**Files:**
- Modify: `src/arxiv_explorer/core/database.py`

- [ ] **Step 1: Add table to SCHEMA string**

In `src/arxiv_explorer/core/database.py`, add before the `-- Indexes` section:

```sql
-- Skill review metadata (file-based reviews generated by Claude skill)
CREATE TABLE IF NOT EXISTS skill_review_meta (
    arxiv_id TEXT PRIMARY KEY NOT NULL,
    review_path TEXT NOT NULL,
    translation_path TEXT,
    source_type TEXT DEFAULT 'abstract',
    has_plots INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

- [ ] **Step 2: Run existing tests to verify no regression**

Run: `uv run pytest -v`
Expected: All PASS (table creation is idempotent via `CREATE TABLE IF NOT EXISTS`)

- [ ] **Step 3: Commit**

```bash
git add src/arxiv_explorer/core/database.py
git commit -m "feat(db): add skill_review_meta table for file-based review tracking"
```

---

### Task 4: Add --json flag to `axp show`

**Files:**
- Modify: `src/arxiv_explorer/cli/daily.py:193-267` (the `show` function)
- Create: `tests/test_show_json.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_show_json.py
"""Tests for axp show --json output."""

import json

from typer.testing import CliRunner

from arxiv_explorer.cli.main import app
from arxiv_explorer.core.config import Config
from arxiv_explorer.core.database import get_connection


runner = CliRunner()


class TestShowJson:
    def test_show_json_outputs_valid_json(self, tmp_config: Config):
        """axp show {id} --json should output valid JSON."""
        # Insert a paper into the cache
        with get_connection() as conn:
            conn.execute(
                """INSERT INTO papers (arxiv_id, title, abstract, authors, categories, published)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    "2401.00001",
                    "Test Paper",
                    "Test abstract.",
                    '["Alice", "Bob"]',
                    '["hep-ph", "cs.LG"]',
                    "2024-01-01T00:00:00",
                ),
            )

        result = runner.invoke(app, ["show", "2401.00001", "--json", "--no-update-check"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["arxiv_id"] == "2401.00001"
        assert data["title"] == "Test Paper"
        assert data["authors"] == ["Alice", "Bob"]
        assert data["categories"] == ["hep-ph", "cs.LG"]

    def test_show_json_no_id_lists_liked(self, tmp_config: Config):
        """axp show --json without ID should list liked paper IDs."""
        # Mark papers as interesting
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO paper_interactions (arxiv_id, interaction_type) VALUES (?, ?)",
                ("2401.00001", "interesting"),
            )

        result = runner.invoke(app, ["show", "--json", "--no-update-check"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "interesting_papers" in data
        assert "2401.00001" in data["interesting_papers"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_show_json.py -v`
Expected: FAIL — `--json` flag doesn't exist yet

- [ ] **Step 3: Add --json to show command**

In `src/arxiv_explorer/cli/daily.py`, update the `show` function signature and add JSON output:

```python
def show(
    arxiv_id: Optional[str] = typer.Argument(
        None, help="arXiv ID (if omitted, shows recently liked papers)"
    ),
    summary: bool = typer.Option(False, "--summary", "-s", help="Include summary"),
    detailed: bool = typer.Option(
        False, "--detailed", "-d", help="Generate detailed summary (longer summary and analysis)"
    ),
    translate: bool = typer.Option(False, "--translate", "-t", help="Include translation"),
    force: bool = typer.Option(False, "--force", "-f", help="Regenerate (ignore cache)"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """View paper details."""
    import json

    service = PaperService()
    pref_service = PreferenceService()

    # If no arxiv_id provided, show recently liked papers
    if arxiv_id is None:
        interesting_ids = pref_service.get_interesting_papers()

        if json_output:
            print(json.dumps({"interesting_papers": interesting_ids}))
            return

        if not interesting_ids:
            print_info("No papers marked as interesting.")
            console.print("\nUsage:")
            console.print("  View a specific paper: [cyan]axp show 2602.04878v1[/cyan]")
            console.print("  With summary: [cyan]axp show 2602.04878v1 --summary[/cyan]")
            console.print("  Detailed summary: [cyan]axp show 2602.04878v1 --detailed[/cyan]")
            console.print("  Fetch recent papers: [cyan]axp daily --days 7[/cyan]")
            console.print('  Search by keyword: [cyan]axp search "quantum computing"[/cyan]')
            return

        console.print("[bold]Recently liked papers:[/bold]\n")
        for i, paper_id in enumerate(interesting_ids[:5], 1):
            console.print(f"{i}. [green]{paper_id}[/green]")

        console.print(f"\nView details: [cyan]axp show {interesting_ids[0]} --detailed[/cyan]")
        return

    paper = service.get_paper(arxiv_id)

    if not paper:
        if json_output:
            print(json.dumps({"error": f"Paper not found: {arxiv_id}"}))
            raise typer.Exit(1)
        print_error(f"Paper not found: {arxiv_id}")
        raise typer.Exit(1)

    if json_output:
        result = {
            "arxiv_id": paper.arxiv_id,
            "title": paper.title,
            "abstract": paper.abstract,
            "authors": paper.authors,
            "categories": paper.categories,
            "published": str(paper.published),
            "updated": str(paper.updated) if paper.updated else None,
            "pdf_url": paper.pdf_url,
        }
        print(json.dumps(result))
        return

    paper_summary = None
    if summary or detailed:
        summarizer = SummarizationService()
        paper_summary = summarizer.summarize(
            arxiv_id, paper.title, paper.abstract, detailed=detailed, force=force
        )

    if (summary or detailed) and paper_summary is None:
        import sys

        print("Failed to generate summary (check provider settings)", file=sys.stderr)
        raise typer.Exit(1)

    paper_translation = None
    if translate:
        translator = TranslationService()
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            progress.add_task("Translating...", total=None)
            paper_translation = translator.translate(
                arxiv_id, paper.title, paper.abstract, force=force
            )

    if translate and paper_translation is None:
        import sys

        print("Failed to generate translation (check provider settings)", file=sys.stderr)
        raise typer.Exit(1)

    print_paper_detail(paper, paper_summary, paper_translation)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_show_json.py -v`
Expected: PASS

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/arxiv_explorer/cli/daily.py tests/test_show_json.py
git commit -m "feat(cli): add --json output to axp show command"
```

---

### Task 5: Create DB migration script for skill

**Files:**
- Create: `~/.claude/skills/arxiv-explorer/scripts/migrate_db.py`

- [ ] **Step 1: Create directory structure**

```bash
mkdir -p ~/.claude/skills/arxiv-explorer/scripts
mkdir -p ~/.claude/skills/arxiv-explorer/references
```

- [ ] **Step 2: Write migration script**

```python
#!/usr/bin/env python3
"""Migrate arXiv Explorer DB from ~/.config to ~/.local/share.

Run this once when the skill is first used. Safe to run multiple times
(idempotent — skips if new location already has a DB).
"""

import os
import shutil
from pathlib import Path


def migrate():
    xdg_data = os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")
    new_dir = Path(xdg_data) / "arxiv-explorer"
    new_db = new_dir / "explorer.db"

    old_db = Path.home() / ".config" / "arxiv-explorer" / "explorer.db"

    if new_db.exists():
        print(f"DB already at new location: {new_db}")
        return

    if old_db.exists():
        new_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(old_db, new_db)
        print(f"Migrated DB: {old_db} → {new_db}")
        print(f"Old DB kept as backup at: {old_db}")
    else:
        print("No existing DB found. A fresh one will be created on first axp run.")

    # Create subdirectories
    for subdir in ("papers", "reviews", "digests"):
        (new_dir / subdir).mkdir(parents=True, exist_ok=True)
        print(f"Created: {new_dir / subdir}")


if __name__ == "__main__":
    migrate()
```

- [ ] **Step 3: Test the script**

Run: `python3 ~/.claude/skills/arxiv-explorer/scripts/migrate_db.py`
Expected: Either "DB already at new location" or "Migrated DB" message, plus subdirectory creation

- [ ] **Step 4: Commit skill script (to project repo for tracking)**

No git commit for global skill files — they live outside the repo. Proceed to next task.

---

### Task 6: Create SKILL.md orchestrator

**Files:**
- Create: `~/.claude/skills/arxiv-explorer/SKILL.md`

- [ ] **Step 1: Write SKILL.md**

```markdown
---
name: arxiv-explorer
description: >
  Personalized arXiv paper discovery, review, and management. Use when the user
  mentions arXiv papers, wants paper recommendations, asks for daily/today's papers,
  wants to like/review/search papers, manage research categories or keywords,
  generate paper reviews with translation, find related papers, create weekly/monthly
  research digests, or take notes on papers. Also triggers on Korean equivalents:
  논문, 아카이브, 추천, 리뷰, 카테고리, 키워드, 메모.
  Orchestrates the axp CLI with Claude-powered review, translation, and analysis.
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, Agent, Skill
user-invocable: true
---

# arXiv Explorer Skill

Conversational interface for personalized arXiv paper management via the `axp` CLI.

## Quick Reference

| Intent | Action | Reference |
|--------|--------|-----------|
| Like papers / mark interesting | `axp like {id}` + keyword extraction | `references/like-papers.md` |
| Add/remove categories | Natural language → arXiv code → `axp prefs` | `references/categories.md` |
| Today's papers / daily fetch | `axp daily --json` → ranked table | `references/daily-fetch.md` |
| Review a paper | Claude writes review + translation | `references/review.md` |
| Find related papers | Extract terms → `axp search --json` | `references/related-papers.md` |
| Weekly/monthly digest | Aggregate likes + reviews → report | `references/digest.md` |
| Add notes to papers | `axp note add` | `references/notes.md` |

## Common Rules

### Base Directory
All files stored under `~/.local/share/arxiv-explorer/`:
```
~/.local/share/arxiv-explorer/
├── explorer.db          # SQLite database
├── papers/              # arxiv-doc-builder output
├── reviews/{arxiv_id}/  # Claude-generated reviews
│   ├── review.md        # Original (English)
│   ├── review_{lang}.md # Translated version
│   └── plots/           # paperbanana output (if available)
└── digests/             # Weekly/monthly summaries
```

### CLI Invocation
1. Try `axp` directly (globally installed via `uv tool install`)
2. If not found, use `uv run --project ~/Documents/Project/AI_Project/arXiv_explorer axp`
3. On first use, if `axp` is unavailable globally, suggest:
   ```
   uv tool install --from ~/Documents/Project/AI_Project/arXiv_explorer arxiv-explorer
   ```

### First Run Setup
On first invocation of any feature:
1. Run `python3 scripts/migrate_db.py` (relative to this skill directory) to ensure DB and directories exist
2. Verify `axp` is accessible

### JSON Output
Use `--json` flag when parsing CLI output. Available on:
- `axp daily --json`
- `axp search --json`
- `axp show {id} --json`
- `axp export interesting --format json`

### Language Settings
- Default language: read from `axp config show` output (look for "Language" line)
- User can override at call time (e.g., "한국어로 리뷰해줘")
- If language is not "en", always produce both English original and translated version

## Intent Router

Read the appropriate reference file based on user intent:

**Like / Interest:**
Keywords: "like", "좋아", "흥미", "interesting", "mark", "저장"
→ Read `references/like-papers.md`

**Categories:**
Keywords: "category", "카테고리", "분야", "add category", "research area"
→ Read `references/categories.md`

**Daily / Today:**
Keywords: "daily", "today", "오늘", "추천", "recommend", "what's new", "이번 주"
→ Read `references/daily-fetch.md`

**Review:**
Keywords: "review", "리뷰", "analyze", "분석", "상세", "detailed"
→ Read `references/review.md`

**Related / Similar:**
Keywords: "related", "similar", "관련", "비슷한", "like this paper"
→ Read `references/related-papers.md`

**Digest / Summary:**
Keywords: "digest", "정리", "요약", "summary", "이번 주 정리", "monthly"
→ Read `references/digest.md`

**Notes:**
Keywords: "note", "메모", "노트", "remember", "질문", "insight"
→ Read `references/notes.md`
```

- [ ] **Step 2: Verify file exists and is well-formed**

Run: `head -5 ~/.claude/skills/arxiv-explorer/SKILL.md`
Expected: Shows YAML frontmatter starting with `---`

---

### Task 7: Create reference — like-papers.md

**Files:**
- Create: `~/.claude/skills/arxiv-explorer/references/like-papers.md`

- [ ] **Step 1: Write like-papers.md**

```markdown
# Like Papers + Keyword Auto-extraction

## When to Use
User mentions arXiv IDs as interesting, wants to save/like papers, or says something
like "이 논문 흥미로워" or "mark these as interesting."

## Workflow

### Step 1: Like the Paper(s)
For each arXiv ID provided:
```bash
axp like {arxiv_id}
```

If multiple IDs given (comma-separated, space-separated, or in a list), like each one.

### Step 2: Get Paper Metadata
```bash
axp show {arxiv_id} --json
```

Parse the JSON to get `title`, `abstract`, `categories`.

### Step 3: Extract Keywords
From the paper's title and abstract, extract 3-5 domain-specific keywords.

**Keyword selection criteria:**
- Specific technical terms (not generic words like "method" or "approach")
- Terms that would help find similar papers in future searches
- Include both broad topics and specific techniques

**Weight assignment:**
- Weight 4-5: Paper's primary research topic (e.g., "jet classification", "dark matter")
- Weight 2-3: Secondary methods or tools (e.g., "transformer", "Monte Carlo")

### Step 4: Confirm with User
Present extracted keywords in a table:

| Keyword | Weight | Reason |
|---------|--------|--------|
| jet classification | 5 | Primary topic |
| graph neural network | 3 | Method used |

Ask: "이 키워드들을 관심사에 추가할까요? (수정하거나 제거할 항목이 있으면 말씀해주세요)"

### Step 5: Register Keywords
For each approved keyword:
```bash
axp prefs add-keyword "{keyword}" --weight {weight}
```

## Edge Cases
- If paper is already liked: `axp like` handles duplicates gracefully, just proceed to keywords
- If user provides invalid arXiv ID: show error and suggest checking the ID format
- If keyword already exists: `axp prefs add-keyword` updates the weight via UPSERT
```

---

### Task 8: Create reference — categories.md

**Files:**
- Create: `~/.claude/skills/arxiv-explorer/references/categories.md`

- [ ] **Step 1: Write categories.md**

```markdown
# Category Management

## When to Use
User wants to add or remove research interest categories. May provide natural language
descriptions ("고에너지 물리", "machine learning") or exact codes ("hep-ph", "cs.LG").

## arXiv Category Taxonomy

Major groups and common subcategories:

**Physics:** astro-ph (+ .CO .EP .GA .HE .IM .SR), cond-mat (+ .mes-hall .mtrl-sci .stat-mech .str-el .supr-con), gr-qc, hep-ex, hep-lat, hep-ph, hep-th, math-ph, nucl-ex, nucl-th, physics.* (acc-ph, ao-ph, app-ph, atom-ph, bio-ph, chem-ph, class-ph, comp-ph, data-an, flu-dyn, gen-ph, geo-ph, hist-ph, ins-det, med-ph, optics, plasm-ph, pop-ph, soc-ph, space-ph), quant-ph

**Computer Science (cs.*):** AI, AR, CC, CE, CG, CL, CR, CV, CY, DB, DC, DL, DM, DS, ET, FL, GL, GR, GT, HC, IR, IT, LG, LO, MA, MM, MS, NA, NE, NI, OH, OS, PF, PL, RO, SC, SD, SE, SI, SY

**Mathematics (math.*):** AC, AG, AP, AT, CA, CO, CT, CV, DG, DS, FA, GM, GN, GR, GT, HO, IT, KT, LO, MG, MP, NA, NT, OA, OC, PR, QA, RA, RT, SG, SP, ST

**Other:** econ.*, eess.*, q-bio.*, q-fin.*, stat.*

## Workflow

### Adding Categories

1. **Parse user input:**
   - If exact code (e.g., "cs.LG"): verify it exists in taxonomy above
   - If natural language: map to candidate codes using taxonomy knowledge

2. **Present candidates:**
   For ambiguous input, show options:
   ```
   "machine learning"과 관련된 카테고리:
   1. cs.LG — Machine Learning (primary)
   2. cs.AI — Artificial Intelligence
   3. stat.ML — Machine Learning (statistics perspective)
   
   어떤 것을 추가할까요? (번호 또는 "all")
   ```

3. **Set priority:**
   Ask user for priority (1-5) or suggest based on context:
   - Primary research field → priority 4-5
   - Secondary interest → priority 2-3
   - Casual curiosity → priority 1

4. **Register:**
   ```bash
   axp prefs add-category {code} --priority {priority}
   ```

### Removing Categories
```bash
axp prefs remove-category {code}
```

### Viewing Current Categories
```bash
axp prefs show
```

## Edge Cases
- User says "물리 전부": suggest individual subcategories rather than adding parent "physics"
- Misspelled codes: fuzzy match and suggest correction
- Duplicate: `axp prefs add-category` handles gracefully
```

---

### Task 9: Create reference — daily-fetch.md

**Files:**
- Create: `~/.claude/skills/arxiv-explorer/references/daily-fetch.md`

- [ ] **Step 1: Write daily-fetch.md**

```markdown
# Daily Fetch (Today's arXiv)

## When to Use
User asks for today's papers, daily recommendations, or "what's new."
Korean triggers: "오늘 논문", "추천 논문", "새 논문", "이번 주 논문"

## Workflow

### Step 1: Fetch Papers
```bash
axp daily --days {N} --limit {L} --json
```

Defaults: days=1, limit=10. Adjust based on user request:
- "오늘": days=1
- "이번 주": days=7
- "지난 3일": days=3
- Custom limit: use user-specified number

### Step 2: Parse JSON Output
The JSON structure:
```json
{
  "author_papers": [...],
  "scored_papers": [
    {
      "arxiv_id": "...",
      "title": "...",
      "abstract": "...",
      "authors": ["..."],
      "categories": ["..."],
      "published": "...",
      "score": 0.85
    }
  ]
}
```

`author_papers` = papers by preferred authors (always shown first).
`scored_papers` = recommendation-engine ranked papers.

### Step 3: Present Results
Format as a table:

```
| # | Score | Title | Authors | Category |
|---|-------|-------|---------|----------|
| 1 | 0.92 | Deep Learning for... | Alice et al. | hep-ph |
| 2 | 0.85 | Quantum Circuit... | Bob, Charlie | quant-ph |
```

- Truncate titles longer than 50 chars with "..."
- Show first author + "et al." if >2 authors
- Show primary category only

### Step 4: Offer Follow-up Actions
After presenting results:
"관심 있는 논문이 있으면 번호나 arXiv ID를 알려주세요. 다음을 할 수 있습니다:
- **like**: 관심 논문으로 등록 (추천 정확도 향상)
- **review**: 상세 리뷰 생성
- **related**: 유사 논문 탐색"

## Edge Cases
- No preferred categories set: prompt user to add categories first via `references/categories.md`
- No papers found: suggest expanding days range or adding more categories
- arXiv API rate limit: `axp` handles 3s delays internally, but warn user if fetch takes long
```

---

### Task 10: Create reference — review.md

**Files:**
- Create: `~/.claude/skills/arxiv-explorer/references/review.md`

- [ ] **Step 1: Write review.md**

```markdown
# Paper Review + Translation + Paperbanana

## When to Use
User asks to review, analyze, or summarize a specific paper in detail.
Korean triggers: "리뷰해줘", "분석해줘", "상세하게 봐줘"

## Workflow

### Step 1: Get Paper Metadata
```bash
axp show {arxiv_id} --json
```
Parse JSON to get title, abstract, authors, categories, published date.

If paper not found in cache, fetch it:
```bash
axp search "{arxiv_id}" --arxiv --json
```

### Step 2: Attempt Full Text (Optional)
Check if arxiv-doc-builder output exists:
```bash
ls ~/.local/share/arxiv-explorer/papers/{arxiv_id}/{arxiv_id}.md
```

If not available, try to generate using arxiv-doc-builder skill:
```
/arxiv-doc-builder {arxiv_id}
```

If full text available, read it for comprehensive review.
If not, review based on abstract only — note this in the review header.

### Step 3: Write Review

**Full mode (default)** — 15 sections:
1. Executive Summary
2. Key Contributions
3. Section Summaries (if full text available)
4. Methodology
5. Mathematical Formulations
6. Figures (if full text)
7. Tables (if full text)
8. Experimental Results
9. Reproducibility
10. Strengths & Weaknesses
11. Impact & Significance
12. Related Work
13. Glossary
14. Questions for Authors
15. Reading Guide

**Quick mode** (when user requests "간단하게", "quick", "경량") — 4 sections:
1. Executive Summary
2. Key Contributions
3. Methodology
4. Strengths & Weaknesses

Write the review in English first (regardless of target translation language).

### Step 4: Save Review
```bash
mkdir -p ~/.local/share/arxiv-explorer/reviews/{arxiv_id}
```

Write to `~/.local/share/arxiv-explorer/reviews/{arxiv_id}/review.md`

**Template:**
```markdown
# Review: {title}

**arXiv:** {arxiv_id}
**Authors:** {authors}
**Categories:** {categories}
**Published:** {date}
**Source:** abstract | full_text
**Generated:** {YYYY-MM-DD}

---

## Executive Summary
(content)

## Key Contributions
(content)

... (remaining sections)
```

### Step 5: Translate
Determine target language:
1. If user specified a language at call time → use that
2. Otherwise, read from config:
   ```bash
   axp config show
   ```
   Look for "Language : {code}" line.

If target language is not "en":
- Translate the entire review to target language
- Save to `~/.local/share/arxiv-explorer/reviews/{arxiv_id}/review_{lang}.md`
- Both files coexist (English original + translation)

### Step 6: Paperbanana Integration (Conditional)
Check if paperbanana skill is available. If so:

1. Identify 2-3 key concepts from the review that benefit from diagrams:
   - Methodology/architecture overview
   - Data flow or processing pipeline
   - Key result comparisons

2. Invoke paperbanana skill for each diagram:
   ```
   /paperbanana {description of diagram}
   ```

3. Move generated plots to:
   ```bash
   mkdir -p ~/.local/share/arxiv-explorer/reviews/{arxiv_id}/plots
   cp outputs/paperbanana/{name}/*.png ~/.local/share/arxiv-explorer/reviews/{arxiv_id}/plots/
   ```

4. Add image references in the review markdown:
   ```markdown
   ![Methodology Overview](plots/methodology.png)
   ```

If paperbanana is not available, skip silently.

### Step 7: Record Metadata in DB
Use `axp` or direct sqlite3 to insert into `skill_review_meta`:
```bash
python3 -c "
import sqlite3, os
from pathlib import Path
data_dir = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share')) / 'arxiv-explorer'
conn = sqlite3.connect(data_dir / 'explorer.db')
conn.execute('''INSERT OR REPLACE INTO skill_review_meta 
    (arxiv_id, review_path, translation_path, source_type, has_plots, updated_at)
    VALUES (?, ?, ?, ?, ?, datetime('now'))''',
    ('{arxiv_id}',
     str(data_dir / 'reviews/{arxiv_id}/review.md'),
     str(data_dir / 'reviews/{arxiv_id}/review_{lang}.md') if '{lang}' != 'en' else None,
     'full_text' if full_text_available else 'abstract',
     1 if plots_generated else 0))
conn.commit()
conn.close()
"
```

### Step 8: Present to User
Show the review directly in the conversation. If translated, show the translated version.
Mention: "리뷰가 저장되었습니다: ~/.local/share/arxiv-explorer/reviews/{arxiv_id}/"

## Edge Cases
- Paper not in arXiv (invalid ID): error and suggest checking ID
- Abstract-only review: clearly mark "Source: abstract" — skip sections that need full text (Section Summaries, Figures, Tables)
- Very long paper: focus on key sections, note that full review may be abbreviated
```

---

### Task 11: Create reference — related-papers.md

**Files:**
- Create: `~/.claude/skills/arxiv-explorer/references/related-papers.md`

- [ ] **Step 1: Write related-papers.md**

```markdown
# Related Paper Discovery

## When to Use
User wants to find papers similar to a specific paper.
Korean triggers: "비슷한 논문", "관련 논문", "이 논문과 유사한"

## Workflow

### Step 1: Get Source Paper
```bash
axp show {arxiv_id} --json
```

Extract: title, abstract, categories, key terms.

### Step 2: Build Search Queries
From the source paper, construct 2-3 targeted search queries:

1. **Primary query:** 3-5 most specific technical terms from title + abstract
2. **Category-scoped query:** broader terms limited to same categories
3. **Method query (optional):** if paper uses specific methodology, search for that

### Step 3: Search
For each query:
```bash
axp search "{query}" --limit 10 --arxiv --json
```

### Step 4: Deduplicate and Rank
- Remove the source paper itself from results
- Remove duplicates across queries
- Results already include recommendation scores from `axp search`
- Sort by score descending

### Step 5: Present Results
Show top 10 related papers as a table (same format as daily-fetch).

Add context: "Based on: {source paper title}"

### Step 6: Offer Follow-up
Same as daily-fetch: user can like, review, or explore further.
```

---

### Task 12: Create reference — digest.md

**Files:**
- Create: `~/.claude/skills/arxiv-explorer/references/digest.md`

- [ ] **Step 1: Write digest.md**

```markdown
# Weekly/Monthly Digest

## When to Use
User wants a summary of recent research activity.
Korean triggers: "이번 주 정리", "월간 요약", "최근 논문 정리"

## Workflow

### Step 1: Determine Period
- "이번 주" / "weekly" → last 7 days
- "이번 달" / "monthly" → last 30 days
- Custom range: parse from user request

### Step 2: Gather Data

**Liked papers:**
```bash
axp export interesting --format json
```
Parse JSON and filter by date range (compare `published` field).

**Existing reviews:**
```bash
ls ~/.local/share/arxiv-explorer/reviews/
```
For each review directory, read the review.md to get the review date from the header.

**Notes:**
```bash
axp note list
```

### Step 3: Write Digest Report
Structure:

```markdown
# Research Digest: {period}

**Period:** {start_date} — {end_date}
**Papers Liked:** {count}
**Reviews Completed:** {count}

---

## Papers Liked

| # | arXiv ID | Title | Category | Date |
|---|----------|-------|----------|------|
| 1 | ... | ... | ... | ... |

## Reviews Completed

For each reviewed paper, include a 2-3 sentence summary from the Executive Summary section.

## Key Themes

Identify 3-5 recurring themes or topics across the liked papers and reviews.

## Suggested Next Reads

Based on liked papers and current keyword interests, suggest 2-3 directions
for future exploration (categories or search terms to try).
```

### Step 4: Save
```bash
mkdir -p ~/.local/share/arxiv-explorer/digests
```

File naming:
- Weekly: `~/.local/share/arxiv-explorer/digests/{YYYY}-W{WW}.md`
- Monthly: `~/.local/share/arxiv-explorer/digests/{YYYY}-{MM}.md`

### Step 5: PDF Export (Optional)
If `md2pdf-typora` skill is available:
```
/md2pdf-typora ~/.local/share/arxiv-explorer/digests/{filename}.md
```

Then copy to Dropbox if configured:
```bash
mkdir -p ~/Dropbox/Magi/arXiv_explorer/
cp {filename}.pdf ~/Dropbox/Magi/arXiv_explorer/
```
```

---

### Task 13: Create reference — notes.md

**Files:**
- Create: `~/.claude/skills/arxiv-explorer/references/notes.md`

- [ ] **Step 1: Write notes.md**

```markdown
# Paper Notes

## When to Use
User makes observations, asks questions, or shares insights about a paper during conversation.
Korean triggers: "메모", "노트", "기억해둬", "질문"

## Workflow

### Step 1: Identify Paper Context
Determine which paper the note is about:
1. User explicitly mentions arXiv ID
2. Paper from the most recent review or daily fetch discussion
3. Ask user if ambiguous: "어떤 논문에 대한 메모인가요?"

### Step 2: Classify Note Type
- `general` — general observation or comment
- `question` — question about the paper (for later investigation)
- `insight` — key insight or learning
- `todo` — action item (e.g., "implement this method", "compare with X")

Classification heuristic:
- Contains "?" or "왜" or "어떻게" → `question`
- Contains "인상적", "핵심", "발견", "깨달" → `insight`
- Contains "해봐야", "구현", "시도", "비교해" → `todo`
- Otherwise → `general`

### Step 3: Save Note
```bash
axp note add {arxiv_id} --type {type} "{content}"
```

Note: content with quotes or special chars should be properly escaped.

### Step 4: Confirm
"메모가 저장되었습니다: [{type}] {content} (논문: {arxiv_id})"

### Viewing Notes
```bash
axp note show {arxiv_id}     # Notes for specific paper
axp note list                 # All notes
axp note list --type question # Filter by type
```
```

---

### Task 14: Run linting and full test suite

**Files:** None (validation only)

- [ ] **Step 1: Run ruff linter**

Run: `uv run ruff check src/ tests/`
Expected: No errors

- [ ] **Step 2: Run full test suite**

Run: `uv run pytest -v`
Expected: All tests pass

- [ ] **Step 3: Verify skill files exist**

Run: `ls -la ~/.claude/skills/arxiv-explorer/ && ls -la ~/.claude/skills/arxiv-explorer/references/`
Expected: SKILL.md + 7 reference files + scripts/migrate_db.py

- [ ] **Step 4: Final commit for axp changes**

```bash
git add -A
git status
git commit -m "feat: arXiv Explorer global skill - DB migration, show --json, review metadata"
```
