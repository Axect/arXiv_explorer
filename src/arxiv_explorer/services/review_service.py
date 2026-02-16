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
    """Generate comprehensive AI paper reviews with incremental caching."""

    # Ordered processing pipeline: (section_type, requires_full_text?)
    SECTION_PIPELINE: list[tuple[ReviewSectionType, bool]] = [
        (ReviewSectionType.EXECUTIVE_SUMMARY, False),
        (ReviewSectionType.KEY_CONTRIBUTIONS, False),
        (ReviewSectionType.SECTION_SUMMARIES, True),
        (ReviewSectionType.METHODOLOGY, True),
        (ReviewSectionType.MATH_FORMULATIONS, True),
        (ReviewSectionType.FIGURES, True),
        (ReviewSectionType.TABLES, True),
        (ReviewSectionType.EXPERIMENTAL_RESULTS, True),
        (ReviewSectionType.STRENGTHS_WEAKNESSES, False),
        (ReviewSectionType.RELATED_WORK, True),
        (ReviewSectionType.GLOSSARY, False),
        (ReviewSectionType.QUESTIONS, False),
    ]

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
        figure_captions = None
        table_content = None
        math_blocks = None
        if full_text_md:
            paper_sections = self._split_into_sections(full_text_md)
            figure_captions = self._extract_figure_captions(full_text_md)
            table_content = self._extract_table_content(full_text_md)
            math_blocks = self._extract_math_blocks(full_text_md)

        # Step 3: Load existing cached sections
        cached = self._get_all_cached_sections(paper.arxiv_id)

        # Step 4: Process each section
        total = len(self.SECTION_PIPELINE)
        sections_data: dict[ReviewSectionType, dict] = {}

        for idx, (section_type, needs_full_text) in enumerate(self.SECTION_PIPELINE):
            if on_section_start:
                on_section_start(section_type, idx, total)

            # Use cached if available and not forcing
            if not force and section_type in cached:
                sections_data[section_type] = json.loads(
                    cached[section_type].content_json
                )
                if on_section_complete:
                    on_section_complete(section_type, True)
                continue

            # Skip data-dependent sections when no data exists
            if needs_full_text and not full_text_md:
                if section_type in (
                    ReviewSectionType.FIGURES,
                    ReviewSectionType.TABLES,
                    ReviewSectionType.MATH_FORMULATIONS,
                ):
                    empty = self._empty_section_data(section_type)
                    sections_data[section_type] = empty
                    self._save_section(
                        paper.arxiv_id, section_type, empty, source_type
                    )
                    if on_section_complete:
                        on_section_complete(section_type, True)
                    continue

            # Build prompt and invoke AI
            prompt = self._build_prompt(
                section_type=section_type,
                paper=paper,
                full_text_md=full_text_md,
                paper_sections=paper_sections,
                figure_captions=figure_captions,
                table_content=table_content,
                math_blocks=math_blocks,
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
            sections={
                st: json.loads(sec.content_json) for st, sec in cached.items()
            },
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
        """Render a PaperReview into final Markdown string."""
        parts: list[str] = []

        # --- Header ---
        parts.append(f"# {review.title}\n")
        author_str = ", ".join(review.authors[:10])
        if len(review.authors) > 10:
            author_str += f" (+{len(review.authors) - 10} more)"
        parts.append(f"**Authors:** {author_str}  ")
        parts.append(
            f"**arXiv ID:** [{review.arxiv_id}]"
            f"(https://arxiv.org/abs/{review.arxiv_id})  "
        )
        parts.append(f"**Categories:** {', '.join(review.categories)}  ")
        parts.append(f"**Published:** {review.published.strftime('%Y-%m-%d')}  ")
        if review.pdf_url:
            parts.append(f"**PDF:** [{review.pdf_url}]({review.pdf_url})  ")
        source_label = (
            "Full text analysis"
            if review.source_type == "full_text"
            else "Abstract-only analysis"
        )
        parts.append(f"**Source:** {source_label}")
        parts.append("")

        # --- Executive Summary ---
        es = review.sections.get(ReviewSectionType.EXECUTIVE_SUMMARY, {})
        if es:
            parts.append("## Executive Summary\n")
            if es.get("tldr"):
                parts.append(f"**TL;DR:** {es['tldr']}\n")
            if es.get("research_question"):
                parts.append(f"**Research Question:** {es['research_question']}\n")
            if es.get("approach_summary"):
                parts.append(f"**Approach:** {es['approach_summary']}\n")
            if es.get("main_result"):
                parts.append(f"**Main Result:** {es['main_result']}\n")

        # --- Key Contributions ---
        kc = review.sections.get(ReviewSectionType.KEY_CONTRIBUTIONS, {})
        if kc and kc.get("contributions"):
            parts.append("## Key Contributions\n")
            for c in kc["contributions"]:
                ctype = c.get("type", "general")
                parts.append(f"- **[{ctype}]** {c.get('contribution', '')}")
                if c.get("significance"):
                    parts.append(f"  - *Significance:* {c['significance']}")
            parts.append("")

        # --- Section-by-Section Summary ---
        ss = review.sections.get(ReviewSectionType.SECTION_SUMMARIES, {})
        if ss and ss.get("sections"):
            parts.append("## Section-by-Section Summary\n")
            for sec in ss["sections"]:
                parts.append(f"### {sec.get('heading', 'Unknown Section')}\n")
                parts.append(f"{sec.get('summary', '')}\n")
                if sec.get("key_points"):
                    for kp in sec["key_points"]:
                        parts.append(f"- {kp}")
                    parts.append("")

        # --- Methodology Analysis ---
        meth = review.sections.get(ReviewSectionType.METHODOLOGY, {})
        if meth:
            parts.append("## Methodology Analysis\n")
            if meth.get("overview"):
                parts.append(f"{meth['overview']}\n")
            if meth.get("steps"):
                for step in meth["steps"]:
                    parts.append(f"### {step.get('step_name', 'Step')}\n")
                    parts.append(f"{step.get('description', '')}\n")
                    novelty = step.get("novelty", "")
                    if novelty and novelty != "standard":
                        parts.append(f"*Novelty:* {novelty}\n")
            if meth.get("assumptions"):
                parts.append("**Assumptions:**\n")
                for a in meth["assumptions"]:
                    parts.append(f"- {a}")
                parts.append("")
            if meth.get("complexity_notes"):
                parts.append(f"**Complexity:** {meth['complexity_notes']}\n")

        # --- Figure Descriptions ---
        figs = review.sections.get(ReviewSectionType.FIGURES, {})
        if figs and figs.get("figures"):
            parts.append("## Figure Descriptions\n")
            for fig in figs["figures"]:
                parts.append(f"### Figure {fig.get('figure_id', '?')}\n")
                parts.append(f"{fig.get('description', '')}\n")
                if fig.get("significance"):
                    parts.append(f"*Significance:* {fig['significance']}\n")

        # --- Table Descriptions ---
        tbls = review.sections.get(ReviewSectionType.TABLES, {})
        if tbls and tbls.get("tables"):
            parts.append("## Table Descriptions\n")
            for tbl in tbls["tables"]:
                cap = tbl.get("caption", "")
                parts.append(f"### Table {tbl.get('table_id', '?')}: {cap}\n")
                parts.append(f"{tbl.get('description', '')}\n")
                if tbl.get("key_findings"):
                    parts.append(f"*Key findings:* {tbl['key_findings']}\n")

        # --- Mathematical Formulations ---
        math = review.sections.get(ReviewSectionType.MATH_FORMULATIONS, {})
        if math and math.get("formulations"):
            parts.append("## Mathematical Formulations\n")
            for f in math["formulations"]:
                parts.append(f"### {f.get('equation_label', 'Equation')}\n")
                if f.get("latex"):
                    parts.append(f"$$\n{f['latex']}\n$$\n")
                if f.get("plain_language"):
                    parts.append(f"**Plain language:** {f['plain_language']}\n")
                if f.get("role"):
                    parts.append(f"*Role:* {f['role']}\n")

        # --- Experimental Results ---
        exp = review.sections.get(ReviewSectionType.EXPERIMENTAL_RESULTS, {})
        if exp:
            parts.append("## Experimental Results\n")
            if exp.get("datasets"):
                parts.append(f"**Datasets:** {', '.join(exp['datasets'])}\n")
            if exp.get("baselines"):
                parts.append(f"**Baselines:** {', '.join(exp['baselines'])}\n")
            if exp.get("metrics"):
                parts.append(f"**Metrics:** {', '.join(exp['metrics'])}\n")
            if exp.get("main_results"):
                parts.append(f"{exp['main_results']}\n")
            if exp.get("ablation_studies"):
                parts.append(f"**Ablation Studies:** {exp['ablation_studies']}\n")
            if exp.get("notable_findings"):
                parts.append("**Notable Findings:**\n")
                for nf in exp["notable_findings"]:
                    parts.append(f"- {nf}")
                parts.append("")

        # --- Strengths and Weaknesses ---
        sw = review.sections.get(ReviewSectionType.STRENGTHS_WEAKNESSES, {})
        if sw:
            parts.append("## Strengths and Weaknesses\n")
            if sw.get("strengths"):
                parts.append("### Strengths\n")
                for s in sw["strengths"]:
                    parts.append(f"- **{s.get('point', '')}**")
                    if s.get("evidence"):
                        parts.append(f"  - {s['evidence']}")
                parts.append("")
            if sw.get("weaknesses"):
                parts.append("### Weaknesses\n")
                for w in sw["weaknesses"]:
                    parts.append(f"- **{w.get('point', '')}**")
                    if w.get("evidence"):
                        parts.append(f"  - {w['evidence']}")
                parts.append("")
            if sw.get("overall_assessment"):
                parts.append(
                    f"**Overall Assessment:** {sw['overall_assessment']}\n"
                )

        # --- Related Work ---
        rw = review.sections.get(ReviewSectionType.RELATED_WORK, {})
        if rw:
            parts.append("## Related Work Context\n")
            if rw.get("research_areas"):
                parts.append(
                    f"**Research Areas:** {', '.join(rw['research_areas'])}\n"
                )
            if rw.get("key_prior_works"):
                for pw in rw["key_prior_works"]:
                    parts.append(f"- **{pw.get('work', '')}**")
                    if pw.get("relationship"):
                        parts.append(f"  - {pw['relationship']}")
                parts.append("")
            if rw.get("positioning"):
                parts.append(f"**Positioning:** {rw['positioning']}\n")

        # --- Glossary ---
        gl = review.sections.get(ReviewSectionType.GLOSSARY, {})
        if gl and gl.get("terms"):
            parts.append("## Glossary\n")
            parts.append("| Term | Definition |")
            parts.append("|------|-----------|")
            for t in gl["terms"]:
                term = t.get("term", "")
                defn = t.get("definition", "").replace("|", "\\|")
                parts.append(f"| **{term}** | {defn} |")
            parts.append("")

        # --- Questions ---
        qs = review.sections.get(ReviewSectionType.QUESTIONS, {})
        if qs and qs.get("questions"):
            parts.append("## Questions for Further Investigation\n")
            for q in qs["questions"]:
                qtype = q.get("type", "general")
                parts.append(f"- **[{qtype}]** {q.get('question', '')}")
                if q.get("motivation"):
                    parts.append(f"  - *Motivation:* {q['motivation']}")
            parts.append("")

        # --- Footer ---
        parts.append("---")
        parts.append(
            f"*Generated by arXiv Explorer"
            f" | {review.generated_at.strftime('%Y-%m-%d %H:%M')}*"
        )

        markdown = "\n".join(parts)

        # --- Translation ---
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

    def _extract_figure_captions(
        self, full_text_md: str
    ) -> list[dict[str, str]]:
        """Extract figure captions and surrounding context."""
        figures: list[dict[str, str]] = []

        # Pattern 1: ![caption](path) followed by *Figure N: caption*
        pattern1 = re.compile(
            r"!\[([^\]]*)\]\([^)]+\)\s*\n\*Figure\s+(\d+):\s*([^*]+)\*",
            re.MULTILINE,
        )
        for m in pattern1.finditer(full_text_md):
            figures.append(
                {
                    "figure_id": m.group(2),
                    "caption": m.group(3).strip(),
                    "context": full_text_md[
                        max(0, m.start() - 200) : m.end() + 200
                    ],
                }
            )

        # Pattern 2: **Figure N:** or *Figure N:* without image
        pattern2 = re.compile(
            r"\*\*?Figure\s+(\d+)[:.]\*?\*?\s*(.+?)(?:\n|$)", re.MULTILINE
        )
        seen_ids = {f["figure_id"] for f in figures}
        for m in pattern2.finditer(full_text_md):
            fid = m.group(1)
            if fid not in seen_ids:
                figures.append(
                    {
                        "figure_id": fid,
                        "caption": m.group(2).strip(),
                        "context": full_text_md[
                            max(0, m.start() - 200) : m.end() + 200
                        ],
                    }
                )
                seen_ids.add(fid)

        return figures

    def _extract_table_content(
        self, full_text_md: str
    ) -> list[dict[str, str]]:
        """Extract markdown tables and their captions."""
        tables: list[dict[str, str]] = []

        # Find markdown table blocks (consecutive lines starting with |)
        table_pattern = re.compile(
            r"((?:\|.+\|\n)+)(?:\s*\*?(?:\*?)Table\s+(\d+)[:.]\*?\*?\s*([^\n*]*))?",
            re.MULTILINE,
        )
        for i, m in enumerate(table_pattern.finditer(full_text_md), 1):
            tables.append(
                {
                    "table_id": m.group(2) or str(i),
                    "caption": (m.group(3) or "").strip(),
                    "content": m.group(1).strip(),
                }
            )
        return tables

    def _extract_math_blocks(self, full_text_md: str) -> list[str]:
        """Extract display math blocks ($$...$$)."""
        pattern = re.compile(r"\$\$\s*\n?(.*?)\n?\s*\$\$", re.DOTALL)
        return [m.group(1).strip() for m in pattern.finditer(full_text_md)]

    # ── Prompt Builders ───────────────────────────────────────────────

    def _build_prompt(
        self,
        section_type: ReviewSectionType,
        paper: Paper,
        full_text_md: str | None,
        paper_sections: dict[str, str] | None,
        figure_captions: list[dict] | None,
        table_content: list[dict] | None,
        math_blocks: list[str] | None,
    ) -> str:
        """Build the AI prompt for a given section type."""
        header = (
            f"Paper: {paper.title}\n"
            f"Authors: {', '.join(paper.authors[:10])}\n"
            f"arXiv ID: {paper.arxiv_id}\n"
            f"Categories: {', '.join(paper.categories)}\n\n"
            f"Abstract: {paper.abstract}"
        )

        builders = {
            ReviewSectionType.EXECUTIVE_SUMMARY: self._prompt_executive_summary,
            ReviewSectionType.KEY_CONTRIBUTIONS: self._prompt_contributions,
            ReviewSectionType.SECTION_SUMMARIES: self._prompt_section_summaries,
            ReviewSectionType.METHODOLOGY: self._prompt_methodology,
            ReviewSectionType.MATH_FORMULATIONS: self._prompt_math,
            ReviewSectionType.FIGURES: self._prompt_figures,
            ReviewSectionType.TABLES: self._prompt_tables,
            ReviewSectionType.EXPERIMENTAL_RESULTS: self._prompt_experiments,
            ReviewSectionType.STRENGTHS_WEAKNESSES: self._prompt_strengths_weaknesses,
            ReviewSectionType.RELATED_WORK: self._prompt_related_work,
            ReviewSectionType.GLOSSARY: self._prompt_glossary,
            ReviewSectionType.QUESTIONS: self._prompt_questions,
        }

        return builders[section_type](
            header=header,
            full_text_md=full_text_md,
            paper_sections=paper_sections,
            figure_captions=figure_captions,
            table_content=table_content,
            math_blocks=math_blocks,
        )

    def _prompt_executive_summary(self, header, full_text_md, **_) -> str:
        context = full_text_md[:4000] if full_text_md else ""
        return f"""{header}

{f"Full text excerpt:\\n{context}" if context else ""}

Analyze this paper and provide an executive summary.
IMPORTANT: Respond ONLY with valid JSON, no other text.
{{
    "tldr": "3-5 sentence TL;DR capturing the core contribution and result",
    "research_question": "The main research question addressed",
    "approach_summary": "1-2 sentence summary of the approach",
    "main_result": "The most important quantitative or qualitative result"
}}"""

    def _prompt_contributions(self, header, full_text_md, **_) -> str:
        context = full_text_md[:3000] if full_text_md else ""
        return f"""{header}

{f"Full text excerpt:\\n{context}" if context else ""}

List the key contributions of this paper.
IMPORTANT: Respond ONLY with valid JSON, no other text.
{{
    "contributions": [
        {{
            "contribution": "Description of the contribution",
            "type": "theoretical|methodological|empirical|system|dataset",
            "significance": "Why this matters"
        }}
    ]
}}"""

    def _prompt_section_summaries(self, header, paper_sections, **_) -> str:
        sections_text = ""
        if paper_sections:
            for heading, content in paper_sections.items():
                if heading == "_preamble":
                    continue
                truncated = content[:1500]
                sections_text += f"\n### {heading}\n{truncated}\n"

        return f"""{header}

Paper sections:
{sections_text if sections_text else "(Full text not available -- analyze based on abstract)"}

For each major section of the paper, provide a summary paragraph.
IMPORTANT: Respond ONLY with valid JSON, no other text.
{{
    "sections": [
        {{
            "heading": "Section heading as it appears",
            "summary": "2-4 sentence summary of this section",
            "key_points": ["point 1", "point 2"]
        }}
    ]
}}"""

    def _prompt_methodology(self, header, paper_sections, full_text_md, **_) -> str:
        method_text = ""
        if paper_sections:
            method_keywords = [
                "method",
                "approach",
                "model",
                "framework",
                "algorithm",
                "architecture",
            ]
            for heading, content in paper_sections.items():
                if any(kw in heading.lower() for kw in method_keywords):
                    method_text += f"\n### {heading}\n{content[:2000]}\n"
        if not method_text and full_text_md:
            method_text = full_text_md[:5000]

        return f"""{header}

Relevant sections:
{method_text if method_text else "(Analyze methodology from abstract)"}

Provide a detailed methodology analysis.
IMPORTANT: Respond ONLY with valid JSON, no other text.
{{
    "overview": "High-level description of the methodology",
    "steps": [
        {{
            "step_name": "Name of this step/component",
            "description": "Detailed explanation",
            "novelty": "What is novel about this step (or 'standard' if not novel)"
        }}
    ],
    "assumptions": ["Key assumption 1", "Key assumption 2"],
    "complexity_notes": "Computational complexity or scalability notes if mentioned"
}}"""

    def _prompt_math(self, header, math_blocks, **_) -> str:
        math_text = ""
        if math_blocks:
            for i, block in enumerate(math_blocks[:15], 1):
                math_text += f"\nEquation {i}: {block}\n"

        return f"""{header}

Key equations found:
{math_text if math_text else "(No display equations detected)"}

Explain the key mathematical formulations in plain language.
IMPORTANT: Respond ONLY with valid JSON, no other text.
{{
    "formulations": [
        {{
            "equation_label": "Equation number or name",
            "latex": "Original LaTeX",
            "plain_language": "What this equation means in plain English",
            "role": "How it fits into the overall methodology"
        }}
    ]
}}"""

    def _prompt_figures(self, header, figure_captions, **_) -> str:
        figs_text = ""
        if figure_captions:
            for fig in figure_captions:
                figs_text += f"\nFigure {fig['figure_id']}: {fig['caption']}\n"
                figs_text += f"Context: {fig['context'][:300]}\n"

        return f"""{header}

Figure captions and context:
{figs_text if figs_text else "(No figures detected)"}

Describe each figure based on its caption and surrounding context.
IMPORTANT: Respond ONLY with valid JSON, no other text.
{{
    "figures": [
        {{
            "figure_id": "1",
            "description": "What this figure likely shows based on caption and context",
            "significance": "Why this figure is important for understanding the paper"
        }}
    ]
}}"""

    def _prompt_tables(self, header, table_content, **_) -> str:
        tables_text = ""
        if table_content:
            for tbl in table_content:
                tables_text += f"\nTable {tbl['table_id']}: {tbl['caption']}\n"
                tables_text += f"{tbl['content'][:500]}\n"

        return f"""{header}

Tables found in paper:
{tables_text if tables_text else "(No tables detected)"}

Analyze each table and describe its contents and significance.
IMPORTANT: Respond ONLY with valid JSON, no other text.
{{
    "tables": [
        {{
            "table_id": "1",
            "caption": "Original caption",
            "description": "What this table shows",
            "key_findings": "Notable results or patterns in the data"
        }}
    ]
}}"""

    def _prompt_experiments(
        self, header, paper_sections, table_content, **_
    ) -> str:
        exp_text = ""
        if paper_sections:
            exp_keywords = [
                "experiment",
                "result",
                "evaluation",
                "ablation",
                "benchmark",
                "performance",
            ]
            for heading, content in paper_sections.items():
                if any(kw in heading.lower() for kw in exp_keywords):
                    exp_text += f"\n### {heading}\n{content[:2000]}\n"

        tables_summary = ""
        if table_content:
            for tbl in table_content[:5]:
                tables_summary += f"\nTable {tbl['table_id']}: {tbl['content'][:300]}\n"

        return f"""{header}

Experimental sections:
{exp_text if exp_text else "(Analyze from abstract)"}

Result tables:
{tables_summary}

Analyze the experimental setup and results.
IMPORTANT: Respond ONLY with valid JSON, no other text.
{{
    "datasets": ["Dataset names used"],
    "baselines": ["Baseline methods compared against"],
    "metrics": ["Evaluation metrics used"],
    "main_results": "Summary of main quantitative results",
    "ablation_studies": "Summary of ablation studies if present",
    "notable_findings": ["Finding 1", "Finding 2"]
}}"""

    def _prompt_strengths_weaknesses(self, header, full_text_md, **_) -> str:
        context = ""
        if full_text_md:
            context = full_text_md[:3000] + "\n...\n" + full_text_md[-2000:]

        return f"""{header}

{f"Paper content:\\n{context}" if context else ""}

Provide a critical analysis of the paper's strengths and weaknesses.
IMPORTANT: Respond ONLY with valid JSON, no other text.
{{
    "strengths": [
        {{
            "point": "Strength description",
            "evidence": "Supporting evidence or reasoning"
        }}
    ],
    "weaknesses": [
        {{
            "point": "Weakness description",
            "evidence": "Supporting evidence or reasoning"
        }}
    ],
    "overall_assessment": "1-2 sentence overall assessment"
}}"""

    def _prompt_related_work(self, header, paper_sections, **_) -> str:
        rw_text = ""
        if paper_sections:
            rw_keywords = [
                "related",
                "background",
                "prior",
                "previous",
                "literature",
            ]
            for heading, content in paper_sections.items():
                if any(kw in heading.lower() for kw in rw_keywords):
                    rw_text += f"\n### {heading}\n{content[:2500]}\n"

        return f"""{header}

Related work sections:
{rw_text if rw_text else "(Analyze related work context from abstract)"}

Summarize the related work landscape and how this paper positions itself.
IMPORTANT: Respond ONLY with valid JSON, no other text.
{{
    "research_areas": ["Area 1", "Area 2"],
    "key_prior_works": [
        {{
            "work": "Author et al. (Year) - brief description",
            "relationship": "How this paper relates to or differs from it"
        }}
    ],
    "positioning": "How the paper positions itself within the field"
}}"""

    def _prompt_glossary(self, header, full_text_md, **_) -> str:
        context = full_text_md[:5000] if full_text_md else ""

        return f"""{header}

{f"Paper content:\\n{context}" if context else ""}

Extract key technical terms and provide definitions.
IMPORTANT: Respond ONLY with valid JSON, no other text.
{{
    "terms": [
        {{
            "term": "Technical term",
            "definition": "Clear definition as used in this paper",
            "first_occurrence": "Section where it first appears (if known)"
        }}
    ]
}}"""

    def _prompt_questions(self, header, full_text_md, **_) -> str:
        context = ""
        if full_text_md:
            context = full_text_md[:2000] + "\n...\n" + full_text_md[-2000:]

        return f"""{header}

{f"Paper content:\\n{context}" if context else ""}

Suggest questions for further investigation based on this paper.
IMPORTANT: Respond ONLY with valid JSON, no other text.
{{
    "questions": [
        {{
            "question": "The question",
            "motivation": "Why this question is interesting or important",
            "type": "clarification|extension|limitation|application"
        }}
    ]
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
                "SELECT * FROM paper_review_sections"
                " WHERE arxiv_id = ? AND section_type = ?",
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

    def _get_all_cached_sections(
        self, arxiv_id: str
    ) -> dict[ReviewSectionType, ReviewSection]:
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM paper_review_sections WHERE arxiv_id = ?",
                (arxiv_id,),
            ).fetchall()
        return {
            ReviewSectionType(row["section_type"]): ReviewSection(
                id=row["id"],
                arxiv_id=row["arxiv_id"],
                section_type=ReviewSectionType(row["section_type"]),
                content_json=row["content_json"],
                generated_at=datetime.fromisoformat(row["generated_at"]),
            )
            for row in rows
        }

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

    @staticmethod
    def _empty_section_data(section_type: ReviewSectionType) -> dict:
        """Return empty but valid JSON for sections with no data."""
        empty_maps: dict[ReviewSectionType, dict] = {
            ReviewSectionType.FIGURES: {"figures": []},
            ReviewSectionType.TABLES: {"tables": []},
            ReviewSectionType.MATH_FORMULATIONS: {"formulations": []},
        }
        return empty_maps.get(section_type, {})

    # ── Translation ───────────────────────────────────────────────────

    def _translate_markdown(
        self, markdown: str, target_language: Language
    ) -> str | None:
        """Translate final markdown, chunking by ## headers if needed."""
        lang_name = _LANG_NAMES.get(target_language, target_language.value)
        max_chunk = 6000

        if len(markdown) <= max_chunk:
            return self._translate_chunk(markdown, lang_name)

        # Split by ## headers to maintain structure
        chunks = re.split(r"(^## .+$)", markdown, flags=re.MULTILINE)
        translated_parts: list[str] = []
        current_chunk = ""

        for chunk in chunks:
            if len(current_chunk) + len(chunk) > max_chunk and current_chunk:
                result = self._translate_chunk(current_chunk, lang_name)
                translated_parts.append(result or current_chunk)
                current_chunk = chunk
            else:
                current_chunk += chunk

        if current_chunk:
            result = self._translate_chunk(current_chunk, lang_name)
            translated_parts.append(result or current_chunk)

        return "".join(translated_parts)

    def _translate_chunk(self, text: str, lang_name: str) -> str | None:
        """Translate a single chunk of markdown."""
        prompt = f"""Translate the following Markdown document into {lang_name}.

IMPORTANT RULES:
- Preserve ALL Markdown formatting (headers, bold, italic, tables, links, code blocks)
- Keep ALL technical terms, model names, dataset names, proper nouns, and acronyms in English
- Keep mathematical notation ($...$, $$...$$) as-is
- Keep URLs and arXiv IDs as-is
- The translation should read naturally in {lang_name}

Text to translate:
{text}

Respond with ONLY the translated markdown, no other text."""

        settings = SettingsService()
        provider = get_provider(settings.get_provider())
        if not provider.is_available():
            return None
        return provider.invoke(
            prompt,
            model=settings.get_model(),
            timeout=settings.get_timeout(),
        )
