"""Tests for core data models."""

from datetime import datetime

from arxiv_explorer.core.models import (
    InteractionType,
    KeywordInterest,
    Language,
    NoteType,
    Paper,
    PaperSummary,
    ReadingListPaper,
    ReadingStatus,
    RecommendedPaper,
)


class TestEnums:
    """Verify enum values match the strings stored in SQLite."""

    def test_interaction_type_values(self):
        assert InteractionType.INTERESTING.value == "interesting"
        assert InteractionType.NOT_INTERESTING.value == "not_interesting"

    def test_reading_status_values(self):
        assert ReadingStatus.UNREAD.value == "unread"
        assert ReadingStatus.READING.value == "reading"
        assert ReadingStatus.COMPLETED.value == "completed"

    def test_note_type_values(self):
        assert NoteType.GENERAL.value == "general"
        assert NoteType.QUESTION.value == "question"
        assert NoteType.INSIGHT.value == "insight"
        assert NoteType.TODO.value == "todo"

    def test_language_values(self):
        assert Language.EN.value == "en"
        assert Language.KO.value == "ko"

    def test_enum_from_string(self):
        """Enums can be constructed from stored string values."""
        assert InteractionType("interesting") is InteractionType.INTERESTING
        assert ReadingStatus("completed") is ReadingStatus.COMPLETED


class TestPaper:
    """Tests for the Paper dataclass."""

    def test_primary_category(self, sample_paper: Paper):
        assert sample_paper.primary_category == "hep-ph"

    def test_primary_category_empty(self):
        paper = Paper(
            arxiv_id="0000.00000",
            title="t",
            abstract="a",
            authors=[],
            categories=[],
            published=datetime(2024, 1, 1),
        )
        assert paper.primary_category == ""

    def test_optional_fields_default_none(self):
        paper = Paper(
            arxiv_id="0000.00000",
            title="t",
            abstract="a",
            authors=[],
            categories=[],
            published=datetime(2024, 1, 1),
        )
        assert paper.updated is None
        assert paper.pdf_url is None


class TestDataclassDefaults:
    """Verify that dataclass default factories work correctly."""

    def test_paper_summary_defaults(self):
        summary = PaperSummary(id=1, arxiv_id="0000.00000", summary_short="Short")
        assert summary.key_findings == []
        assert summary.summary_detailed is None

    def test_reading_list_paper_defaults(self):
        rlp = ReadingListPaper(id=1, list_id=1, arxiv_id="0000.00000")
        assert rlp.status == ReadingStatus.UNREAD
        assert rlp.position == 0

    def test_keyword_interest_defaults(self):
        ki = KeywordInterest(id=1, keyword="test")
        assert ki.weight == 1.0
        assert ki.source == "explicit"

    def test_recommended_paper_defaults(self, sample_paper: Paper):
        rp = RecommendedPaper(paper=sample_paper, score=0.75)
        assert rp.summary is None
