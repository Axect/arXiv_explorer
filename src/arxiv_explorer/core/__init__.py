"""Core module."""

from .config import Config, get_config
from .database import get_connection, init_db
from .models import (
    InteractionType,
    KeywordInterest,
    NoteType,
    Paper,
    PaperInteraction,
    PaperNote,
    PaperSummary,
    PreferredCategory,
    ReadingList,
    ReadingListPaper,
    ReadingStatus,
    RecommendedPaper,
)

__all__ = [
    "Config",
    "get_config",
    "init_db",
    "get_connection",
    "Paper",
    "PreferredCategory",
    "PaperInteraction",
    "PaperSummary",
    "ReadingList",
    "ReadingListPaper",
    "PaperNote",
    "KeywordInterest",
    "RecommendedPaper",
    "InteractionType",
    "ReadingStatus",
    "NoteType",
]
