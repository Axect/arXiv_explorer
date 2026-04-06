# arXiv Explorer Major TUI Update — Design Spec

**Date:** 2026-04-06
**Approach:** Feature-by-Feature (6 independent feature branches)

---

## Overview

Six features spanning DB schema, services, and TUI layers:

1. Reading List Hierarchy + Date Folder Toggle
2. Like/Dislike Lists
3. Preferred Authors + Daily Separate Section
4. Background Jobs System
5. Weight Percentage System
6. Category Fuzzy Search + Hierarchical Browser

Visual style: **Left Border Color Coding** (Catppuccin-inspired palette).

---

## Feature 1: Reading List Hierarchy + Month Folder Toggle

**Branch:** `feature/reading-list-hierarchy`

### DB Schema

```sql
ALTER TABLE reading_lists ADD COLUMN parent_id INTEGER REFERENCES reading_lists(id) ON DELETE CASCADE;
ALTER TABLE reading_lists ADD COLUMN is_folder BOOLEAN DEFAULT 0;
```

- `is_folder=1`: can contain child lists
- `parent_id=NULL`: top-level item
- Max depth: 2 levels (folder → list)

### Data Model

```python
@dataclass
class ReadingList:
    id: int
    name: str
    description: Optional[str]
    parent_id: Optional[int]     # NEW
    is_folder: bool              # NEW
    is_system: bool              # NEW (added in Feature 2)
    created_at: datetime
```

### Service Changes

`ReadingListService` new methods:

- `create_folder(name, parent_id=None) -> ReadingList`
- `move_item(item_id, target_folder_id) -> bool`
- `copy_item(item_id, target_folder_id) -> ReadingList | ReadingListPaper`
- `rename_item(item_id, new_name) -> bool`
- `toggle_paper_in_month_folder(arxiv_id, date) -> bool`
  - Checks for month folder (e.g. `202604`, `is_folder=1`), auto-creates if missing
  - Papers are added directly to the month folder (folder acts as a flat list of papers)
  - Adds paper if not present, removes if present (toggle)
  - Uses `added_at` from `reading_list_papers` for date tracking

### Daily TUI Toggle

- Key binding: `b` (bookmark)
- Toggled papers: **green left border** (`#a6e3a1`) + `✓` icon
- Operates on currently selected paper in Daily view

### Lists TUI

Tree structure with fold/unfold:

```
📋 Like (12)
📋 Dislike (5)
───────────────────
📁 202604 (10)
📁 202603 (23)
📋 Quantum Papers (4)
```

Selecting a folder/list shows papers with **Added column**, sorted by most recent first:

```
 ID          Title                          Added       Score
 2506.01234  Attention Is All You Need...   04-06 14:32  0.82
 2506.01235  Quantum Error Correction...    04-05 09:15  0.75
 2506.01236  Neural ODE for Physics...      04-03 20:41  0.68
                                       [s] Sort  [↑↓] Navigate
```

- `s`: toggle sort (newest ↔ oldest)
- Default: newest first (descending by `added_at`)

Key bindings (Lists tab):

| Key | Action |
|-----|--------|
| `f` | Create new folder |
| `m` | Move list/paper to another folder |
| `c` | Copy list/paper to another folder |
| `r` | Rename folder/list (inline edit) |

Copy behavior:
- **Paper selected**: copy paper to target folder/list (original retained)
- **List selected**: copy list + all contained papers to target folder

Move behavior: same as copy but removes original.

---

## Feature 2: Like/Dislike Lists

**Branch:** `feature/like-dislike-lists`
**Depends on:** Feature 1 (reading list hierarchy schema)

### DB Schema

```sql
ALTER TABLE reading_lists ADD COLUMN is_system BOOLEAN DEFAULT 0;
```

### Auto-creation

On first run / migration, create two system lists:

```python
ReadingList(name="Like", is_system=True, is_folder=False, parent_id=None)
ReadingList(name="Dislike", is_system=True, is_folder=False, parent_id=None)
```

`is_system=True` lists cannot be deleted or renamed.

### Dual Storage

When user presses `l` (like) in Daily:
1. `paper_interactions` → `INTERESTING` (existing, for recommendation engine)
2. "Like" reading list → add paper

When user presses `d` (dislike) in Daily:
1. `paper_interactions` → `NOT_INTERESTING` (existing)
2. "Dislike" reading list → add paper

Switching Like → Dislike: remove from Like list, add to Dislike list (and vice versa).

### TUI Display

System lists pinned at top of Lists tab, always visible:

```
📋 Like (12)          ← system, pinned
📋 Dislike (5)        ← system, pinned
───────────────────
📁 202604 (10)
📁 202603 (23)
📋 Quantum Papers (4)
```

---

## Feature 3: Preferred Authors + Daily Separate Section

**Branch:** `feature/preferred-authors`

### DB Schema

```sql
CREATE TABLE preferred_authors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Data Model

```python
@dataclass
class PreferredAuthor:
    id: int
    name: str
    added_at: datetime
```

### Author Matching Algorithm

Structural name comparison (not substring matching):

```python
def matches_author(registered: str, paper_author: str) -> bool:
    # 1) Normalize: lowercase, strip extra whitespace
    # 2) Last name (last token) must match exactly
    # 3) First/middle name tokens: accept full match, initial match,
    #    or whitespace merge (e.g. "Dong Woo" ↔ "Dongwoo")
    # 4) ALL name tokens from registered name must be accounted for
```

Examples with registered name `"Dong Woo Kang"`:

| Paper Author | Match | Reason |
|---|---|---|
| `Dong Woo Kang` | YES | Exact |
| `D. W. Kang` | YES | Initial expansion |
| `Dongwoo Kang` | YES | Whitespace merge |
| `D. Kang` | NO | First name partially missing |
| `Dong Woo Kim` | NO | Last name mismatch |
| `Kang` | NO | No first name |

### Recommendation Changes

`PaperService.get_daily_papers()` returns two separate lists:

```python
def get_daily_papers(days, limit) -> tuple[list[Paper], list[RecommendedPaper]]:
    all_papers = fetch_by_categories(...)
    
    # 1) Separate author-matched papers
    author_papers = [p for p in all_papers if matches_preferred_author(p)]
    remaining = [p for p in all_papers if p not in author_papers]
    
    # 2) Score remaining with existing algorithm
    scored = recommendation_engine.score_papers(remaining, ...)[:limit]
    
    return author_papers, scored
```

- Author-matched papers are NOT counted against `limit`
- Author papers still get scores computed (for display), but are never filtered out

### Daily TUI

Two sections with distinct visual treatment:

```
── From Your Authors ──────────────────────────
│ 2506.01237  Quantum Gravity Revisited...
│             K. Lee, J. Park  |  hep-th
│ 2506.01240  New Bounds on Dark Matter...
│             S. Kim et al.    |  hep-ph
── Recommended ────────────────────────────────
  2506.01234  Attention Is All You Need...
              cs.AI  |  Score: 0.82
  2506.01235  Neural ODE for Physics...
              cs.ML  |  Score: 0.75
```

- "From Your Authors" section: **yellow left border** (`#f9e2af`)
- All Daily key bindings (`b`, `l`, `d`, `s`, `t`, `w`) work in both sections

### Prefs TUI

New "Authors" section in Preferences tab:

| Key | Action |
|-----|--------|
| `a` | Add author (text input) |
| `x` | Delete selected author |

---

## Feature 4: Background Jobs System

**Branch:** `feature/background-jobs`

### Architecture

In-memory job tracking using Textual Workers. No DB persistence — results are already cached in `paper_summaries`, `paper_translations`, `paper_review_sections`.

### Data Models

```python
class JobType(Enum):
    SUMMARIZE = "summarize"
    TRANSLATE = "translate"
    REVIEW = "review"

class JobStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

@dataclass
class Job:
    id: str                       # UUID
    paper_id: str                 # arxiv_id
    paper_title: str              # display name
    job_type: JobType
    status: JobStatus
    started_at: datetime
    completed_at: Optional[datetime]
    error: Optional[str]
```

### JobManager Service

```python
class JobManager:
    jobs: dict[str, Job]
    on_status_change: Callback    # triggers TUI notification
    
    def submit(job_type, paper) -> Job
    def cancel(job_id) -> bool
    def get_active_jobs() -> list[Job]
    def get_all_jobs() -> list[Job]
```

- `submit()` runs task as Textual Worker (background async)
- Worker continues running even when navigating away from paper detail
- On completion/failure, `on_status_change` callback notifies TUI

### TUI Components

**1) Toast Notification** (bottom-right, auto-dismiss 3s):

```
┌─────────────────────────┐
│ ✓ Summary completed     │
│   2506.01234             │
└─────────────────────────┘
```

**2) Status Bar** (persistent, bottom-right of footer):

```
─────────────────── Jobs: 2 running ──
```

Hidden when no active jobs.

**3) Jobs Panel** — toggle with `j` key:

```
── Active Jobs ─────────────────────────
⟳ REVIEW    2506.01237  Quantum Gravity...    1m 23s
⟳ TRANSLATE 2506.01234  Attention Is All...   0m 45s

── Completed ───────────────────────────
✓ SUMMARY   2506.01235  Neural ODE...         Done
✗ TRANSLATE 2506.01236  Dark Matter...        Failed: timeout

                    [x] Cancel  [c] Clear completed
```

| Key | Action |
|-----|--------|
| `j` | Toggle Jobs panel (global binding) |
| `x` | Cancel selected running job |
| `c` | Clear completed/failed entries |

---

## Feature 5: Weight Percentage System

**Branch:** `feature/weight-percentage`

### Default Values

```
Content Similarity:  60%
Category Match:      20%
Keyword Match:       15%
Recency Bonus:        5%
Total:              100%
```

### Storage

Migrated from hardcoded `Config` dataclass to `app_settings` table:

```python
# app_settings keys
"weight_content":  "60"
"weight_category": "20"
"weight_keyword":  "15"
"weight_recency":  "5"
```

Migration: existing hardcoded values (0.5, 0.2, 0.1, 0.05) are replaced by new defaults (60, 20, 15, 5).

### Internal Conversion

```python
# Scoring uses: weight_percent / 100.0
content_score = (60 / 100.0) * cosine_similarity  # = 0.6 * similarity
```

### Auto-Adjustment Algorithm

When user changes one weight, remaining weights scale proportionally to maintain 100% total:

```python
def adjust_weights(changed_key: str, new_value: int, weights: dict[str, int]) -> dict[str, int]:
    weights[changed_key] = new_value
    remaining = 100 - new_value
    others = {k: v for k, v in weights.items() if k != changed_key}
    others_sum = sum(others.values())
    
    if others_sum == 0:
        # Edge case: distribute equally
        equal = remaining // len(others)
        for k in others:
            weights[k] = equal
    else:
        for k in others:
            weights[k] = round(remaining * others[k] / others_sum)
    
    # Rounding error correction: adjust largest item by ±1
    diff = 100 - sum(weights.values())
    if diff != 0:
        largest = max(others, key=lambda k: weights[k])
        weights[largest] += diff
    
    return weights
```

### Prefs TUI

```
── Recommendation Weights ──────────────────
  Content Similarity  [████████████████████░░░░░░░░░░]  60%
  Category Match      [██████░░░░░░░░░░░░░░░░░░░░░░░░]  20%
  Keyword Match       [█████░░░░░░░░░░░░░░░░░░░░░░░░░]  15%
  Recency Bonus       [██░░░░░░░░░░░░░░░░░░░░░░░░░░░░]   5%
                                                  Total: 100%

              [←→] Adjust  [Enter] Confirm  [r] Reset defaults
```

- Left/right arrows: ±1% adjustment, others auto-adjust
- `r`: reset to defaults (60/20/15/5)

---

## Feature 6: Category Fuzzy Search + Hierarchical Browser

**Branch:** `feature/category-fuzzy-search`

### Category Data

Static bundled data in `core/arxiv_categories.py`:

```python
ARXIV_CATEGORIES = {
    "Physics": {
        "astro-ph": "Astrophysics",
        "astro-ph.CO": "Cosmology and Nongalactic Astrophysics",
        "hep-ph": "High Energy Physics - Phenomenology",
        "hep-th": "High Energy Physics - Theory",
        "quant-ph": "Quantum Physics",
        ...
    },
    "Computer Science": {
        "cs.AI": "Artificial Intelligence",
        "cs.CL": "Computation and Language",
        "cs.LG": "Machine Learning",
        ...
    },
    "Mathematics": { ... },
    ...  # ~150+ categories total
}
```

Both code and full name are searchable.

### Fuzzy Matching

Built-in scorer, no external dependencies (only ~150 items):

```python
def fuzzy_score(query: str, target: str) -> float:
    # 1) Exact prefix match → highest score
    # 2) Contiguous substring match → high score
    # 3) Token-wise match (order-independent) → medium score
    # 4) Individual character sequential match → low score
```

### TUI: Dual Mode

Category addition (`a` key in Prefs tab) opens modal with two modes:

**Default: Fuzzy Search Mode**

```
── Add Category ─────────────────────────────
  Search: quan█

  quant-ph       Quantum Physics
  q-fin.QR       Quantitative Finance - Quantitative...
  cs.QI          Quantum Information

              [↑↓] Navigate  [Enter] Select  [Tab] Browse
```

- Real-time filtering as user types
- Searches both category code and full name

**Tab: Hierarchical Browser Mode**

```
── Add Category ─────────────────────────────
  ▸ Physics (52)
  ▾ Computer Science (40)
      cs.AI    Artificial Intelligence
      cs.CL    Computation and Language
      cs.CV    Computer Vision and Pattern Rec...
      cs.LG    Machine Learning
  ▸ Mathematics (32)
  ▸ Quantitative Biology (10)

     [↑↓] Navigate  [Enter] Select/Expand  [Tab] Search
```

- Top-level groups fold/unfold
- `Enter` on category: select → prompt for priority → add
- `Tab`: switch back to fuzzy search mode

---

## Cross-Cutting Concerns

### Visual Style

Left Border Color Coding with Catppuccin Mocha palette:

| State | Border Color | Icon |
|-------|-------------|------|
| Normal | `#585b70` (surface2) | — |
| Preferred Author | `#f9e2af` (yellow) | ★ |
| Saved to month folder | `#a6e3a1` (green) | ✓ |
| Author + Saved | `#f9e2af` (yellow) border + `#a6e3a1` green icon | ★✓ |

When both states apply: yellow border takes precedence (author), green `✓` and folder badge shown alongside.

### Feature Branch Dependencies

```
feature/reading-list-hierarchy     (independent)
    └── feature/like-dislike-lists (depends on hierarchy schema)
feature/preferred-authors          (independent)
feature/background-jobs            (independent)
feature/weight-percentage          (independent)
feature/category-fuzzy-search      (independent)
```

Merge order: `reading-list-hierarchy` must merge before `like-dislike-lists`. All others are independent and can be developed in parallel.

### Migration Strategy

All DB migrations are additive (ALTER TABLE ADD COLUMN, CREATE TABLE). No destructive changes. Applied in `init_db()` with `IF NOT EXISTS` / `IF NOT COLUMN` guards for idempotency.
