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
        (ReviewSectionType.REPRODUCIBILITY, True),
        (ReviewSectionType.STRENGTHS_WEAKNESSES, False),
        (ReviewSectionType.IMPACT_SIGNIFICANCE, False),
        (ReviewSectionType.RELATED_WORK, True),
        (ReviewSectionType.GLOSSARY, False),
        (ReviewSectionType.QUESTIONS, False),
        (ReviewSectionType.READING_GUIDE, False),
    ]

    # Shared reviewer persona prefix for all prompts
    _REVIEWER_PERSONA = (
        "You are a senior reviewer for a top-tier venue (e.g., NeurIPS, ICML, Nature, JMLR). "
        "You have deep expertise in the paper's domain and extensive experience evaluating "
        "research for novelty, rigor, clarity, and significance. "
        "Your analysis must be evidence-grounded: cite specific sections, equations, figures, "
        "or tables from the paper to support every claim. "
        "Avoid vague praise or criticism — be precise and constructive.\n\n"
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
                sections_data[section_type] = json.loads(cached[section_type].content_json)
                if on_section_complete:
                    on_section_complete(section_type, True)
                continue

            # Skip data-dependent sections when no data exists
            if needs_full_text and not full_text_md:
                if section_type in (
                    ReviewSectionType.FIGURES,
                    ReviewSectionType.TABLES,
                    ReviewSectionType.MATH_FORMULATIONS,
                    ReviewSectionType.REPRODUCIBILITY,
                ):
                    empty = self._empty_section_data(section_type)
                    sections_data[section_type] = empty
                    self._save_section(paper.arxiv_id, section_type, empty, source_type)
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

    # ── Severity / Rating Formatting Helpers ────────────────────────────

    _SEVERITY_BADGES: dict[str, str] = {
        "critical": "**[CRITICAL]**",
        "major": "**[MAJOR]**",
        "moderate": "[MODERATE]",
        "minor": "[minor]",
    }

    _RECOMMENDATION_LABELS: dict[str, str] = {
        "strong_accept": "Strong Accept",
        "accept": "Accept",
        "weak_accept": "Weak Accept",
        "borderline": "Borderline",
        "weak_reject": "Weak Reject",
        "reject": "Reject",
    }

    _SIGNIFICANCE_LABELS: dict[str, str] = {
        "transformative": "Transformative",
        "significant": "Significant",
        "solid_contribution": "Solid Contribution",
        "incremental": "Incremental",
        "limited": "Limited",
    }

    def render_markdown(
        self,
        review: PaperReview,
        language: Language = Language.EN,
    ) -> str:
        """Render a PaperReview into publication-quality Markdown."""
        parts: list[str] = []
        sw = review.sections.get(ReviewSectionType.STRENGTHS_WEAKNESSES, {})
        imp = review.sections.get(ReviewSectionType.IMPACT_SIGNIFICANCE, {})

        # ═══════════════════════════════════════════════════════════════
        # HEADER & METADATA
        # ═══════════════════════════════════════════════════════════════
        parts.append(f"# {review.title}\n")
        author_str = ", ".join(review.authors[:10])
        if len(review.authors) > 10:
            author_str += f" (+{len(review.authors) - 10} more)"

        source_label = "Full text" if review.source_type == "full_text" else "Abstract only"

        # Quick Reference Card
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
        parts.append(f"| **Analysis Source** | {source_label} |")

        # Inject recommendation & significance into the card if available
        rec = sw.get("recommendation", "")
        if rec:
            rec_label = self._RECOMMENDATION_LABELS.get(rec, rec)
            parts.append(f"| **Recommendation** | **{rec_label}** |")
        sig = imp.get("significance_rating", "")
        if sig:
            sig_label = self._SIGNIFICANCE_LABELS.get(sig, sig)
            parts.append(f"| **Significance** | {sig_label} |")
        confidence = sw.get("confidence", "")
        if confidence:
            parts.append(f"| **Reviewer Confidence** | {confidence} |")
        parts.append("")

        # ═══════════════════════════════════════════════════════════════
        # TABLE OF CONTENTS
        # ═══════════════════════════════════════════════════════════════
        toc_sections = [
            (ReviewSectionType.EXECUTIVE_SUMMARY, "Executive Summary"),
            (ReviewSectionType.KEY_CONTRIBUTIONS, "Key Contributions"),
            (ReviewSectionType.SECTION_SUMMARIES, "Section-by-Section Summary"),
            (ReviewSectionType.METHODOLOGY, "Methodology Analysis"),
            (ReviewSectionType.MATH_FORMULATIONS, "Mathematical Formulations"),
            (ReviewSectionType.FIGURES, "Figure Analysis"),
            (ReviewSectionType.TABLES, "Table Analysis"),
            (ReviewSectionType.EXPERIMENTAL_RESULTS, "Experimental Results"),
            (ReviewSectionType.REPRODUCIBILITY, "Reproducibility Assessment"),
            (ReviewSectionType.STRENGTHS_WEAKNESSES, "Strengths & Weaknesses"),
            (ReviewSectionType.IMPACT_SIGNIFICANCE, "Impact & Significance"),
            (ReviewSectionType.RELATED_WORK, "Related Work"),
            (ReviewSectionType.GLOSSARY, "Glossary"),
            (ReviewSectionType.QUESTIONS, "Questions for Authors"),
            (ReviewSectionType.READING_GUIDE, "Reading Guide"),
        ]
        toc_items = []
        for st, label in toc_sections:
            data = review.sections.get(st, {})
            if data:
                anchor = label.lower().replace(" ", "-").replace("&", "").replace("--", "-")
                toc_items.append(f"[{label}](#{anchor})")
        if toc_items:
            parts.append(f"**Contents:** {' | '.join(toc_items)}\n")

        parts.append("---\n")

        # ═══════════════════════════════════════════════════════════════
        # EXECUTIVE SUMMARY
        # ═══════════════════════════════════════════════════════════════
        es = review.sections.get(ReviewSectionType.EXECUTIVE_SUMMARY, {})
        if es:
            parts.append("## Executive Summary\n")
            if es.get("tldr"):
                parts.append(f"> {es['tldr']}\n")
            if es.get("research_question"):
                parts.append(f"**Research Question:** {es['research_question']}\n")
            if es.get("approach_summary"):
                parts.append(f"**Approach:** {es['approach_summary']}\n")
            if es.get("main_result"):
                parts.append(f"**Main Result:** {es['main_result']}\n")
            if es.get("novelty_claim"):
                parts.append(f"**Novelty:** {es['novelty_claim']}\n")
            if es.get("one_sentence_verdict"):
                parts.append(f"**Verdict:** *{es['one_sentence_verdict']}*\n")
            if es.get("target_audience"):
                parts.append(f"**Target Audience:** {es['target_audience']}\n")

        # ═══════════════════════════════════════════════════════════════
        # KEY CONTRIBUTIONS
        # ═══════════════════════════════════════════════════════════════
        kc = review.sections.get(ReviewSectionType.KEY_CONTRIBUTIONS, {})
        if kc and kc.get("contributions"):
            parts.append("## Key Contributions\n")
            for i, c in enumerate(kc["contributions"], 1):
                ctype = c.get("type", "general")
                novelty = c.get("novelty", "")
                novelty_tag = f" `{novelty}`" if novelty else ""
                parts.append(f"**{i}. [{ctype}]{novelty_tag}** {c.get('contribution', '')}\n")
                if c.get("significance"):
                    parts.append(f"- *Significance:* {c['significance']}")
                if c.get("evidence_strength"):
                    parts.append(f"- *Evidence:* {c['evidence_strength']}")
                parts.append("")

        # ═══════════════════════════════════════════════════════════════
        # SECTION-BY-SECTION SUMMARY
        # ═══════════════════════════════════════════════════════════════
        ss = review.sections.get(ReviewSectionType.SECTION_SUMMARIES, {})
        if ss and ss.get("sections"):
            parts.append("## Section-by-Section Summary\n")
            for sec in ss["sections"]:
                clarity = sec.get("clarity_assessment", "")
                clarity_tag = f" `{clarity}`" if clarity else ""
                parts.append(f"### {sec.get('heading', 'Unknown Section')}{clarity_tag}\n")
                parts.append(f"{sec.get('summary', '')}\n")
                if sec.get("key_points"):
                    for kp in sec["key_points"]:
                        parts.append(f"- {kp}")
                    parts.append("")

        # ═══════════════════════════════════════════════════════════════
        # METHODOLOGY ANALYSIS
        # ═══════════════════════════════════════════════════════════════
        meth = review.sections.get(ReviewSectionType.METHODOLOGY, {})
        if meth:
            parts.append("## Methodology Analysis\n")
            if meth.get("overview"):
                parts.append(f"{meth['overview']}\n")
            if meth.get("steps"):
                for step in meth["steps"]:
                    novelty = step.get("novelty", "standard")
                    novelty_badge = f" `{novelty}`" if novelty != "standard" else ""
                    parts.append(f"### {step.get('step_name', 'Step')}{novelty_badge}\n")
                    parts.append(f"{step.get('description', '')}\n")
                    if step.get("justification"):
                        parts.append(f"*Justification:* {step['justification']}\n")
            if meth.get("assumptions"):
                parts.append("### Assumptions\n")
                # Support both old (list of strings) and new (list of dicts) format
                for a in meth["assumptions"]:
                    if isinstance(a, dict):
                        parts.append(f"- **{a.get('assumption', '')}**")
                        if a.get("validity"):
                            parts.append(f"  - *Validity:* {a['validity']}")
                        if a.get("impact_if_violated"):
                            parts.append(f"  - *If violated:* {a['impact_if_violated']}")
                    else:
                        parts.append(f"- {a}")
                parts.append("")
            if meth.get("limitations"):
                parts.append("### Methodological Limitations\n")
                for lim in meth["limitations"]:
                    parts.append(f"- {lim}")
                parts.append("")
            if meth.get("complexity_notes"):
                parts.append(f"**Complexity:** {meth['complexity_notes']}\n")

        # ═══════════════════════════════════════════════════════════════
        # MATHEMATICAL FORMULATIONS
        # ═══════════════════════════════════════════════════════════════
        math_data = review.sections.get(ReviewSectionType.MATH_FORMULATIONS, {})
        if math_data and math_data.get("formulations"):
            parts.append("## Mathematical Formulations\n")
            for f in math_data["formulations"]:
                role = f.get("role", "")
                role_tag = f" `{role}`" if role else ""
                parts.append(f"### {f.get('equation_label', 'Equation')}{role_tag}\n")
                if f.get("latex"):
                    parts.append(f"$$\n{f['latex']}\n$$\n")
                if f.get("plain_language"):
                    parts.append(f"{f['plain_language']}\n")
                if f.get("variables"):
                    parts.append(f"*Variables:* {f['variables']}\n")
                if f.get("correctness_note") and f["correctness_note"] != "appears sound":
                    parts.append(f"> **Note:** {f['correctness_note']}\n")

        # ═══════════════════════════════════════════════════════════════
        # FIGURE ANALYSIS
        # ═══════════════════════════════════════════════════════════════
        figs = review.sections.get(ReviewSectionType.FIGURES, {})
        if figs and figs.get("figures"):
            parts.append("## Figure Analysis\n")
            for fig in figs["figures"]:
                sig = fig.get("significance", "")
                sig_tag = f" `{sig}`" if sig else ""
                parts.append(f"### Figure {fig.get('figure_id', '?')}{sig_tag}\n")
                parts.append(f"{fig.get('description', '')}\n")
                if fig.get("claim_supported"):
                    parts.append(f"- *Supports:* {fig['claim_supported']}")
                if fig.get("caption_quality"):
                    parts.append(f"- *Caption:* {fig['caption_quality']}")
                if fig.get("presentation_issues") and fig["presentation_issues"] != "none":
                    parts.append(f"- *Issues:* {fig['presentation_issues']}")
                parts.append("")

        # ═══════════════════════════════════════════════════════════════
        # TABLE ANALYSIS
        # ═══════════════════════════════════════════════════════════════
        tbls = review.sections.get(ReviewSectionType.TABLES, {})
        if tbls and tbls.get("tables"):
            parts.append("## Table Analysis\n")
            for tbl in tbls["tables"]:
                cap = tbl.get("caption", "")
                ttype = tbl.get("table_type", "")
                type_tag = f" `{ttype}`" if ttype else ""
                parts.append(f"### Table {tbl.get('table_id', '?')}: {cap}{type_tag}\n")
                parts.append(f"{tbl.get('description', '')}\n")
                if tbl.get("key_findings"):
                    parts.append(f"**Key findings:** {tbl['key_findings']}\n")
                if tbl.get("issues") and tbl["issues"] != "none":
                    parts.append(f"> **Issues:** {tbl['issues']}\n")

        # ═══════════════════════════════════════════════════════════════
        # EXPERIMENTAL RESULTS
        # ═══════════════════════════════════════════════════════════════
        exp = review.sections.get(ReviewSectionType.EXPERIMENTAL_RESULTS, {})
        if exp:
            parts.append("## Experimental Results\n")
            # Setup summary table
            setup_rows = []
            if exp.get("datasets"):
                setup_rows.append(("Datasets", ", ".join(exp["datasets"])))
            if exp.get("baselines"):
                setup_rows.append(("Baselines", ", ".join(exp["baselines"])))
            if exp.get("metrics"):
                setup_rows.append(("Metrics", ", ".join(exp["metrics"])))
            if setup_rows:
                parts.append("| Aspect | Details |")
                parts.append("|:-------|:--------|")
                for label, val in setup_rows:
                    parts.append(f"| {label} | {val} |")
                parts.append("")

            if exp.get("main_results"):
                parts.append(f"### Main Results\n\n{exp['main_results']}\n")
            if exp.get("statistical_rigor"):
                parts.append(f"### Statistical Rigor\n\n{exp['statistical_rigor']}\n")
            if exp.get("ablation_studies"):
                parts.append(f"### Ablation Studies\n\n{exp['ablation_studies']}\n")
            if exp.get("missing_experiments"):
                parts.append("### Missing Experiments\n")
                for me in exp["missing_experiments"]:
                    parts.append(f"- {me}")
                parts.append("")
            if exp.get("notable_findings"):
                parts.append("### Notable Findings\n")
                for nf in exp["notable_findings"]:
                    parts.append(f"- {nf}")
                parts.append("")

        # ═══════════════════════════════════════════════════════════════
        # REPRODUCIBILITY ASSESSMENT
        # ═══════════════════════════════════════════════════════════════
        repro = review.sections.get(ReviewSectionType.REPRODUCIBILITY, {})
        if repro and repro.get("reproducibility_score", "unknown") != "unknown":
            parts.append("## Reproducibility Assessment\n")
            score = repro.get("reproducibility_score", "unknown")
            parts.append(f"**Overall Score: `{score}`**\n")

            parts.append("| Dimension | Assessment |")
            parts.append("|:----------|:-----------|")
            dims = [
                ("Code Availability", "code_availability"),
                ("Data Availability", "data_availability"),
                ("Methodology Clarity", "methodology_clarity"),
                ("Hyperparameter Reporting", "hyperparameter_reporting"),
                ("Compute Requirements", "computational_requirements"),
                ("Variance Reporting", "variance_reporting"),
            ]
            for label, key in dims:
                val = repro.get(key, "")
                if val:
                    parts.append(f"| {label} | {val} |")
            parts.append("")

            if repro.get("missing_details"):
                parts.append("**Missing for Reproducibility:**\n")
                for md in repro["missing_details"]:
                    parts.append(f"- {md}")
                parts.append("")

        # ═══════════════════════════════════════════════════════════════
        # STRENGTHS & WEAKNESSES
        # ═══════════════════════════════════════════════════════════════
        if sw:
            parts.append("## Strengths & Weaknesses\n")
            if sw.get("strengths"):
                parts.append("### Strengths\n")
                for s in sw["strengths"]:
                    cat = s.get("category", "")
                    sig_level = s.get("significance", "")
                    tags = []
                    if cat:
                        tags.append(cat)
                    if sig_level:
                        tags.append(sig_level)
                    tag_str = f" `{'|'.join(tags)}`" if tags else ""
                    parts.append(f"- **{s.get('point', '')}**{tag_str}")
                    if s.get("evidence"):
                        parts.append(f"  - {s['evidence']}")
                parts.append("")
            if sw.get("weaknesses"):
                parts.append("### Weaknesses\n")
                for w in sw["weaknesses"]:
                    severity = w.get("severity", "")
                    badge = self._SEVERITY_BADGES.get(severity, "")
                    cat = w.get("category", "")
                    cat_tag = f" `{cat}`" if cat else ""
                    parts.append(f"- {badge} **{w.get('point', '')}**{cat_tag}")
                    if w.get("evidence"):
                        parts.append(f"  - {w['evidence']}")
                    if w.get("suggestion"):
                        parts.append(f"  - *Suggestion:* {w['suggestion']}")
                parts.append("")
            if sw.get("overall_assessment"):
                parts.append(f"> **Assessment:** {sw['overall_assessment']}\n")

        # ═══════════════════════════════════════════════════════════════
        # IMPACT & SIGNIFICANCE
        # ═══════════════════════════════════════════════════════════════
        if imp:
            parts.append("## Impact & Significance\n")
            sig_rating = imp.get("significance_rating", "")
            if sig_rating:
                label = self._SIGNIFICANCE_LABELS.get(sig_rating, sig_rating)
                parts.append(f"**Rating: `{label}`**\n")
            if imp.get("field_impact"):
                parts.append(f"**Field Impact:** {imp['field_impact']}\n")
            if imp.get("practical_applications"):
                parts.append("**Practical Applications:**\n")
                for pa in imp["practical_applications"]:
                    parts.append(f"- {pa}")
                parts.append("")
            if imp.get("broader_impact"):
                parts.append(f"**Broader Impact:** {imp['broader_impact']}\n")
            if imp.get("limitations_of_impact"):
                parts.append(f"**Limitations:** {imp['limitations_of_impact']}\n")
            if imp.get("future_directions"):
                parts.append("### Future Directions\n")
                for fd in imp["future_directions"]:
                    if isinstance(fd, dict):
                        parts.append(f"- **{fd.get('direction', '')}**")
                        if fd.get("potential"):
                            parts.append(f"  - {fd['potential']}")
                    else:
                        parts.append(f"- {fd}")
                parts.append("")

        # ═══════════════════════════════════════════════════════════════
        # RELATED WORK
        # ═══════════════════════════════════════════════════════════════
        rw = review.sections.get(ReviewSectionType.RELATED_WORK, {})
        if rw:
            parts.append("## Related Work\n")
            if rw.get("research_areas"):
                # Support both old (list of strings) and new (list of dicts) format
                for area in rw["research_areas"]:
                    if isinstance(area, dict):
                        parts.append(f"**{area.get('area', '')}:** {area.get('description', '')}\n")
                    else:
                        parts.append(f"- {area}")
                if isinstance(rw["research_areas"][0], str):
                    parts.append("")
            if rw.get("key_prior_works"):
                parts.append("### Key Prior Works\n")
                for pw in rw["key_prior_works"]:
                    rel = pw.get("relationship", "")
                    rel_tag = f" `{rel}`" if rel else ""
                    parts.append(f"- **{pw.get('work', '')}**{rel_tag}")
                    if pw.get("comparison"):
                        parts.append(f"  - {pw['comparison']}")
                parts.append("")
            if rw.get("coverage_gaps"):
                parts.append("### Coverage Gaps\n")
                for gap in rw["coverage_gaps"]:
                    parts.append(f"- {gap}")
                parts.append("")
            if rw.get("positioning"):
                parts.append(f"**Positioning:** {rw['positioning']}\n")

        # ═══════════════════════════════════════════════════════════════
        # GLOSSARY
        # ═══════════════════════════════════════════════════════════════
        gl = review.sections.get(ReviewSectionType.GLOSSARY, {})
        if gl and gl.get("terms"):
            parts.append("## Glossary\n")
            parts.append("| Term | Category | Definition |")
            parts.append("|:-----|:---------|:-----------|")
            for t in gl["terms"]:
                term = t.get("term", "")
                defn = t.get("definition", "").replace("|", "\\|")
                cat = t.get("category", "concept")
                parts.append(f"| **{term}** | `{cat}` | {defn} |")
            parts.append("")

        # ═══════════════════════════════════════════════════════════════
        # QUESTIONS FOR AUTHORS
        # ═══════════════════════════════════════════════════════════════
        qs = review.sections.get(ReviewSectionType.QUESTIONS, {})
        if qs and qs.get("questions"):
            parts.append("## Questions for Authors\n")
            for i, q in enumerate(qs["questions"], 1):
                qtype = q.get("type", "general")
                priority = q.get("priority", "")
                priority_tag = f" `{priority}`" if priority else ""
                parts.append(f"**Q{i} [{qtype}]{priority_tag}:** {q.get('question', '')}\n")
                if q.get("motivation"):
                    parts.append(f"*{q['motivation']}*\n")
                if q.get("relevant_section"):
                    parts.append(f"*Related to: {q['relevant_section']}*\n")

        # ═══════════════════════════════════════════════════════════════
        # READING GUIDE
        # ═══════════════════════════════════════════════════════════════
        rg = review.sections.get(ReviewSectionType.READING_GUIDE, {})
        if rg:
            parts.append("## Reading Guide\n")
            time_est = rg.get("time_estimate_minutes", "")
            difficulty = rg.get("difficulty_level", "")
            if time_est or difficulty:
                meta = []
                if time_est:
                    meta.append(f"~{time_est} min")
                if difficulty:
                    meta.append(difficulty)
                parts.append(f"**{' | '.join(meta)}**\n")
            if rg.get("essential_sections"):
                parts.append("**Must-read sections:**\n")
                for s in rg["essential_sections"]:
                    parts.append(f"- {s}")
                parts.append("")
            if rg.get("skip_if_familiar"):
                parts.append("**Skip if familiar with the domain:**\n")
                for s in rg["skip_if_familiar"]:
                    parts.append(f"- {s}")
                parts.append("")
            if rg.get("suggested_reading_order"):
                order = " -> ".join(rg["suggested_reading_order"])
                parts.append(f"**Suggested reading order:** {order}\n")
            if rg.get("key_figures"):
                parts.append("**Key figures:** " + ", ".join(rg["key_figures"]) + "\n")
            if rg.get("key_tables"):
                parts.append("**Key tables:** " + ", ".join(rg["key_tables"]) + "\n")
            if rg.get("prerequisite_knowledge"):
                parts.append("**Prerequisites:**\n")
                for p in rg["prerequisite_knowledge"]:
                    parts.append(f"- {p}")
                parts.append("")

        # ═══════════════════════════════════════════════════════════════
        # FOOTER
        # ═══════════════════════════════════════════════════════════════
        parts.append("---")
        parts.append(
            f"*Generated by arXiv Explorer | "
            f"{review.generated_at.strftime('%Y-%m-%d %H:%M')} | "
            f"{len(review.sections)}/{len(ReviewSectionType)} sections*"
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

    def _extract_figure_captions(self, full_text_md: str) -> list[dict[str, str]]:
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
                    "context": full_text_md[max(0, m.start() - 200) : m.end() + 200],
                }
            )

        # Pattern 2: **Figure N:** or *Figure N:* without image
        pattern2 = re.compile(r"\*\*?Figure\s+(\d+)[:.]\*?\*?\s*(.+?)(?:\n|$)", re.MULTILINE)
        seen_ids = {f["figure_id"] for f in figures}
        for m in pattern2.finditer(full_text_md):
            fid = m.group(1)
            if fid not in seen_ids:
                figures.append(
                    {
                        "figure_id": fid,
                        "caption": m.group(2).strip(),
                        "context": full_text_md[max(0, m.start() - 200) : m.end() + 200],
                    }
                )
                seen_ids.add(fid)

        return figures

    def _extract_table_content(self, full_text_md: str) -> list[dict[str, str]]:
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
            f"{self._REVIEWER_PERSONA}"
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
            ReviewSectionType.REPRODUCIBILITY: self._prompt_reproducibility,
            ReviewSectionType.STRENGTHS_WEAKNESSES: self._prompt_strengths_weaknesses,
            ReviewSectionType.IMPACT_SIGNIFICANCE: self._prompt_impact_significance,
            ReviewSectionType.RELATED_WORK: self._prompt_related_work,
            ReviewSectionType.GLOSSARY: self._prompt_glossary,
            ReviewSectionType.QUESTIONS: self._prompt_questions,
            ReviewSectionType.READING_GUIDE: self._prompt_reading_guide,
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
        context_block = f"Full text excerpt:\n{context}" if context else ""
        return f"""{header}

{context_block}

Provide an executive summary as if writing the opening paragraph of a peer review.
Your summary must demonstrate that you understand the paper's core argument, not just its topic.

EVALUATION CRITERIA:
- The TL;DR should convey what was done, why, and the key result — a reader should be able to decide whether to read the paper from this alone.
- The research question must be stated as a precise, answerable question, not a vague topic.
- The novelty claim must distinguish what is genuinely new vs. what is incremental improvement.
- The verdict must be a honest, balanced assessment — not sales copy.

IMPORTANT: Respond ONLY with valid JSON, no other text.
{{
    "tldr": "3-5 sentence TL;DR that captures the problem, approach, key result, and why it matters",
    "research_question": "The precise research question or hypothesis this paper addresses",
    "approach_summary": "1-2 sentence summary of the technical approach and its key innovation",
    "main_result": "The single most important result, stated with specific numbers/metrics where available",
    "novelty_claim": "What the paper claims as its novel contribution, distinguished from prior work",
    "target_audience": "Who would benefit most from reading this paper (specific research communities or practitioners)",
    "one_sentence_verdict": "Single sentence balanced assessment capturing both promise and limitations"
}}"""

    def _prompt_contributions(self, header, full_text_md, **_) -> str:
        context = full_text_md[:3000] if full_text_md else ""
        context_block = f"Full text excerpt:\n{context}" if context else ""
        return f"""{header}

{context_block}

Identify and evaluate the key contributions of this paper. For each contribution:
- Distinguish between claimed contributions and actually demonstrated ones.
- Assess novelty relative to the state of the art — is this genuinely new, or an incremental refinement?
- Evaluate how well the paper supports each claim with evidence (experiments, proofs, ablations).

DO NOT simply restate the paper's own claims. Critically evaluate whether the evidence supports them.
Limit to 3-6 contributions, ranked by significance.

IMPORTANT: Respond ONLY with valid JSON, no other text.
{{
    "contributions": [
        {{
            "contribution": "Precise description of the contribution",
            "type": "theoretical|methodological|empirical|system|dataset",
            "novelty": "incremental|moderate|significant — justify in one phrase",
            "significance": "Why this contribution matters to the field",
            "evidence_strength": "How well the paper supports this claim (strong/moderate/weak, with brief justification)"
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

Provide a structured summary of each major section. For each section:
- Summarize the content in your own words (do not copy verbatim).
- Identify 2-4 key points that carry the argument forward.
- Assess how well the section fulfills its role in the paper's overall narrative.
- Rate the clarity: is the section well-written, or does it need improvement?

IMPORTANT: Respond ONLY with valid JSON, no other text.
{{
    "sections": [
        {{
            "heading": "Section heading as it appears in the paper",
            "summary": "2-4 sentence summary capturing the section's purpose and content",
            "key_points": ["key point 1", "key point 2"],
            "clarity_assessment": "clear|mostly_clear|needs_improvement — brief justification"
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

Provide a rigorous methodology analysis through the lens of a peer reviewer.

EVALUATION CRITERIA:
- Is the method well-motivated? Does the paper justify why this approach over alternatives?
- Is each step clearly defined with enough detail for replication?
- Are assumptions stated explicitly? How reasonable are they?
- What are the methodological limitations the authors may not acknowledge?
- Is the computational complexity discussed?

For each methodological step, assess whether it is genuinely novel, an adaptation of existing work, or standard practice. Identify the specific prior work it builds upon where applicable.

IMPORTANT: Respond ONLY with valid JSON, no other text.
{{
    "overview": "High-level description of the methodology and its key innovation",
    "steps": [
        {{
            "step_name": "Name of this step/component",
            "description": "Detailed technical explanation",
            "novelty": "novel|adaptation|standard — cite the specific prior work if adaptation/standard",
            "justification": "Why this design choice was made (as stated or inferred)"
        }}
    ],
    "assumptions": [
        {{
            "assumption": "Description of the assumption",
            "validity": "How reasonable this assumption is and when it might break",
            "impact_if_violated": "Consequence if this assumption does not hold"
        }}
    ],
    "limitations": ["Methodological limitation not acknowledged by the authors"],
    "complexity_notes": "Computational/memory complexity and scalability analysis"
}}"""

    def _prompt_math(self, header, math_blocks, **_) -> str:
        math_text = ""
        if math_blocks:
            for i, block in enumerate(math_blocks[:15], 1):
                math_text += f"\nEquation {i}: {block}\n"

        return f"""{header}

Key equations found:
{math_text if math_text else "(No display equations detected)"}

Analyze the key mathematical formulations. For each equation:
- Provide the original LaTeX (preserve notation exactly).
- Explain in plain language what the equation computes and why.
- Identify which variables are inputs, outputs, and hyperparameters.
- Assess correctness: are there dimensional inconsistencies, missing terms, or notation ambiguities?
- Explain its role in the paper's argument — is this a definition, a derivation step, or a key result?

Focus on the 5-10 most important equations. Skip trivial definitions.

IMPORTANT: Respond ONLY with valid JSON, no other text.
{{
    "formulations": [
        {{
            "equation_label": "Equation number or descriptive name (e.g., 'Eq. 3 — Loss function')",
            "latex": "Original LaTeX notation",
            "plain_language": "What this equation computes, explained for a graduate student",
            "variables": "Key variables and their meanings",
            "role": "definition|derivation_step|key_result|constraint|objective — how it fits the argument",
            "correctness_note": "Any concerns about correctness, notation, or missing terms (or 'appears sound')"
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

Analyze each figure as a reviewer would. For each figure:
- Describe what the figure shows (chart type, axes, data series).
- Assess whether the caption is self-contained — could a reader understand the figure from the caption alone?
- Evaluate the figure's role: does it support a specific claim in the text? Which one?
- Note any presentation issues: missing labels, unclear legends, inappropriate chart types, etc.

IMPORTANT: Respond ONLY with valid JSON, no other text.
{{
    "figures": [
        {{
            "figure_id": "1",
            "description": "What the figure shows — chart type, axes, key data points",
            "claim_supported": "Which specific claim or result this figure supports",
            "caption_quality": "Is the caption self-contained? What's missing?",
            "presentation_issues": "Any issues with readability, labeling, or chart type choice (or 'none')",
            "significance": "How critical this figure is to the paper's argument (essential|supporting|supplementary)"
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

Analyze each table with the rigor of a peer reviewer. For each table:
- Describe what the table presents (comparison, ablation, dataset statistics, etc.).
- Identify the key takeaway — what is the most important result in this table?
- Check for issues: missing baselines, unfair comparisons, cherry-picked metrics, or inconsistencies.
- Note whether the table is self-contained with its caption.

IMPORTANT: Respond ONLY with valid JSON, no other text.
{{
    "tables": [
        {{
            "table_id": "1",
            "caption": "Original caption text",
            "table_type": "comparison|ablation|statistics|configuration|other",
            "description": "What the table presents and how to read it",
            "key_findings": "The most important result or pattern, with specific numbers",
            "issues": "Any concerns: missing baselines, unfair comparisons, incomplete data (or 'none')"
        }}
    ]
}}"""

    def _prompt_experiments(self, header, paper_sections, table_content, **_) -> str:
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

Provide a rigorous analysis of the experimental evaluation as a peer reviewer.

EVALUATION CRITERIA:
- Are the datasets appropriate for the claims being made? Are they standard benchmarks?
- Are the baselines fair and up-to-date? Are any important baselines missing?
- Are the metrics standard for this task? Are they sufficient to support the conclusions?
- Is there statistical significance reporting (error bars, confidence intervals, multiple runs)?
- Are ablation studies present and do they isolate the contribution of each component?
- Are there experiments that should have been included but weren't?

Be specific: cite numbers from the tables where available.

IMPORTANT: Respond ONLY with valid JSON, no other text.
{{
    "datasets": ["Dataset name — brief description of why it's appropriate or concerning"],
    "baselines": ["Baseline method — is it a fair, up-to-date comparison?"],
    "metrics": ["Metric — appropriate for the task?"],
    "main_results": "Summary of quantitative results with specific numbers where available",
    "statistical_rigor": "Assessment of statistical methodology: error bars, significance tests, number of runs",
    "ablation_studies": "Summary of ablation studies and whether they sufficiently isolate contributions",
    "missing_experiments": ["Experiment that would strengthen the paper but is absent"],
    "notable_findings": ["Surprising or particularly strong/weak finding"]
}}"""

    def _prompt_reproducibility(self, header, paper_sections, full_text_md, **_) -> str:
        method_text = ""
        if paper_sections:
            method_keywords = [
                "method",
                "experiment",
                "implementation",
                "setup",
                "training",
                "hyperparameter",
                "appendix",
            ]
            for heading, content in paper_sections.items():
                if any(kw in heading.lower() for kw in method_keywords):
                    method_text += f"\n### {heading}\n{content[:1500]}\n"
        if not method_text and full_text_md:
            method_text = full_text_md[:4000]

        return f"""{header}

Relevant sections:
{method_text if method_text else "(Analyze from abstract)"}

Assess the reproducibility of this work. This is one of the most important aspects of scientific rigor.

EVALUATE EACH DIMENSION:
1. **Code**: Is code provided, promised, or entirely absent? Is it a link to a repo, pseudocode, or nothing?
2. **Data**: Are datasets publicly available? Are preprocessing steps documented?
3. **Method clarity**: Could an expert in the field reimplement the method from the paper alone?
4. **Hyperparameters**: Are all hyperparameters, training details, and architectural choices specified?
5. **Compute**: Are computational requirements (GPU type, training time, memory) reported?
6. **Random seeds & variance**: Are experiments run with multiple seeds? Is variance reported?

Assign a reproducibility score based on the NeurIPS reproducibility checklist standards.

IMPORTANT: Respond ONLY with valid JSON, no other text.
{{
    "code_availability": "available_with_link|promised|pseudocode_only|not_mentioned — include URL if available",
    "data_availability": "public_benchmark|available_with_link|described_but_not_shared|proprietary|not_mentioned",
    "methodology_clarity": "sufficient_for_reimplementation|mostly_clear_with_gaps|insufficient — describe what's missing",
    "hyperparameter_reporting": "complete|mostly_complete|significant_gaps|minimal — list what's missing",
    "computational_requirements": "fully_reported|partially_reported|not_mentioned — include specifics if available",
    "variance_reporting": "multiple_seeds_with_error_bars|single_run_acknowledged|not_addressed",
    "reproducibility_score": "high|medium|low",
    "missing_details": ["Specific detail needed for reproducibility that is absent from the paper"]
}}"""

    def _prompt_strengths_weaknesses(self, header, full_text_md, **_) -> str:
        context = ""
        if full_text_md:
            context = full_text_md[:3000] + "\n...\n" + full_text_md[-2000:]
        context_block = f"Paper content:\n{context}" if context else ""

        return f"""{header}

{context_block}

Write a structured peer review covering strengths and weaknesses, as if submitting a review to a top-tier venue.

GUIDELINES:
- Every point must cite specific evidence from the paper (section, equation, figure, or table number).
- Categorize each point: technical correctness, novelty, presentation quality, experimental rigor, reproducibility, or scope.
- Assign severity: minor (cosmetic or easily fixable), moderate (weakens but doesn't invalidate), major (significant concern), critical (potentially invalidating).
- Strengths should be substantive, not generic ("well-written" alone is not a strength).
- Weaknesses should be constructive: suggest how each could be addressed.
- Provide 3-6 strengths and 3-6 weaknesses. Do NOT pad the list with trivial points.

Finally, provide an overall recommendation as a reviewer would:
- strong_accept: Excellent, top 5% of submissions
- accept: Clear accept, solid contribution
- weak_accept: Leans positive, minor concerns
- borderline: Could go either way
- weak_reject: Leans negative, significant concerns
- reject: Below threshold for the venue

IMPORTANT: Respond ONLY with valid JSON, no other text.
{{
    "strengths": [
        {{
            "point": "Concise strength statement",
            "evidence": "Specific evidence from the paper (cite section/figure/table)",
            "category": "technical|novelty|presentation|experimental|reproducibility|scope",
            "significance": "minor|moderate|major"
        }}
    ],
    "weaknesses": [
        {{
            "point": "Concise weakness statement",
            "evidence": "Specific evidence from the paper",
            "category": "technical|novelty|presentation|experimental|reproducibility|scope",
            "severity": "minor|moderate|major|critical",
            "suggestion": "How this weakness could be addressed"
        }}
    ],
    "overall_assessment": "2-3 sentence balanced assessment that weighs strengths against weaknesses",
    "recommendation": "strong_accept|accept|weak_accept|borderline|weak_reject|reject",
    "confidence": "high|medium|low — how confident you are in this assessment"
}}"""

    def _prompt_impact_significance(self, header, full_text_md, **_) -> str:
        context = ""
        if full_text_md:
            # Read intro and conclusion for impact context
            context = full_text_md[:2500] + "\n...\n" + full_text_md[-2500:]
        context_block = f"Paper content:\n{context}" if context else ""

        return f"""{header}

{context_block}

Assess the broader impact and significance of this work. Think beyond the immediate technical contribution.

EVALUATE:
1. **Field impact**: How does this advance the state of the art? Is it opening a new direction or refining an existing one?
2. **Practical applications**: Could this work be deployed in real systems? What are the barriers?
3. **Broader impact**: Are there societal implications (positive or negative)?
4. **Limitations of impact**: What factors limit the paper's influence (narrow scope, strong assumptions, limited evaluation)?
5. **Future directions**: What research does this naturally lead to?

Be realistic — most papers are incremental improvements, and that's fine. But clearly distinguish between truly significant work and solid-but-incremental contributions.

IMPORTANT: Respond ONLY with valid JSON, no other text.
{{
    "field_impact": "How this work advances the field — be specific about what changes",
    "practical_applications": ["Concrete practical application or use case"],
    "broader_impact": "Societal or cross-disciplinary implications, if any",
    "limitations_of_impact": "What limits the paper's real-world influence",
    "future_directions": [
        {{
            "direction": "Specific future research direction",
            "potential": "Why this direction is promising"
        }}
    ],
    "significance_rating": "transformative|significant|solid_contribution|incremental|limited"
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

Analyze the related work and the paper's positioning within the field.

EVALUATION CRITERIA:
- Does the paper adequately cover the relevant literature? Are there notable omissions?
- Is the comparison to prior work fair and accurate?
- Does the paper clearly articulate how it differs from and improves upon existing approaches?
- Are there concurrent works that should be acknowledged?

Group related works by research area/theme rather than listing them sequentially.

IMPORTANT: Respond ONLY with valid JSON, no other text.
{{
    "research_areas": [
        {{
            "area": "Research area or theme name",
            "description": "Brief description of this line of work and its relevance"
        }}
    ],
    "key_prior_works": [
        {{
            "work": "Author et al. (Year) — brief description",
            "relationship": "extends|improves_upon|alternative_to|builds_on|concurrent_with",
            "comparison": "How this paper specifically differs from or improves upon this work"
        }}
    ],
    "coverage_gaps": ["Important related work that appears to be missing from the paper's discussion"],
    "positioning": "How the paper positions itself — is this positioning fair and well-supported?"
}}"""

    def _prompt_glossary(self, header, full_text_md, **_) -> str:
        context = full_text_md[:5000] if full_text_md else ""
        context_block = f"Paper content:\n{context}" if context else ""

        return f"""{header}

{context_block}

Extract key technical terms, acronyms, and domain-specific notation used in this paper.
Focus on terms that a reader from a related (but not identical) field would need defined.
Skip universally known terms (e.g., "neural network", "gradient descent") unless the paper uses them with a non-standard meaning.
Include mathematical notation where the paper defines symbols with specific meaning.

IMPORTANT: Respond ONLY with valid JSON, no other text.
{{
    "terms": [
        {{
            "term": "Technical term or symbol",
            "definition": "Clear definition as used specifically in this paper",
            "first_occurrence": "Section where it first appears (if known)",
            "category": "concept|acronym|notation|metric"
        }}
    ]
}}"""

    def _prompt_questions(self, header, full_text_md, **_) -> str:
        context = ""
        if full_text_md:
            context = full_text_md[:2000] + "\n...\n" + full_text_md[-2000:]
        context_block = f"Paper content:\n{context}" if context else ""

        return f"""{header}

{context_block}

Generate substantive questions that a thoughtful reviewer or reader would ask.

Include a mix of:
- **Clarification questions**: Where the paper is ambiguous or under-specified
- **Methodological questions**: About design choices, alternatives, or limitations
- **Extension questions**: How this work could be extended or applied to new domains
- **Challenge questions**: Potential counterarguments or edge cases the authors should address

Each question should be specific enough that the authors could write a concrete response. Avoid vague questions like "Can you elaborate on X?"

Provide 5-8 questions, prioritized by importance.

IMPORTANT: Respond ONLY with valid JSON, no other text.
{{
    "questions": [
        {{
            "question": "Specific, answerable question",
            "motivation": "Why this question matters — what gap or concern it addresses",
            "type": "clarification|methodological|extension|challenge",
            "priority": "high|medium|low",
            "relevant_section": "Which section of the paper this question relates to"
        }}
    ]
}}"""

    def _prompt_reading_guide(self, header, full_text_md, paper_sections, **_) -> str:
        sections_list = ""
        if paper_sections:
            sections_list = ", ".join(h for h in paper_sections.keys() if h != "_preamble")

        context = full_text_md[:3000] if full_text_md else ""
        context_block = f"Paper structure:\n{context}" if context else ""

        return f"""{header}

{context_block}
Paper sections: {sections_list if sections_list else "(not available)"}

Create a reading guide for this paper. The goal is to help a busy researcher decide how to invest their reading time.

Consider:
- Which sections are essential to understand the core contribution?
- Which sections can be skipped by someone already familiar with the domain?
- What is the optimal reading order (which may differ from the paper's linear order)?
- Which figures and tables convey the most information?
- What background knowledge is assumed?
- How long should a thorough read take?

IMPORTANT: Respond ONLY with valid JSON, no other text.
{{
    "essential_sections": ["Section names that are must-read to understand the paper"],
    "skip_if_familiar": ["Sections an expert can safely skip"],
    "key_figures": ["Figure N — brief reason why it's important"],
    "key_tables": ["Table N — brief reason why it's important"],
    "prerequisite_knowledge": ["Background knowledge or papers assumed by the authors"],
    "suggested_reading_order": ["Optimal section order for maximum understanding"],
    "time_estimate_minutes": 30,
    "difficulty_level": "introductory|intermediate|advanced|expert"
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
            ReviewSectionType.REPRODUCIBILITY: {
                "code_availability": "Unknown (full text not available)",
                "data_availability": "Unknown",
                "methodology_clarity": "Cannot assess without full text",
                "hyperparameter_reporting": "Cannot assess without full text",
                "computational_requirements": "Not mentioned",
                "reproducibility_score": "unknown",
                "missing_details": [],
            },
        }
        return empty_maps.get(section_type, {})

    # ── Translation ───────────────────────────────────────────────────

    def _translate_markdown(self, markdown: str, target_language: Language) -> str | None:
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
