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

        result = runner.invoke(app, ["--no-update-check", "show", "2401.00001", "--json"])
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

        result = runner.invoke(app, ["--no-update-check", "show", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "interesting_papers" in data
        assert "2401.00001" in data["interesting_papers"]
