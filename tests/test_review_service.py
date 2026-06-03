"""Tests for the paper review service (journal-club 9-section structure)."""

import json
from unittest.mock import MagicMock

import pytest

from arxiv_explorer.core.config import Config
from arxiv_explorer.core.models import (
    PaperReview,
    ReviewSectionType,
)
from arxiv_explorer.services.review_service import PaperReviewService

# ── Fixtures ───────────────────────────────────────────────────────────


@pytest.fixture()
def review_service() -> PaperReviewService:
    return PaperReviewService()


# ── Model Tests ────────────────────────────────────────────────────────


class TestPaperReviewModel:
    """Test PaperReview dataclass with the 9-section structure."""

    def _make_review(self, sample_paper, sections=None, figure_paths=None):
        return PaperReview(
            arxiv_id=sample_paper.arxiv_id,
            title=sample_paper.title,
            authors=sample_paper.authors,
            categories=sample_paper.categories,
            published=sample_paper.published,
            abstract=sample_paper.abstract,
            sections=sections or {},
            figure_paths=figure_paths or {},
        )

    def test_is_complete_false_with_one_section(self, sample_paper):
        review = self._make_review(
            sample_paper,
            sections={ReviewSectionType.HOOK: {}},
        )
        assert review.is_complete is False
        assert len(review.missing_sections) == len(ReviewSectionType) - 1

    def test_is_complete_true_with_all_nine_sections(self, sample_paper):
        all_sections = {st: {} for st in ReviewSectionType}
        review = self._make_review(sample_paper, sections=all_sections)
        assert review.is_complete is True
        assert review.missing_sections == []

    def test_missing_sections_returns_correct_types(self, sample_paper):
        review = self._make_review(
            sample_paper,
            sections={
                ReviewSectionType.HOOK: {},
                ReviewSectionType.PROBLEM: {},
            },
        )
        missing = review.missing_sections
        assert ReviewSectionType.HOOK not in missing
        assert ReviewSectionType.PROBLEM not in missing
        assert ReviewSectionType.METHOD in missing
        assert ReviewSectionType.RESULTS in missing
        assert ReviewSectionType.TAKEAWAYS in missing

    def test_figure_paths_field_defaults_to_empty_dict(self, sample_paper):
        review = self._make_review(sample_paper)
        assert review.figure_paths == {}

    def test_figure_paths_stores_method_and_results(self, sample_paper):
        paths = {"method": "figures/method.png", "results": "figures/results.png"}
        review = self._make_review(sample_paper, figure_paths=paths)
        assert review.figure_paths["method"] == "figures/method.png"
        assert review.figure_paths["results"] == "figures/results.png"

    def test_all_nine_section_types_exist(self):
        expected = {
            "hook", "problem", "key_idea", "method", "results",
            "significance", "appraisal", "discussion", "takeaways",
        }
        actual = {st.value for st in ReviewSectionType}
        assert actual == expected

    def test_missing_sections_empty_when_all_present(self, sample_paper):
        review = self._make_review(
            sample_paper,
            sections={st: {} for st in ReviewSectionType},
        )
        assert review.missing_sections == []


# ── Caching Tests ──────────────────────────────────────────────────────


class TestReviewCaching:
    """Test section-level cache operations with new section types."""

    def test_save_and_load_hook_section(self, tmp_config: Config, review_service):
        data = {"one_liner": "Great paper", "why_care": "Important work", "field": "ML"}
        review_service._save_section("2401.00001", ReviewSectionType.HOOK, data, "abstract")
        cached = review_service._get_cached_section("2401.00001", ReviewSectionType.HOOK)
        assert cached is not None
        assert json.loads(cached.content_json) == data

    def test_save_and_load_method_section(self, tmp_config: Config, review_service):
        data = {
            "overview": "We propose X",
            "steps": ["Step 1", "Step 2"],
            "key_components": [],
            "figure_brief": {
                "headline": "Method overview",
                "subtitle": "Pipeline diagram",
                "panels": [{"name": "Input", "content": "Box labeled Input"}],
            },
        }
        review_service._save_section("2401.00001", ReviewSectionType.METHOD, data, "full_text")
        cached = review_service._get_cached_section("2401.00001", ReviewSectionType.METHOD)
        assert cached is not None
        assert json.loads(cached.content_json)["overview"] == "We propose X"

    def test_get_all_cached_returns_all_saved(self, tmp_config: Config, review_service):
        review_service._save_section(
            "2401.00001", ReviewSectionType.HOOK, {"one_liner": "test"}, "abstract"
        )
        review_service._save_section(
            "2401.00001", ReviewSectionType.PROBLEM, {"problem": "hard"}, "abstract"
        )
        all_cached = review_service._get_all_cached_sections("2401.00001")
        assert len(all_cached) == 2
        assert ReviewSectionType.HOOK in all_cached
        assert ReviewSectionType.PROBLEM in all_cached

    def test_cache_replaces_on_update(self, tmp_config: Config, review_service):
        review_service._save_section(
            "2401.00001", ReviewSectionType.HOOK, {"one_liner": "old"}, "abstract"
        )
        review_service._save_section(
            "2401.00001", ReviewSectionType.HOOK, {"one_liner": "new"}, "full_text"
        )
        cached = review_service._get_cached_section("2401.00001", ReviewSectionType.HOOK)
        assert json.loads(cached.content_json)["one_liner"] == "new"

    def test_delete_review_removes_all_sections(self, tmp_config: Config, review_service):
        review_service._save_section(
            "2401.00001", ReviewSectionType.HOOK, {"one_liner": "test"}, "abstract"
        )
        review_service._save_section(
            "2401.00001", ReviewSectionType.TAKEAWAYS, {"bullets": []}, "abstract"
        )
        assert review_service.delete_review("2401.00001") is True
        assert review_service._get_cached_section("2401.00001", ReviewSectionType.HOOK) is None
        assert review_service._get_cached_section("2401.00001", ReviewSectionType.TAKEAWAYS) is None

    def test_delete_nonexistent_returns_false(self, tmp_config: Config, review_service):
        assert review_service.delete_review("9999.99999") is False

    def test_get_cached_review_returns_hook_data(self, tmp_config: Config, review_service):
        review_service._save_section(
            "2401.00001",
            ReviewSectionType.HOOK,
            {"one_liner": "cached hook"},
            "abstract",
        )
        cached_review = review_service.get_cached_review("2401.00001")
        assert cached_review is not None
        assert ReviewSectionType.HOOK in cached_review.sections
        assert cached_review.sections[ReviewSectionType.HOOK]["one_liner"] == "cached hook"

    def test_get_cached_review_none_for_unknown_id(self, tmp_config: Config, review_service):
        assert review_service.get_cached_review("9999.99999") is None


# ── Rendering Tests ────────────────────────────────────────────────────


class TestMarkdownRendering:
    """Test render_markdown output for the 9-section journal-club structure."""

    def _make_review(self, sample_paper, sections=None, figure_paths=None):
        return PaperReview(
            arxiv_id=sample_paper.arxiv_id,
            title=sample_paper.title,
            authors=sample_paper.authors,
            categories=sample_paper.categories,
            published=sample_paper.published,
            abstract=sample_paper.abstract,
            sections=sections or {},
            figure_paths=figure_paths or {},
        )

    def test_renders_paper_title_and_arxiv_id(self, review_service, sample_paper):
        review = self._make_review(sample_paper)
        md = review_service.render_markdown(review)
        assert sample_paper.title in md
        assert sample_paper.arxiv_id in md
        assert "**Authors**" in md

    def test_renders_source_label_full_text(self, review_service, sample_paper):
        review = self._make_review(sample_paper)
        review.source_type = "full_text"
        md = review_service.render_markdown(review)
        assert "Full text" in md

    def test_renders_source_label_abstract_only(self, review_service, sample_paper):
        review = self._make_review(sample_paper)
        review.source_type = "abstract"
        md = review_service.render_markdown(review)
        assert "Abstract only" in md

    def test_renders_footer(self, review_service, sample_paper):
        review = self._make_review(sample_paper)
        md = review_service.render_markdown(review)
        assert "Generated by arXiv Explorer" in md

    def test_renders_tldr_heading_from_hook(self, review_service, sample_paper):
        review = self._make_review(
            sample_paper,
            sections={
                ReviewSectionType.HOOK: {
                    "one_liner": "This paper solves everything.",
                    "why_care": "Matters because of reasons.",
                    "field": "Probabilistic ML",
                }
            },
        )
        md = review_service.render_markdown(review)
        assert "## TL;DR" in md
        assert "This paper solves everything." in md
        assert "Probabilistic ML" in md

    def test_renders_the_problem_heading(self, review_service, sample_paper):
        review = self._make_review(
            sample_paper,
            sections={
                ReviewSectionType.PROBLEM: {
                    "problem": "Classification is hard.",
                    "motivation": "Performance gap exists.",
                    "prior_gap": "Prior work ignored X.",
                }
            },
        )
        md = review_service.render_markdown(review)
        assert "## The Problem" in md
        assert "Classification is hard." in md
        assert "Prior work ignored X." in md

    def test_renders_key_idea_heading(self, review_service, sample_paper):
        review = self._make_review(
            sample_paper,
            sections={
                ReviewSectionType.KEY_IDEA: {
                    "idea": "Use attention.",
                    "intuition": "Attention focuses.",
                    "analogy": "Like a spotlight.",
                }
            },
        )
        md = review_service.render_markdown(review)
        assert "## Key Idea" in md
        assert "Use attention." in md
        assert "Like a spotlight." in md

    def test_renders_how_it_works_heading(self, review_service, sample_paper):
        review = self._make_review(
            sample_paper,
            sections={
                ReviewSectionType.METHOD: {
                    "overview": "We stack layers.",
                    "steps": ["Encode input", "Apply attention"],
                    "key_components": [{"name": "Encoder", "role": "Embeds tokens"}],
                    "figure_brief": {
                        "headline": "Method overview",
                        "subtitle": "The pipeline",
                        "panels": [],
                    },
                }
            },
        )
        md = review_service.render_markdown(review)
        assert "## How It Works" in md
        assert "We stack layers." in md
        assert "Encoder" in md

    def test_renders_key_results_heading(self, review_service, sample_paper):
        review = self._make_review(
            sample_paper,
            sections={
                ReviewSectionType.RESULTS: {
                    "headline": "SOTA on CIFAR-10.",
                    "key_numbers": [
                        {"metric": "Accuracy", "value": "95.3%", "meaning": "Best reported"}
                    ],
                    "takeaway": "Method generalizes well.",
                    "figure_brief": {
                        "headline": "Key results",
                        "subtitle": "Comparison chart",
                        "panels": [],
                    },
                }
            },
        )
        md = review_service.render_markdown(review)
        assert "## Key Results" in md
        assert "SOTA on CIFAR-10." in md
        assert "95.3%" in md

    def test_renders_why_it_matters_heading(self, review_service, sample_paper):
        review = self._make_review(
            sample_paper,
            sections={
                ReviewSectionType.SIGNIFICANCE: {
                    "why_matters": "Changes the field.",
                    "applications": ["Drug discovery"],
                    "who_should_care": "ML practitioners",
                }
            },
        )
        md = review_service.render_markdown(review)
        assert "## Why It Matters" in md
        assert "Changes the field." in md
        assert "Drug discovery" in md

    def test_renders_strengths_limitations_heading(self, review_service, sample_paper):
        review = self._make_review(
            sample_paper,
            sections={
                ReviewSectionType.APPRAISAL: {
                    "strengths": ["Clear exposition"],
                    "limitations": ["Small dataset"],
                    "open_questions": ["Does it scale?"],
                }
            },
        )
        md = review_service.render_markdown(review)
        assert "## Strengths, Limitations & Open Questions" in md
        assert "Clear exposition" in md
        assert "Small dataset" in md
        assert "Does it scale?" in md

    def test_renders_discussion_questions_heading(self, review_service, sample_paper):
        review = self._make_review(
            sample_paper,
            sections={
                ReviewSectionType.DISCUSSION: {
                    "questions": [
                        {
                            "question": "Why did this work?",
                            "why_interesting": "Fundamental question.",
                        }
                    ]
                }
            },
        )
        md = review_service.render_markdown(review)
        assert "## Discussion Questions" in md
        assert "Why did this work?" in md

    def test_renders_takeaways_heading(self, review_service, sample_paper):
        review = self._make_review(
            sample_paper,
            sections={
                ReviewSectionType.TAKEAWAYS: {
                    "bullets": ["Point one", "Point two"],
                    "one_sentence": "A great paper.",
                }
            },
        )
        md = review_service.render_markdown(review)
        assert "## Takeaways" in md
        assert "Point one" in md
        assert "A great paper." in md

    def test_method_figure_embedded_when_path_present(self, review_service, sample_paper):
        review = self._make_review(
            sample_paper,
            sections={
                ReviewSectionType.METHOD: {
                    "overview": "Pipeline here.",
                    "steps": [],
                    "key_components": [],
                    "figure_brief": {"headline": "X", "subtitle": "Y", "panels": []},
                }
            },
            figure_paths={"method": "figures/method.png", "results": "figures/results.png"},
        )
        md = review_service.render_markdown(review)
        assert "![Method overview](figures/method.png)" in md

    def test_results_figure_embedded_when_path_present(self, review_service, sample_paper):
        review = self._make_review(
            sample_paper,
            sections={
                ReviewSectionType.RESULTS: {
                    "headline": "SOTA.",
                    "key_numbers": [],
                    "takeaway": "Good.",
                    "figure_brief": {"headline": "X", "subtitle": "Y", "panels": []},
                }
            },
            figure_paths={"method": "figures/method.png", "results": "figures/results.png"},
        )
        md = review_service.render_markdown(review)
        assert "![Key results](figures/results.png)" in md

    def test_no_figure_tags_when_figure_paths_empty(self, review_service, sample_paper):
        review = self._make_review(
            sample_paper,
            sections={
                ReviewSectionType.METHOD: {
                    "overview": "Pipeline.",
                    "steps": [],
                    "key_components": [],
                    "figure_brief": {"headline": "X", "subtitle": "Y", "panels": []},
                },
                ReviewSectionType.RESULTS: {
                    "headline": "SOTA.",
                    "key_numbers": [],
                    "takeaway": "Good.",
                    "figure_brief": {"headline": "X", "subtitle": "Y", "panels": []},
                },
            },
            figure_paths={},
        )
        md = review_service.render_markdown(review)
        assert "![Method overview]" not in md
        assert "![Key results]" not in md

    def test_no_accept_reject_wording_in_output(self, review_service, sample_paper):
        all_sections = {
            ReviewSectionType.HOOK: {
                "one_liner": "Great work.",
                "why_care": "Important.",
                "field": "ML",
            },
            ReviewSectionType.APPRAISAL: {
                "strengths": ["Clear"],
                "limitations": ["Limited data"],
                "open_questions": ["Future work?"],
            },
        }
        review = self._make_review(sample_paper, sections=all_sections)
        md = review_service.render_markdown(review)
        md_lower = md.lower()
        assert "strong_accept" not in md_lower
        assert "weak_reject" not in md_lower
        assert "weak_accept" not in md_lower
        assert "strong_reject" not in md_lower


# ── Empty Section Data Tests ───────────────────────────────────────────


class TestEmptySectionData:
    """Test render_markdown with missing or empty section dicts does not raise."""

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

    def test_empty_sections_dict_does_not_raise(self, review_service, sample_paper):
        review = self._make_review(sample_paper, sections={})
        md = review_service.render_markdown(review)
        assert sample_paper.title in md

    def test_hook_with_empty_dict_does_not_raise(self, review_service, sample_paper):
        review = self._make_review(sample_paper, sections={ReviewSectionType.HOOK: {}})
        md = review_service.render_markdown(review)
        assert sample_paper.title in md

    def test_method_with_empty_dict_does_not_raise(self, review_service, sample_paper):
        review = self._make_review(sample_paper, sections={ReviewSectionType.METHOD: {}})
        md = review_service.render_markdown(review)
        assert sample_paper.title in md

    def test_results_with_empty_dict_does_not_raise(self, review_service, sample_paper):
        review = self._make_review(sample_paper, sections={ReviewSectionType.RESULTS: {}})
        md = review_service.render_markdown(review)
        assert sample_paper.title in md

    def test_appraisal_with_empty_dict_does_not_raise(self, review_service, sample_paper):
        review = self._make_review(sample_paper, sections={ReviewSectionType.APPRAISAL: {}})
        md = review_service.render_markdown(review)
        assert sample_paper.title in md

    def test_discussion_with_empty_dict_does_not_raise(self, review_service, sample_paper):
        review = self._make_review(sample_paper, sections={ReviewSectionType.DISCUSSION: {}})
        md = review_service.render_markdown(review)
        assert sample_paper.title in md

    def test_takeaways_with_empty_dict_does_not_raise(self, review_service, sample_paper):
        review = self._make_review(sample_paper, sections={ReviewSectionType.TAKEAWAYS: {}})
        md = review_service.render_markdown(review)
        assert sample_paper.title in md


# ── Prompt Builder Tests ───────────────────────────────────────────────


class TestPromptBuilders:
    """Test that all 9 prompt builders produce valid prompts."""

    def test_all_nine_section_types_have_prompt_builder(self, review_service, sample_paper):
        for section_type, _ in review_service.SECTION_PIPELINE:
            prompt = review_service._build_prompt(
                section_type=section_type,
                paper=sample_paper,
                full_text_md=None,
                paper_sections=None,
            )
            assert isinstance(prompt, str)
            assert len(prompt) > 0
            assert sample_paper.title in prompt

    def test_section_pipeline_has_exactly_nine_entries(self, review_service):
        assert len(review_service.SECTION_PIPELINE) == 9

    def test_pipeline_covers_all_section_types(self, review_service):
        pipeline_types = {st for st, _ in review_service.SECTION_PIPELINE}
        assert pipeline_types == set(ReviewSectionType)

    def test_method_prompt_mentions_figure_brief(self, review_service, sample_paper):
        prompt = review_service._build_prompt(
            section_type=ReviewSectionType.METHOD,
            paper=sample_paper,
            full_text_md=None,
            paper_sections=None,
        )
        assert "figure_brief" in prompt

    def test_results_prompt_mentions_figure_brief(self, review_service, sample_paper):
        prompt = review_service._build_prompt(
            section_type=ReviewSectionType.RESULTS,
            paper=sample_paper,
            full_text_md=None,
            paper_sections=None,
        )
        assert "figure_brief" in prompt

    def test_hook_prompt_does_not_mention_figure_brief(self, review_service, sample_paper):
        prompt = review_service._build_prompt(
            section_type=ReviewSectionType.HOOK,
            paper=sample_paper,
            full_text_md=None,
            paper_sections=None,
        )
        assert "figure_brief" not in prompt

    def test_method_prompt_uses_paper_sections(self, review_service, sample_paper):
        paper_sections = {
            "_preamble": "title",
            "1. Introduction": "intro text",
            "2. Method": "our novel architecture uses cross-attention layers",
            "3. Experiments": "we test on cifar10",
        }
        prompt = review_service._build_prompt(
            section_type=ReviewSectionType.METHOD,
            paper=sample_paper,
            full_text_md=None,
            paper_sections=paper_sections,
        )
        assert "cross-attention" in prompt

    def test_results_prompt_uses_experiment_sections(self, review_service, sample_paper):
        paper_sections = {
            "_preamble": "title",
            "1. Method": "our approach",
            "2. Experiments": "state-of-the-art on imagenet benchmark",
        }
        prompt = review_service._build_prompt(
            section_type=ReviewSectionType.RESULTS,
            paper=sample_paper,
            full_text_md=None,
            paper_sections=paper_sections,
        )
        assert "imagenet" in prompt


# ── Integration Tests (mocked AI) ─────────────────────────────────────


class TestGenerateReviewMocked:
    """Test generate_review with mocked _invoke_ai."""

    def _mock_responses(self):
        """Return realistic per-section JSON dicts matching new schema."""
        return {
            ReviewSectionType.HOOK: {
                "one_liner": "A new way to classify jets.",
                "why_care": "Opens doors for HEP analysis.",
                "field": "Particle Physics ML",
            },
            ReviewSectionType.PROBLEM: {
                "problem": "Jet classification is compute-heavy.",
                "motivation": "Faster inference enables real-time triggers.",
                "prior_gap": "Prior methods require full event reconstruction.",
            },
            ReviewSectionType.KEY_IDEA: {
                "idea": "Use graph networks directly on particle clouds.",
                "intuition": "Graphs capture local neighbourhood structure.",
                "analogy": "Like a social network of particles.",
            },
            ReviewSectionType.METHOD: {
                "overview": "Graph neural network on particle-flow inputs.",
                "steps": ["Build graph", "Message passing", "Aggregate"],
                "key_components": [{"name": "Edge conv", "role": "Aggregates neighbours"}],
                "figure_brief": {
                    "headline": "Method overview",
                    "subtitle": "GNN pipeline for jet tagging",
                    "panels": [
                        {"name": "Input", "content": "Box: particle list"},
                        {"name": "GNN", "content": "Arrows between nodes"},
                    ],
                },
            },
            ReviewSectionType.RESULTS: {
                "headline": "Achieves 95% accuracy on top-quark tagging.",
                "key_numbers": [
                    {"metric": "AUC", "value": "0.987", "meaning": "Near-perfect discrimination"}
                ],
                "takeaway": "Competitive with much heavier models.",
                "figure_brief": {
                    "headline": "Key results",
                    "subtitle": "ROC curves across taggers",
                    "panels": [
                        {"name": "ROC", "content": "Curves above diagonal"},
                    ],
                },
            },
            ReviewSectionType.SIGNIFICANCE: {
                "why_matters": "Enables real-time particle tagging.",
                "applications": ["LHC trigger systems"],
                "who_should_care": "HEP experimentalists and ML researchers",
            },
            ReviewSectionType.APPRAISAL: {
                "strengths": ["Rigorous ablation", "Open code"],
                "limitations": ["Only tested at LHC energies"],
                "open_questions": ["Does it transfer to other colliders?"],
            },
            ReviewSectionType.DISCUSSION: {
                "questions": [
                    {
                        "question": "Can this scale to full events?",
                        "why_interesting": "Full-event tagging is the next challenge.",
                    }
                ]
            },
            ReviewSectionType.TAKEAWAYS: {
                "bullets": ["GNN outperforms CNN baselines", "3x faster inference"],
                "one_sentence": "Graph networks are the future of jet tagging.",
            },
        }

    def _make_mock_invoke(self, service, responses):
        section_order = [st for st, _ in service.SECTION_PIPELINE]
        call_count = [0]

        def mock_invoke(prompt):
            idx = call_count[0]
            call_count[0] += 1
            st = section_order[idx] if idx < len(section_order) else None
            return responses.get(st, {})

        return mock_invoke

    def test_generates_all_nine_sections(self, tmp_config: Config, sample_paper):
        service = PaperReviewService()
        service._extract_full_text = MagicMock(return_value=None)
        responses = self._mock_responses()
        service._invoke_ai = self._make_mock_invoke(service, responses)

        review = service.generate_review(sample_paper)
        assert review is not None
        assert review.source_type == "abstract"
        assert len(review.sections) == 9

    def test_resumes_from_cache_for_hook(self, tmp_config: Config, sample_paper):
        service = PaperReviewService()
        service._extract_full_text = MagicMock(return_value=None)

        service._save_section(
            sample_paper.arxiv_id,
            ReviewSectionType.HOOK,
            {"one_liner": "Cached hook", "why_care": "Important.", "field": "ML"},
            "abstract",
        )

        invoke_calls: list[str] = []

        def tracking_invoke(prompt):
            invoke_calls.append(prompt)
            return {"dummy": "data"}

        service._invoke_ai = tracking_invoke

        review = service.generate_review(sample_paper)
        assert review.sections[ReviewSectionType.HOOK]["one_liner"] == "Cached hook"
        # AI invoked for all sections except the one cached HOOK
        assert len(invoke_calls) == len(ReviewSectionType) - 1

    def test_force_flag_regenerates_cached_section(self, tmp_config: Config, sample_paper):
        service = PaperReviewService()
        service._extract_full_text = MagicMock(return_value=None)

        service._save_section(
            sample_paper.arxiv_id,
            ReviewSectionType.HOOK,
            {"one_liner": "Old cached"},
            "abstract",
        )

        responses = self._mock_responses()
        service._invoke_ai = self._make_mock_invoke(service, responses)

        review = service.generate_review(sample_paper, force=True)
        assert review.sections[ReviewSectionType.HOOK]["one_liner"] == "A new way to classify jets."

    def test_callbacks_invoked_for_all_nine_sections(self, tmp_config: Config, sample_paper):
        service = PaperReviewService()
        service._extract_full_text = MagicMock(return_value=None)
        responses = self._mock_responses()
        service._invoke_ai = self._make_mock_invoke(service, responses)

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
        assert len(start_calls) == 9
        assert len(complete_calls) == 9
        assert all(s for _, s in complete_calls)

    def test_on_section_start_receives_correct_total(self, tmp_config: Config, sample_paper):
        service = PaperReviewService()
        service._extract_full_text = MagicMock(return_value=None)
        responses = self._mock_responses()
        service._invoke_ai = self._make_mock_invoke(service, responses)

        totals: list[int] = []

        def on_start(st, idx, total):
            totals.append(total)

        service.generate_review(sample_paper, on_section_start=on_start)
        assert all(t == 9 for t in totals)

    def test_returns_none_when_all_ai_calls_fail(self, tmp_config: Config, sample_paper):
        service = PaperReviewService()
        service._extract_full_text = MagicMock(return_value=None)
        service._invoke_ai = MagicMock(return_value=None)

        review = service.generate_review(sample_paper)
        assert review is None

    def test_partial_failure_still_returns_review(self, tmp_config: Config, sample_paper):
        service = PaperReviewService()
        service._extract_full_text = MagicMock(return_value=None)
        responses = self._mock_responses()
        call_count = [0]

        def partial_invoke(prompt):
            call_count[0] += 1
            # Fail on every other call
            if call_count[0] % 2 == 0:
                return None
            return list(responses.values())[call_count[0] % len(responses)]

        service._invoke_ai = partial_invoke

        review = service.generate_review(sample_paper)
        assert review is not None
        assert len(review.sections) > 0
