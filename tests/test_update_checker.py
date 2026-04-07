"""Tests for the git update checker."""

import time
from pathlib import Path
from unittest.mock import patch

import pytest

from arxiv_explorer.core.update_checker import (
    CHECK_INTERVAL_SECONDS,
    UpdateStatus,
    _get_stamp_path,
    _should_check,
    _touch_stamp,
    check_for_updates,
    pull_updates,
)


@pytest.fixture
def fake_repo(tmp_path: Path):
    """Create a fake git directory structure."""
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    return tmp_path


# ── Throttling Tests ─────────────────────────────────────────────────


class TestThrottling:
    def test_should_check_no_stamp(self, fake_repo):
        """First run should always check."""
        assert _should_check(fake_repo) is True

    def test_should_check_fresh_stamp(self, fake_repo):
        """Just checked — should not check again."""
        _touch_stamp(fake_repo)
        assert _should_check(fake_repo) is False

    def test_should_check_stale_stamp(self, fake_repo):
        """Stamp older than interval — should check."""
        stamp = _get_stamp_path(fake_repo)
        stamp.write_text(str(time.time() - CHECK_INTERVAL_SECONDS - 1))
        assert _should_check(fake_repo) is True

    def test_should_check_corrupt_stamp(self, fake_repo):
        """Corrupt stamp file — should check."""
        stamp = _get_stamp_path(fake_repo)
        stamp.write_text("not-a-number")
        assert _should_check(fake_repo) is True

    def test_touch_stamp_creates_file(self, fake_repo):
        stamp = _get_stamp_path(fake_repo)
        assert not stamp.exists()
        _touch_stamp(fake_repo)
        assert stamp.exists()
        value = float(stamp.read_text())
        assert abs(value - time.time()) < 5


# ── UpdateStatus Tests ───────────────────────────────────────────────


class TestUpdateStatus:
    def test_defaults(self):
        s = UpdateStatus()
        assert s.has_update is False
        assert s.behind_count == 0
        assert s.conflict_files is None

    def test_with_conflicts(self):
        s = UpdateStatus(
            has_update=True,
            behind_count=3,
            changed_files=["a.py", "b.py", "c.py"],
            conflict_files=["b.py"],
        )
        assert s.has_update
        assert s.conflict_files == ["b.py"]


# ── check_for_updates Tests ─────────────────────────────────────────


class TestCheckForUpdates:
    def test_returns_none_when_no_repo(self):
        """Not a git repo — should return None."""
        result = check_for_updates(repo=Path("/tmp/definitely-not-a-repo"))
        assert result is None

    def test_returns_none_when_throttled(self, fake_repo):
        """Recently checked — should skip."""
        _touch_stamp(fake_repo)
        result = check_for_updates(repo=fake_repo)
        assert result is None

    def test_force_bypasses_throttle(self, fake_repo):
        """force=True should check even if recently checked."""
        _touch_stamp(fake_repo)
        with patch(
            "arxiv_explorer.core.update_checker._get_tracking_branch",
            return_value=None,
        ), patch(
            "arxiv_explorer.core.update_checker._run_git",
            return_value=None,
        ):
            result = check_for_updates(repo=fake_repo, force=True)
            # No tracking branch → returns None after fetch attempt
            assert result is None

    @patch("arxiv_explorer.core.update_checker._run_git")
    @patch(
        "arxiv_explorer.core.update_checker._get_tracking_branch",
        return_value="origin/main",
    )
    def test_no_update_when_refs_match(self, _mock_track, mock_git, fake_repo):
        """Same HEAD and remote — no update."""
        same_ref = "abc123"
        mock_git.side_effect = lambda repo, *args, **kw: {
            ("fetch",): "",
            ("rev-parse", "HEAD"): same_ref,
            ("rev-parse", "origin/main"): same_ref,
        }.get(args, "")

        result = check_for_updates(repo=fake_repo, force=True)
        assert result is not None
        assert result.has_update is False

    @patch("arxiv_explorer.core.update_checker._run_git")
    @patch(
        "arxiv_explorer.core.update_checker._get_tracking_branch",
        return_value="origin/main",
    )
    def test_detects_update(self, _mock_track, mock_git, fake_repo):
        """Remote is ahead — should detect update."""

        def git_dispatcher(repo, *args, **kw):
            key = args
            return {
                ("fetch", "origin", "--quiet"): "",
                ("rev-parse", "HEAD"): "local111",
                ("rev-parse", "origin/main"): "remote222",
                ("rev-list", "--left-right", "--count", "HEAD...origin/main"): "0\t5",
                ("diff", "--name-only", "HEAD...origin/main"): "src/a.py\nsrc/b.py",
                ("diff", "--name-only"): "",
                ("diff", "--name-only", "--cached"): "",
                ("ls-files", "--others", "--exclude-standard"): "",
            }.get(key)

        mock_git.side_effect = git_dispatcher

        result = check_for_updates(repo=fake_repo, force=True)
        assert result is not None
        assert result.has_update is True
        assert result.behind_count == 5
        assert result.changed_files == ["src/a.py", "src/b.py"]
        assert result.conflict_files is None

    @patch("arxiv_explorer.core.update_checker._run_git")
    @patch(
        "arxiv_explorer.core.update_checker._get_tracking_branch",
        return_value="origin/main",
    )
    def test_detects_conflicts(self, _mock_track, mock_git, fake_repo):
        """Locally modified file overlaps with remote change."""

        def git_dispatcher(repo, *args, **kw):
            key = args
            return {
                ("fetch", "origin", "--quiet"): "",
                ("rev-parse", "HEAD"): "local111",
                ("rev-parse", "origin/main"): "remote222",
                ("rev-list", "--left-right", "--count", "HEAD...origin/main"): "0\t2",
                ("diff", "--name-only", "HEAD...origin/main"): "src/a.py\nsrc/b.py",
                ("diff", "--name-only"): "src/b.py",  # locally modified
                ("diff", "--name-only", "--cached"): "",
                ("ls-files", "--others", "--exclude-standard"): "",
            }.get(key)

        mock_git.side_effect = git_dispatcher

        result = check_for_updates(repo=fake_repo, force=True)
        assert result is not None
        assert result.has_update is True
        assert result.conflict_files == ["src/b.py"]

    @patch("arxiv_explorer.core.update_checker._run_git")
    @patch(
        "arxiv_explorer.core.update_checker._get_tracking_branch",
        return_value="origin/main",
    )
    def test_fetch_failure_returns_error(self, _mock_track, mock_git, fake_repo):
        """Network failure during fetch — returns error status."""
        mock_git.return_value = None  # all git commands fail

        result = check_for_updates(repo=fake_repo, force=True)
        assert result is not None
        assert result.error is not None
        assert "fetch" in result.error

    @patch("arxiv_explorer.core.update_checker._run_git")
    @patch(
        "arxiv_explorer.core.update_checker._get_tracking_branch",
        return_value="origin/main",
    )
    def test_local_ahead_no_update(self, _mock_track, mock_git, fake_repo):
        """Local is ahead of remote — no update needed."""

        def git_dispatcher(repo, *args, **kw):
            return {
                ("fetch", "origin", "--quiet"): "",
                ("rev-parse", "HEAD"): "local111",
                ("rev-parse", "origin/main"): "remote222",
                ("rev-list", "--left-right", "--count", "HEAD...origin/main"): "3\t0",
            }.get(args)

        mock_git.side_effect = git_dispatcher

        result = check_for_updates(repo=fake_repo, force=True)
        assert result is not None
        assert result.has_update is False
        assert result.ahead_count == 3


# ── pull_updates Tests ───────────────────────────────────────────────


class TestPullUpdates:
    @patch("arxiv_explorer.core.update_checker._get_repo_root", return_value=None)
    def test_not_a_repo(self, _mock):
        success, msg = pull_updates(repo=None)
        assert success is False

    @patch("arxiv_explorer.core.update_checker._run_git")
    def test_ff_pull_success(self, mock_git, fake_repo):
        mock_git.return_value = "Fast-forward\n 2 files changed"
        success, msg = pull_updates(repo=fake_repo)
        assert success is True
        assert "Fast-forward" in msg

    @patch("arxiv_explorer.core.update_checker._run_git")
    def test_ff_fails_normal_succeeds(self, mock_git, fake_repo):
        mock_git.side_effect = [None, "Merge made by 'ort'"]
        success, msg = pull_updates(repo=fake_repo)
        assert success is True

    @patch("arxiv_explorer.core.update_checker._run_git")
    def test_both_fail(self, mock_git, fake_repo):
        mock_git.return_value = None
        success, msg = pull_updates(repo=fake_repo)
        assert success is False
        assert "failed" in msg
