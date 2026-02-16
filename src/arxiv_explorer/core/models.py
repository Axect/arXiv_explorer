"""Data model definitions."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class InteractionType(str, Enum):
    INTERESTING = "interesting"
    NOT_INTERESTING = "not_interesting"


class ReadingStatus(str, Enum):
    UNREAD = "unread"
    READING = "reading"
    COMPLETED = "completed"


class NoteType(str, Enum):
    GENERAL = "general"
    QUESTION = "question"
    INSIGHT = "insight"
    TODO = "todo"


class AIProviderType(str, Enum):
    GEMINI = "gemini"
    CLAUDE = "claude"
    OPENAI = "openai"
    OLLAMA = "ollama"
    OPENCODE = "opencode"
    CUSTOM = "custom"


class Language(str, Enum):
    EN = "en"
    KO = "ko"


class ReviewSectionType(str, Enum):
    EXECUTIVE_SUMMARY = "executive_summary"
    KEY_CONTRIBUTIONS = "key_contributions"
    SECTION_SUMMARIES = "section_summaries"
    METHODOLOGY = "methodology"
    MATH_FORMULATIONS = "math_formulations"
    FIGURES = "figures"
    TABLES = "tables"
    EXPERIMENTAL_RESULTS = "experimental_results"
    STRENGTHS_WEAKNESSES = "strengths_weaknesses"
    RELATED_WORK = "related_work"
    GLOSSARY = "glossary"
    QUESTIONS = "questions"


@dataclass
class Paper:
    """Paper data model."""

    arxiv_id: str
    title: str
    abstract: str
    authors: list[str]
    categories: list[str]
    published: datetime
    updated: Optional[datetime] = None
    pdf_url: Optional[str] = None

    @property
    def primary_category(self) -> str:
        return self.categories[0] if self.categories else ""


@dataclass
class PreferredCategory:
    """Preferred category."""

    id: int
    category: str
    priority: int = 1
    added_at: datetime = field(default_factory=datetime.now)


@dataclass
class PaperInteraction:
    """Paper interaction record."""

    id: int
    arxiv_id: str
    interaction_type: InteractionType
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class PaperSummary:
    """Paper summary cache."""

    id: int
    arxiv_id: str
    summary_short: str
    summary_detailed: Optional[str] = None
    key_findings: list[str] = field(default_factory=list)
    generated_at: datetime = field(default_factory=datetime.now)


@dataclass
class PaperTranslation:
    """Cached paper translation."""

    id: int
    arxiv_id: str
    target_language: Language
    translated_title: str
    translated_abstract: str
    generated_at: datetime = field(default_factory=datetime.now)


@dataclass
class ReadingList:
    """Reading list."""

    id: int
    name: str
    description: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class ReadingListPaper:
    """Paper in a reading list."""

    id: int
    list_id: int
    arxiv_id: str
    status: ReadingStatus = ReadingStatus.UNREAD
    position: int = 0
    added_at: datetime = field(default_factory=datetime.now)


@dataclass
class PaperNote:
    """Paper note."""

    id: int
    arxiv_id: str
    note_type: NoteType
    content: str
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class KeywordInterest:
    """Keyword interest."""

    id: int
    keyword: str
    weight: float = 1.0
    source: str = "explicit"  # 'explicit' or 'inferred'


@dataclass
class ReviewSection:
    """One section of a paper review, cached individually."""

    id: int
    arxiv_id: str
    section_type: ReviewSectionType
    content_json: str
    generated_at: datetime = field(default_factory=datetime.now)


@dataclass
class PaperReview:
    """Assembled paper review."""

    arxiv_id: str
    title: str
    authors: list[str]
    categories: list[str]
    published: datetime
    abstract: str
    sections: dict[ReviewSectionType, dict] = field(default_factory=dict)
    pdf_url: Optional[str] = None
    source_type: str = "abstract"
    generated_at: datetime = field(default_factory=datetime.now)

    @property
    def is_complete(self) -> bool:
        return set(self.sections.keys()) == set(ReviewSectionType)

    @property
    def missing_sections(self) -> list[ReviewSectionType]:
        return [s for s in ReviewSectionType if s not in self.sections]


@dataclass
class RecommendedPaper:
    """Recommended paper with score."""

    paper: Paper
    score: float
    summary: Optional[PaperSummary] = None
