"""Paper service."""

from ..core.models import Paper, RecommendedPaper
from .arxiv_client import ArxivClient
from .preference_service import PreferenceService
from .recommendation import get_recommendation_engine


class PaperService:
    """Paper-related service."""

    def __init__(self):
        self.arxiv_client = ArxivClient()
        self.preference_service = PreferenceService()

    def get_daily_papers(
        self,
        days: int = 1,
        limit: int = 50,
    ) -> list[RecommendedPaper]:
        """Get daily papers with personalized scores."""
        # Get preferred categories
        categories = self.preference_service.get_categories()
        if not categories:
            return []

        category_names = [c.category for c in categories]

        # Fetch papers
        papers = self.arxiv_client.fetch_by_category(
            categories=category_names,
            days=days,
            max_results=200,
        )

        # Calculate recommendation scores
        engine = get_recommendation_engine()

        # Build user profile from liked papers (cache-first batch lookup)
        liked_ids = self.preference_service.get_interesting_papers()
        liked_ids = liked_ids[:50]  # Most recent 50 only

        # Batch lookup from cache
        cached = self.arxiv_client.get_papers_cached_batch(liked_ids)
        liked_papers = list(cached.values())

        # Only fetch from API for papers not in cache
        missing_ids = [aid for aid in liked_ids if aid not in cached]
        for arxiv_id in missing_ids:
            paper = self.arxiv_client.get_paper(arxiv_id)
            if paper:
                liked_papers.append(paper)

        user_profile = engine.build_user_profile(liked_papers)
        keywords = self.preference_service.get_keywords()

        # Score and sort
        recommended = engine.score_papers(
            papers=papers,
            user_profile=user_profile,
            preferred_categories=categories,
            keywords=keywords,
        )

        return recommended[:limit]

    def search_papers(
        self,
        query: str,
        limit: int = 20,
        from_arxiv: bool = False,
    ) -> list[RecommendedPaper]:
        """Search papers."""
        if from_arxiv:
            papers = self.arxiv_client.search(query, max_results=limit)
        else:
            # TODO: Implement local DB search
            papers = self.arxiv_client.search(query, max_results=limit)

        # Calculate recommendation scores
        engine = get_recommendation_engine()
        categories = self.preference_service.get_categories()
        keywords = self.preference_service.get_keywords()

        # Simple scoring (without user profile)
        recommended = engine.score_papers(
            papers=papers,
            user_profile=None,
            preferred_categories=categories,
            keywords=keywords,
        )

        return recommended[:limit]

    def get_paper(self, arxiv_id: str) -> Paper | None:
        """Get a specific paper."""
        return self.arxiv_client.get_paper(arxiv_id)
