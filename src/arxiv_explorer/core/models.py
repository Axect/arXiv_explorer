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
class RecommendedPaper:
    """Recommended paper with score."""

    paper: Paper
    score: float
    summary: Optional[PaperSummary] = None
