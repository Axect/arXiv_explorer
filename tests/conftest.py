"""Shared test fixtures."""

from datetime import datetime
from pathlib import Path

import pytest

from arxiv_explorer.core.config import Config
from arxiv_explorer.core.database import init_db
from arxiv_explorer.core.models import KeywordInterest, Paper, PreferredCategory


@pytest.fixture()
def tmp_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Config:
    """Create an isolated Config pointing to a temp database."""
    db_path = tmp_path / "test.db"
    config = Config(
        db_path=db_path,
        arxivterminal_db_path=tmp_path / "arxivterminal.db",
    )

    def _get_config() -> Config:
        return config

    # Patch every module that imports get_config at the top level
    monkeypatch.setattr("arxiv_explorer.core.database.get_config", _get_config)
    monkeypatch.setattr("arxiv_explorer.services.recommendation.get_config", _get_config)

    # Reset the global config singleton so it doesn't leak between tests
    monkeypatch.setattr("arxiv_explorer.core.config._config", config)

    init_db(db_path)
    return config


@pytest.fixture()
def sample_paper() -> Paper:
    """A minimal Paper for testing."""
    return Paper(
        arxiv_id="2401.00001",
        title="Deep Learning for Particle Physics",
        abstract="We present a novel deep learning approach to jet classification in high energy physics.",
        authors=["Alice", "Bob"],
        categories=["hep-ph", "cs.LG"],
        published=datetime(2024, 1, 1),
    )


@pytest.fixture()
def sample_papers() -> list[Paper]:
    """A list of diverse papers for recommendation testing."""
    return [
        Paper(
            arxiv_id="2401.00001",
            title="Deep Learning for Particle Physics",
            abstract="We present a novel deep learning approach to jet classification.",
            authors=["Alice"],
            categories=["hep-ph", "cs.LG"],
            published=datetime(2024, 1, 1),
        ),
        Paper(
            arxiv_id="2401.00002",
            title="Quantum Computing Survey",
            abstract="A comprehensive survey of quantum computing algorithms and applications.",
            authors=["Bob"],
            categories=["quant-ph", "cs.CC"],
            published=datetime(2024, 1, 5),
        ),
        Paper(
            arxiv_id="2401.00003",
            title="Reinforcement Learning in Robotics",
            abstract="Applying reinforcement learning to autonomous robot navigation.",
            authors=["Charlie"],
            categories=["cs.AI", "cs.RO"],
            published=datetime(2024, 1, 10),
        ),
    ]


@pytest.fixture()
def sample_categories() -> list[PreferredCategory]:
    """Sample preferred categories for scoring tests."""
    return [
        PreferredCategory(id=1, category="hep-ph", priority=2),
        PreferredCategory(id=2, category="cs.AI", priority=1),
    ]


@pytest.fixture()
def sample_keywords() -> list[KeywordInterest]:
    """Sample keywords for scoring tests."""
    return [
        KeywordInterest(id=1, keyword="deep learning", weight=1.5),
        KeywordInterest(id=2, keyword="quantum", weight=1.0),
    ]
