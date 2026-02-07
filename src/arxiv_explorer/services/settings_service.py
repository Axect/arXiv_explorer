"""App settings service."""

from ..core.database import get_connection
from ..core.models import AIProviderType, Language

DEFAULTS: dict[str, str] = {
    "ai_provider": AIProviderType.GEMINI.value,
    "ai_model": "",
    "ai_timeout": "120",
    "custom_command": "",
    "language": Language.EN.value,
}


class SettingsService:
    """CRUD for the app_settings table."""

    def get(self, key: str) -> str:
        """Get a setting value (returns default if not found)."""
        with get_connection() as conn:
            row = conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
            if row:
                return row["value"]
        return DEFAULTS.get(key, "")

    def set(self, key: str, value: str) -> None:
        """Save a setting value."""
        with get_connection() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO app_settings (key, value, updated_at)
                   VALUES (?, ?, CURRENT_TIMESTAMP)""",
                (key, value),
            )
            conn.commit()

    def get_all(self) -> dict[str, str]:
        """Get all settings (merged with defaults)."""
        settings = dict(DEFAULTS)
        with get_connection() as conn:
            rows = conn.execute("SELECT key, value FROM app_settings").fetchall()
            for row in rows:
                settings[row["key"]] = row["value"]
        return settings

    def get_provider(self) -> AIProviderType:
        """Get the current AI provider."""
        return AIProviderType(self.get("ai_provider"))

    def get_model(self) -> str:
        """Get the current AI model override."""
        return self.get("ai_model")

    def get_timeout(self) -> int:
        """Get the current timeout (seconds)."""
        try:
            return int(self.get("ai_timeout"))
        except ValueError:
            return int(DEFAULTS["ai_timeout"])

    def get_language(self) -> Language:
        """Current language setting."""
        try:
            return Language(self.get("language"))
        except ValueError:
            return Language.EN
