"""App settings service."""

from ..core.database import get_connection
from ..core.models import AIProviderType, Language

DEFAULTS: dict[str, str] = {
    "ai_provider": AIProviderType.GEMINI.value,
    "ai_model": "",
    "ai_timeout": "120",
    "custom_command": "",
    "language": Language.EN.value,
    "weight_content": "60",
    "weight_category": "20",
    "weight_keyword": "15",
    "weight_recency": "5",
}

WEIGHT_KEYS = ["content", "category", "keyword", "recency"]
DEFAULT_WEIGHTS = {"content": 60, "category": 20, "keyword": 15, "recency": 5}


def adjust_weights(changed_key: str, new_value: int, weights: dict[str, int]) -> dict[str, int]:
    """Adjust all weights proportionally so they always sum to 100."""
    result = dict(weights)
    result[changed_key] = new_value
    remaining = 100 - new_value
    others = {k: v for k, v in result.items() if k != changed_key}
    others_sum = sum(others.values())
    if others_sum == 0:
        equal = remaining // len(others)
        for k in others:
            result[k] = equal
    else:
        for k in others:
            result[k] = round(remaining * others[k] / others_sum)
    diff = 100 - sum(result.values())
    if diff != 0:
        largest = max(others, key=lambda k: result[k])
        result[largest] += diff
    return result


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

    def get_provider(self) -> str:
        """Return the active provider name as a string."""
        return self.get("ai_provider")

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

    def get_weights(self) -> dict[str, int]:
        """Get current recommendation weights."""
        return {key: int(self.get(f"weight_{key}")) for key in WEIGHT_KEYS}

    def set_weights(self, weights: dict[str, int]) -> None:
        """Save recommendation weights."""
        for key in WEIGHT_KEYS:
            self.set(f"weight_{key}", str(weights[key]))

    def reset_weights(self) -> None:
        """Reset recommendation weights to defaults."""
        self.set_weights(DEFAULT_WEIGHTS)

    # Reserved names that cannot be used for custom providers
    RESERVED_PROVIDERS = {"gemini", "claude", "openai", "ollama", "opencode", "custom"}

    def get_custom_providers(self) -> list:
        """Return all custom providers as list of CustomProviderConfig."""
        from ..core.models import CustomProviderConfig

        with get_connection() as conn:
            rows = conn.execute(
                "SELECT name, preset, command_template, default_model FROM custom_providers ORDER BY name"
            ).fetchall()
            return [
                CustomProviderConfig(
                    name=r["name"],
                    preset=r["preset"],
                    command_template=r["command_template"],
                    default_model=r["default_model"] or "",
                )
                for r in rows
            ]

    def add_custom_provider(
        self, name: str, preset: str, command_template: str, default_model: str = ""
    ) -> None:
        """Register a custom provider. Raises ValueError if name is reserved or duplicate."""
        if name.lower() in self.RESERVED_PROVIDERS:
            raise ValueError(f"'{name}' is a reserved provider name")
        with get_connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO custom_providers (name, preset, command_template, default_model) "
                "VALUES (?, ?, ?, ?)",
                (name, preset, command_template, default_model),
            )
            conn.commit()

    def remove_custom_provider(self, name: str) -> None:
        """Remove a custom provider. If it's the active provider, switch to gemini."""
        with get_connection() as conn:
            conn.execute("DELETE FROM custom_providers WHERE name = ?", (name,))
            conn.commit()
        # If active provider was deleted, reset to gemini
        if self.get("ai_provider") == name:
            self.set("ai_provider", "gemini")
