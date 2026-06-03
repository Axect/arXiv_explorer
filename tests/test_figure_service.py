"""Offline tests for figure_service (no codex or network calls)."""

from pathlib import Path

import arxiv_explorer.services.figure_service as figure_service
from arxiv_explorer.services.figure_service import (
    codex_imagegen_available,
    compose_prompt,
    generate_figures,
)

# ── compose_prompt ─────────────────────────────────────────────────────


class TestComposePrompt:
    """Test the prompt composition helper."""

    def _minimal_brief(self):
        return {
            "headline": "H",
            "subtitle": "S",
            "panels": [{"name": "P1", "content": "draw boxes around inputs"}],
        }

    def test_contains_overall_look_style_header(self):
        prompt = compose_prompt(self._minimal_brief(), "friendly")
        assert "OVERALL LOOK" in prompt

    def test_contains_headline(self):
        prompt = compose_prompt(self._minimal_brief(), "friendly")
        assert "H" in prompt

    def test_contains_panel_content(self):
        prompt = compose_prompt(self._minimal_brief(), "friendly")
        assert "draw boxes around inputs" in prompt

    def test_contains_english_guard_text(self):
        prompt = compose_prompt(self._minimal_brief(), "friendly")
        assert "readable English" in prompt

    def test_returns_string(self):
        prompt = compose_prompt(self._minimal_brief(), "friendly")
        assert isinstance(prompt, str)

    def test_contains_subtitle(self):
        prompt = compose_prompt(self._minimal_brief(), "friendly")
        assert "S" in prompt

    def test_falls_back_to_friendly_for_unknown_theme(self):
        prompt = compose_prompt(self._minimal_brief(), "nonexistent_theme")
        # Should still produce a non-empty string with style content
        assert "OVERALL LOOK" in prompt

    def test_multiple_panels_all_present(self):
        brief = {
            "headline": "Multi panel",
            "subtitle": "Three steps",
            "panels": [
                {"name": "Step1", "content": "boxes labeled A"},
                {"name": "Step2", "content": "arrows pointing right"},
                {"name": "Step3", "content": "output box"},
            ],
        }
        prompt = compose_prompt(brief, "friendly")
        assert "boxes labeled A" in prompt
        assert "arrows pointing right" in prompt
        assert "output box" in prompt

    def test_empty_panels_list_does_not_raise(self):
        brief = {"headline": "No panels", "subtitle": "Empty", "panels": []}
        prompt = compose_prompt(brief, "friendly")
        assert isinstance(prompt, str)

    def test_missing_headline_does_not_raise(self):
        brief = {"panels": [{"name": "P", "content": "stuff"}]}
        prompt = compose_prompt(brief, "friendly")
        assert isinstance(prompt, str)


# ── generate_figures ───────────────────────────────────────────────────


class TestGenerateFigures:
    """Test generate_figures returns {} gracefully when runtime is absent."""

    def test_returns_empty_dict_when_codex_unavailable(
        self, tmp_path: Path, monkeypatch
    ):
        monkeypatch.setattr(figure_service, "_bundled_codex", lambda: None)
        brief = {
            "headline": "Method overview",
            "subtitle": "Pipeline",
            "panels": [{"name": "Input", "content": "A box"}],
        }
        result = generate_figures([("method", brief)], tmp_path)
        assert result == {}

    def test_returns_empty_dict_for_empty_briefs_list(
        self, tmp_path: Path, monkeypatch
    ):
        monkeypatch.setattr(figure_service, "_bundled_codex", lambda: None)
        result = generate_figures([], tmp_path)
        assert result == {}

    def test_creates_output_directory_even_without_codex(
        self, tmp_path: Path, monkeypatch
    ):
        out_dir = tmp_path / "new_figures"
        monkeypatch.setattr(figure_service, "_bundled_codex", lambda: None)
        generate_figures([("method", {"headline": "X", "subtitle": "Y", "panels": []})], out_dir)
        assert out_dir.exists()


# ── codex_imagegen_available ───────────────────────────────────────────


class TestCodexImagegenAvailable:
    """Test availability detection when the runtime is absent."""

    def test_returns_false_when_bundled_codex_is_none(self, monkeypatch):
        monkeypatch.setattr(figure_service, "_bundled_codex", lambda: None)
        monkeypatch.setattr(figure_service, "_AVAILABLE_CACHE", None)
        result = codex_imagegen_available()
        assert result is False

    def test_sets_cache_to_false_when_bundled_codex_is_none(self, monkeypatch):
        monkeypatch.setattr(figure_service, "_bundled_codex", lambda: None)
        monkeypatch.setattr(figure_service, "_AVAILABLE_CACHE", None)
        codex_imagegen_available()
        assert figure_service._AVAILABLE_CACHE is False

    def test_uses_cache_on_second_call(self, monkeypatch):
        monkeypatch.setattr(figure_service, "_AVAILABLE_CACHE", False)
        call_count = [0]

        def counting_bundled_codex():
            call_count[0] += 1
            return None

        monkeypatch.setattr(figure_service, "_bundled_codex", counting_bundled_codex)
        result = codex_imagegen_available()
        assert result is False
        assert call_count[0] == 0  # cache was hit, not recomputed
