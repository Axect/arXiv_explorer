"""Core module."""
from .config import Config, get_config
from .database import init_db, get_connection
from .models import (
    Paper, PreferredCategory, PaperInteraction, PaperSummary,
    ReadingList, ReadingListPaper, PaperNote, KeywordInterest,
    RecommendedPaper, InteractionType, ReadingStatus, NoteType
)

__all__ = [
    "Config", "get_config",
    "init_db", "get_connection",
    "Paper", "PreferredCategory", "PaperInteraction", "PaperSummary",
    "ReadingList", "ReadingListPaper", "PaperNote", "KeywordInterest",
    "RecommendedPaper", "InteractionType", "ReadingStatus", "NoteType",
]
