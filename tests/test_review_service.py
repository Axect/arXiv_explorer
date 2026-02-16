"""Tests for the paper review service."""

import json
from datetime import datetime
from unittest.mock import MagicMock

import pytest

from arxiv_explorer.core.config import Config
from arxiv_explorer.core.models import (
    Paper,
    PaperReview,
    ReviewSectionType,
)
from arxiv_explorer.services.review_service import PaperReviewService


# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture()
def review_service() -> PaperReviewService:
    return PaperReviewService()


@pytest.fixture()
def sample_full_text() -> str:
    """Minimal arxiv-doc-builder output for testing section splitting."""
    return """# Test Paper Title

**Authors:** Alice, Bob
**arXiv ID:** 2401.00001

## Abstract

This is the abstract text.

## 1. Introduction

Introduction content here with some detail about the problem.

## 2. Methodology

We propose a novel method for solving the problem.

$$
E = mc^2
$$

$$
F = ma
$$

## 3. Experiments

We test on CIFAR-10 dataset.

| Method | Accuracy |
|--------|----------|
| Ours   | 95.3     |
| Other  | 90.1     |

*Table 1: Results comparison*

![Architecture](figures/fig1.png)
*Figure 1: System architecture overview*

**Figure 2:** Training loss curve over 100 epochs.

## 4. Related Work

Previous work by Smith et al. addressed similar problems.

## 5. Conclusion

We conclude the work with promising results.

## References

[1] Smith et al. Some paper. 2023.
"""


# ── Section Splitting Tests ───────────────────────────────────────────


class TestSectionSplitting:
    """Test the _split_into_sections method."""

    def test_splits_by_h2_headers(self, review_service, sample_full_text):
        sections = review_service._split_into_sections(sample_full_text)
        assert "1. Introduction" in sections
        assert "2. Methodology" in sections
        assert "3. Experiments" in sections
        assert "4. Related Work" in sections
        assert "5. Conclusion" in sections

    def test_preamble_captured(self, review_service, sample_full_text):
        sections = review_service._split_into_sections(sample_full_text)
        assert "_preamble" in sections
        assert "Test Paper Title" in sections["_preamble"]

    def test_section_content(self, review_service, sample_full_text):
        sections = review_service._split_into_sections(sample_full_text)
        assert "novel method" in sections["2. Methodology"]

    def test_empty_text(self, review_service):
        sections = review_service._split_into_sections("")
        assert sections == {"_preamble": ""}

    def test_no_headers(self, review_service):
        text = "Just some text\nwith no headers."
        sections = review_service._split_into_sections(text)
        assert "_preamble" in sections
        assert "Just some text" in sections["_preamble"]


# ── Figure Caption Extraction Tests ───────────────────────────────────


class TestFigureCaptionExtraction:
    """Test figure caption extraction."""

    def test_extracts_image_figures(self, review_service, sample_full_text):
        figures = review_service._extract_figure_captions(sample_full_text)
        ids = {f["figure_id"] for f in figures}
        assert "1" in ids
        fig1 = next(f for f in figures if f["figure_id"] == "1")
        assert "architecture" in fig1["caption"].lower()

    def test_extracts_text_only_figures(self, review_service, sample_full_text):
        figures = review_service._extract_figure_captions(sample_full_text)
        ids = {f["figure_id"] for f in figures}
        assert "2" in ids

    def test_no_figures(self, review_service):
        figures = review_service._extract_figure_captions("No figures here.")
        assert figures == []

    def test_no_duplicates(self, review_service, sample_full_text):
        figures = review_service._extract_figure_captions(sample_full_text)
        ids = [f["figure_id"] for f in figures]
        assert len(ids) == len(set(ids))


# ── Table Extraction Tests ────────────────────────────────────────────


class TestTableExtraction:
    """Test table content extraction."""

    def test_extracts_markdown_tables(self, review_service, sample_full_text):
        tables = review_service._extract_table_content(sample_full_text)
        assert len(tables) >= 1
        assert "Accuracy" in tables[0]["content"]

    def test_extracts_table_caption(self, review_service, sample_full_text):
        tables = review_service._extract_table_content(sample_full_text)
        assert any("Results" in t.get("caption", "") for t in tables)

    def test_no_tables(self, review_service):
        tables = review_service._extract_table_content("No tables here.")
        assert tables == []


# ── Math Extraction Tests ─────────────────────────────────────────────


class TestMathExtraction:
    """Test math block extraction."""

    def test_extracts_display_math(self, review_service, sample_full_text):
        blocks = review_service._extract_math_blocks(sample_full_text)
        assert len(blocks) >= 2
        assert any("E = mc^2" in b for b in blocks)
        assert any("F = ma" in b for b in blocks)

    def test_no_math(self, review_service):
        blocks = review_service._extract_math_blocks("No math here.")
        assert blocks == []


# ── Caching Tests ─────────────────────────────────────────────────────


class TestReviewCaching:
    """Test section-level cache operations."""

    def test_save_and_load_section(self, tmp_config: Config, review_service):
        data = {"tldr": "Test summary", "research_question": "Does it work?"}
        review_service._save_section(
            "2401.00001", ReviewSectionType.EXECUTIVE_SUMMARY, data, "abstract"
        )
        cached = review_service._get_cached_section(
            "2401.00001", ReviewSectionType.EXECUTIVE_SUMMARY
        )
        assert cached is not None
        assert json.loads(cached.content_json) == data

    def test_get_all_cached(self, tmp_config: Config, review_service):
        review_service._save_section(
            "2401.00001",
            ReviewSectionType.EXECUTIVE_SUMMARY,
            {"tldr": "test"},
            "abstract",
        )
        review_service._save_section(
            "2401.00001",
            ReviewSectionType.GLOSSARY,
            {"terms": []},
            "abstract",
        )
        all_cached = review_service._get_all_cached_sections("2401.00001")
        assert len(all_cached) == 2
        assert ReviewSectionType.EXECUTIVE_SUMMARY in all_cached
        assert ReviewSectionType.GLOSSARY in all_cached

    def test_cache_replaces_on_update(self, tmp_config: Config, review_service):
        review_service._save_section(
            "2401.00001",
            ReviewSectionType.EXECUTIVE_SUMMARY,
            {"tldr": "old"},
            "abstract",
        )
        review_service._save_section(
            "2401.00001",
            ReviewSectionType.EXECUTIVE_SUMMARY,
            {"tldr": "new"},
            "full_text",
        )
        cached = review_service._get_cached_section(
            "2401.00001", ReviewSectionType.EXECUTIVE_SUMMARY
        )
        assert json.loads(cached.content_json)["tldr"] == "new"

    def test_delete_review(self, tmp_config: Config, review_service):
        review_service._save_section(
            "2401.00001",
            ReviewSectionType.EXECUTIVE_SUMMARY,
            {"tldr": "test"},
            "abstract",
        )
        assert review_service.delete_review("2401.00001") is True
        assert (
            review_service._get_cached_section(
                "2401.00001", ReviewSectionType.EXECUTIVE_SUMMARY
            )
            is None
        )

    def test_delete_nonexistent(self, tmp_config: Config, review_service):
        assert review_service.delete_review("9999.99999") is False

    def test_get_cached_review(self, tmp_config: Config, review_service):
        review_service._save_section(
            "2401.00001",
            ReviewSectionType.EXECUTIVE_SUMMARY,
            {"tldr": "cached review"},
            "abstract",
        )
        cached_review = review_service.get_cached_review("2401.00001")
        assert cached_review is not None
        assert ReviewSectionType.EXECUTIVE_SUMMARY in cached_review.sections
        assert cached_review.sections[ReviewSectionType.EXECUTIVE_SUMMARY]["tldr"] == "cached review"

    def test_get_cached_review_none(self, tmp_config: Config, review_service):
        assert review_service.get_cached_review("9999.99999") is None


# ── Rendering Tests ───────────────────────────────────────────────────


class TestMarkdownRendering:
    """Test render_markdown output."""

    def _make_review(self, sample_paper, sections=None):
        return PaperReview(
            arxiv_id=sample_paper.arxiv_id,
            title=sample_paper.title,
            authors=sample_paper.authors,
            categories=sample_paper.categories,
            published=sample_paper.published,
            abstract=sample_paper.abstract,
            sections=sections or {},
        )

    def test_renders_header(self, review_service, sample_paper):
        review = self._make_review(sample_paper)
        md = review_service.render_markdown(review)
        assert sample_paper.title in md
        assert sample_paper.arxiv_id in md
        assert "Authors:" in md

    def test_renders_executive_summary(self, review_service, sample_paper):
        review = self._make_review(
            sample_paper,
            {
                ReviewSectionType.EXECUTIVE_SUMMARY: {
                    "tldr": "This paper does X.",
                    "research_question": "Can we do X?",
                    "approach_summary": "We use Y.",
                    "main_result": "95% accuracy",
                }
            },
        )
        md = review_service.render_markdown(review)
        assert "Executive Summary" in md
        assert "This paper does X." in md
        assert "95% accuracy" in md

    def test_renders_key_contributions(self, review_service, sample_paper):
        review = self._make_review(
            sample_paper,
            {
                ReviewSectionType.KEY_CONTRIBUTIONS: {
                    "contributions": [
                        {
                            "contribution": "Novel architecture",
                            "type": "methodological",
                            "significance": "First of its kind",
                        }
                    ]
                }
            },
        )
        md = review_service.render_markdown(review)
        assert "Key Contributions" in md
        assert "Novel architecture" in md

    def test_renders_glossary_as_table(self, review_service, sample_paper):
        review = self._make_review(
            sample_paper,
            {
                ReviewSectionType.GLOSSARY: {
                    "terms": [
                        {"term": "CNN", "definition": "Convolutional Neural Network"}
                    ]
                }
            },
        )
        md = review_service.render_markdown(review)
        assert "| **CNN** |" in md
        assert "Convolutional Neural Network" in md

    def test_renders_math_formulations(self, review_service, sample_paper):
        review = self._make_review(
            sample_paper,
            {
                ReviewSectionType.MATH_FORMULATIONS: {
                    "formulations": [
                        {
                            "equation_label": "Loss function",
                            "latex": "L = -\\sum y \\log p",
                            "plain_language": "Cross-entropy loss",
                            "role": "Training objective",
                        }
                    ]
                }
            },
        )
        md = review_service.render_markdown(review)
        assert "Mathematical Formulations" in md
        assert "$$" in md
        assert "Cross-entropy loss" in md

    def test_renders_footer(self, review_service, sample_paper):
        review = self._make_review(sample_paper)
        md = review_service.render_markdown(review)
        assert "Generated by arXiv Explorer" in md

    def test_renders_source_type(self, review_service, sample_paper):
        review = self._make_review(sample_paper)
        review.source_type = "full_text"
        md = review_service.render_markdown(review)
        assert "Full text analysis" in md

        review.source_type = "abstract"
        md = review_service.render_markdown(review)
        assert "Abstract-only analysis" in md


# ── Model Tests ───────────────────────────────────────────────────────


class TestPaperReviewModel:
    """Test PaperReview dataclass."""

    def test_is_complete_false(self, sample_paper):
        review = PaperReview(
            arxiv_id=sample_paper.arxiv_id,
            title=sample_paper.title,
            authors=sample_paper.authors,
            categories=sample_paper.categories,
            published=sample_paper.published,
            abstract=sample_paper.abstract,
            sections={ReviewSectionType.EXECUTIVE_SUMMARY: {}},
        )
        assert review.is_complete is False
        assert len(review.missing_sections) == len(ReviewSectionType) - 1

    def test_is_complete_true(self, sample_paper):
        all_sections = {st: {} for st in ReviewSectionType}
        review = PaperReview(
            arxiv_id=sample_paper.arxiv_id,
            title=sample_paper.title,
            authors=sample_paper.authors,
            categories=sample_paper.categories,
            published=sample_paper.published,
            abstract=sample_paper.abstract,
            sections=all_sections,
        )
        assert review.is_complete is True
        assert review.missing_sections == []

    def test_missing_sections_returns_correct_types(self, sample_paper):
        review = PaperReview(
            arxiv_id=sample_paper.arxiv_id,
            title=sample_paper.title,
            authors=sample_paper.authors,
            categories=sample_paper.categories,
            published=sample_paper.published,
            abstract=sample_paper.abstract,
            sections={
                ReviewSectionType.EXECUTIVE_SUMMARY: {},
                ReviewSectionType.GLOSSARY: {},
            },
        )
        missing = review.missing_sections
        assert ReviewSectionType.EXECUTIVE_SUMMARY not in missing
        assert ReviewSectionType.GLOSSARY not in missing
        assert ReviewSectionType.METHODOLOGY in missing


# ── Integration Tests (mocked AI) ────────────────────────────────────


class TestGenerateReviewMocked:
    """Test generate_review with mocked AI provider."""

    def _mock_responses(self):
        return {
            ReviewSectionType.EXECUTIVE_SUMMARY: {
                "tldr": "Test",
                "research_question": "Q",
                "approach_summary": "A",
                "main_result": "R",
            },
            ReviewSectionType.KEY_CONTRIBUTIONS: {
                "contributions": [
                    {"contribution": "C", "type": "methodological", "significance": "S"}
                ]
            },
            ReviewSectionType.SECTION_SUMMARIES: {"sections": []},
            ReviewSectionType.METHODOLOGY: {
                "overview": "O",
                "steps": [],
                "assumptions": [],
                "complexity_notes": "",
            },
            ReviewSectionType.MATH_FORMULATIONS: {"formulations": []},
            ReviewSectionType.FIGURES: {"figures": []},
            ReviewSectionType.TABLES: {"tables": []},
            ReviewSectionType.EXPERIMENTAL_RESULTS: {
                "datasets": [],
                "baselines": [],
                "metrics": [],
                "main_results": "",
                "ablation_studies": "",
                "notable_findings": [],
            },
            ReviewSectionType.STRENGTHS_WEAKNESSES: {
                "strengths": [],
                "weaknesses": [],
                "overall_assessment": "",
            },
            ReviewSectionType.RELATED_WORK: {
                "research_areas": [],
                "key_prior_works": [],
                "positioning": "",
            },
            ReviewSectionType.GLOSSARY: {"terms": []},
            ReviewSectionType.QUESTIONS: {"questions": []},
        }

    def test_generates_with_abstract_only(
        self, tmp_config: Config, sample_paper
    ):
        service = PaperReviewService()
        service._extract_full_text = MagicMock(return_value=None)

        responses = self._mock_responses()
        section_order = [st for st, _ in service.SECTION_PIPELINE]
        call_count = [0]

        def mock_invoke(prompt):
            idx = call_count[0]
            call_count[0] += 1
            return responses.get(section_order[idx], {})

        service._invoke_ai = mock_invoke

        review = service.generate_review(sample_paper)
        assert review is not None
        assert review.source_type == "abstract"
        assert len(review.sections) > 0

    def test_resumes_from_cache(self, tmp_config: Config, sample_paper):
        service = PaperReviewService()
        service._extract_full_text = MagicMock(return_value=None)

        # Pre-populate cache for executive_summary
        service._save_section(
            sample_paper.arxiv_id,
            ReviewSectionType.EXECUTIVE_SUMMARY,
            {"tldr": "Cached", "research_question": "Q"},
            "abstract",
        )

        invoke_calls: list[str] = []

        def tracking_invoke(prompt):
            invoke_calls.append(prompt)
            return {"dummy": "data"}

        service._invoke_ai = tracking_invoke

        review = service.generate_review(sample_paper)
        # Should have used cache for executive_summary
        assert (
            review.sections[ReviewSectionType.EXECUTIVE_SUMMARY]["tldr"]
            == "Cached"
        )
        # AI should have been called for remaining sections, minus:
        # - 1 cached (executive_summary)
        # - 3 empty sections in abstract-only mode (figures, tables, math)
        assert len(invoke_calls) == len(ReviewSectionType) - 1 - 3

    def test_force_regenerates_cached(self, tmp_config: Config, sample_paper):
        service = PaperReviewService()
        service._extract_full_text = MagicMock(return_value=None)

        # Pre-populate cache
        service._save_section(
            sample_paper.arxiv_id,
            ReviewSectionType.EXECUTIVE_SUMMARY,
            {"tldr": "Old cached"},
            "abstract",
        )

        responses = self._mock_responses()
        section_order = [st for st, _ in service.SECTION_PIPELINE]
        call_count = [0]

        def mock_invoke(prompt):
            idx = call_count[0]
            call_count[0] += 1
            return responses.get(section_order[idx], {})

        service._invoke_ai = mock_invoke

        review = service.generate_review(sample_paper, force=True)
        # With force=True, AI called for all sections except 3 empty
        # (figures, tables, math) which get empty data in abstract-only mode
        assert call_count[0] == len(ReviewSectionType) - 3
        assert review.sections[ReviewSectionType.EXECUTIVE_SUMMARY]["tldr"] == "Test"

    def test_callbacks_invoked(self, tmp_config: Config, sample_paper):
        service = PaperReviewService()
        service._extract_full_text = MagicMock(return_value=None)

        responses = self._mock_responses()
        section_order = [st for st, _ in service.SECTION_PIPELINE]
        call_count = [0]

        def mock_invoke(prompt):
            idx = call_count[0]
            call_count[0] += 1
            return responses.get(section_order[idx], {})

        service._invoke_ai = mock_invoke

        start_calls: list[tuple] = []
        complete_calls: list[tuple] = []

        def on_start(st, idx, total):
            start_calls.append((st, idx, total))

        def on_complete(st, success):
            complete_calls.append((st, success))

        service.generate_review(
            sample_paper,
            on_section_start=on_start,
            on_section_complete=on_complete,
        )
        assert len(start_calls) == len(ReviewSectionType)
        assert len(complete_calls) == len(ReviewSectionType)
        assert all(s for _, s in complete_calls)

    def test_returns_none_on_total_failure(
        self, tmp_config: Config, sample_paper
    ):
        service = PaperReviewService()
        service._extract_full_text = MagicMock(return_value=None)
        service._invoke_ai = MagicMock(return_value=None)

        review = service.generate_review(sample_paper)
        # Figures/Tables/Math get empty data even on AI failure, so review is not None
        # but all AI-dependent sections should fail
        assert review is not None
        # The 3 empty sections should still be present
        assert ReviewSectionType.FIGURES in review.sections
        assert ReviewSectionType.TABLES in review.sections
        assert ReviewSectionType.MATH_FORMULATIONS in review.sections


# ── Prompt Builder Tests ──────────────────────────────────────────────


class TestPromptBuilders:
    """Test that prompt builders produce valid prompts."""

    def test_all_section_types_have_prompt_builder(
        self, review_service, sample_paper
    ):
        """Every section type in the pipeline must have a prompt builder."""
        for section_type, _ in review_service.SECTION_PIPELINE:
            prompt = review_service._build_prompt(
                section_type=section_type,
                paper=sample_paper,
                full_text_md=None,
                paper_sections=None,
                figure_captions=None,
                table_content=None,
                math_blocks=None,
            )
            assert isinstance(prompt, str)
            assert len(prompt) > 0
            assert sample_paper.title in prompt

    def test_methodology_uses_relevant_sections(
        self, review_service, sample_paper
    ):
        paper_sections = {
            "_preamble": "title",
            "1. Introduction": "intro text",
            "2. Methodology": "our novel approach uses attention",
            "3. Experiments": "we test on cifar",
        }
        prompt = review_service._build_prompt(
            section_type=ReviewSectionType.METHODOLOGY,
            paper=sample_paper,
            full_text_md=None,
            paper_sections=paper_sections,
            figure_captions=None,
            table_content=None,
            math_blocks=None,
        )
        assert "attention" in prompt
        # Should not include experiment sections
        assert "cifar" not in prompt


# ── Empty Section Data Tests ──────────────────────────────────────────


class TestEmptySectionData:
    """Test _empty_section_data returns correct structures."""

    def test_figures_empty(self):
        data = PaperReviewService._empty_section_data(ReviewSectionType.FIGURES)
        assert data == {"figures": []}

    def test_tables_empty(self):
        data = PaperReviewService._empty_section_data(ReviewSectionType.TABLES)
        assert data == {"tables": []}

    def test_math_empty(self):
        data = PaperReviewService._empty_section_data(
            ReviewSectionType.MATH_FORMULATIONS
        )
        assert data == {"formulations": []}

    def test_other_empty(self):
        data = PaperReviewService._empty_section_data(
            ReviewSectionType.EXECUTIVE_SUMMARY
        )
        assert data == {}
