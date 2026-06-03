"""Paper review service using map-reduce AI analysis."""

import json
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from ..core.database import get_connection
from ..core.models import (
    Language,
    Paper,
    PaperReview,
    ReviewSection,
    ReviewSectionType,
)
from .providers import get_provider
from .settings_service import SettingsService

# Language display names for translation prompts
_LANG_NAMES: dict[Language, str] = {
    Language.KO: "Korean",
}


class PaperReviewService:
    """Generate journal-club AI paper presentations with incremental caching."""

    # Ordered processing pipeline: (section_type, requires_full_text?)
    SECTION_PIPELINE: list[tuple[ReviewSectionType, bool]] = [
        (ReviewSectionType.HOOK, False),
        (ReviewSectionType.PROBLEM, False),
        (ReviewSectionType.KEY_IDEA, False),
        (ReviewSectionType.METHOD, True),
        (ReviewSectionType.RESULTS, True),
        (ReviewSectionType.SIGNIFICANCE, False),
        (ReviewSectionType.APPRAISAL, False),
        (ReviewSectionType.DISCUSSION, False),
        (ReviewSectionType.TAKEAWAYS, False),
    ]

    # Shared presenter persona prefix for all prompts
    _PRESENTER_PERSONA = (
        "You are an enthusiastic, clear research presenter leading a journal club for graduate "
        "students and fellow researchers. Your goal is to help the group UNDERSTAND and DISCUSS "
        "this paper, not to gatekeep, score, or accept/reject it. Explain intuitively, use "
        "analogies when helpful, stay accurate and grounded in the paper's actual content, and "
        "be honest about limitations without an adversarial tone. "
        "Your analysis must be evidence-grounded: cite specific sections, equations, or figures "
        "from the paper to support every claim. Avoid vague assertions -- be precise.\n\n"
        "MATH FORMATTING: Write every mathematical expression, variable, symbol, unit with a "
        "power/subscript, or numeric range as LaTeX. Use inline math $...$ for in-sentence "
        "notation and display math $$...$$ for standalone equations. For example write "
        r"$10^{17}$--$10^{23}\,\mathrm{g}$, $M_\odot$, $\rho \propto r^{-2}$ -- never plain-text "
        "forms like 10^17-10^23 g or M_sun. This applies to all string fields in your JSON "
        "(including inside lists), but NOT to any figure panel descriptions (those stay plain "
        "English, no formulas).\n\n"
    )

    def generate_review(
        self,
        paper: Paper,
        force: bool = False,
        on_section_start: Optional[Callable[[ReviewSectionType, int, int], None]] = None,
        on_section_complete: Optional[Callable[[ReviewSectionType, bool], None]] = None,
    ) -> PaperReview | None:
        """Generate a full review. Resumes from cache if interrupted."""
        # Step 1: Attempt full text extraction
        full_text_md = self._extract_full_text(paper.arxiv_id)
        source_type = "full_text" if full_text_md else "abstract"

        # Step 2: Pre-parse full text if available
        paper_sections = None
        if full_text_md:
            paper_sections = self._split_into_sections(full_text_md)

        # Step 3: Load existing cached sections
        cached = self._get_all_cached_sections(paper.arxiv_id)

        # Step 4: Process each section
        total = len(self.SECTION_PIPELINE)
        sections_data: dict[ReviewSectionType, dict] = {}

        for idx, (section_type, _needs_full_text) in enumerate(self.SECTION_PIPELINE):
            if on_section_start:
                on_section_start(section_type, idx, total)

            # Use cached if available and not forcing
            if not force and section_type in cached:
                sections_data[section_type] = json.loads(cached[section_type].content_json)
                if on_section_complete:
                    on_section_complete(section_type, True)
                continue

            # Build prompt and invoke AI
            prompt = self._build_prompt(
                section_type=section_type,
                paper=paper,
                full_text_md=full_text_md,
                paper_sections=paper_sections,
            )

            data = self._invoke_ai(prompt)
            if data:
                sections_data[section_type] = data
                self._save_section(paper.arxiv_id, section_type, data, source_type)
                if on_section_complete:
                    on_section_complete(section_type, True)
            else:
                if on_section_complete:
                    on_section_complete(section_type, False)

        if not sections_data:
            return None

        return PaperReview(
            arxiv_id=paper.arxiv_id,
            title=paper.title,
            authors=paper.authors,
            categories=paper.categories,
            published=paper.published,
            pdf_url=paper.pdf_url,
            abstract=paper.abstract,
            sections=sections_data,
            source_type=source_type,
        )

    def get_cached_review(self, arxiv_id: str) -> PaperReview | None:
        """Retrieve a partially or fully cached review."""
        cached = self._get_all_cached_sections(arxiv_id)
        if not cached:
            return None

        # We need paper metadata but don't have a Paper object here;
        # return a minimal PaperReview with just sections populated.
        first = next(iter(cached.values()))
        return PaperReview(
            arxiv_id=arxiv_id,
            title="",
            authors=[],
            categories=[],
            published=datetime.now(),
            abstract="",
            sections={st: json.loads(sec.content_json) for st, sec in cached.items()},
            source_type="cached",
            generated_at=first.generated_at,
        )

    def delete_review(self, arxiv_id: str) -> bool:
        """Delete all cached review sections for a paper."""
        with get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM paper_review_sections WHERE arxiv_id = ?",
                (arxiv_id,),
            )
            conn.commit()
            return cursor.rowcount > 0

    def render_markdown(
        self,
        review: PaperReview,
        language: Language = Language.EN,
    ) -> str:
        """Render a PaperReview into journal-club Markdown."""
        parts: list[str] = []

        # Header and metadata
        parts.append(f"# {review.title}\n")
        author_str = ", ".join(review.authors[:10])
        if len(review.authors) > 10:
            author_str += f" (+{len(review.authors) - 10} more)"

        source_label = "Full text" if review.source_type == "full_text" else "Abstract only"

        parts.append("| | |")
        parts.append("|:--|:--|")
        parts.append(f"| **Authors** | {author_str} |")
        parts.append(
            f"| **arXiv** | [{review.arxiv_id}](https://arxiv.org/abs/{review.arxiv_id}) |"
        )
        parts.append(f"| **Categories** | {', '.join(review.categories)} |")
        parts.append(f"| **Published** | {review.published.strftime('%Y-%m-%d')} |")
        if review.pdf_url:
            parts.append(f"| **PDF** | [{review.pdf_url}]({review.pdf_url}) |")
        parts.append(f"| **Analysis source** | {source_label} |")
        parts.append("")

        parts.append("---\n")

        # TL;DR (HOOK)
        hook = review.sections.get(ReviewSectionType.HOOK, {})
        if hook:
            parts.append("## TL;DR\n")
            if hook.get("one_liner"):
                parts.append(f"> {hook['one_liner']}\n")
            if hook.get("why_care"):
                parts.append(f"{hook['why_care']}\n")
            if hook.get("field"):
                parts.append(f"**Field:** {hook['field']}\n")

        # The Problem (PROBLEM)
        problem = review.sections.get(ReviewSectionType.PROBLEM, {})
        if problem:
            parts.append("## The Problem\n")
            if problem.get("problem"):
                parts.append(f"{problem['problem']}\n")
            if problem.get("motivation"):
                parts.append(f"**Motivation:** {problem['motivation']}\n")
            if problem.get("prior_gap"):
                parts.append(f"**What was missing:** {problem['prior_gap']}\n")

        # Key Idea (KEY_IDEA)
        key_idea = review.sections.get(ReviewSectionType.KEY_IDEA, {})
        if key_idea:
            parts.append("## Key Idea\n")
            if key_idea.get("idea"):
                parts.append(f"{key_idea['idea']}\n")
            if key_idea.get("intuition"):
                parts.append(f"**Intuition:** {key_idea['intuition']}\n")
            analogy = key_idea.get("analogy", "")
            if analogy:
                parts.append(f"**Analogy:** {analogy}\n")

        # How It Works (METHOD)
        method = review.sections.get(ReviewSectionType.METHOD, {})
        if method:
            parts.append("## How It Works\n")
            if method.get("overview"):
                parts.append(f"{method['overview']}\n")
            steps = method.get("steps", [])
            if steps:
                for i, step in enumerate(steps, 1):
                    parts.append(f"{i}. {step}")
                parts.append("")
            components = method.get("key_components", [])
            if components:
                parts.append("**Key components:**\n")
                for comp in components:
                    name = comp.get("name", "")
                    role = comp.get("role", "")
                    if name:
                        parts.append(f"- **{name}** - {role}")
                parts.append("")
            # Embed generated method figure if available
            method_fig = review.figure_paths.get("method")
            if method_fig:
                parts.append(f"![Method overview]({method_fig})\n")

        # Key Results (RESULTS)
        results = review.sections.get(ReviewSectionType.RESULTS, {})
        if results:
            parts.append("## Key Results\n")
            if results.get("headline"):
                parts.append(f"{results['headline']}\n")
            key_numbers = results.get("key_numbers", [])
            if key_numbers:
                parts.append("| Metric | Value | What it means |")
                parts.append("|:-------|:------|:--------------|")
                for kn in key_numbers:
                    metric = kn.get("metric", "").replace("|", "\\|")
                    value = kn.get("value", "").replace("|", "\\|")
                    meaning = kn.get("meaning", "").replace("|", "\\|")
                    parts.append(f"| {metric} | {value} | {meaning} |")
                parts.append("")
            if results.get("takeaway"):
                parts.append(f"**Takeaway:** {results['takeaway']}\n")
            # Embed generated results figure if available
            results_fig = review.figure_paths.get("results")
            if results_fig:
                parts.append(f"![Key results]({results_fig})\n")

        # Why It Matters (SIGNIFICANCE)
        significance = review.sections.get(ReviewSectionType.SIGNIFICANCE, {})
        if significance:
            parts.append("## Why It Matters\n")
            if significance.get("why_matters"):
                parts.append(f"{significance['why_matters']}\n")
            applications = significance.get("applications", [])
            if applications:
                parts.append("**Applications:**\n")
                for app in applications:
                    parts.append(f"- {app}")
                parts.append("")
            if significance.get("who_should_care"):
                parts.append(f"**Who should care:** {significance['who_should_care']}\n")

        # Strengths, Limitations & Open Questions (APPRAISAL)
        appraisal = review.sections.get(ReviewSectionType.APPRAISAL, {})
        if appraisal:
            parts.append("## Strengths, Limitations & Open Questions\n")
            strengths = appraisal.get("strengths", [])
            if strengths:
                parts.append("**Strengths:**\n")
                for s in strengths:
                    parts.append(f"- {s}")
                parts.append("")
            limitations = appraisal.get("limitations", [])
            if limitations:
                parts.append("**Limitations:**\n")
                for lim in limitations:
                    parts.append(f"- {lim}")
                parts.append("")
            open_questions = appraisal.get("open_questions", [])
            if open_questions:
                parts.append("**Open questions:**\n")
                for oq in open_questions:
                    parts.append(f"- {oq}")
                parts.append("")

        # Discussion Questions (DISCUSSION)
        discussion = review.sections.get(ReviewSectionType.DISCUSSION, {})
        if discussion and discussion.get("questions"):
            parts.append("## Discussion Questions\n")
            for i, q in enumerate(discussion["questions"], 1):
                question = q.get("question", "")
                why = q.get("why_interesting", "")
                parts.append(f"{i}. {question}")
                if why:
                    parts.append(f"   *{why}*")
                parts.append("")

        # Takeaways (TAKEAWAYS)
        takeaways = review.sections.get(ReviewSectionType.TAKEAWAYS, {})
        if takeaways:
            parts.append("## Takeaways\n")
            bullets = takeaways.get("bullets", [])
            if bullets:
                for b in bullets:
                    parts.append(f"- {b}")
                parts.append("")
            if takeaways.get("one_sentence"):
                parts.append(f"**{takeaways['one_sentence']}**\n")

        # Footer
        parts.append("---")
        parts.append(
            f"*Generated by arXiv Explorer | "
            f"{review.generated_at.strftime('%Y-%m-%d %H:%M')} | "
            f"{len(review.sections)}/{len(ReviewSectionType)} sections*"
        )

        markdown = "\n".join(parts)

        # Translation
        if language != Language.EN:
            translated = self._translate_markdown(markdown, language)
            if translated:
                return translated

        return markdown

    # ── Full Text Extraction ──────────────────────────────────────────

    def _extract_full_text(self, arxiv_id: str) -> str | None:
        """Get full text: check existing file, then try conversion."""
        existing = self._find_existing_markdown(arxiv_id)
        if existing:
            return existing.read_text(encoding="utf-8")

        output_path = self._run_arxiv_doc_builder(arxiv_id)
        if output_path and output_path.exists():
            return output_path.read_text(encoding="utf-8")

        return None

    def _find_existing_markdown(self, arxiv_id: str) -> Path | None:
        """Check standard locations for existing conversion output."""
        normalized = arxiv_id.replace("/", "_")
        candidates = [
            Path.cwd() / "papers" / normalized / f"{normalized}.md",
            Path.cwd() / normalized / f"{normalized}.md",
        ]
        for p in candidates:
            if p.exists():
                return p
        return None

    def _run_arxiv_doc_builder(self, arxiv_id: str) -> Path | None:
        """Run convert_paper.py, return output path on success."""
        script_path = (
            Path(__file__).parent.parent.parent.parent
            / ".claude"
            / "skills"
            / "arxiv-doc-builder"
            / "scripts"
            / "convert_paper.py"
        )
        if not script_path.exists():
            return None

        normalized = arxiv_id.replace("/", "_")
        output_dir = Path.cwd() / "papers"

        try:
            result = subprocess.run(
                [
                    "uv",
                    "run",
                    str(script_path),
                    arxiv_id,
                    "--output-dir",
                    str(output_dir),
                ],
                capture_output=True,
                text=True,
                timeout=300,
            )
            if result.returncode == 0:
                return output_dir / normalized / f"{normalized}.md"
        except (subprocess.TimeoutExpired, Exception):
            pass

        return None

    # ── Section Splitting ─────────────────────────────────────────────

    def _split_into_sections(self, full_text_md: str) -> dict[str, str]:
        """Split markdown into named sections by ## headers."""
        sections: dict[str, str] = {}
        current_heading = "_preamble"
        current_lines: list[str] = []

        for line in full_text_md.split("\n"):
            match = re.match(r"^## (.+)$", line)
            if match:
                if current_lines:
                    sections[current_heading] = "\n".join(current_lines).strip()
                current_heading = match.group(1).strip()
                current_lines = []
            else:
                current_lines.append(line)

        if current_lines:
            sections[current_heading] = "\n".join(current_lines).strip()

        return sections

    # ── Prompt Builders ───────────────────────────────────────────────

    def _build_prompt(
        self,
        section_type: ReviewSectionType,
        paper: Paper,
        full_text_md: str | None,
        paper_sections: dict[str, str] | None,
    ) -> str:
        """Build the AI prompt for a given section type."""
        header = (
            f"{self._PRESENTER_PERSONA}"
            f"Paper: {paper.title}\n"
            f"Authors: {', '.join(paper.authors[:10])}\n"
            f"arXiv ID: {paper.arxiv_id}\n"
            f"Categories: {', '.join(paper.categories)}\n\n"
            f"Abstract: {paper.abstract}"
        )

        builders = {
            ReviewSectionType.HOOK: self._prompt_hook,
            ReviewSectionType.PROBLEM: self._prompt_problem,
            ReviewSectionType.KEY_IDEA: self._prompt_key_idea,
            ReviewSectionType.METHOD: self._prompt_method,
            ReviewSectionType.RESULTS: self._prompt_results,
            ReviewSectionType.SIGNIFICANCE: self._prompt_significance,
            ReviewSectionType.APPRAISAL: self._prompt_appraisal,
            ReviewSectionType.DISCUSSION: self._prompt_discussion,
            ReviewSectionType.TAKEAWAYS: self._prompt_takeaways,
        }

        return builders[section_type](
            header=header,
            full_text_md=full_text_md,
            paper_sections=paper_sections,
        )

    def _prompt_hook(self, header: str, full_text_md: str | None, **_) -> str:
        context = full_text_md[:3000] if full_text_md else ""
        context_block = f"Full text excerpt:\n{context}" if context else ""
        return f"""{header}

{context_block}

You are opening a journal-club session on this paper. Craft a compelling hook that makes the room lean forward.

IMPORTANT: Respond ONLY with a JSON object (no markdown fences, no other text).
{{
    "one_liner": "One sentence that captures the paper's core contribution and why it's exciting",
    "why_care": "2-3 sentences explaining why this paper is worth a full journal-club slot -- what gap it fills and who benefits",
    "field": "Short domain label, e.g. 'Probabilistic ML', 'Computational Neuroscience', 'NLP'"
}}"""

    def _prompt_problem(self, header: str, full_text_md: str | None, **_) -> str:
        context = full_text_md[:4000] if full_text_md else ""
        context_block = f"Full text excerpt:\n{context}" if context else ""
        return f"""{header}

{context_block}

Explain the problem this paper tackles, grounded in the paper's actual framing (cite the relevant section when helpful).

IMPORTANT: Respond ONLY with a JSON object (no markdown fences, no other text).
{{
    "problem": "Clear statement of the core problem the paper addresses",
    "motivation": "Why this problem matters -- practical or theoretical stakes",
    "prior_gap": "What existing approaches were missing or where they failed"
}}"""

    def _prompt_key_idea(self, header: str, full_text_md: str | None, **_) -> str:
        context = full_text_md[:4000] if full_text_md else ""
        context_block = f"Full text excerpt:\n{context}" if context else ""
        return f"""{header}

{context_block}

Distill the paper's central insight into plain language. Focus on WHY the idea works, not just what it does.

IMPORTANT: Respond ONLY with a JSON object (no markdown fences, no other text).
{{
    "idea": "1-2 sentences stating the key idea precisely",
    "intuition": "Plain-language explanation of why this idea works -- what does it exploit or avoid?",
    "analogy": "A relatable analogy that makes the idea click for someone unfamiliar with the domain (or empty string if none fits)"
}}"""

    def _prompt_method(
        self,
        header: str,
        full_text_md: str | None,
        paper_sections: dict[str, str] | None,
        **_,
    ) -> str:
        method_text = ""
        if paper_sections:
            method_keywords = ["method", "approach", "model", "framework", "algorithm", "architecture"]
            for heading, content in paper_sections.items():
                if any(kw in heading.lower() for kw in method_keywords):
                    method_text += f"\n### {heading}\n{content[:2000]}\n"
        if not method_text and full_text_md:
            method_text = full_text_md[:5000]

        return f"""{header}

Relevant sections:
{method_text if method_text else "(Analyze methodology from abstract)"}

Walk the group through how the method works, step by step. The figure_brief panels will be drawn as a
friendly whiteboard infographic (left-to-right flow), so each panel's "content" should be a short
visual description using boxes, arrows, and labels -- English only, no formulas.

IMPORTANT: Respond ONLY with a JSON object (no markdown fences, no other text).
{{
    "overview": "1-2 sentences summarizing the overall pipeline or approach",
    "steps": ["Short description of step 1", "Short description of step 2"],
    "key_components": [
        {{"name": "Component name", "role": "What this component does in the pipeline"}}
    ],
    "figure_brief": {{
        "headline": "Method overview (<=8 words)",
        "subtitle": "One sentence describing what the figure shows",
        "panels": [
            {{"name": "Panel label", "content": "Short visual description: boxes, arrows, labels"}}
        ]
    }}
}}"""

    def _prompt_results(
        self,
        header: str,
        full_text_md: str | None,
        paper_sections: dict[str, str] | None,
        **_,
    ) -> str:
        exp_text = ""
        if paper_sections:
            exp_keywords = ["experiment", "result", "evaluation", "ablation", "benchmark", "performance"]
            for heading, content in paper_sections.items():
                if any(kw in heading.lower() for kw in exp_keywords):
                    exp_text += f"\n### {heading}\n{content[:2000]}\n"
        if not exp_text and full_text_md:
            exp_text = full_text_md[-4000:]

        return f"""{header}

Results sections:
{exp_text if exp_text else "(Analyze results from abstract)"}

Summarize the key empirical findings. Cite specific numbers where available. The figure_brief panels
will be drawn as a friendly whiteboard infographic, so each panel's "content" should be a short visual
description using bars, arrows, labels, or comparison callouts -- English only.

IMPORTANT: Respond ONLY with a JSON object (no markdown fences, no other text).
{{
    "headline": "The main empirical takeaway in one sentence",
    "key_numbers": [
        {{"metric": "Metric name", "value": "Reported value with units", "meaning": "Why this number matters"}}
    ],
    "takeaway": "1-2 sentences on what the results tell us about the method",
    "figure_brief": {{
        "headline": "Key results (<=8 words)",
        "subtitle": "One sentence describing what the figure shows",
        "panels": [
            {{"name": "Panel label", "content": "Short visual description: bars, callouts, comparisons"}}
        ]
    }}
}}"""

    def _prompt_significance(self, header: str, full_text_md: str | None, **_) -> str:
        context = ""
        if full_text_md:
            context = full_text_md[:2000] + "\n...\n" + full_text_md[-2000:]
        context_block = f"Paper content:\n{context}" if context else ""

        return f"""{header}

{context_block}

Explain why this paper matters beyond its immediate benchmark numbers. Be realistic and specific.

IMPORTANT: Respond ONLY with a JSON object (no markdown fences, no other text).
{{
    "why_matters": "Why this work is significant -- what changes as a result of this paper?",
    "applications": ["Concrete application or use case this enables"],
    "who_should_care": "Which communities or practitioners should pay attention to this work and why"
}}"""

    def _prompt_appraisal(self, header: str, full_text_md: str | None, **_) -> str:
        context = ""
        if full_text_md:
            context = full_text_md[:3000] + "\n...\n" + full_text_md[-2000:]
        context_block = f"Paper content:\n{context}" if context else ""

        return f"""{header}

{context_block}

Provide an honest, constructive appraisal for the journal-club group. NO accept/reject verdict,
NO severity labels, NO scores -- just a balanced and collegial assessment.

IMPORTANT: Respond ONLY with a JSON object (no markdown fences, no other text).
{{
    "strengths": ["What the paper does well -- be specific, not generic"],
    "limitations": ["Honest limitations or gaps -- constructive, not adversarial"],
    "open_questions": ["Questions the paper leaves unanswered or directions it does not address"]
}}"""

    def _prompt_discussion(self, header: str, full_text_md: str | None, **_) -> str:
        context = ""
        if full_text_md:
            context = full_text_md[:2000] + "\n...\n" + full_text_md[-2000:]
        context_block = f"Paper content:\n{context}" if context else ""

        return f"""{header}

{context_block}

Generate 4-6 discussion questions that would spark a lively, productive journal-club conversation.
Mix conceptual, methodological, and forward-looking questions.

IMPORTANT: Respond ONLY with a JSON object (no markdown fences, no other text).
{{
    "questions": [
        {{
            "question": "The discussion question",
            "why_interesting": "Why this question is worth the group's time"
        }}
    ]
}}"""

    def _prompt_takeaways(self, header: str, full_text_md: str | None, **_) -> str:
        context = full_text_md[:2000] if full_text_md else ""
        context_block = f"Full text excerpt:\n{context}" if context else ""

        return f"""{header}

{context_block}

Wrap up the journal-club session. Give 3-5 crisp bullet takeaways and one memorable closing sentence.

IMPORTANT: Respond ONLY with a JSON object (no markdown fences, no other text).
{{
    "bullets": ["Concise takeaway 1", "Concise takeaway 2", "Concise takeaway 3"],
    "one_sentence": "One memorable sentence that captures the paper's lasting contribution"
}}"""

    # ── AI Invocation ─────────────────────────────────────────────────

    def _invoke_ai(self, prompt: str) -> dict | None:
        """Invoke AI provider, extract JSON, parse."""
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
            return json.loads(output)
        except json.JSONDecodeError:
            return None

    # ── Cache Operations ──────────────────────────────────────────────

    def _get_cached_section(
        self, arxiv_id: str, section_type: ReviewSectionType
    ) -> ReviewSection | None:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM paper_review_sections WHERE arxiv_id = ? AND section_type = ?",
                (arxiv_id, section_type.value),
            ).fetchone()
            if row:
                return ReviewSection(
                    id=row["id"],
                    arxiv_id=row["arxiv_id"],
                    section_type=ReviewSectionType(row["section_type"]),
                    content_json=row["content_json"],
                    generated_at=datetime.fromisoformat(row["generated_at"]),
                )
        return None

    def _get_all_cached_sections(self, arxiv_id: str) -> dict[ReviewSectionType, ReviewSection]:
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM paper_review_sections WHERE arxiv_id = ?",
                (arxiv_id,),
            ).fetchall()
        result: dict[ReviewSectionType, ReviewSection] = {}
        for row in rows:
            # Skip rows from a previous review schema (legacy section_type values
            # that are no longer part of the journal-club pipeline).
            try:
                section_type = ReviewSectionType(row["section_type"])
            except ValueError:
                continue
            result[section_type] = ReviewSection(
                id=row["id"],
                arxiv_id=row["arxiv_id"],
                section_type=section_type,
                content_json=row["content_json"],
                generated_at=datetime.fromisoformat(row["generated_at"]),
            )
        return result

    def _save_section(
        self,
        arxiv_id: str,
        section_type: ReviewSectionType,
        data: dict,
        source_type: str,
    ) -> None:
        with get_connection() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO paper_review_sections
                   (arxiv_id, section_type, content_json, source_type)
                   VALUES (?, ?, ?, ?)""",
                (
                    arxiv_id,
                    section_type.value,
                    json.dumps(data, ensure_ascii=False),
                    source_type,
                ),
            )
            conn.commit()

    # ── Translation ───────────────────────────────────────────────────

    _HEADING_RE = re.compile(r"(?m)^(#{1,6}) (.*)$")
    _PLACEHOLDER = "@@JCRH{}@@"

    def _translate_markdown(self, markdown: str, target_language: Language) -> str | None:
        """Translate final markdown into ``target_language``.

        Headings are masked with placeholders before translation and re-inserted
        afterwards with forced surrounding blank lines, so the translator can
        never merge a heading into the following body text (which would turn a
        whole paragraph into one giant heading). The body is translated in
        paragraph-aligned chunks and rejoined with explicit blank lines, so lost
        whitespace at chunk boundaries cannot glue paragraphs together either.
        """
        lang_name = _LANG_NAMES.get(target_language, target_language.value)

        # 1. Mask heading lines, recording their level and original text.
        levels: list[str] = []
        texts: list[str] = []

        def _mask(match: re.Match) -> str:
            idx = len(texts)
            levels.append(match.group(1))
            texts.append(match.group(2).strip())
            return self._PLACEHOLDER.format(idx)

        masked = self._HEADING_RE.sub(_mask, markdown)

        # 2. Translate the body (no headings inside it now).
        translated = self._translate_body(masked, lang_name)
        if translated is None:
            return None

        # 3. Translate the heading texts and restore them on their own lines,
        #    forcing blank lines around each placeholder even if the translator
        #    glued surrounding text to it.
        translated_headings = self._translate_headings(texts, lang_name)
        for idx, (level, heading) in enumerate(zip(levels, translated_headings, strict=True)):
            placeholder = re.escape(self._PLACEHOLDER.format(idx))
            replacement = f"\n\n{level} {heading}\n\n"
            translated = re.sub(
                r"[ \t]*" + placeholder + r"[ \t]*",
                lambda _m, r=replacement: r,
                translated,
                count=1,
            )

        # Collapse the runs of blank lines the forced newlines may have created.
        return re.sub(r"\n{3,}", "\n\n", translated).strip() + "\n"

    def _translate_body(self, text: str, lang_name: str, max_chunk: int = 6000) -> str | None:
        """Translate masked body text in paragraph-aligned chunks."""
        if len(text) <= max_chunk:
            return self._translate_chunk(text, lang_name)

        paragraphs = text.split("\n\n")
        chunks: list[str] = []
        current = ""
        for para in paragraphs:
            addition = para if not current else "\n\n" + para
            if current and len(current) + len(addition) > max_chunk:
                chunks.append(current)
                current = para
            else:
                current += addition
        if current:
            chunks.append(current)

        translated_parts: list[str] = []
        for chunk in chunks:
            result = self._translate_chunk(chunk, lang_name)
            translated_parts.append((result or chunk).strip("\n"))
        # Rejoin with explicit blank lines so dropped boundary whitespace cannot
        # glue paragraphs from adjacent chunks.
        return "\n\n".join(translated_parts)

    def _translate_headings(self, texts: list[str], lang_name: str) -> list[str]:
        """Translate heading texts, batched into one call with a per-line fallback."""
        if not texts:
            return []

        numbered = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(texts))
        prompt = f"""Translate each numbered section heading below into {lang_name}.

RULES:
- Keep technical terms, model/dataset names, proper nouns, acronyms, and math in English.
- Return EXACTLY {len(texts)} lines, same numbering and order, one heading per line.
- Output only the translated headings, nothing else.

{numbered}"""
        output = self._invoke_text(prompt)
        if output:
            lines = [
                re.sub(r"^\s*\d+[.)]\s*", "", ln).strip()
                for ln in output.strip().splitlines()
                if ln.strip()
            ]
            if len(lines) == len(texts):
                return lines

        # Fallback: translate each heading individually.
        return [self._translate_chunk(t, lang_name) or t for t in texts]

    def _translate_chunk(self, text: str, lang_name: str) -> str | None:
        """Translate a single chunk of markdown body text."""
        prompt = f"""Translate the following Markdown into {lang_name}.

IMPORTANT RULES:
- Preserve ALL Markdown formatting (bold, italic, tables, links, lists, code blocks).
- Keep placeholder tokens like @@JCRH0@@ EXACTLY as they are, on their own line.
- Keep ALL technical terms, model names, dataset names, proper nouns, and acronyms in English.
- Keep mathematical notation ($...$, $$...$$) as-is.
- Keep URLs and arXiv IDs as-is.
- The translation should read naturally in {lang_name}.

Text to translate:
{text}

Respond with ONLY the translated markdown, no other text."""
        return self._invoke_text(prompt)

    def _invoke_text(self, prompt: str) -> str | None:
        """Invoke the configured provider for a plain-text response."""
        settings = SettingsService()
        provider = get_provider(settings.get_provider())
        if not provider.is_available():
            return None
        return provider.invoke(
            prompt,
            model=settings.get_model(),
            timeout=settings.get_timeout(),
        )
