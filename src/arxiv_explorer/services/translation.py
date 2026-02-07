"""Translation service using AI providers."""

import json
from datetime import datetime

from ..core.database import get_connection
from ..core.models import Language, PaperTranslation
from .providers import get_provider
from .settings_service import SettingsService

# Language display names for prompts
_LANG_NAMES: dict[Language, str] = {
    Language.KO: "Korean",
}


class TranslationService:
    """Paper translation via AI CLI providers."""

    def translate(
        self,
        arxiv_id: str,
        title: str,
        abstract: str,
        target_language: Language | None = None,
    ) -> PaperTranslation | None:
        """Translate paper title and abstract."""
        # Resolve target language from settings if not given
        if target_language is None:
            target_language = SettingsService().get_language()

        # English → no-op: return original text as-is
        if target_language == Language.EN:
            return PaperTranslation(
                id=0,
                arxiv_id=arxiv_id,
                target_language=Language.EN,
                translated_title=title,
                translated_abstract=abstract,
            )

        # Check cache
        cached = self._get_cached(arxiv_id, target_language)
        if cached:
            return cached

        lang_name = _LANG_NAMES.get(target_language, target_language.value)

        prompt = f"""Translate the following academic paper title and abstract into {lang_name}.

IMPORTANT RULES:
- Keep ALL technical terms, model names, dataset names, proper nouns, and acronyms in English.
  Examples to keep in English: Transformer, CNN, LSTM, GPT, BERT, ResNet, ImageNet, CIFAR-10,
  attention mechanism, self-supervised learning, fine-tuning, pre-training, benchmark, etc.
- Keep mathematical notation and formulas as-is.
- The translation should read naturally in {lang_name} while preserving technical accuracy.
- Respond ONLY with valid JSON, no other text.

Title: {title}

Abstract: {abstract}

Respond in this exact JSON format:
{{
    "translated_title": "translated title here",
    "translated_abstract": "translated abstract here"
}}"""

        try:
            settings = SettingsService()
            provider = get_provider(settings.get_provider())
            if not provider.is_available():
                return None
            output = provider.invoke(
                prompt,
                model=settings.get_model(),
                timeout=settings.get_timeout(),
            )
            if output is None:
                return None

            # Extract JSON block
            if "```json" in output:
                output = output.split("```json")[1].split("```")[0]
            elif "```" in output:
                output = output.split("```")[1].split("```")[0]

            output = output.strip()

            try:
                data = json.loads(output)
            except json.JSONDecodeError as e:
                import sys

                if "--verbose" in sys.argv or "-v" in sys.argv:
                    print(f"\nTranslation failed ({arxiv_id}): JSON parse error")
                    print(f"Error: {e}")
                    print(f"Output sample: {output[:300]}...")
                return None

            translation = PaperTranslation(
                id=0,
                arxiv_id=arxiv_id,
                target_language=target_language,
                translated_title=data.get("translated_title", ""),
                translated_abstract=data.get("translated_abstract", ""),
                generated_at=datetime.now(),
            )

            self._save_cache(translation)
            return translation

        except Exception as e:
            import sys

            if "--verbose" in sys.argv or "-v" in sys.argv:
                print(f"\nTranslation error ({arxiv_id}): {e}")
            return None

    def _get_cached(self, arxiv_id: str, target_language: Language) -> PaperTranslation | None:
        """Retrieve cached translation."""
        with get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM paper_translations WHERE arxiv_id = ? AND target_language = ?",
                (arxiv_id, target_language.value),
            ).fetchone()

            if row:
                return PaperTranslation(
                    id=row["id"],
                    arxiv_id=row["arxiv_id"],
                    target_language=Language(row["target_language"]),
                    translated_title=row["translated_title"],
                    translated_abstract=row["translated_abstract"],
                    generated_at=datetime.fromisoformat(row["generated_at"]),
                )
            return None

    def _save_cache(self, translation: PaperTranslation) -> None:
        """Save translation to cache."""
        with get_connection() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO paper_translations
                   (arxiv_id, target_language, translated_title, translated_abstract)
                   VALUES (?, ?, ?, ?)""",
                (
                    translation.arxiv_id,
                    translation.target_language.value,
                    translation.translated_title,
                    translation.translated_abstract,
                ),
            )
            conn.commit()
