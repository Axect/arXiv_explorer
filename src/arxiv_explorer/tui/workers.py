"""Service facade — holds all service instances."""

from ..services.paper_service import PaperService
from ..services.preference_service import PreferenceService
from ..services.reading_list_service import ReadingListService
from ..services.notes_service import NotesService
from ..services.summarization import SummarizationService
from ..services.translation import TranslationService
from ..services.settings_service import SettingsService


class ServiceBridge:
    """Service facade used by the TUI.

    Creates service instances once and shares them.
    All methods are synchronous, so call within @work(thread=True).
    """

    def __init__(self) -> None:
        self.papers = PaperService()
        self.preferences = PreferenceService()
        self.reading_lists = ReadingListService()
        self.notes = NotesService()
        self.summarization = SummarizationService()
        self.translation = TranslationService()
        self.settings = SettingsService()
