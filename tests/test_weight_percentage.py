from unittest.mock import patch

import pytest

from arxiv_explorer.core.config import Config
from arxiv_explorer.core.database import init_db
from arxiv_explorer.services.settings_service import SettingsService, adjust_weights


@pytest.fixture
def db(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    return db_path


@pytest.fixture
def svc(db, tmp_path):
    config = Config(db_path=db, arxivterminal_db_path=tmp_path / "at.db")
    with patch("arxiv_explorer.core.database.get_config", return_value=config):
        yield SettingsService()


class TestWeightDefaults:
    def test_default_weights(self, svc):
        weights = svc.get_weights()
        assert weights == {"content": 60, "category": 20, "keyword": 15, "recency": 5}

    def test_weights_sum_to_100(self, svc):
        weights = svc.get_weights()
        assert sum(weights.values()) == 100


class TestAdjustWeights:
    def test_increase_one_decreases_others(self):
        weights = {"content": 60, "category": 20, "keyword": 15, "recency": 5}
        result = adjust_weights("content", 80, weights)
        assert result["content"] == 80
        assert sum(result.values()) == 100

    def test_set_to_zero(self):
        weights = {"content": 60, "category": 20, "keyword": 15, "recency": 5}
        result = adjust_weights("content", 0, weights)
        assert result["content"] == 0
        assert sum(result.values()) == 100

    def test_set_to_100(self):
        weights = {"content": 60, "category": 20, "keyword": 15, "recency": 5}
        result = adjust_weights("content", 100, weights)
        assert result["content"] == 100
        assert result["category"] == 0
        assert result["keyword"] == 0
        assert result["recency"] == 0

    def test_all_others_zero_distributes_equally(self):
        weights = {"content": 100, "category": 0, "keyword": 0, "recency": 0}
        result = adjust_weights("content", 70, weights)
        assert result["content"] == 70
        assert sum(result.values()) == 100
        assert result["category"] == 10
        assert result["keyword"] == 10
        assert result["recency"] == 10


class TestWeightPersistence:
    def test_save_and_load(self, svc):
        svc.set_weights({"content": 50, "category": 25, "keyword": 20, "recency": 5})
        weights = svc.get_weights()
        assert weights == {"content": 50, "category": 25, "keyword": 20, "recency": 5}

    def test_reset_to_defaults(self, svc):
        svc.set_weights({"content": 50, "category": 25, "keyword": 20, "recency": 5})
        svc.reset_weights()
        weights = svc.get_weights()
        assert weights == {"content": 60, "category": 20, "keyword": 15, "recency": 5}
