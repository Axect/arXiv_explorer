"""Summarization service using AI providers."""

import json
from datetime import datetime

from ..core.database import get_connection
from ..core.models import PaperSummary
from .providers import get_provider
from .settings_service import SettingsService


class SummarizationService:
    """Paper summarization using AI CLI providers."""

    def summarize(
        self, arxiv_id: str, title: str, abstract: str, detailed: bool = False
    ) -> PaperSummary | None:
        """Generate a paper summary."""
        # Check cache
        cached = self._get_cached(arxiv_id)
        if cached:
            # If detailed summary requested but not cached, regenerate
            if detailed and not cached.summary_detailed:
                pass  # Regenerate below
            else:
                return cached

        # Generate summary using AI provider
        if detailed:
            prompt = f"""Analyze the following academic paper and respond in JSON format:

Title: {title}

Abstract: {abstract}

IMPORTANT: The response must be valid JSON. Express LaTeX formulas and special characters as plain text.
Escape backslashes (\\) as double backslashes (\\\\).

Output only JSON in the following format (no other text):
{{
    "summary_short": "1-2 sentence core summary of the paper",
    "summary_detailed": "## Context\\nExplain the research background, motivation, and problem being addressed in 2-3 sentences.\\n\\n## Approach\\nDescribe the core methodology, techniques, or theoretical framework proposed in 2-3 sentences.\\n\\n## Results\\nSummarize the main findings, experimental results, or theoretical contributions in 2-3 sentences.\\n\\n## Significance\\nExplain the impact, limitations, and potential future directions in 2-3 sentences.",
    "key_findings": ["Key finding 1", "Key finding 2", "Key finding 3", "Key finding 4", "Key finding 5"]
}}"""
        else:
            prompt = f"""Analyze the following academic paper and respond in JSON format:

Title: {title}

Abstract: {abstract}

IMPORTANT: The response must be valid JSON. Express LaTeX formulas and special characters as plain text.
Escape backslashes (\\) as double backslashes (\\\\).

Output only JSON in the following format (no other text):
{{
    "summary_short": "2-3 sentence summary covering: what problem is addressed, what approach is used, and what results are achieved",
    "key_findings": ["Key finding 1", "Key finding 2", "Key finding 3"]
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
            # Extract JSON block (may be in ```json ... ``` format)
            if "```json" in output:
                output = output.split("```json")[1].split("```")[0]
            elif "```" in output:
                output = output.split("```")[1].split("```")[0]

            output = output.strip()

            try:
                data = json.loads(output)
            except json.JSONDecodeError as e:
                # JSON parse failure - print debug info and return None
                import sys

                if "--verbose" in sys.argv or "-v" in sys.argv:
                    print(f"\nSummary generation failed ({arxiv_id}): JSON parse error")
                    print(f"Error: {e}")
                    print(f"Output sample: {output[:300]}...")
                return None

            summary = PaperSummary(
                id=0,
                arxiv_id=arxiv_id,
                summary_short=data.get("summary_short", ""),
                summary_detailed=data.get("summary_detailed"),
                key_findings=data.get("key_findings", []),
                generated_at=datetime.now(),
            )

            # Save to cache
            self._save_cache(summary)

            return summary

        except Exception as e:
            # Other error - fail silently
            import sys

            if "--verbose" in sys.argv or "-v" in sys.argv:
                print(f"\nError during summary generation ({arxiv_id}): {e}")
            return None

    def _get_cached(self, arxiv_id: str) -> PaperSummary | None:
        """Retrieve a cached summary."""
        with get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM paper_summaries WHERE arxiv_id = ?", (arxiv_id,)
            ).fetchone()

            if row:
                return PaperSummary(
                    id=row["id"],
                    arxiv_id=row["arxiv_id"],
                    summary_short=row["summary_short"],
                    summary_detailed=row["summary_detailed"],
                    key_findings=json.loads(row["key_findings"] or "[]"),
                    generated_at=datetime.fromisoformat(row["generated_at"]),
                )
            return None

    def _save_cache(self, summary: PaperSummary) -> None:
        """Save a summary to cache."""
        with get_connection() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO paper_summaries
                   (arxiv_id, summary_short, summary_detailed, key_findings)
                   VALUES (?, ?, ?, ?)""",
                (
                    summary.arxiv_id,
                    summary.summary_short,
                    summary.summary_detailed,
                    json.dumps(summary.key_findings),
                ),
            )
            conn.commit()
