"""Tests for the recommendation engine."""

from datetime import datetime, timedelta

from arxiv_explorer.core.config import Config
from arxiv_explorer.core.models import KeywordInterest, Paper, PreferredCategory
from arxiv_explorer.services.recommendation import RecommendationEngine


class TestCategoryScoring:
    """Category matching contributes to the paper score."""

    def test_matching_category_increases_score(
        self,
        tmp_config: Config,
        sample_papers: list[Paper],
        sample_categories: list[PreferredCategory],
    ):
        engine = RecommendationEngine()
        results = engine.score_papers(sample_papers, None, sample_categories, [])

        # Paper with hep-ph (priority 2) should rank above paper with cs.AI (priority 1)
        scores = {r.paper.arxiv_id: r.score for r in results}
        assert scores["2401.00001"] > scores["2401.00003"]

    def test_no_category_match_gives_zero_category_score(
        self, tmp_config: Config, sample_categories: list[PreferredCategory]
    ):
        engine = RecommendationEngine()
        paper = Paper(
            arxiv_id="9999.00001",
            title="Unrelated",
            abstract="Nothing relevant.",
            authors=["X"],
            categories=["math.AG"],
            published=datetime(2024, 1, 1),
        )
        results = engine.score_papers([paper], None, sample_categories, [])
        # Score should be very small (only recency if applicable, no category)
        assert results[0].score < tmp_config.category_weight


class TestKeywordScoring:
    """Keyword matching contributes to the paper score."""

    def test_keyword_match_increases_score(
        self, tmp_config: Config, sample_papers: list[Paper], sample_keywords: list[KeywordInterest]
    ):
        engine = RecommendationEngine()
        results = engine.score_papers(sample_papers, None, [], sample_keywords)
        scores = {r.paper.arxiv_id: r.score for r in results}

        # "deep learning" matches paper 1, "quantum" matches paper 2
        assert scores["2401.00001"] > 0
        assert scores["2401.00002"] > 0

    def test_keyword_weight_affects_score(self, tmp_config: Config):
        engine = RecommendationEngine()
        paper = Paper(
            arxiv_id="0001",
            title="Deep learning methods",
            abstract="Using deep learning.",
            authors=[],
            categories=[],
            published=datetime(2024, 1, 1),
        )
        low_weight = [KeywordInterest(id=1, keyword="deep learning", weight=0.5)]
        high_weight = [KeywordInterest(id=1, keyword="deep learning", weight=2.0)]

        score_low = engine.score_papers([paper], None, [], low_weight)[0].score
        score_high = engine.score_papers([paper], None, [], high_weight)[0].score
        assert score_high > score_low


class TestRecencyScoring:
    """Recent papers get a bonus."""

    def test_recent_paper_gets_bonus(self, tmp_config: Config):
        engine = RecommendationEngine()
        recent = Paper(
            arxiv_id="new",
            title="X",
            abstract="Y",
            authors=[],
            categories=[],
            published=datetime.now() - timedelta(days=1),
        )
        old = Paper(
            arxiv_id="old",
            title="X",
            abstract="Y",
            authors=[],
            categories=[],
            published=datetime.now() - timedelta(days=60),
        )
        results = engine.score_papers([recent, old], None, [], [])
        scores = {r.paper.arxiv_id: r.score for r in results}
        assert scores["new"] > scores["old"]


class TestSortOrder:
    """Results are sorted by score descending."""

    def test_results_sorted_descending(
        self,
        tmp_config: Config,
        sample_papers: list[Paper],
        sample_categories: list[PreferredCategory],
    ):
        engine = RecommendationEngine()
        results = engine.score_papers(sample_papers, None, sample_categories, [])
        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True)


class TestUserProfile:
    """TF-IDF user profile building."""

    def test_empty_likes_returns_none(self):
        engine = RecommendationEngine()
        assert engine.build_user_profile([]) is None

    def test_profile_from_papers(self, sample_papers: list[Paper]):
        engine = RecommendationEngine()
        profile = engine.build_user_profile(sample_papers)
        assert profile is not None
        assert profile.shape[0] > 0

    def test_content_similarity_affects_score(self, tmp_config: Config):
        engine = RecommendationEngine()

        liked = [
            Paper(
                arxiv_id="liked1",
                title="Neural network optimization",
                abstract="Gradient descent methods for training deep neural networks.",
                authors=[],
                categories=[],
                published=datetime(2024, 1, 1),
            ),
        ]
        profile = engine.build_user_profile(liked)

        similar = Paper(
            arxiv_id="sim",
            title="Neural network training",
            abstract="New optimization techniques for deep neural networks.",
            authors=[],
            categories=[],
            published=datetime(2024, 1, 1),
        )
        different = Paper(
            arxiv_id="diff",
            title="Galaxy formation",
            abstract="Cosmological simulations of galaxy formation in dark matter halos.",
            authors=[],
            categories=[],
            published=datetime(2024, 1, 1),
        )

        results = engine.score_papers([similar, different], profile, [], [])
        scores = {r.paper.arxiv_id: r.score for r in results}
        assert scores["sim"] > scores["diff"]
