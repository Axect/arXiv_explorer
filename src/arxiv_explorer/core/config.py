"""Configuration management."""
import os
from pathlib import Path
from dataclasses import dataclass


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

    # Recommendation weights
    content_weight: float = 0.5
    category_weight: float = 0.2
    keyword_weight: float = 0.1
    recency_weight: float = 0.05

    @classmethod
    def default(cls) -> "Config":
        """Load default configuration."""
        config_dir = Path.home() / ".config" / "arxiv-explorer"
        config_dir.mkdir(parents=True, exist_ok=True)

        # Find arxivterminal DB path
        # Priority: XDG_DATA_HOME > ~/.local/share > macOS path
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
            db_path=config_dir / "explorer.db",
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
