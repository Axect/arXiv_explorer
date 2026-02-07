"""Recommendation engine."""
from datetime import datetime
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from ..core.models import Paper, RecommendedPaper, PreferredCategory, KeywordInterest
from ..core.config import get_config


class RecommendationEngine:
    """TF-IDF based recommendation engine."""

    def __init__(self):
        self.vectorizer = TfidfVectorizer(
            max_features=5000,
            stop_words="english",
            ngram_range=(1, 2),
            min_df=1,
        )
        self._is_fitted = False
        self._paper_vectors = None
        self._paper_ids: list[str] = []

    def build_user_profile(
        self,
        liked_papers: list[Paper],
    ) -> np.ndarray | None:
        """Build a user profile from liked papers."""
        if not liked_papers:
            return None

        # Combine paper text
        documents = [
            f"{p.title} {p.abstract}"
            for p in liked_papers
        ]

        # Compute TF-IDF vectors
        if not self._is_fitted:
            vectors = self.vectorizer.fit_transform(documents)
            self._is_fitted = True
        else:
            vectors = self.vectorizer.transform(documents)

        # Create profile as mean vector
        profile = np.asarray(vectors.mean(axis=0)).flatten()
        return profile

    def score_papers(
        self,
        papers: list[Paper],
        user_profile: np.ndarray | None,
        preferred_categories: list[PreferredCategory],
        keywords: list[KeywordInterest],
    ) -> list[RecommendedPaper]:
        """Assign recommendation scores to papers."""
        config = get_config()

        # Category/keyword lookup
        category_priorities = {c.category: c.priority for c in preferred_categories}
        max_priority = max((c.priority for c in preferred_categories), default=1)
        keyword_weights = {k.keyword: k.weight for k in keywords}

        results = []

        for paper in papers:
            score = 0.0

            # 1. Content similarity (TF-IDF)
            if user_profile is not None and self._is_fitted:
                doc = f"{paper.title} {paper.abstract}"
                paper_vector = self.vectorizer.transform([doc])
                content_sim = cosine_similarity(
                    user_profile.reshape(1, -1),
                    paper_vector
                )[0, 0]
                score += content_sim * config.content_weight

            # 2. Category matching
            for cat in paper.categories:
                if cat in category_priorities:
                    priority = category_priorities[cat]
                    normalized = priority / max_priority if max_priority > 0 else 1
                    score += config.category_weight * normalized
                    break  # Use only the first match

            # 3. Keyword matching
            text = f"{paper.title} {paper.abstract}".lower()
            for keyword, weight in keyword_weights.items():
                if keyword in text:
                    score += config.keyword_weight * weight

            # 4. Recency bonus
            days_old = (datetime.now() - paper.published).days
            if days_old < 30:
                recency_factor = 1 - (days_old / 30)
                score += config.recency_weight * recency_factor

            results.append(RecommendedPaper(paper=paper, score=score))

        # Sort by score
        results.sort(key=lambda x: x.score, reverse=True)
        return results


# Singleton instance
_engine: RecommendationEngine | None = None


def get_recommendation_engine() -> RecommendationEngine:
    """Get the recommendation engine instance."""
    global _engine
    if _engine is None:
        _engine = RecommendationEngine()
    return _engine
