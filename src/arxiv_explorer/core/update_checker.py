"""Git-based update checker with throttling and conflict detection."""

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

# Throttle: check at most once per this many seconds
CHECK_INTERVAL_SECONDS = 12 * 60 * 60  # 12 hours

# Git command timeout
GIT_TIMEOUT_SECONDS = 10


@dataclass
class UpdateStatus:
    """Result of an update check."""

    has_update: bool = False
    local_ref: str = ""
    remote_ref: str = ""
    behind_count: int = 0
    ahead_count: int = 0
    changed_files: list[str] | None = None  # files changed on remote
    conflict_files: list[str] | None = None  # locally modified files that remote also changed
    error: str | None = None


def _get_repo_root() -> Path | None:
    """Find the git repo root from the package's installed location."""
    # Walk up from this file to find .git
    current = Path(__file__).resolve().parent
    for _ in range(10):
        if (current / ".git").exists():
            return current
        parent = current.parent
        if parent == current:
            break
        current = parent
    return None


def _run_git(repo: Path, *args: str, timeout: int = GIT_TIMEOUT_SECONDS) -> str | None:
    """Run a git command, return stdout or None on failure."""
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return None
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None


def _get_stamp_path(repo: Path) -> Path:
    """Path to the last-check timestamp file."""
    return repo / ".git" / "axp_update_check"


def _should_check(repo: Path) -> bool:
    """Return True if enough time has passed since the last check."""
    stamp = _get_stamp_path(repo)
    if not stamp.exists():
        return True
    try:
        last = float(stamp.read_text().strip())
        return (time.time() - last) >= CHECK_INTERVAL_SECONDS
    except (ValueError, OSError):
        return True


def _touch_stamp(repo: Path) -> None:
    """Record the current time as last-checked."""
    try:
        _get_stamp_path(repo).write_text(str(time.time()))
    except OSError:
        pass


def _get_tracking_branch(repo: Path) -> str | None:
    """Get the remote tracking branch for the current branch (e.g. 'origin/main')."""
    branch = _run_git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    if not branch:
        return None
    upstream = _run_git(repo, "rev-parse", "--abbrev-ref", f"{branch}@{{upstream}}")
    return upstream  # e.g. "origin/main"


def check_for_updates(repo: Path | None = None, force: bool = False) -> UpdateStatus | None:
    """Check if the remote has new commits.

    Returns UpdateStatus if a check was performed, None if skipped (throttled or not a repo).
    """
    if repo is None:
        repo = _get_repo_root()
    if repo is None:
        return None

    if not force and not _should_check(repo):
        return None

    # Find tracking branch
    upstream = _get_tracking_branch(repo)
    if not upstream:
        _touch_stamp(repo)
        return None

    remote_name = upstream.split("/")[0] if "/" in upstream else "origin"

    # Fetch from remote (lightweight, no merge)
    fetch_result = _run_git(repo, "fetch", remote_name, "--quiet")
    if fetch_result is None:
        # Network failure — silently skip
        _touch_stamp(repo)
        return UpdateStatus(error="fetch failed (network issue?)")

    _touch_stamp(repo)

    # Compare local HEAD vs upstream
    local_ref = _run_git(repo, "rev-parse", "HEAD") or ""
    remote_ref = _run_git(repo, "rev-parse", upstream) or ""

    if local_ref == remote_ref:
        return UpdateStatus(local_ref=local_ref, remote_ref=remote_ref)

    # Count ahead/behind
    rev_list = _run_git(repo, "rev-list", "--left-right", "--count", f"HEAD...{upstream}")
    ahead, behind = 0, 0
    if rev_list:
        parts = rev_list.split()
        if len(parts) == 2:
            ahead, behind = int(parts[0]), int(parts[1])

    if behind == 0:
        # Local is ahead or in sync — no update needed
        return UpdateStatus(
            local_ref=local_ref,
            remote_ref=remote_ref,
            ahead_count=ahead,
        )

    # There are updates to pull — find which files changed
    changed_raw = _run_git(repo, "diff", "--name-only", f"HEAD...{upstream}")
    changed_files = changed_raw.splitlines() if changed_raw else []

    # Detect potential conflicts: locally modified files that also changed on remote
    local_modified_raw = _run_git(repo, "diff", "--name-only")
    local_staged_raw = _run_git(repo, "diff", "--name-only", "--cached")

    local_dirty: set[str] = set()
    if local_modified_raw:
        local_dirty.update(local_modified_raw.splitlines())
    if local_staged_raw:
        local_dirty.update(local_staged_raw.splitlines())

    # Also check untracked files that overlap with remote changes
    # (not common but possible if remote adds a file the user also created)
    untracked_raw = _run_git(repo, "ls-files", "--others", "--exclude-standard")
    if untracked_raw:
        local_dirty.update(untracked_raw.splitlines())

    conflict_files = sorted(local_dirty & set(changed_files))

    return UpdateStatus(
        has_update=True,
        local_ref=local_ref,
        remote_ref=remote_ref,
        behind_count=behind,
        ahead_count=ahead,
        changed_files=changed_files,
        conflict_files=conflict_files if conflict_files else None,
    )


def pull_updates(repo: Path | None = None) -> tuple[bool, str]:
    """Run git pull. Returns (success, message)."""
    if repo is None:
        repo = _get_repo_root()
    if repo is None:
        return False, "Not a git repository"

    result = _run_git(repo, "pull", "--ff-only", timeout=30)
    if result is not None:
        return True, result

    # --ff-only failed, try normal pull
    result = _run_git(repo, "pull", timeout=30)
    if result is not None:
        return True, result

    return False, "git pull failed — you may need to resolve conflicts manually"
