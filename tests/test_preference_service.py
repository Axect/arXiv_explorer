"""Tests for the preference service."""

from arxiv_explorer.core.config import Config
from arxiv_explorer.core.models import InteractionType
from arxiv_explorer.services.preference_service import PreferenceService


class TestCategoryManagement:
    """CRUD for preferred categories."""

    def test_add_category(self, tmp_config: Config):
        service = PreferenceService()
        cat = service.add_category("hep-ph", priority=2)

        assert cat.category == "hep-ph"
        assert cat.priority == 2

    def test_add_category_update_priority(self, tmp_config: Config):
        """Adding the same category again updates its priority."""
        service = PreferenceService()
        service.add_category("cs.AI", priority=1)
        updated = service.add_category("cs.AI", priority=3)

        assert updated.priority == 3

    def test_get_categories_ordered_by_priority(self, tmp_config: Config):
        service = PreferenceService()
        service.add_category("cs.AI", priority=1)
        service.add_category("hep-ph", priority=3)
        service.add_category("quant-ph", priority=2)

        cats = service.get_categories()
        priorities = [c.priority for c in cats]
        assert priorities == sorted(priorities, reverse=True)

    def test_remove_category(self, tmp_config: Config):
        service = PreferenceService()
        service.add_category("cs.AI")

        assert service.remove_category("cs.AI") is True
        assert service.get_categories() == []

    def test_remove_nonexistent_category(self, tmp_config: Config):
        service = PreferenceService()
        assert service.remove_category("nonexistent") is False


class TestPaperInteractions:
    """Like/dislike paper interactions."""

    def test_mark_interesting(self, tmp_config: Config):
        service = PreferenceService()
        service.mark_interesting("2401.00001")

        assert service.get_interaction("2401.00001") == InteractionType.INTERESTING
        assert "2401.00001" in service.get_interesting_papers()

    def test_mark_not_interesting(self, tmp_config: Config):
        service = PreferenceService()
        service.mark_not_interesting("2401.00001")

        assert service.get_interaction("2401.00001") == InteractionType.NOT_INTERESTING
        assert "2401.00001" not in service.get_interesting_papers()

    def test_like_replaces_dislike(self, tmp_config: Config):
        """Liking a paper removes any previous dislike."""
        service = PreferenceService()
        service.mark_not_interesting("2401.00001")
        service.mark_interesting("2401.00001")

        assert service.get_interaction("2401.00001") == InteractionType.INTERESTING

    def test_dislike_replaces_like(self, tmp_config: Config):
        """Disliking a paper removes any previous like."""
        service = PreferenceService()
        service.mark_interesting("2401.00001")
        service.mark_not_interesting("2401.00001")

        assert service.get_interaction("2401.00001") == InteractionType.NOT_INTERESTING
        assert "2401.00001" not in service.get_interesting_papers()

    def test_no_interaction_returns_none(self, tmp_config: Config):
        service = PreferenceService()
        assert service.get_interaction("9999.99999") is None


class TestKeywordManagement:
    """CRUD for keyword interests."""

    def test_add_keyword(self, tmp_config: Config):
        service = PreferenceService()
        service.add_keyword("machine learning", weight=1.5)

        keywords = service.get_keywords()
        assert len(keywords) == 1
        assert keywords[0].keyword == "machine learning"
        assert keywords[0].weight == 1.5

    def test_keyword_lowercased(self, tmp_config: Config):
        """Keywords are stored in lowercase."""
        service = PreferenceService()
        service.add_keyword("Deep Learning")

        keywords = service.get_keywords()
        assert keywords[0].keyword == "deep learning"

    def test_add_keyword_update_weight(self, tmp_config: Config):
        """Adding the same keyword again updates its weight."""
        service = PreferenceService()
        service.add_keyword("quantum", weight=1.0)
        service.add_keyword("quantum", weight=2.5)

        keywords = service.get_keywords()
        assert len(keywords) == 1
        assert keywords[0].weight == 2.5

    def test_get_keywords_ordered_by_weight(self, tmp_config: Config):
        service = PreferenceService()
        service.add_keyword("low", weight=0.5)
        service.add_keyword("high", weight=2.0)
        service.add_keyword("mid", weight=1.0)

        keywords = service.get_keywords()
        weights = [k.weight for k in keywords]
        assert weights == sorted(weights, reverse=True)

    def test_remove_keyword(self, tmp_config: Config):
        service = PreferenceService()
        service.add_keyword("test")

        assert service.remove_keyword("test") is True
        assert service.get_keywords() == []

    def test_remove_nonexistent_keyword(self, tmp_config: Config):
        service = PreferenceService()
        assert service.remove_keyword("nonexistent") is False
