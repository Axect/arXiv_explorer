"""Tests for DB path migration from ~/.config to ~/.local/share."""

from pathlib import Path

from arxiv_explorer.core.config import Config


class TestConfigDefaultPath:
    def test_default_uses_xdg_data_home(self, monkeypatch, tmp_path):
        """DB should be at XDG_DATA_HOME/arxiv-explorer/explorer.db."""
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
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


class TestDBAutoMigration:
    def test_copies_old_db_to_new_location(self, monkeypatch, tmp_path):
        """If old DB exists and new doesn't, copy it over."""
        old_config_dir = tmp_path / ".config" / "arxiv-explorer"
        old_config_dir.mkdir(parents=True)
        old_db = old_config_dir / "explorer.db"
        old_db.write_text("fake-db-content")

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
