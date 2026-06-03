"""Figure generation for reviews via the bundled codex image_generation tool.

When the OpenAI/codex runtime is installed and logged in (ChatGPT auth), the
bundled `codex` binary can generate PNG infographics with its built-in
`image_generation` tool, no API key required. We compose a wide-slide-style
prompt (default "friendly" = Friendly Whiteboard) from a structured figure
brief and let codex render it.
"""

import subprocess
from pathlib import Path

# ---------------------------------------------------------------------------
# Style blocks (baked from the wide-slide-illustrator skill so the app does not
# depend on the skill at runtime). Keep the wording; it is load-bearing.
# ---------------------------------------------------------------------------

_FRIENDLY_STYLE = """OVERALL LOOK:
- Clean off-white / warm cream background with a subtle dotted grid.
- Modern flat-illustration style with a hand-drawn / whiteboard-sketch feel:
  slightly wavy strokes, soft drop shadows, rounded corners on every box.
- Friendly palette: teal (#2EC4B6), coral (#FF6B6B), mustard (#FFB627),
  soft purple (#7C5CFF), forest green (#3FA34D), charcoal (#2B2D42) for text.
  No pure black, no neon.
- Panels flow LEFT to RIGHT, separated by chunky chalk-style arrows with
  little motion lines, like a comic strip. Each panel has a numbered circular
  badge in its top-left corner.
- Small playful touches: a tiny domain-relevant sticker doodle in one corner,
  a sticky note pinned to a panel for a key takeaway. A research-group
  whiteboard vibe, not childish.

TYPOGRAPHY:
- Headlines: bold geometric sans (Inter / Manrope feel).
- Body labels: friendly humanist sans, slightly looser tracking.
- Equations rendered cleanly, NOT as garbled math glyphs.
- All annotations short, never more than 6 words per line.

COMPOSITION:
- Strict 18:9 aspect ratio, generous internal margins.
- Panels are roughly equal width; widen the most content-heavy panel slightly.
- Arrows between panels are chunky, slightly tilted, with small dashed motion
  marks, playful but readable.
- Avoid clutter: lots of breathing room, no overlapping text.

MOOD: a research postdoc's friendly explainer slide for a small group talk:
clear, warm, a bit playful, but every label is technically correct."""

_ENGLISH_GUARD = (
    "IMPORTANT: every character on the canvas must be readable English. Render "
    "math with plain ASCII / Greek letters only (alpha beta sigma mu Sigma are "
    "fine); no decorative non-Latin script anywhere. No watermarks, no fake "
    "logos, no brand names."
)

THEMES: dict[str, str] = {
    "friendly": _FRIENDLY_STYLE,
}

DEFAULT_THEME = "friendly"


def compose_prompt(brief: dict, theme: str = DEFAULT_THEME) -> str:
    """Compose a full image-generation prompt from a structured figure brief.

    ``brief`` shape::

        {"headline": str (<= 8 words),
         "subtitle": str,
         "panels": [{"name": str, "content": str}, ...]}
    """
    style = THEMES.get(theme, _FRIENDLY_STYLE)
    headline = (brief.get("headline") or "").strip()
    subtitle = (brief.get("subtitle") or "").strip()
    panels = brief.get("panels") or []

    lines = [style, ""]
    lines.append("TITLE BAR (top, full width):")
    lines.append(f'- Bold headline: "{headline}"')
    if subtitle:
        lines.append(f'- Subtitle: "{subtitle}"')
    lines.append("")
    if panels:
        lines.append(f"{len(panels)} panels flow left to right:")
        for i, panel in enumerate(panels, 1):
            name = (panel.get("name") or "").strip()
            content = (panel.get("content") or "").strip()
            lines.append(f'PANEL {i} - "{name}":')
            lines.append(f"  - {content}")
    lines.append("")
    lines.append(_ENGLISH_GUARD)
    return "\n".join(lines)


# Backwards-friendly alias matching the plan's name.
friendly_whiteboard_prompt = compose_prompt


# ---------------------------------------------------------------------------
# codex runtime
# ---------------------------------------------------------------------------

_AVAILABLE_CACHE: bool | None = None


def _bundled_codex() -> str | None:
    """Path to the bundled codex binary, or None if the SDK runtime is absent."""
    try:
        from codex_cli_bin import bundled_codex_path

        return str(bundled_codex_path())
    except Exception:
        return None


def codex_imagegen_available() -> bool:
    """True when the bundled codex runtime exists and is logged in (ChatGPT)."""
    global _AVAILABLE_CACHE
    if _AVAILABLE_CACHE is not None:
        return _AVAILABLE_CACHE

    bin_path = _bundled_codex()
    if bin_path is None:
        _AVAILABLE_CACHE = False
        return False
    try:
        result = subprocess.run(
            [bin_path, "login", "status"],
            capture_output=True,
            text=True,
            timeout=20,
        )
        blob = (result.stdout + result.stderr).lower()
        _AVAILABLE_CACHE = result.returncode == 0 and "logged in" in blob
    except Exception:
        _AVAILABLE_CACHE = False
    return _AVAILABLE_CACHE


def generate_figures(
    briefs: list[tuple[str, dict]],
    out_dir: Path,
    theme: str = DEFAULT_THEME,
    force: bool = False,
    timeout: int = 300,
) -> dict[str, Path]:
    """Generate one PNG per (name, brief), in parallel, into ``out_dir``.

    Returns a dict of name -> saved Path for figures that produced a non-empty
    PNG. Missing/failed figures are simply omitted so the review still renders.
    Existing non-empty PNGs are reused unless ``force`` is set.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    bin_path = _bundled_codex()
    if bin_path is None:
        return {}

    log_dir = out_dir / ".codex-logs"
    log_dir.mkdir(exist_ok=True)

    results: dict[str, Path] = {}
    running: dict[str, tuple[subprocess.Popen, Path]] = {}

    for name, brief in briefs:
        png = out_dir / f"{name}.png"
        if png.exists() and png.stat().st_size > 0 and not force:
            results[name] = png
            continue
        prompt = compose_prompt(brief, theme)
        instruction = (
            f"Use the image_generation tool to create the following wide 18:9 "
            f"infographic slide and save it as ./{name}.png in the current "
            f"directory. Do not edit any other files. Report only the saved "
            f"file path.\n\nPROMPT:\n{prompt}"
        )
        cmd = [
            bin_path,
            "exec",
            "--sandbox",
            "workspace-write",
            "--skip-git-repo-check",
            "--cd",
            str(out_dir),
            "-o",
            str(log_dir / f"{name}.md"),
            instruction,
        ]
        proc = subprocess.Popen(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        running[name] = (proc, png)

    for name, (proc, png) in running.items():
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
        if png.exists() and png.stat().st_size > 0:
            results[name] = png

    return results
