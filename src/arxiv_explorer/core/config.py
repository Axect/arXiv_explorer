"""Configuration management."""

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Config:
    """Application configuration."""

    # Database path
    db_path: Path

    # arxivterminal DB path (read-only)
    arxivterminal_db_path: Path

    # Default settings
    default_fetch_days: int = 1
    default_result_limit: int = 20

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


# Global config instance
_config: Config | None = None


def get_config() -> Config:
    """Get configuration."""
    global _config
    if _config is None:
        _config = Config.default()
    return _config
